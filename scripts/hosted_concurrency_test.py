#!/usr/bin/env python3
"""Run the 50-concurrent duplicate ingest proof against a hosted EventLedger API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime

import httpx


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EVENTLEDGER_URL", "").rstrip("/"),
        help="Hosted API base URL (or set EVENTLEDGER_URL)",
    )
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument(
        "--output",
        default="docs/deploy_evidence/hosted_concurrency_result.json",
        help="Where to write JSON evidence",
    )
    return parser.parse_args()


async def _run(base_url: str, concurrency: int) -> dict:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "idempotency_key": f"hosted-concurrency-{run_id}",
        "event_type": "deploy.proof",
        "payload": {"run_id": run_id, "concurrency": concurrency},
    }

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        health = await client.get("/health")
        health.raise_for_status()

        started = time.perf_counter()
        responses = await asyncio.gather(
            *[client.post("/events", json=payload) for _ in range(concurrency)]
        )
        elapsed_s = time.perf_counter() - started

    statuses = [r.status_code for r in responses]
    bodies = [r.json() for r in responses]
    created = sum(1 for s in statuses if s == 201)
    duplicates = sum(1 for s in statuses if s == 200)
    unique_ids = {b.get("id") for b in bodies}
    server_errors = [s for s in statuses if s >= 500]

    passed = (
        not server_errors
        and all(s in (200, 201) for s in statuses)
        and created == 1
        and duplicates == concurrency - 1
        and len(unique_ids) == 1
        and len({json.dumps(b, sort_keys=True) for b in bodies}) == 1
    )

    return {
        "timestamp_utc": run_id,
        "base_url": base_url,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed_s, 3),
        "requests_per_second": round(concurrency / elapsed_s, 2) if elapsed_s else None,
        "status_counts": {
            "201": created,
            "200": duplicates,
            "5xx": len(server_errors),
        },
        "unique_event_ids": len(unique_ids),
        "event_id": next(iter(unique_ids)) if unique_ids else None,
        "health_status": health.status_code,
        "passed": passed,
    }


def main() -> int:
    args = _parse_args()
    if not args.base_url:
        print("ERROR: pass --base-url or set EVENTLEDGER_URL", file=sys.stderr)
        return 2

    result = asyncio.run(_run(args.base_url, args.concurrency))
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")

    print(json.dumps(result, indent=2))
    if not result["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
