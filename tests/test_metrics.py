import pytest


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_ingest_counter(client, sample_event):
    await client.post("/events", json=sample_event)
    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "events_ingested_total" in body
    assert "event_processing_duration_seconds" in body
    assert "events_pending_processing" in body


@pytest.mark.asyncio
async def test_metrics_records_new_and_duplicate(client, sample_event):
    await client.post("/events", json=sample_event)
    await client.post("/events", json=sample_event)

    response = await client.get("/metrics")
    body = response.text
    assert 'result="new"' in body or 'result="duplicate"' in body
