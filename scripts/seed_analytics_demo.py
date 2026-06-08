#!/usr/bin/env python3
"""Seed EventLedger with demo events for analytics dashboards and /analytics API."""

from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx

DEFAULT_BASE = "http://localhost:8000"


def post(client: httpx.Client, base: str, key: str, event_type: str, payload: dict) -> int:
    response = client.post(
        f"{base}/events",
        json={"idempotency_key": key, "event_type": event_type, "payload": payload},
        timeout=10.0,
    )
    return response.status_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed analytics demo data")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--orders", type=int, default=12)
    parser.add_argument("--claims", type=int, default=8)
    parser.add_argument("--duplicates", type=int, default=6)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"Seeding EventLedger at {base}")

    with httpx.Client() as client:
        health = client.get(f"{base}/health", timeout=5.0)
        if health.status_code != 200:
            print("API health check failed. Run: docker compose up --build")
            return 1

        dup_key = "seed-dup-order-001"
        for i in range(args.orders):
            status = post(
                client,
                base,
                f"seed-order-{uuid.uuid4()}",
                "order.created",
                {"sku": f"SKU-{i}", "quantity": i + 1},
            )
            print(f"  order.created -> {status}")

        for i in range(args.claims):
            status = post(
                client,
                base,
                f"seed-claim-{uuid.uuid4()}",
                "claim.submitted",
                {"claim_id": f"c-{i}"},
            )
            print(f"  claim.submitted -> {status}")

        for _ in range(args.duplicates):
            status = post(client, base, dup_key, "order.created", {"sku": "DUP", "quantity": 1})
            print(f"  duplicate order.created -> {status}")

        time.sleep(0.5)
        for path in ("/analytics/health", "/analytics/duplicate-rate", "/analytics/daily-volume"):
            resp = client.get(f"{base}{path}", timeout=5.0)
            print(f"{path} -> {resp.status_code}")

    print("Seed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
