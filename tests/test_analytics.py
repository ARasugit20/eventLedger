import pytest


@pytest.mark.asyncio
async def test_analytics_health_returns_kpis(client, sample_event):
    await client.post("/events", json=sample_event)

    response = await client.get("/analytics/health")
    assert response.status_code == 200
    body = response.json()
    assert body["total_events_all_time"] >= 1
    assert "overall_success_rate_pct" in body


@pytest.mark.asyncio
async def test_analytics_duplicate_rate_after_retry(client, sample_event):
    await client.post("/events", json=sample_event)
    await client.post("/events", json=sample_event)

    response = await client.get("/analytics/duplicate-rate")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 1
    order_row = next(r for r in rows if r["event_type"] == "order.created")
    assert order_row["total_attempts"] >= 2
    assert order_row["duplicate_attempts"] >= 1
    assert order_row["duplicate_rate_pct"] > 0


@pytest.mark.asyncio
async def test_analytics_latency_and_daily_volume(client, sample_event):
    from app.worker import process_message

    create = await client.post("/events", json=sample_event)
    process_message(create.json()["id"])

    latency = await client.get("/analytics/latency")
    assert latency.status_code == 200
    assert isinstance(latency.json(), list)

    daily = await client.get("/analytics/daily-volume")
    assert daily.status_code == 200
    assert isinstance(daily.json(), list)
