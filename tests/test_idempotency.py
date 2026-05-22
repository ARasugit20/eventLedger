import asyncio

import pytest


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_same_id(client, sample_event):
    first = await client.post("/events", json=sample_event)
    assert first.status_code == 201
    first_body = first.json()

    second = await client.post("/events", json=sample_event)
    assert second.status_code == 200
    second_body = second.json()

    assert first_body["id"] == second_body["id"]
    assert first_body["idempotency_key"] == second_body["idempotency_key"]


@pytest.mark.asyncio
async def test_concurrent_duplicate_requests_same_id(client, sample_event):
    responses = await asyncio.gather(
        *[client.post("/events", json=sample_event) for _ in range(12)]
    )
    success = [r for r in responses if r.status_code in (200, 201)]
    assert len(success) == 12
    ids = {r.json()["id"] for r in success}
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_different_keys_create_separate_events(client, sample_event):
    first = await client.post("/events", json=sample_event)
    assert first.status_code == 201

    other = {**sample_event, "idempotency_key": "order-8822-create"}
    second = await client.post("/events", json=other)
    assert second.status_code == 201

    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_same_key_different_payload_returns_409(client, sample_event):
    first = await client.post("/events", json=sample_event)
    assert first.status_code == 201

    conflict = {
        **sample_event,
        "payload": {"sku": "DIFFERENT", "quantity": 99},
    }
    second = await client.post("/events", json=conflict)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_invalid_payload_returns_422(client):
    response = await client.post(
        "/events",
        json={"idempotency_key": "k1", "event_type": "order.created"},
    )
    assert response.status_code == 422
