# EventLedger — Load Testing

> **Scope:** every number in [`loadtest/results.md`](../loadtest/results.md) was
> measured against **local Colima containers on `http://localhost:8000`**, not the
> hosted deploy. The `188.44` requests/second figure is a local benchmark only.
> For hosted numbers see [`docs/deploy_evidence/`](deploy_evidence/), which records
> a 50-request burst against the live Railway URL. The two are not comparable —
> different concurrency, duration, and network path.

Run the measured benchmark script against a containerized stack:

```bash
chmod +x loadtest/run.sh
./loadtest/run.sh
```

Raw command output is saved under `loadtest/output/` and summarized in [`loadtest/results.md`](results.md).

## Tools

- [wrk](https://github.com/wg/wrk) with [`loadtest/unique.lua`](unique.lua) for unique-key ingest
- [hey](https://github.com/rakyll/hey) for duplicate-key concurrency and latency percentiles

Both are invoked by `loadtest/run.sh`. Install locally via Homebrew if needed:

```bash
brew install wrk hey jq
```

## What the script measures

1. Starts `postgres`, `redis`, `api`, and `worker` via Docker Compose
2. Waits for `/health`
3. Runs a warm-up ingest
4. 60s unique-key ingest at 50 connections (`wrk`)
5. 60s duplicate-key phase at 50 concurrency (`hey`)
6. Queries `/analytics/duplicate-rate` for the run-specific event type
7. Generates `loadtest/results.md` from raw output (do not hand-edit benchmark numbers)

## Evidence sources

- API responses and `/analytics/*` SQL views
- Container logs during the run
- Prometheus scrapes **only** `api:8000`; worker counters are not scraped in the default Compose stack

## First bottleneck at 10× (design note)

**PostgreSQL connection contention** on POST `/events` is typically the first wall under sustained concurrency:

- Each request: Redis NX → INSERT → XADD stream → commit
- Default SQLAlchemy pool (5 + 10 overflow) saturates under sustained 50+ concurrent clients
- Symptom: rising ingest latency while CPU is still moderate

See measured numbers in `loadtest/results.md` for this environment.
