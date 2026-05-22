import asyncio

import pytest

from app.worker import process_message


@pytest.mark.asyncio
async def test_ingest_worker_get_processed(client, sample_event):
    create_resp = await client.post("/events", json=sample_event)
    assert create_resp.status_code == 201
    event_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "received"

    process_message(event_id)

    for _ in range(20):
        get_resp = await client.get(f"/events/{event_id}")
        assert get_resp.status_code == 200
        if get_resp.json()["status"] == "processed":
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("Event did not reach processed status")

    body = get_resp.json()
    assert body["status"] == "processed"
    assert body["result"] is not None
    assert body["result"]["processed"] is True
    assert body["processed_at"] is not None


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
