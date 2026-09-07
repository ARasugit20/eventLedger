#!/bin/sh
# Run API and worker in one Railway/Render web service (deploy orchestration only).
set -eu

until alembic upgrade head; do
  echo "waiting-for-db"
  sleep 2
done

PORT="${PORT:-8000}"
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &
API_PID=$!
python -m app.worker &
WORKER_PID=$!

trap 'kill "$API_PID" "$WORKER_PID" 2>/dev/null || true' INT TERM

wait "$API_PID" "$WORKER_PID"
