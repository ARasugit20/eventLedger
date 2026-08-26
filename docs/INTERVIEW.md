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
| **Redis SET NX** | Coordinates idempotency keys whose requests are concurrently in flight. |
| **PostgreSQL UNIQUE** | Durable source of truth. Survives Redis TTL expiry and concurrent races. |

The current API checks PostgreSQL first for an already-committed key, then uses Redis
before attempting a new insert. If Redis reports an in-flight duplicate but PostgreSQL
has no row yet, the unique constraint still picks the eventual winner. If Redis forgets
a key after its TTL, PostgreSQL still returns the original durable event.

---

## Q3: What happens if Redis crashes?

**Answer:**

- **Existing key:** An already-committed duplicate is found in PostgreSQL before the
  Redis claim and can still return the original event.
- **New ingest:** The Redis `SET NX` exception currently propagates, so a new event
  fails rather than falling open to PostgreSQL.
- **After a database commit:** If `XADD` alone fails, enqueue is retried three times.
  The row can remain `received`; there is no transactional outbox or recovery scanner.
- **Worker:** It cannot consume or reclaim stream messages until Redis returns.

**Interview line:** "Postgres remains the durable dedupe authority, but Redis is
currently required for new ingestion and queue delivery; fail-open ingest is future work."

---

## Q4: What does the concurrency test prove?

**Answer:** `tests/test_concurrency.py` fires **50 parallel POST requests** with the **same** `idempotency_key`. We assert:

- Exactly **one** HTTP 201 (created)
- **49** HTTP 200 (duplicate)
- **Zero** 5xx errors
- **One** row in the database
- All responses return the **same event UUID**

This proves the **ingest path** is race-safe under concurrent retries. Separate worker
tests prove a terminal event is not processed twice; the test does not claim
exactly-once behavior for arbitrary downstream systems.

---

## Q5: How would you scale EventLedger to 10,000 events/second?

**Answer:** Bottlenecks appear in this order:

1. **PostgreSQL writes** — each ingest is a transaction. Mitigate: connection pooling (PgBouncer), batch inserts, or write sharding by tenant.
2. **Redis CPU** — single-threaded; SET NX on every request gets hot. Mitigate: Redis Cluster, or rely on Postgres with prepared statements.
3. **Worker throughput** — one consumer group member is serial. Mitigate: multiple worker replicas in the same consumer group.
4. **Observability** — the default Prometheus target exposes API ingest metrics. Add a
   worker metrics endpoint/scrape target before relying on processing latency, retry, or
   stream-depth panels.

**Interview line:** "I'd pool database connections and scale workers first, then expose
worker metrics so measurements—not guesses—drive the next bottleneck fix."

---

## Q6: How do retries and the dead-letter queue work?

**Answer:** Redis Streams deliver **at-least-once** to the worker consumer group. EventLedger handles that without double side effects:

| Outcome | Behavior |
|---------|----------|
| **Success** | Event marked `processed`, message ACKed |
| **Permanent failure** (e.g. `.fail` types) | Event marked `failed`, message ACKed |
| **Transient failure** (e.g. `.retry` types) | Claim released to `received`, message stays pending |
| **Max redeliveries exceeded** | Durable Postgres DLQ row + terminal event update commit, Redis mirror written, then message ACKed |

Stale pending messages are reclaimed with `XAUTOCLAIM` so crashed workers don't strand
work. Postgres is the DLQ source of truth; `eventledger:stream:dlq` is the operational
mirror. Replay is manual after inspecting the durable row.

**Interview line:** "We guarantee idempotent side effects, not exactly-once delivery. The DLQ catches poison pills after bounded retries."

---

See also: [LOAD_TEST.md](./LOAD_TEST.md), [OPERATIONS.md](./OPERATIONS.md)
