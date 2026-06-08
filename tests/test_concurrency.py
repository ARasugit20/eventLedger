import asyncio

import pytest
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Event
from app.services.events import count_events


@pytest.mark.asyncio
async def test_concurrent_duplicate_ingest(client, sample_event):
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

    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1

    db: Session = SessionLocal()
    try:
        assert count_events(db) == 1
        event = db.query(Event).one()
        assert event.idempotency_key == sample_event["idempotency_key"]
        assert event.event_type == sample_event["event_type"]
    finally:
        db.close()


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
