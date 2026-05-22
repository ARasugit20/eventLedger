# EventLedger — Load Testing Notes

## Tools

Use [hey](https://github.com/rakyll/hey) or [wrk](https://github.com/wg/wrk) against a running stack:

```bash
docker compose up --build -d

# Warm-up
curl -s http://localhost:8000/health | jq

# 10k requests, 50 concurrent workers, unique idempotency keys
hey -n 10000 -c 50 -m POST \
  -H "Content-Type: application/json" \
  -d '{"idempotency_key":"load-{{.RequestNumber}}","event_type":"order.created","payload":{"sku":"X1","quantity":1}}' \
  http://localhost:8000/events
```

For wrk, use a Lua script to generate unique `idempotency_key` values per request.

## Baseline expectations (local Docker, M-series Mac / 4 vCPU CI runner)

| Traffic | Approx RPS | p99 ingest latency | First symptom |
|---------|------------|--------------------|---------------|
| 1×      | ~200–400   | < 50 ms            | — |
| 10×     | ~800–1500  | 100–300 ms         | Connection pool wait, Redis CPU |

Numbers vary by hardware; treat these as order-of-magnitude guides.

## First bottleneck at 10×

**PostgreSQL connection contention** on POST /events is typically the first wall:

- Each request: Redis NX → INSERT → XADD stream → commit
- Default SQLAlchemy pool (5 + 10 overflow) saturates under sustained 50+ concurrent clients
- Symptom: rising `latency_ms` in API logs while CPU is still moderate

**Second:** Redis SET NX at ingest — single-threaded Redis hits high CPU before Postgres maxes disk I/O on this workload.

**Third:** Worker lag — stream depth grows if workers < ingest rate; GET /events?status=received backlog increases.

## Mitigations (production roadmap)

- PgBouncer or raise pool size with monitoring
- Redis Cluster or dedicated dedupe shard
- Multiple worker replicas in the same consumer group
- Rate limiting / backpressure at the API gateway

## Duplicate-key load (idempotency path)

```bash
hey -n 5000 -c 50 -m POST \
  -H "Content-Type: application/json" \
  -d '{"idempotency_key":"same-key-1","event_type":"order.created","payload":{"sku":"X1"}}' \
  http://localhost:8000/events
```

Expect mostly **200** responses after the first **201**; Redis dedupe reduces duplicate INSERT pressure.
