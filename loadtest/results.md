# EventLedger load test results

- Timestamp (UTC): 2026-08-17T07:20:24+00:00
- Run ID: load-20260817T071003Z
- Event type: loadtest.load-20260817T071003Z
- Host: Darwin 25.5.0 arm64
- Colima: default: 4 CPUs, 8 GiB memory, 60 GiB disk, runtime=docker
- Base URL: http://localhost:8000

## Commands

```bash
docker-compose up --build -d postgres redis api worker
LOADTEST_RUN_ID=load-20260817T071003Z LOADTEST_EVENT_TYPE=loadtest.load-20260817T071003Z wrk -t4 -c50 -d60s -s loadtest/unique.lua http://localhost:8000
hey -z 60s -c 50 -m POST -H 'Content-Type: application/json' -d '{"idempotency_key":"dup-load-20260817T071003Z","event_type":"loadtest.load-20260817T071003Z","payload":{"dup":true}}' http://localhost:8000/events
curl -s http://localhost:8000/analytics/duplicate-rate | jq
```

## Unique-key ingest (wrk)

```
Running 1m test @ http://localhost:8000
  4 threads and 50 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency   260.36ms  135.62ms   1.54s    77.20%
    Req/Sec    47.75     19.28   118.00     69.30%
  11324 requests in 1.00m, 4.96MB read
Requests/sec:    188.44
Transfer/sec:     84.51KB
```

- Requests/sec: 188.44
- Transfer/sec: 84.51KB
- Non-2xx responses: 0

## Duplicate-key concurrency (hey)

```
Summary:
  Total:	60.1429 secs
  Slowest:	1.1351 secs
  Fastest:	0.0407 secs
  Average:	0.1653 secs
  Requests/sec:	302.0972
  
  Total data:	5794566 bytes
  Size/request:	318 bytes

Response time histogram:
  0.041 [1]	|
  0.150 [9545]	|■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  0.260 [6413]	|■■■■■■■■■■■■■■■■■■■■■■■■■■■
  0.369 [1646]	|■■■■■■■
  0.478 [413]	|■■
  0.588 [105]	|
  0.697 [33]	|
  0.807 [8]	|
  0.916 [3]	|
  1.026 [1]	|
  1.135 [1]	|


Latency distribution:
  10%% in 0.0794 secs
  25%% in 0.1054 secs
  50%% in 0.1455 secs
  75%% in 0.2016 secs
  90%% in 0.2752 secs
  95%% in 0.3288 secs
  99%% in 0.4634 secs

Details (average, fastest, slowest):
  DNS+dialup:	0.0000 secs, 0.0000 secs, 0.0068 secs
  DNS-lookup:	0.0000 secs, 0.0000 secs, 0.0042 secs
  req write:	0.0000 secs, 0.0000 secs, 0.0007 secs
  resp wait:	0.1636 secs, 0.0403 secs, 1.1347 secs
  resp read:	0.0017 secs, 0.0000 secs, 0.0835 secs

Status code distribution:
  [200]	18168 responses
  [201]	1 responses
```

- Observed duplicate rate for `loadtest.load-20260817T071003Z`: 61.5%
- p50 latency: 0.1455 secs
- p95 latency: 0.3288 secs
- p99 latency: 0.4634 secs

## Analytics snapshot

```json
[
  {
    "event_type": "loadtest.load-20260817T071003Z",
    "total_attempts": 29542,
    "duplicate_attempts": 18168,
    "new_attempts": 11374,
    "unique_idempotency_keys": 11374,
    "duplicate_rate_pct": 61.5
  }
]
```

## Limitations

- Benchmarks run against the local Docker Compose stack on this host.
- Worker-process Prometheus counters are not scraped; evidence uses API responses and analytics SQL views.
- Results depend on Colima/CPU allocation and concurrent local workloads.
