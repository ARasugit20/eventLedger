
import pytest

from app.config import settings
from app.services.idempotency import get_redis
from app.worker import process_message


@pytest.mark.asyncio
async def test_ingest_worker_get_processed(client, sample_event):
    create_resp = await client.post("/events", json=sample_event)
    assert create_resp.status_code == 201
    event_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "received"

    assert process_message(event_id) is True

    get_resp = await client.get(f"/events/{event_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["status"] == "processed"
    assert body["result"] is not None
    assert body["result"]["processed"] is True
    assert body["processed_at"] is not None


@pytest.mark.asyncio
async def test_event_enqueued_to_redis_stream(client, sample_event):
    create_resp = await client.post("/events", json=sample_event)
    assert create_resp.status_code == 201
    event_id = create_resp.json()["id"]

    messages = get_redis().xread({settings.event_stream: "0"}, count=100)
    stream_event_ids = [
        fields["event_id"]
        for _stream, entries in messages
        for _msg_id, fields in entries
    ]
    assert event_id in stream_event_ids


@pytest.mark.asyncio
async def test_failed_event_retains_error_message(client):
    fail_event = {
        "idempotency_key": "claim-fail-1",
        "event_type": "claim.fail",
        "payload": {"claim_id": "c-1"},
    }
    create_resp = await client.post("/events", json=fail_event)
    assert create_resp.status_code == 201
    event_id = create_resp.json()["id"]

    process_message(event_id)

    get_resp = await client.get(f"/events/{event_id}")
    body = get_resp.json()
    assert body["status"] == "failed"
    assert body["error_message"] is not None
    assert "Simulated failure" in body["error_message"]


@pytest.mark.asyncio
async def test_double_process_is_idempotent(client, sample_event):
    create_resp = await client.post("/events", json=sample_event)
    event_id = create_resp.json()["id"]

    assert process_message(event_id) is True
    assert process_message(event_id) is False

    get_resp = await client.get(f"/events/{event_id}")
    assert get_resp.json()["status"] == "processed"


@pytest.mark.asyncio
async def test_list_events_with_status_filter(client, sample_event):
    await client.post("/events", json=sample_event)

    all_resp = await client.get("/events")
    assert all_resp.status_code == 200
    assert all_resp.json()["total"] >= 1

    processed_resp = await client.get("/events", params={"status": "processed"})
    assert processed_resp.status_code == 200
    assert isinstance(processed_resp.json()["items"], list)


@pytest.mark.asyncio
async def test_get_event_not_found(client):
    response = await client.get("/events/00000000-0000-0000-0000-000000000099")
    assert response.status_code == 404
