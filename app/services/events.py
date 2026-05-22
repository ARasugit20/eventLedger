import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import IdempotencyConflictError
from app.models import Event, EventStatus
from app.schemas import EventCreate
from app.services.idempotency import claim_idempotency_key, get_redis

logger = logging.getLogger(__name__)


def _matches_request(event: Event, body: EventCreate) -> bool:
    return event.event_type == body.event_type and event.payload == body.payload


def _enqueue_event(event_id: UUID, retries: int = 3) -> None:
    client = get_redis()
    for attempt in range(retries):
        try:
            client.xadd(settings.event_stream, {"event_id": str(event_id)})
            return
        except Exception:
            if attempt == retries - 1:
                logger.exception("Failed to enqueue event %s after %s attempts", event_id, retries)
                return
            time.sleep(0.05 * (2**attempt))


def get_event_by_id(db: Session, event_id: UUID) -> Event | None:
    return db.get(Event, event_id)


def get_event_by_idempotency_key(db: Session, key: str) -> Event | None:
    stmt = select(Event).where(Event.idempotency_key == key)
    return db.scalar(stmt)


def create_event(db: Session, body: EventCreate) -> tuple[Event, bool]:
    """Returns (event, is_duplicate). Duplicate = same idempotency_key already stored."""
    existing = get_event_by_idempotency_key(db, body.idempotency_key)
    if existing:
        if not _matches_request(existing, body):
            raise IdempotencyConflictError(body.idempotency_key)
        return existing, True

    if not claim_idempotency_key(body.idempotency_key):
        existing = get_event_by_idempotency_key(db, body.idempotency_key)
        if existing:
            if not _matches_request(existing, body):
                raise IdempotencyConflictError(body.idempotency_key)
            return existing, True
        # Redis key held by in-flight request; DB unique constraint is source of truth

    event = Event(
        idempotency_key=body.idempotency_key,
        event_type=body.event_type,
        payload=body.payload,
        status=EventStatus.received,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_event_by_idempotency_key(db, body.idempotency_key)
        if existing:
            if not _matches_request(existing, body):
                raise IdempotencyConflictError(body.idempotency_key) from None
            return existing, True
        raise
    db.refresh(event)

    _enqueue_event(event.id)
    return event, False


def list_events(
    db: Session,
    *,
    status: EventStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Event], int]:
    base = select(Event)
    count_stmt = select(func.count()).select_from(Event)
    if status is not None:
        base = base.where(Event.status == status)
        count_stmt = count_stmt.where(Event.status == status)

    total = db.scalar(count_stmt) or 0
    stmt = base.order_by(Event.created_at.desc()).limit(limit).offset(offset)
    items = list(db.scalars(stmt).all())
    return items, total


def try_claim_for_processing(db: Session, event_id: UUID) -> Event | None:
    """Atomically move received → processing; returns None if already claimed or terminal."""
    stmt = (
        update(Event)
        .where(Event.id == event_id)
        .where(Event.status == EventStatus.received)
        .values(status=EventStatus.processing)
        .returning(Event.id)
    )
    claimed_id = db.scalar(stmt)
    if not claimed_id:
        db.rollback()
        return None
    db.commit()
    return get_event_by_id(db, event_id)


def mark_processed(db: Session, event: Event, result: dict) -> Event:
    event.status = EventStatus.processed
    event.result = result
    event.processed_at = datetime.now(UTC)
    event.error_message = None
    db.commit()
    db.refresh(event)
    return event


def mark_failed(db: Session, event: Event, error_message: str) -> Event:
    event.status = EventStatus.failed
    event.error_message = error_message
    event.processed_at = datetime.now(UTC)
    db.commit()
    db.refresh(event)
    return event


def stable_payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def simulate_processing(event: Event) -> dict:
    """Deterministic worker output for demo and tests."""
    if event.event_type.endswith(".fail"):
        raise ValueError(f"Simulated failure for event type {event.event_type}")

    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "processed": True,
        "payload_hash": stable_payload_hash(event.payload),
    }
