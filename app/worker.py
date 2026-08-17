"""Background worker — consumes Redis Stream and processes events.

What: Reads event IDs from a Redis Stream, runs handlers, updates Postgres status.
Why: Ingest API returns fast; heavy/slow work happens here asynchronously.
Key function: process_message() — claim event, simulate handler, mark processed|failed.
"""

import logging
import socket
import time
from uuid import UUID

from app.config import settings
from app.db import SessionLocal
from app.dlq import get_delivery_count, move_to_dlq, should_move_to_dlq
from app.exceptions import TransientProcessingError
from app.metrics import (
    event_processing_duration_seconds,
    stream_pending_messages,
    worker_processing_failures_total,
    worker_retries_total,
)
from app.models import EventStatus
from app.services.events import (
    get_event_by_id,
    mark_failed,
    mark_processed,
    refresh_pending_gauge,
    release_processing_claim,
    simulate_processing,
    try_claim_for_processing,
)
from app.services.idempotency import get_redis

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"time":"%(asctime)s","level":"%(levelname)s","message":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

CONSUMER_NAME = f"worker-{socket.gethostname()}"


def ensure_consumer_group() -> None:
    client = get_redis()
    try:
        client.xgroup_create(settings.event_stream, settings.consumer_group, id="0", mkstream=True)
        logger.info("Created consumer group %s", settings.consumer_group)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def refresh_stream_pending_gauge() -> None:
    client = get_redis()
    try:
        pending = client.xpending(settings.event_stream, settings.consumer_group)
        stream_pending_messages.set(pending["pending"])
    except Exception:
        stream_pending_messages.set(0)


def process_message(event_id: str, *, correlation_id: str = "") -> bool:
    """Process one event. Returns True if work was performed."""
    db = SessionLocal()
    try:
        refresh_pending_gauge(db)

        event = get_event_by_id(db, UUID(event_id))
        if not event:
            logger.warning(
                '{"event_id":"%s","correlation_id":"%s","status":"missing"}',
                event_id,
                correlation_id,
            )
            return False
        if event.status in (EventStatus.processed, EventStatus.failed):
            logger.info(
                '{"event_id":"%s","correlation_id":"%s","status":"terminal","state":"%s"}',
                event_id,
                correlation_id,
                event.status.value,
            )
            return False

        event = try_claim_for_processing(db, UUID(event_id))
        if not event:
            logger.info(
                '{"event_id":"%s","correlation_id":"%s","status":"already_claimed"}',
                event_id,
                correlation_id,
            )
            return False

        with event_processing_duration_seconds.time():
            try:
                result = simulate_processing(event)
                mark_processed(db, event, result)
                logger.info(
                    '{"event_id":"%s","correlation_id":"%s","status":"processed"}',
                    event_id,
                    correlation_id,
                )
            except TransientProcessingError:
                release_processing_claim(db, UUID(event_id))
                raise
            except Exception as exc:
                mark_failed(db, event, str(exc))
                worker_processing_failures_total.inc()
                logger.error(
                    '{"event_id":"%s","correlation_id":"%s","status":"failed","error":"%s"}',
                    event_id,
                    correlation_id,
                    exc,
                )
        return True
    finally:
        db.close()


def handle_stream_message(message_id: str, fields: dict[str, str]) -> None:
    """Ack, retry, or DLQ a single stream message based on handler outcome."""
    client = get_redis()
    event_id = fields.get("event_id")
    correlation_id = fields.get("correlation_id", "")

    if not event_id:
        client.xack(settings.event_stream, settings.consumer_group, message_id)
        return

    try:
        process_message(event_id, correlation_id=correlation_id)
        client.xack(settings.event_stream, settings.consumer_group, message_id)
    except TransientProcessingError as exc:
        delivery_count = get_delivery_count(message_id)
        worker_retries_total.inc()
        logger.warning(
            '{"event_id":"%s","correlation_id":"%s","status":"retry","delivery_count":%s}',
            event_id,
            correlation_id,
            delivery_count,
        )
        if should_move_to_dlq(delivery_count):
            db = SessionLocal()
            try:
                move_to_dlq(
                    db,
                    message_id=message_id,
                    fields=fields,
                    reason=str(exc),
                    delivery_count=delivery_count,
                )
            finally:
                db.close()
            client.xack(settings.event_stream, settings.consumer_group, message_id)
    except Exception:
        worker_processing_failures_total.inc()
        logger.exception(
            '{"event_id":"%s","correlation_id":"%s","status":"handler_error"}',
            event_id,
            correlation_id,
        )
        raise


def reclaim_stale_messages(consumer_name: str = CONSUMER_NAME) -> int:
    """Reclaim idle pending messages via XAUTOCLAIM and process them."""
    client = get_redis()
    reclaimed = 0
    start_id = "0-0"

    while True:
        result = client.xautoclaim(
            settings.event_stream,
            settings.consumer_group,
            consumer_name,
            settings.pending_idle_ms,
            start_id,
            count=10,
        )
        if len(result) == 3:
            _next_id, messages, _deleted = result
        else:
            _next_id, messages = result

        if not messages:
            break

        for message_id, fields in messages:
            handle_stream_message(message_id, fields)
            reclaimed += 1

        start_id = _next_id
        if start_id == "0-0":
            break

    refresh_stream_pending_gauge()
    return reclaimed


def run_worker() -> None:
    ensure_consumer_group()
    client = get_redis()
    logger.info("Worker %s listening on stream %s", CONSUMER_NAME, settings.event_stream)

    while True:
        try:
            reclaim_stale_messages()
            refresh_stream_pending_gauge()

            messages = client.xreadgroup(
                settings.consumer_group,
                CONSUMER_NAME,
                {settings.event_stream: ">"},
                count=10,
                block=5000,
            )
            if not messages:
                continue

            for _stream, entries in messages:
                for message_id, fields in entries:
                    handle_stream_message(message_id, fields)
        except Exception:
            logger.exception("Worker loop error")
            time.sleep(1)


if __name__ == "__main__":
    run_worker()
