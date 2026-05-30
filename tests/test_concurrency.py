import asyncio

import pytest
from sqlalchemy.orm import Session

from app.db import SessionLocal
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
    finally:
        db.close()
