import pytest


@pytest.mark.asyncio
async def test_analytics_health_returns_kpis(client, sample_event):
    await client.post("/events", json=sample_event)

    response = await client.get("/analytics/health")
    assert response.status_code == 200
    body = response.json()
    assert body["total_events_all_time"] >= 1
    assert body["events_last_24h"] >= 1
    assert "overall_success_rate_pct" in body
    assert isinstance(body["overall_success_rate_pct"], int | float)
    assert body["p95_latency_seconds"] >= 0


@pytest.mark.asyncio
async def test_analytics_health_empty_db(client):
    response = await client.get("/analytics/health")
    assert response.status_code == 200
    body = response.json()
    assert body["total_events_all_time"] == 0
    assert body["overall_success_rate_pct"] == 0
    assert body["p95_latency_seconds"] == 0


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
    assert order_row["new_attempts"] >= 1
    assert order_row["duplicate_rate_pct"] > 0
    assert 0 < order_row["duplicate_rate_pct"] <= 100


@pytest.mark.asyncio
async def test_analytics_duplicate_rate_empty(client):
    response = await client.get("/analytics/duplicate-rate")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_analytics_latency_and_daily_volume(client, sample_event):
    from app.worker import process_message

    create = await client.post("/events", json=sample_event)
    process_message(create.json()["id"])

    latency = await client.get("/analytics/latency")
    assert latency.status_code == 200
    latency_rows = latency.json()
    assert isinstance(latency_rows, list)
    assert len(latency_rows) >= 1
    row = next(r for r in latency_rows if r["event_type"] == "order.created")
    assert row["processed_count"] >= 1
    assert row["p50_seconds"] >= 0
    assert row["p95_seconds"] >= 0

    daily = await client.get("/analytics/daily-volume")
    assert daily.status_code == 200
    daily_rows = daily.json()
    assert isinstance(daily_rows, list)
    assert len(daily_rows) >= 1
    assert daily_rows[0]["total_events"] >= 1
