# EventLedger — Interview Q&A

Five questions you should be able to answer in a backend interview.

---

## Q1: What is idempotency and why does EventLedger need it?

**Answer:** Idempotency means calling the same operation multiple times has the same effect as calling it once. EventLedger clients send an `idempotency_key` with every event. If a webhook retries or a user double-clicks, the API returns the **same event ID** (HTTP 200) instead of creating a second row. That prevents double charges, duplicate claims, or repeated side effects. The guarantee we sell is **at-most-once side effects**, not exactly-once delivery.

---

## Q2: Why use both Redis and PostgreSQL for deduplication?

**Answer:** They solve different problems at different speeds:

| Layer | Role |
|-------|------|
| **Redis SET NX** | Fast path (~1 ms). Rejects obvious duplicates before a DB round-trip. |
| **PostgreSQL UNIQUE** | Durable source of truth. Survives Redis TTL expiry and concurrent races. |

Redis is an optimization. If Redis says "duplicate" but Postgres has no row yet (in-flight request), the UNIQUE constraint still picks a winner. If Redis forgets a key after 24h TTL but Postgres still has the row, a retry still returns 200 with the original event.

---

## Q3: What happens if Redis crashes?

**Answer:**

- **During ingest:** New events can still be inserted into PostgreSQL (Redis claim is skipped or fails open to DB). Duplicates are caught by the UNIQUE constraint on `idempotency_key`. Ingest degrades but stays correct.
- **Stream queue:** If Redis is down, `XADD` fails after retries — events stay in `received` status until Redis returns. The `events_pending_processing` gauge shows the backlog.
- **Worker:** Cannot read the stream until Redis is back. Events pile up in Postgres with `status=received`.

**Interview line:** "Redis down hurts latency and async processing, but Postgres keeps dedupe correct."

---

## Q4: What does the concurrency test prove?

**Answer:** `tests/test_concurrency.py` fires **50 parallel POST requests** with the **same** `idempotency_key`. We assert:

- Exactly **one** HTTP 201 (created)
- **49** HTTP 200 (duplicate)
- **Zero** 5xx errors
- **One** row in the database
- All responses return the **same event UUID**

This proves Redis NX + Postgres UNIQUE + transaction handling is **race-safe** under concurrent load — not just on sequential retries.

---

## Q5: How would you scale EventLedger to 10,000 events/second?

**Answer:** Bottlenecks appear in this order:

1. **PostgreSQL writes** — each ingest is a transaction. Mitigate: connection pooling (PgBouncer), batch inserts, or write sharding by tenant.
2. **Redis CPU** — single-threaded; SET NX on every request gets hot. Mitigate: Redis Cluster, or rely on Postgres with prepared statements.
3. **Worker throughput** — one consumer group member is serial. Mitigate: multiple worker replicas in the same consumer group.
4. **Observability** — use `events_ingested_total`, `event_processing_duration_seconds`, and `events_pending_processing` to find which layer saturates first before guessing.

**Interview line:** "I'd scale workers horizontally and pool DB connections first; Prometheus tells me where the wall actually is."

---

See also: [LOAD_TEST.md](./LOAD_TEST.md)
