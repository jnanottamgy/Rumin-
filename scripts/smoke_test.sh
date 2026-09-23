#!/usr/bin/env bash
# End-to-end smoke test for RUMIN.
#
#   1. creates a throwaway SQLite database,
#   2. applies the Alembic migrations, loads the illustrative sample dataset and the series
#      catalogue, imports a tiny SYNTHETIC price file through the ingestion CLI, and builds
#      the knowledge graph from all of it,
#   3. starts the API on a spare port,
#   4. runs the frontend's integration suite (its real service layer) against it,
#   5. stops the API and deletes the database, whatever the outcome.
#
# Usage: scripts/smoke_test.sh
# Needs: the backend environment (`uv sync --extra dev` in backend/) and the frontend
# dependencies (`npm ci` in frontend/). Nothing outside a temporary directory is touched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${RUMIN_SMOKE_PORT:-8765}"
WORKDIR="$(mktemp -d)"
API_PID=""

cleanup() {
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
  rm -rf "${WORKDIR}"
}
trap cleanup EXIT

# Explicit settings, so a developer's .env cannot change what is being tested.
export RUMIN_DATABASE_URL="sqlite:///${WORKDIR}/smoke.db"
export RUMIN_ENVIRONMENT="test"
export RUMIN_LOG_LEVEL="WARNING"
export RUMIN_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"

# The backend's Python: from uv when available, else from backend/.venv.
if command -v uv >/dev/null 2>&1; then
  PYTHON="$(cd "${ROOT}/backend" && uv run --frozen python -c 'import sys; print(sys.executable)')"
elif [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/backend/.venv/bin/python"
else
  echo "error: install uv, or create backend/.venv (see README)" >&2
  exit 1
fi

backend_python() {
  (cd "${ROOT}/backend" && exec "${PYTHON}" "$@")
}

if [[ ! -d "${ROOT}/frontend/node_modules" ]]; then
  echo "error: run 'npm ci' in frontend/ first" >&2
  exit 1
fi

echo "==> Migrating a fresh database"
backend_python -m alembic upgrade head

echo "==> Loading the illustrative sample dataset"
backend_python -m app.db.seed

echo "==> Loading the series catalogue (definitions only: nothing is fetched)"
backend_python -m app.ingestion catalog

# Three made-up trading days, labelled as sample data everywhere they appear. No provider is
# contacted: the smoke test never depends on the network.
echo "==> Importing a SYNTHETIC price file through the ingestion CLI"
cat > "${WORKDIR}/smoke-prices.csv" <<'CSV'
date,open,high,low,close,volume
2025-03-03,100.00,101.50,99.50,101.00,1200
2025-03-04,101.00,102.25,100.75,102.00,1350
2025-03-05,102.00,102.00,100.10,100.40,990
CSV
cat > "${WORKDIR}/smoke-manifest.json" <<'JSON'
{
  "dataset": {
    "id": "smoke-synthetic-prices",
    "name": "SYNTHETIC smoke-test prices (not market data)",
    "description": "Three made-up trading days used by the smoke test.",
    "license": "None (synthetic test data)",
    "attribution": "Synthetic test data",
    "provenance_note": "Written by scripts/smoke_test.sh. Not market data.",
    "is_illustrative": true
  },
  "instrument": {
    "id": "smoke-synthetic",
    "name": "SYNTHETIC smoke-test instrument (not a real security)",
    "instrument_type": "equity",
    "exchange_mic": "XNSE",
    "symbol": "SMOKETEST",
    "currency": "INR"
  },
  "adjustment": "unadjusted"
}
JSON
backend_python -m app.ingestion import-prices \
  --manifest "${WORKDIR}/smoke-manifest.json" --file "${WORKDIR}/smoke-prices.csv"

echo "==> Building the knowledge graph (and checking a rebuild changes nothing)"
backend_python -m app.graph build
backend_python -m app.graph build | tee "${WORKDIR}/rebuild.txt"
grep -Eq "^Changes: nodes \+0 added, 0 changed, 0 retired, [0-9]+ unchanged · edges \+0 added, 0 changed, 0 retired" \
  "${WORKDIR}/rebuild.txt" || {
  echo "error: rebuilding an unchanged graph changed it" >&2
  exit 1
}

echo "==> Starting the API on port ${PORT}"
# Not through backend_python: `exec` in a directly backgrounded subshell makes $! the
# server's own PID, so cleanup stops the server rather than a wrapper shell.
(cd "${ROOT}/backend" &&
  exec "${PYTHON}" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}" --log-level warning) &
API_PID=$!

# Readiness answers 503 until the database, migrations and dataset check out.
if ! curl -fs --retry 30 --retry-delay 1 --retry-connrefused --retry-all-errors \
  "http://127.0.0.1:${PORT}/health/ready" >/dev/null; then
  echo "error: the API did not become ready within 30 s" >&2
  exit 1
fi

echo "==> Running the frontend integration suite against it"
(cd "${ROOT}/frontend" && RUMIN_API_URL="http://127.0.0.1:${PORT}" npm run --silent test:integration)

echo "==> Smoke test passed"
