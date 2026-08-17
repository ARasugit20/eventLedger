"""Tests for durable dead-letter queue behavior."""

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.dlq import get_dlq_stats, move_to_dlq, should_move_to_dlq
from app.models import DeadLetterEvent, EventStatus
from app.services.idempotency import get_redis
from app.worker import ensure_consumer_group, handle_stream_message


@pytest.mark.asyncio
async def test_should_move_to_dlq_respects_threshold(monkeypatch):
    monkeypatch.setattr("app.config.settings.max_delivery_attempts", 3)
    assert should_move_to_dlq(2) is False
    assert should_move_to_dlq(3) is True


@pytest.mark.asyncio
async def test_transient_failure_stays_retryable_below_threshold(client, monkeypatch):
    ensure_consumer_group()
    monkeypatch.setattr("app.config.settings.max_delivery_attempts", 3)

    create = await client.post(
        "/events",
        json={
            "idempotency_key": "dlq-below-threshold",
            "event_type": "order.retry",
            "payload": {"sku": "R1"},
        },
    )
    assert create.status_code == 201
    event_id = create.json()["id"]

    messages = get_redis().xreadgroup(
        settings.consumer_group,
        "dlq-below-threshold-consumer",
        {settings.event_stream: ">"},
        count=1,
    )
    message_id, fields = messages[0][1][0]
    monkeypatch.setattr("app.worker.get_delivery_count", lambda _mid: 2)

    handle_stream_message(message_id, fields)

    pending = get_redis().xpending_range(
        settings.event_stream,
        settings.consumer_group,
        message_id,
        message_id,
        1,
    )
    assert pending, "message should remain pending below max attempts"

    dlq = await client.get("/analytics/dlq")
    assert dlq.json()["count"] == 0

    get_resp = await client.get(f"/events/{event_id}")
    assert get_resp.json()["status"] == "received"


@pytest.mark.asyncio
async def test_max_attempts_create_single_durable_dlq_row(client, db_session, monkeypatch):
    ensure_consumer_group()
    monkeypatch.setattr("app.config.settings.max_delivery_attempts", 3)

    create = await client.post(
        "/events",
        json={
            "idempotency_key": "dlq-at-threshold",
            "event_type": "signal.retry",
            "payload": {"symbol": "AAPL"},
        },
    )
    assert create.status_code == 201
    event_id = create.json()["id"]

    messages = get_redis().xreadgroup(
        settings.consumer_group,
        "dlq-at-threshold-consumer",
        {settings.event_stream: ">"},
        count=1,
    )
    message_id, fields = messages[0][1][0]
    monkeypatch.setattr("app.worker.get_delivery_count", lambda _mid: 3)

    handle_stream_message(message_id, fields)

    count = db_session.scalar(select(func.count()).select_from(DeadLetterEvent))
    assert count == 1

    pending = get_redis().xpending_range(
        settings.event_stream,
        settings.consumer_group,
        message_id,
        message_id,
        1,
    )
    assert not pending, "message should be acknowledged after DLQ move"

    dlq_messages = get_redis().xread({settings.dlq_stream: "0"}, count=10)
    dlq_event_ids = [
        f.get("event_id") for _stream, entries in dlq_messages for _msg_id, f in entries
    ]
    assert event_id in dlq_event_ids

    get_resp = await client.get(f"/events/{event_id}")
    assert get_resp.json()["status"] == "failed"

    analytics = await client.get("/analytics/dlq")
    body = analytics.json()
    assert body["count"] == 1
    assert body["oldest_item_age_seconds"] >= 0


@pytest.mark.asyncio
async def test_move_to_dlq_is_idempotent_for_same_message(client, db_session, monkeypatch):
    ensure_consumer_group()
    monkeypatch.setattr("app.config.settings.max_delivery_attempts", 2)

    create = await client.post(
        "/events",
        json={
            "idempotency_key": "dlq-idempotent",
            "event_type": "claim.retry",
            "payload": {"claim_id": "c-1"},
        },
    )
    event_id = create.json()["id"]

    messages = get_redis().xreadgroup(
        settings.consumer_group,
        "dlq-idempotent-consumer",
        {settings.event_stream: ">"},
        count=1,
    )
    message_id, fields = messages[0][1][0]
    reason = "simulated transient failure"

    first = move_to_dlq(
        db_session,
        message_id=message_id,
        fields=fields,
        reason=reason,
        delivery_count=2,
    )
    second = move_to_dlq(
        db_session,
        message_id=message_id,
        fields=fields,
        reason=reason,
        delivery_count=2,
    )

    assert first is not None
    assert second is not None
    assert first.id == second.id

    count = db_session.scalar(select(func.count()).select_from(DeadLetterEvent))
    assert count == 1

    stats = get_dlq_stats(db_session)
    assert stats["count"] == 1

    get_resp = await client.get(f"/events/{event_id}")
    assert get_resp.json()["status"] == EventStatus.failed.value
