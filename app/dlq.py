"""Dead-letter queue operations for failed worker deliveries.

What: Move poison messages to durable Postgres storage and mirror them in Redis.
Why: Bounded retries need an auditable DLQ with analytics-friendly health metrics.
Key exports: should_move_to_dlq(), move_to_dlq(), get_dlq_stats(), run_dlq_sweep().
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.metrics import dlq_messages_total
from app.models import DeadLetterEvent, Event
from app.services.events import mark_failed, refresh_pending_gauge
from app.services.idempotency import get_redis

logger = logging.getLogger(__name__)


def should_move_to_dlq(delivery_count: int) -> bool:
    """Return True when a stream message has exhausted configured retries."""
    return delivery_count >= settings.max_delivery_attempts


def get_delivery_count(message_id: str) -> int:
    """Read the Redis PEL delivery count for a pending stream message."""
    client = get_redis()
    entries = client.xpending_range(
        settings.event_stream,
        settings.consumer_group,
        message_id,
        message_id,
        1,
    )
    if not entries:
        return 1
    entry = entries[0]
    return int(entry.get("times_delivered", entry.get("delivery_count", 1)))


def _mirror_to_redis_dlq(message_id: str, fields: dict[str, str], reason: str) -> None:
    client = get_redis()
    client.xadd(
        settings.dlq_stream,
        {
            "source_message_id": message_id,
            "event_id": fields.get("event_id", ""),
            "correlation_id": fields.get("correlation_id", ""),
            "reason": reason,
        },
    )
    dlq_messages_total.inc()


def move_to_dlq(
    db: Session,
    *,
    message_id: str,
    fields: dict[str, str],
    reason: str,
    delivery_count: int,
) -> DeadLetterEvent:
    """Persist a dead-letter record and mark the source event failed."""
    event_id_raw = fields.get("event_id")
    if not event_id_raw:
        raise ValueError("DLQ message is missing event_id")

    try:
        event_id = UUID(event_id_raw)
    except ValueError:
        logger.warning(
            '{"status":"dlq_skipped","reason":"invalid_event_id","event_id":"%s"}',
            event_id_raw,
        )
        raise

    existing = db.scalar(
        select(DeadLetterEvent).where(DeadLetterEvent.source_message_id == message_id)
    )
    if existing:
        return existing

    event = db.get(Event, event_id)
    if not event:
        logger.warning(
            '{"status":"dlq_skipped","reason":"missing_event","event_id":"%s"}',
            event_id_raw,
        )
        raise LookupError(f"DLQ source event does not exist: {event_id_raw}")

    record = DeadLetterEvent(
        event_id=event_id,
        source_message_id=message_id,
        correlation_id=fields.get("correlation_id"),
        reason=reason,
        delivery_count=delivery_count,
    )
    db.add(record)
    mark_failed(db, event, reason)
    db.commit()
    db.refresh(record)
    refresh_pending_gauge(db)

    _mirror_to_redis_dlq(message_id, fields, reason)
    logger.error(
        '{"message_id":"%s","event_id":"%s","correlation_id":"%s","status":"dlq","reason":"%s"}',
        message_id,
        event_id_raw,
        fields.get("correlation_id", ""),
        reason,
    )
    return record


def get_dlq_stats(db: Session) -> dict[str, Any]:
    """Return durable DLQ count and oldest-item age in seconds."""
    count = db.scalar(select(func.count()).select_from(DeadLetterEvent)) or 0
    oldest = db.scalar(select(func.min(DeadLetterEvent.moved_at)))
    oldest_age_seconds = 0.0
    if oldest is not None:
        oldest_age_seconds = max((datetime.now(UTC) - oldest).total_seconds(), 0.0)
    return {
        "count": int(count),
        "oldest_item_age_seconds": round(oldest_age_seconds, 3),
    }


def run_dlq_sweep(db: Session) -> dict[str, Any]:
    """Log current DLQ health for scheduled orchestration jobs."""
    stats = get_dlq_stats(db)
    logger.info(
        '{"status":"dlq_sweep","count":%s,"oldest_item_age_seconds":%s}',
        stats["count"],
        stats["oldest_item_age_seconds"],
    )
    return stats
