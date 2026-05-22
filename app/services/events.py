import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Event, EventStatus
from app.schemas import EventCreate
from app.services.idempotency import claim_idempotency_key, get_redis, release_idempotency_key

logger = logging.getLogger(__name__)


def _enqueue_event(event_id: UUID) -> None:
    client = get_redis()
    client.xadd(settings.event_stream, {"event_id": str(event_id)})


def get_event_by_id(db: Session, event_id: UUID) -> Event | None:
    return db.get(Event, event_id)


def get_event_by_idempotency_key(db: Session, key: str) -> Event | None:
    stmt = select(Event).where(Event.idempotency_key == key)
    return db.scalar(stmt)


def create_event(db: Session, body: EventCreate) -> tuple[Event, bool]:
    """Returns (event, is_duplicate). Duplicate = same idempotency_key already stored."""
    existing = get_event_by_idempotency_key(db, body.idempotency_key)
    if existing:
        return existing, True

    if not claim_idempotency_key(body.idempotency_key):
        existing = get_event_by_idempotency_key(db, body.idempotency_key)
        if existing:
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
            return existing, True
        raise
    db.refresh(event)

    try:
        _enqueue_event(event.id)
    except Exception:
        logger.exception("Failed to enqueue event %s", event.id)

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


def mark_processing(db: Session, event: Event) -> Event:
    event.status = EventStatus.processing
    db.commit()
    db.refresh(event)
    return event


def mark_processed(db: Session, event: Event, result: dict) -> Event:
    event.status = EventStatus.processed
    event.result = result
    event.processed_at = datetime.now(timezone.utc)
    event.error_message = None
    db.commit()
    db.refresh(event)
    return event


def mark_failed(db: Session, event: Event, error_message: str) -> Event:
    event.status = EventStatus.failed
    event.error_message = error_message
    event.processed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return event


def simulate_processing(event: Event) -> dict:
    """Deterministic worker output for demo and tests."""
    if event.event_type.endswith(".fail"):
        raise ValueError(f"Simulated failure for event type {event.event_type}")

    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "processed": True,
        "payload_hash": hash(json.dumps(event.payload, sort_keys=True)),
    }
