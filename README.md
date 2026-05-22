# EventLedger

[![CI](https://github.com/YOUR_USERNAME/EventLedger/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/EventLedger/actions/workflows/ci.yml)

**Idempotent event ingestion and async processing for order/claims-style workflows.**

Live demo: https://[deploy-later]

Clients send events with an `idempotency_key`; duplicate requests return the same result — no double processing. Events move through an audit trail: `received` → `processing` → `processed` | `failed`.

---

## Problem

In distributed systems, **duplicate events are normal**. Payment webhooks retry, mobile clients double-tap, and load balancers replay requests. Without idempotency, you get double charges, duplicate claims, and inconsistent state.

## Solution

EventLedger guarantees **at-most-once side effects** via:

- Client-supplied **idempotency keys**
- **Redis SET NX** for fast dedupe before DB write
- **PostgreSQL UNIQUE constraint** as durable source of truth
- **Redis Streams** + async workers for processing
- Full **audit trail** with status lifecycle

Duplicate POST `/events` returns **200** with the same event `id` as the original **201**.

## Architecture

```mermaid
flowchart LR
    Client --> FastAPI
    FastAPI --> Redis dedupe["Redis dedupe"]
    FastAPI --> PostgreSQL
    FastAPI --> Redis Stream["Redis Stream"]
    Redis Stream --> Worker
    Worker --> PostgreSQL
```

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| API | FastAPI + Pydantic v2 | Typed contracts, OpenAPI out of the box |
| Database | PostgreSQL 16 + JSONB | ACID, unique constraints, flexible payloads |
| Cache / queue | Redis 7 | SET NX dedupe + Streams consumer groups |
| ORM | SQLAlchemy 2.0 + Alembic | Migrations, production-grade data layer |
| Runtime | Docker Compose | One-command local stack |

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/EventLedger.git
cd EventLedger
docker compose up --build
```

API: http://localhost:8000  
OpenAPI docs: http://localhost:8000/docs

### Sample flow

```bash
# Ingest an event (201 Created)
curl -s -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "order-8821-create",
    "event_type": "order.created",
    "payload": {"sku": "X1", "quantity": 2, "customer_id": "c-99"}
  }' | jq

# Duplicate ingest (200 OK, same id)
curl -s -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "order-8821-create",
    "event_type": "order.created",
    "payload": {"sku": "X1", "quantity": 2, "customer_id": "c-99"}
  }' | jq

# Poll until processed (worker runs async)
curl -s http://localhost:8000/events/<EVENT_ID> | jq

# List by status
curl -s "http://localhost:8000/events?status=processed&limit=10" | jq

# Health (DB + Redis)
curl -s http://localhost:8000/health | jq
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness; checks PostgreSQL + Redis |
| POST | `/events` | Ingest event; 201 new, 200 duplicate |
| GET | `/events/{id}` | Get single event |
| GET | `/events` | List with `?status=` filter, `limit`, `offset` |

Interactive docs: **http://localhost:8000/docs**

## Redis dedupe trade-off

Before inserting into PostgreSQL, the API executes `SET idempotency:{key} NX EX 86400`. This rejects most duplicates in ~1 ms.

**Trade-off:** If Redis evicts the key (TTL expiry) but the DB row remains, a retry with the same key hits the DB unique constraint and still returns 200. Redis is an optimization layer; PostgreSQL is the source of truth.

## Tests & CI

```bash
pip install -r requirements.txt
pytest -v
```

GitHub Actions runs pytest on every push (uses testcontainers for PostgreSQL 16 + Redis 7).

## Deploy

**Render / Railway (suggested):**

1. Provision PostgreSQL 16 and Redis 7 add-ons
2. Deploy `api` service: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Deploy `worker` service: `alembic upgrade head && python -m app.worker`
4. Set `DATABASE_URL`, `REDIS_URL`, and copy values from `.env.example`

Update the live demo URL at the top of this README after deploy.

## Roadmap

- [x] Phase 1 — Core API, migrations, structured logging
- [x] Phase 2 — Redis dedupe, async worker, status lifecycle
- [x] Phase 3 — Tests, CI, interview + load-test docs
- [ ] Auth / API keys
- [ ] Dead-letter queue stream + replay UI
- [ ] Prometheus metrics + Grafana dashboard
- [ ] Horizontal worker autoscaling

## What I learned

- **Idempotency is a contract, not a library** — you need client keys, DB constraints, and worker guards together; any single layer can race under retries.
- **Redis NX before DB is a latency win with a TTL caveat** — always keep PostgreSQL as the authoritative dedupe store.
- **At-least-once delivery is fine** if side effects are guarded by status transitions and terminal-state checks in workers.

## Docs

- [Interview talking points](docs/INTERVIEW.md)
- [Load testing notes](docs/LOAD_TEST.md)

---

**Resume bullet:** Built EventLedger, an idempotent event ingestion API (FastAPI, PostgreSQL, Redis) with async workers and duplicate-request safety; documented failure modes under 10× load.
