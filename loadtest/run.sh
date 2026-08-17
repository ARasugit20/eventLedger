#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="$ROOT/loadtest/output"
RESULTS="$ROOT/loadtest/results.md"
mkdir -p "$OUT_DIR"

RUN_ID="${RUN_ID:-load-$(date -u +%Y%m%dT%H%M%SZ)}"
EVENT_TYPE="${EVENT_TYPE:-loadtest.${RUN_ID}}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
UNIQUE_DURATION="${UNIQUE_DURATION:-60}"
UNIQUE_CONNECTIONS="${UNIQUE_CONNECTIONS:-50}"
DUPLICATE_DURATION="${DUPLICATE_DURATION:-60}"
DUPLICATE_CONCURRENCY="${DUPLICATE_CONCURRENCY:-50}"
DUPLICATE_KEY="${DUPLICATE_KEY:-dup-${RUN_ID}}"
UNIQUE_OUT="$OUT_DIR/wrk_unique.txt"
DUPLICATE_OUT="$OUT_DIR/hey_duplicate.txt"
ANALYTICS_OUT="$OUT_DIR/analytics_duplicate_rate.json"

HOST_INFO="$(uname -srm 2>/dev/null || echo unknown)"
COLIMA_INFO="not detected"
if command -v colima >/dev/null 2>&1; then
  COLIMA_INFO="$(
    colima list --json 2>/dev/null |
      jq -r '"\(.name): \(.cpus) CPUs, \(.memory / 1073741824) GiB memory, \(.disk / 1073741824) GiB disk, runtime=\(.runtime)"'
  )"
fi

export LOADTEST_RUN_ID="$RUN_ID"
export LOADTEST_EVENT_TYPE="$EVENT_TYPE"
export BASE_URL UNIQUE_DURATION UNIQUE_CONNECTIONS DUPLICATE_DURATION
export DUPLICATE_CONCURRENCY DUPLICATE_KEY HOST_INFO COLIMA_INFO

if [[ "${GENERATE_ONLY:-0}" != "1" ]]; then
  echo "Starting stack..."
  docker-compose up --build -d postgres redis api worker

  echo "Waiting for ${BASE_URL}/health..."
  for _ in $(seq 1 90); do
    if curl -sf "${BASE_URL}/health" >/dev/null; then
      break
    fi
    sleep 2
  done
  curl -sf "${BASE_URL}/health" | jq . >"$OUT_DIR/health.json"

  echo "Warm-up..."
  curl -sf -X POST "${BASE_URL}/events" \
    -H "Content-Type: application/json" \
    -d "{\"idempotency_key\":\"warm-${RUN_ID}\",\"event_type\":\"${EVENT_TYPE}\",\"payload\":{\"warm\":true}}" \
    >/dev/null

  echo "Running wrk unique-key phase..."
  wrk -t4 -c"${UNIQUE_CONNECTIONS}" -d"${UNIQUE_DURATION}s" \
    -s "$ROOT/loadtest/unique.lua" \
    "${BASE_URL}" 2>&1 | tee "$UNIQUE_OUT"

  echo "Running hey duplicate-key phase..."
  hey -z "${DUPLICATE_DURATION}s" -c "${DUPLICATE_CONCURRENCY}" -m POST \
    -H "Content-Type: application/json" \
    -d "{\"idempotency_key\":\"${DUPLICATE_KEY}\",\"event_type\":\"${EVENT_TYPE}\",\"payload\":{\"dup\":true}}" \
    "${BASE_URL}/events" 2>&1 | tee "$DUPLICATE_OUT"

  curl -sf "${BASE_URL}/analytics/duplicate-rate" | jq . >"$ANALYTICS_OUT"
fi

DUPLICATE_RATE="$(python3 - <<PY
import json
from pathlib import Path
rows = json.loads(Path("$ANALYTICS_OUT").read_text())
match = next((r for r in rows if r.get("event_type") == "$EVENT_TYPE"), None)
print(match["duplicate_rate_pct"] if match else "n/a")
PY
)"
export DUPLICATE_RATE
export UNIQUE_OUT DUPLICATE_OUT ANALYTICS_OUT

python3 - <<'PY' >"$RESULTS"
from pathlib import Path
import datetime
import os

RUN_ID = os.environ["LOADTEST_RUN_ID"]
EVENT_TYPE = os.environ["LOADTEST_EVENT_TYPE"]
BASE_URL = os.environ["BASE_URL"]
UNIQUE_DURATION = os.environ["UNIQUE_DURATION"]
UNIQUE_CONNECTIONS = os.environ["UNIQUE_CONNECTIONS"]
DUPLICATE_DURATION = os.environ["DUPLICATE_DURATION"]
DUPLICATE_CONCURRENCY = os.environ["DUPLICATE_CONCURRENCY"]
DUPLICATE_KEY = os.environ["DUPLICATE_KEY"]
DUPLICATE_RATE = os.environ["DUPLICATE_RATE"]

unique = Path(os.environ["UNIQUE_OUT"]).read_text()
duplicate = Path(os.environ["DUPLICATE_OUT"]).read_text()
analytics = Path(os.environ["ANALYTICS_OUT"]).read_text()

def pick(line_prefix, text, default="n/a"):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(line_prefix):
            return line.split(":", 1)[1].strip() if ":" in line else default
    return default

def percentile(prefix, text, default="n/a"):
    for line in text.splitlines():
        line = line.strip().replace("%%", "%")
        if line.startswith(prefix) and " in " in line:
            return line.split(" in ", 1)[1]
    return default

now = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
print("# EventLedger load test results")
print()
print(f"- Timestamp (UTC): {now}")
print(f"- Run ID: {RUN_ID}")
print(f"- Event type: {EVENT_TYPE}")
print(f"- Host: {os.environ['HOST_INFO']}")
print(f"- Colima: {os.environ['COLIMA_INFO']}")
print(f"- Base URL: {BASE_URL}")
print()
print("## Commands")
print()
print("```bash")
print("docker-compose up --build -d postgres redis api worker")
print(f"LOADTEST_RUN_ID={RUN_ID} LOADTEST_EVENT_TYPE={EVENT_TYPE} wrk -t4 -c{UNIQUE_CONNECTIONS} -d{UNIQUE_DURATION}s -s loadtest/unique.lua {BASE_URL}")
print(f"hey -z {DUPLICATE_DURATION}s -c {DUPLICATE_CONCURRENCY} -m POST -H 'Content-Type: application/json' -d '{{\"idempotency_key\":\"{DUPLICATE_KEY}\",\"event_type\":\"{EVENT_TYPE}\",\"payload\":{{\"dup\":true}}}}' {BASE_URL}/events")
print(f"curl -s {BASE_URL}/analytics/duplicate-rate | jq")
print("```")
print()
print("## Unique-key ingest (wrk)")
print()
print("```")
print(unique.strip())
print("```")
print()
print(f"- Requests/sec: {pick('Requests/sec', unique)}")
print(f"- Transfer/sec: {pick('Transfer/sec', unique)}")
print(f"- Non-2xx responses: {pick('Non-2xx or 3xx responses', unique, '0')}")
print()
print("## Duplicate-key concurrency (hey)")
print()
print("```")
print(duplicate.strip())
print("```")
print()
print(f"- Observed duplicate rate for `{EVENT_TYPE}`: {DUPLICATE_RATE}%")
print(f"- p50 latency: {percentile('50%', duplicate)}")
print(f"- p95 latency: {percentile('95%', duplicate)}")
print(f"- p99 latency: {percentile('99%', duplicate)}")
print()
print("## Analytics snapshot")
print()
print("```json")
print(analytics.strip())
print("```")
print()
print("## Limitations")
print()
print("- Benchmarks run against the local Docker Compose stack on this host.")
print("- Worker-process Prometheus counters are not scraped; evidence uses API responses and analytics SQL views.")
print("- Results depend on Colima/CPU allocation and concurrent local workloads.")
PY

echo "Wrote $RESULTS"
