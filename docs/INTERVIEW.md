# EventLedger — Interview Guide

Five talking points for backend / SWE intern interviews.

## 1. Idempotency keys

Clients send a stable `idempotency_key` with every event. EventLedger deduplicates at three layers:

- **Redis SET NX** — fast reject of obvious duplicates before hitting PostgreSQL
- **PostgreSQL UNIQUE constraint** on `idempotency_key` — durable source of truth
- **Worker idempotence** — terminal events (`processed` / `failed`) are not re-processed

Duplicate POSTs return **200** with the same `id` and body as the original **201**, so callers can safely retry on timeouts.

**Payload conflict:** Reusing an idempotency key with a *different* `event_type` or `payload` returns **409 Conflict** — this catches client bugs and key collision abuse.

## 2. At-least-once delivery vs at-most-once side effects

Redis Streams and HTTP retries mean messages may be delivered **more than once**. That is acceptable: workers check event status before processing and only apply side effects when transitioning from `received` → `processing`.

The guarantee we sell is **at-most-once side effects** (no double charges, no duplicate claim payouts), not exactly-once delivery.

## 3. Audit trail and observability

Every event moves through a visible lifecycle: `received` → `processing` → `processed` | `failed`. Structured JSON logs include `event_id`, `idempotency_key`, and `latency_ms` on ingest.

Operators can list/filter events by status and inspect `error_message` on failures without SSH-ing into workers.

## 4. Dead-letter / failure handling (DLQ pattern)

Failed events stay in PostgreSQL with `status=failed` and `error_message` populated. They are not silently dropped.

A production extension would move repeatedly failing stream entries to a **dead-letter stream** (or table) after N attempts, with alerting. EventLedger v1 retains failures in the primary table for simplicity and demo clarity.

## 5. What breaks at 10× traffic

See [LOAD_TEST.md](./LOAD_TEST.md) for numbers. Expect these bottlenecks first:

1. **PostgreSQL connection pool** — each ingest opens a transaction; pool exhaustion adds queueing latency
2. **Redis single-threaded CPU** — dedupe SET NX becomes hot at high RPS
3. **Worker throughput** — one consumer group member processes serially per partition; scale horizontally by adding workers

Mitigations: connection pooling (PgBouncer), batch stream reads, read replicas for GET/list, and horizontal worker scaling.
