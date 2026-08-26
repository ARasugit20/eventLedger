#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "Docker Compose is required." >&2
  exit 1
fi

for command in curl jq; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required." >&2
    exit 1
  fi
done

BASE_URL="${BASE_URL:-http://localhost:8000}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
IDEMPOTENCY_KEY="interview-demo-${RUN_ID}"
EVENT_TYPE="demo.idempotency.${RUN_ID}"
CORRELATION_ID="demo-${RUN_ID}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Starting EventLedger..."
"${COMPOSE[@]}" up --build -d

echo "Waiting for API health..."
healthy=0
for _ in $(seq 1 90); do
  if curl -sf "${BASE_URL}/health" >/dev/null; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != "1" ]]; then
  echo "API did not become healthy. Recent logs:" >&2
  "${COMPOSE[@]}" logs --no-color api worker >&2
  exit 1
fi

payload="$(
  jq -nc \
    --arg key "$IDEMPOTENCY_KEY" \
    --arg event_type "$EVENT_TYPE" \
    '{
      idempotency_key: $key,
      event_type: $event_type,
      payload: {sku: "INTERVIEW-1", quantity: 1}
    }'
)"

post_event() {
  local output_file="$1"
  curl -sS \
    -o "$output_file" \
    -w "%{http_code}" \
    -X POST "${BASE_URL}/events" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: ${CORRELATION_ID}" \
    -d "$payload"
}

first_code="$(post_event "$TMP_DIR/first.json")"
second_code="$(post_event "$TMP_DIR/second.json")"
first_id="$(jq -r '.id' "$TMP_DIR/first.json")"
second_id="$(jq -r '.id' "$TMP_DIR/second.json")"

if [[ "$first_code" != "201" || "$second_code" != "200" ]]; then
  echo "Expected HTTP 201 then 200, got ${first_code} then ${second_code}." >&2
  exit 1
fi
if [[ -z "$first_id" || "$first_id" == "null" || "$first_id" != "$second_id" ]]; then
  echo "Duplicate requests did not return the same event ID." >&2
  exit 1
fi

echo "Duplicate ingest proof:"
echo "  first request:  HTTP ${first_code}"
echo "  second request: HTTP ${second_code}"
echo "  shared event ID: ${first_id}"

terminal_status=""
for _ in $(seq 1 60); do
  terminal_status="$(
    curl -sf "${BASE_URL}/events/${first_id}" |
      jq -r '.status'
  )"
  if [[ "$terminal_status" == "processed" || "$terminal_status" == "failed" ]]; then
    break
  fi
  sleep 0.5
done
if [[ "$terminal_status" != "processed" ]]; then
  echo "Expected event to reach processed; got ${terminal_status}." >&2
  exit 1
fi
echo "  worker result:  ${terminal_status}"

echo
echo "Duplicate analytics for this run:"
curl -sf "${BASE_URL}/analytics/duplicate-rate" |
  jq --arg event_type "$EVENT_TYPE" \
    '.[] | select(.event_type == $event_type)'

echo
echo "API ingest counters:"
curl -sfL "${BASE_URL}/metrics/" |
  grep -E '^events_ingested_total'

echo
echo "Correlated API/worker logs:"
"${COMPOSE[@]}" logs --no-color --since 5m api worker |
  grep -F "$CORRELATION_ID" || true

echo
echo "PASS: one durable event ID, one queued handler path, duplicate returned safely."
