# EventLedger Operations Guide

## Delivery guarantees

EventLedger provides **at-least-once stream delivery** with **at-most-once side effects**:

- Duplicate HTTP requests with the same `idempotency_key` and body return the same event ID (200).
- PostgreSQL `UNIQUE(idempotency_key)` is the durable dedupe source of truth.
- Redis SET NX is a fast-path optimization with TTL.
- Workers atomically claim `received → processing` before side effects.
- Terminal states (`processed`, `failed`) are never re-run.

This is **not** exactly-once end-to-end. Retries and stream redelivery are expected; idempotency prevents duplicate business effects.

## Correlation IDs

- Clients may send `X-Correlation-ID` on ingest requests.
- If omitted, the API generates a UUID and returns it in the response header.
- Correlation IDs are written to Redis stream fields and included in structured JSON logs across ingest, enqueue, worker processing, and DLQ moves.

## Worker retry and DLQ behavior

| Setting | Default | Purpose |
|---------|---------|---------|
| `MAX_DELIVERY_ATTEMPTS` | 3 | Stream redeliveries before DLQ |
| `PENDING_IDLE_MS` | 60000 | Idle threshold for `XAUTOCLAIM` |
| `DLQ_STREAM` | `eventledger:stream:dlq` | Dead-letter stream |

Flow:

1. Worker reads message from Redis Stream consumer group.
2. Transient failures (event types ending in `.retry`) leave the message pending.
3. After `MAX_DELIVERY_ATTEMPTS` redeliveries, message moves to DLQ and is ACKed.
4. Permanent handler failures mark the event `failed` in Postgres and ACK the message.
5. Stale pending messages are reclaimed via `XAUTOCLAIM` each worker loop.

DLQ replay is manual in v1 — inspect DLQ stream entries and re-ingest if appropriate.

## Metrics and alerts

Prometheus metrics at `GET /metrics`:

| Metric | Meaning |
|--------|---------|
| `events_ingested_total{result}` | New vs duplicate ingest |
| `event_processing_duration_seconds` | Worker latency histogram |
| `events_pending_processing` | DB rows in received/processing |
| `stream_pending_messages` | Redis PEL depth |
| `worker_retries_total` | Transient retry count |
| `worker_processing_failures_total` | Permanent failures |
| `dlq_messages_total` | Messages moved to DLQ |

Example alert rules: [`deploy/prometheus/alerts.yml`](../deploy/prometheus/alerts.yml)

## Verification commands

```bash
ruff check app tests analytics scripts
make test-cov
make demo   # requires docker compose up
```

## Failure modes

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Rising `stream_pending_messages` | Worker down or slow | Scale/restart worker, check logs |
| `dlq_messages_total` increasing | Poison messages | Inspect DLQ stream, fix payload/handler |
| Duplicate rate spike | Client retries | Expected; verify idempotency keys stable |
| Redis TTL expired, DB row exists | Normal race | Postgres UNIQUE resolves; no duplicate row |

## Financial audit rules

- Event `payload` is immutable after ingest.
- Duplicate retries log to `ingest_attempts` without creating extra `events` rows.
- Same key + different body returns **409 Conflict** — never silently overwrites.
