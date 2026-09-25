#!/usr/bin/env bash
# The launch verification suite (Phase 10).
#
#   1. creates a throwaway SQLite database with the migrations, the illustrative sample
#      dataset, the series catalogue, a tiny SYNTHETIC price file and the knowledge graph,
#   2. creates an administrator with a random password,
#   3. starts the API and serves the built web app with `vite preview` (which proxies /api),
#   4. runs the Playwright suite in Chromium — signing in, every page on a desktop and a
#      phone (axe, console errors, overflow, timings) and the core workflows,
#   5. stops both servers and deletes the database, whatever the outcome.
#
# Usage: scripts/e2e.sh [playwright options, e.g. --project=desktop]
# Needs the backend environment (uv), the frontend dependencies (npm ci) and Playwright's
# Chromium (`npx playwright install chromium`). Results: frontend/e2e-results/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${RUMIN_E2E_API_PORT:-8766}"
WEB_PORT="${RUMIN_E2E_WEB_PORT:-4174}"
WORKDIR="$(mktemp -d)"
PIDS=()

cleanup() {
  for pid in "${PIDS[@]}"; do
    kill "${pid}" 2> /dev/null || true
    wait "${pid}" 2> /dev/null || true
  done
  rm -rf "${WORKDIR}"
}
trap cleanup EXIT

export RUMIN_DATABASE_URL="sqlite:///${WORKDIR}/e2e.db"
export RUMIN_ENVIRONMENT="test"
export RUMIN_LOG_LEVEL="WARNING"
export RUMIN_ANALYST_PROVIDER="grounded"

if command -v uv > /dev/null 2>&1; then
  PYTHON="$(cd "${ROOT}/backend" && uv run --frozen python -c 'import sys; print(sys.executable)')"
else
  PYTHON="${ROOT}/backend/.venv/bin/python"
fi
backend_python() { (cd "${ROOT}/backend" && exec "${PYTHON}" "$@"); }

echo "==> Preparing a fresh database"
backend_python -m alembic upgrade head > /dev/null
backend_python -m app.db.seed > /dev/null
backend_python -m app.ingestion catalog > /dev/null
cat > "${WORKDIR}/prices.csv" << 'CSV'
date,open,high,low,close,volume
2025-03-03,100.00,101.50,99.50,101.00,1200
2025-03-04,101.00,102.25,100.75,102.00,1350
2025-03-05,102.00,102.00,100.10,100.40,990
CSV
cat > "${WORKDIR}/manifest.json" << 'JSON'
{
  "dataset": {
    "id": "e2e-synthetic-prices",
    "name": "SYNTHETIC e2e prices (not market data)",
    "description": "Three made-up trading days used by the launch suite.",
    "license": "None (synthetic test data)",
    "attribution": "Synthetic test data",
    "provenance_note": "Written by scripts/e2e.sh. Not market data.",
    "is_illustrative": true
  },
  "instrument": {
    "id": "e2e-synthetic",
    "name": "SYNTHETIC e2e instrument (not a real security)",
    "instrument_type": "equity",
    "exchange_mic": "XNSE",
    "symbol": "E2ETEST",
    "currency": "INR"
  },
  "adjustment": "unadjusted"
}
JSON
backend_python -m app.ingestion import-prices \
  --manifest "${WORKDIR}/manifest.json" --file "${WORKDIR}/prices.csv" > /dev/null
backend_python -m app.graph build > /dev/null

echo "==> Creating the run's administrator"
export RUMIN_TEST_EMAIL="e2e-admin@rumin.test"
RUMIN_TEST_PASSWORD="$("${PYTHON}" -c 'import secrets; print(secrets.token_urlsafe(24))')"
export RUMIN_TEST_PASSWORD
printf '%s\n' "${RUMIN_TEST_PASSWORD}" |
  backend_python -m app.auth create-user --email "${RUMIN_TEST_EMAIL}" \
    --name "Launch Suite" --role admin --password-stdin > /dev/null

echo "==> Starting the API on ${API_PORT} and the web app on ${WEB_PORT}"
(cd "${ROOT}/backend" &&
  exec "${PYTHON}" -m uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT}" \
    --log-level warning --no-access-log) &
PIDS+=($!)
(cd "${ROOT}/frontend" && npm run --silent build > /dev/null)
(cd "${ROOT}/frontend" && RUMIN_API_PROXY_TARGET="http://127.0.0.1:${API_PORT}" \
  exec node_modules/.bin/vite preview --host 127.0.0.1 --port "${WEB_PORT}" --strictPort \
  > /dev/null 2>&1) &
PIDS+=($!)
if ! curl -fs --noproxy '*' --retry 40 --retry-delay 1 --retry-connrefused --retry-all-errors \
  "http://127.0.0.1:${WEB_PORT}/health/ready" > /dev/null; then
  echo "error: the web app or the API did not become ready" >&2
  exit 1
fi

echo "==> Running the launch suite"
cd "${ROOT}/frontend"
RUMIN_E2E_URL="http://127.0.0.1:${WEB_PORT}" npx playwright test "$@"
