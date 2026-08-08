import pytest

from app.config import settings
from app.services.idempotency import get_redis
from app.worker import (
    ensure_consumer_group,
    handle_stream_message,
    process_message,
    reclaim_stale_messages,
)


@pytest.mark.asyncio
async def test_correlation_id_propagates_to_stream(client, sample_event):
    correlation_id = "corr-test-12345"
    response = await client.post(
        "/events",
        json=sample_event,
        headers={"X-Correlation-ID": correlation_id},
    )
    assert response.status_code == 201
    assert response.headers.get("X-Correlation-ID") == correlation_id

    messages = get_redis().xread({settings.event_stream: "0"}, count=10)
    stream_fields = [
        fields for _stream, entries in messages for _msg_id, fields in entries
    ]
    assert any(f.get("correlation_id") == correlation_id for f in stream_fields)


@pytest.mark.asyncio
async def test_transient_failure_retries_without_ack(client):
    ensure_consumer_group()
    body = {
        "idempotency_key": "retry-key-1",
        "event_type": "order.retry",
        "payload": {"sku": "R1"},
    }
    create = await client.post("/events", json=body)
    assert create.status_code == 201

    messages = get_redis().xreadgroup(
        settings.consumer_group,
        "test-consumer-retry",
        {settings.event_stream: ">"},
        count=1,
    )
    message_id, fields = messages[0][1][0]

    handle_stream_message(message_id, fields)

    pending = get_redis().xpending_range(
        settings.event_stream,
        settings.consumer_group,
        message_id,
        message_id,
        1,
    )
    assert pending, "transient failure should leave message pending for retry"

    get_resp = await client.get(f"/events/{create.json()['id']}")
    assert get_resp.json()["status"] == "received"


@pytest.mark.asyncio
async def test_transient_failure_moves_to_dlq_after_max_attempts(client, monkeypatch):
    ensure_consumer_group()
    monkeypatch.setattr("app.worker.settings.max_delivery_attempts", 2)

    body = {
        "idempotency_key": "retry-key-dlq",
        "event_type": "signal.retry",
        "payload": {"symbol": "AAPL"},
    }
    create = await client.post("/events", json=body)
    event_id = create.json()["id"]

    messages = get_redis().xreadgroup(
        settings.consumer_group,
        "test-consumer-dlq",
        {settings.event_stream: ">"},
        count=1,
    )
    message_id, fields = messages[0][1][0]
    monkeypatch.setattr("app.worker.get_delivery_count", lambda _mid: 2)

    handle_stream_message(message_id, fields)

    dlq_messages = get_redis().xread({settings.dlq_stream: "0"}, count=10)
    dlq_event_ids = [
        f.get("event_id") for _stream, entries in dlq_messages for _msg_id, f in entries
    ]
    assert event_id in dlq_event_ids


@pytest.mark.asyncio
async def test_terminal_event_not_reprocessed(client, sample_event):
    create = await client.post("/events", json=sample_event)
    event_id = create.json()["id"]

    assert process_message(event_id) is True
    assert process_message(event_id) is False

    get_resp = await client.get(f"/events/{event_id}")
    assert get_resp.json()["status"] == "processed"


@pytest.mark.asyncio
async def test_stale_pending_message_reclaimed(client, monkeypatch):
    ensure_consumer_group()
    monkeypatch.setattr("app.worker.settings.pending_idle_ms", 0)

    body = {
        "idempotency_key": "stale-key-1",
        "event_type": "order.created",
        "payload": {"sku": "S1"},
    }
    create = await client.post("/events", json=body)
    event_id = create.json()["id"]

    messages = get_redis().xreadgroup(
        settings.consumer_group,
        "stale-holder",
        {settings.event_stream: ">"},
        count=1,
    )
    message_id, _fields = messages[0][1][0]
    assert message_id

    reclaimed = reclaim_stale_messages(consumer_name="reclaim-worker")
    assert reclaimed >= 1

    get_resp = await client.get(f"/events/{event_id}")
    assert get_resp.json()["status"] == "processed"
