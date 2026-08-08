#!/usr/bin/env python3
"""Seed EventLedger with demo events for analytics dashboards and /analytics API."""

from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx

DEFAULT_BASE = "http://localhost:8000"
CORRELATION_ID = "demo-run-001"


def post(
    client: httpx.Client,
    base: str,
    key: str,
    event_type: str,
    payload: dict,
) -> tuple[int, str | None]:
    response = client.post(
        f"{base}/events",
        json={"idempotency_key": key, "event_type": event_type, "payload": payload},
        headers={"X-Correlation-ID": CORRELATION_ID},
        timeout=10.0,
    )
    event_id = response.json().get("id") if response.content else None
    return response.status_code, event_id


def poll_terminal(client: httpx.Client, base: str, event_id: str, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"{base}/events/{event_id}", timeout=5.0)
        if response.status_code == 200:
            status = response.json().get("status")
            if status in ("processed", "failed"):
                return status
        time.sleep(0.5)
    return "timeout"


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed analytics demo data")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--orders", type=int, default=8)
    parser.add_argument("--signals", type=int, default=5)
    parser.add_argument("--duplicates", type=int, default=4)
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until worker marks events terminal",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"Seeding EventLedger at {base} (correlation_id={CORRELATION_ID})")

    created_ids: list[str] = []
    with httpx.Client() as client:
        health = client.get(f"{base}/health", timeout=5.0)
        if health.status_code != 200:
            print("API health check failed. Run: docker compose up --build")
            return 1

        dup_key = "seed-dup-order-001"
        for i in range(args.orders):
            status, event_id = post(
                client,
                base,
                f"seed-order-{uuid.uuid4()}",
                "order.created",
                {"sku": f"SKU-{i}", "quantity": i + 1},
            )
            print(f"  order.created -> {status}")
            if event_id:
                created_ids.append(event_id)

        for i in range(args.signals):
            status, event_id = post(
                client,
                base,
                f"seed-signal-{uuid.uuid4()}",
                "signal.generated",
                {"symbol": f"SYM{i}", "score": round(0.5 + i * 0.05, 2)},
            )
            print(f"  signal.generated -> {status}")
            if event_id:
                created_ids.append(event_id)

            status, event_id = post(
                client,
                base,
                f"seed-rec-{uuid.uuid4()}",
                "recommendation.created",
                {"symbol": f"SYM{i}", "action": "hold"},
            )
            print(f"  recommendation.created -> {status}")
            if event_id:
                created_ids.append(event_id)

        for _ in range(args.duplicates):
            status, _ = post(
                client,
                base,
                dup_key,
                "order.created",
                {"sku": "DUP", "quantity": 1},
            )
            print(f"  duplicate order.created -> {status}")

        if args.wait and created_ids:
            print("Waiting for worker to process events...")
            for event_id in created_ids[:5]:
                status = poll_terminal(client, base, event_id)
                print(f"  event {event_id[:8]}... -> {status}")

        for path in (
            "/analytics/health",
            "/analytics/duplicate-rate",
            "/analytics/daily-volume",
            "/metrics",
        ):
            resp = client.get(f"{base}{path}", timeout=5.0)
            print(f"{path} -> {resp.status_code}")

    print("Seed complete. Open Grafana -> EventLedger Overview for ingest/latency/pending panels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
