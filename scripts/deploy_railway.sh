#!/usr/bin/env bash
# One-shot Railway deploy for EventLedger (API + worker + managed Postgres + Redis).
# Requires: railway CLI logged in (`railway login`).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! railway whoami >/dev/null 2>&1; then
  echo "Run: railway login"
  exit 1
fi

PROJECT_NAME="${RAILWAY_PROJECT_NAME:-eventledger}"

if ! railway status >/dev/null 2>&1; then
  railway init --name "$PROJECT_NAME"
fi

echo "Ensure managed Postgres and Redis exist in this Railway project."
echo "In the dashboard: + New > Database > PostgreSQL, then + New > Database > Redis"
echo "Then add a second GitHub service for the worker using deploy/railway-worker.toml start command."

railway up --service "${RAILWAY_API_SERVICE:-eventledger-api}" || railway up

DOMAIN="$(railway domain 2>/dev/null || true)"
echo "Public URL: ${DOMAIN:-assign under Settings > Networking > Generate Domain}"
