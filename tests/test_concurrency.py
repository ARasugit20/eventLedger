import asyncio
import json

import pytest

from app.models import Event
from app.services.events import count_events


@pytest.mark.asyncio
async def test_concurrent_duplicate_ingest(client, db_session, sample_event):
    """50 parallel POSTs with the same idempotency_key must create exactly one row."""
    responses = await asyncio.gather(
        *[client.post("/events", json=sample_event) for _ in range(50)]
    )

    statuses = [r.status_code for r in responses]
    assert not any(s >= 500 for s in statuses), f"server errors: {statuses}"
    assert all(s in (200, 201) for s in statuses)

    created = sum(1 for s in statuses if s == 201)
    duplicates = sum(1 for s in statuses if s == 200)
    assert created == 1, f"expected exactly one 201, got {created}"
    assert duplicates == 49, f"expected 49 duplicates, got {duplicates}"

    bodies = [r.json() for r in responses]
    assert len({json.dumps(b, sort_keys=True) for b in bodies}) == 1

    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1

    assert count_events(db_session) == 1
    event = db_session.query(Event).one()
    assert event.idempotency_key == sample_event["idempotency_key"]
    assert event.event_type == sample_event["event_type"]
    assert event.payload == sample_event["payload"]


@pytest.mark.asyncio
async def test_concurrent_duplicate_ingest_analytics(client, sample_event):
    """Duplicate attempts must appear in analytics without extra event rows."""
    await asyncio.gather(*[client.post("/events", json=sample_event) for _ in range(10)])

    dup_rate = await client.get("/analytics/duplicate-rate")
    assert dup_rate.status_code == 200
    rows = dup_rate.json()
    order_row = next(r for r in rows if r["event_type"] == "order.created")
    assert order_row["total_attempts"] == 10
    assert order_row["duplicate_attempts"] == 9
    assert order_row["unique_idempotency_keys"] == 1

    health = await client.get("/analytics/health")
    assert health.json()["total_events_all_time"] == 1


@pytest.mark.asyncio
async def test_concurrent_payload_conflict_returns_409(client, db_session, sample_event):
    """Same idempotency key with different payload must never create a second row."""
    first = await client.post("/events", json=sample_event)
    assert first.status_code == 201

    conflict_body = {
        **sample_event,
        "payload": {"sku": "DIFFERENT", "quantity": 99},
    }
    responses = await asyncio.gather(
        *[client.post("/events", json=conflict_body) for _ in range(10)]
    )
    assert all(r.status_code == 409 for r in responses)

    assert count_events(db_session) == 1
    event = db_session.query(Event).one()
    assert event.payload == sample_event["payload"]
