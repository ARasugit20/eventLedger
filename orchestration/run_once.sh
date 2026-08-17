#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EVIDENCE="$ROOT/orchestration/evidence/dag_test.log"
mkdir -p "$(dirname "$EVIDENCE")"

echo "Starting core stack..."
docker-compose up --build -d postgres redis api worker

echo "Waiting for API health..."
for _ in $(seq 1 60); do
  if curl -sf http://localhost:8000/health >/dev/null; then
    break
  fi
  sleep 2
done
curl -sf http://localhost:8000/health | jq .

echo "Building Airflow image..."
docker-compose --profile orchestration build airflow

RUN_DATE="$(date -u +%Y-%m-%d)"
echo "Running airflow dags test eventledger_dlq_health_sweep ${RUN_DATE}..."
{
  echo "=== EventLedger DLQ health sweep dag test ==="
  echo "run_date=${RUN_DATE}"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker-compose --profile orchestration run --rm airflow -c \
    "airflow db migrate && airflow dags test eventledger_dlq_health_sweep '$RUN_DATE'"
  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "status=success"
} 2>&1 | tee "$EVIDENCE"

echo "Evidence written to $EVIDENCE"
