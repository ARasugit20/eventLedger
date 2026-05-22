import logging
import socket
import time
from uuid import UUID

from app.config import settings
from app.db import SessionLocal
from app.models import EventStatus
from app.services.events import (
    get_event_by_id,
    mark_failed,
    mark_processed,
    mark_processing,
    simulate_processing,
)
from app.services.idempotency import get_redis

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"time":"%(asctime)s","level":"%(levelname)s","message":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

CONSUMER_NAME = f"worker-{socket.gethostname()}-{settings.consumer_group}"


def ensure_consumer_group() -> None:
    client = get_redis()
    try:
        client.xgroup_create(settings.event_stream, settings.consumer_group, id="0", mkstream=True)
        logger.info("Created consumer group %s", settings.consumer_group)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def process_message(event_id: str) -> None:
    db = SessionLocal()
    try:
        event = get_event_by_id(db, UUID(event_id))
        if not event:
            logger.warning("Event %s not found", event_id)
            return
        if event.status in (EventStatus.processed, EventStatus.failed):
            logger.info("Event %s already terminal (%s)", event_id, event.status.value)
            return

        mark_processing(db, event)
        try:
            result = simulate_processing(event)
            mark_processed(db, event, result)
            logger.info('{"event_id":"%s","status":"processed"}', event_id)
        except Exception as exc:
            mark_failed(db, event, str(exc))
            logger.error('{"event_id":"%s","status":"failed","error":"%s"}', event_id, exc)
    finally:
        db.close()


def run_worker() -> None:
    ensure_consumer_group()
    client = get_redis()
    logger.info("Worker %s listening on stream %s", CONSUMER_NAME, settings.event_stream)

    while True:
        try:
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
                    event_id = fields.get("event_id")
                    if not event_id:
                        client.xack(settings.event_stream, settings.consumer_group, message_id)
                        continue
                    try:
                        process_message(event_id)
                        client.xack(settings.event_stream, settings.consumer_group, message_id)
                    except Exception:
                        logger.exception("Failed processing message %s", message_id)
        except Exception:
            logger.exception("Worker loop error")
            time.sleep(1)


if __name__ == "__main__":
    run_worker()
