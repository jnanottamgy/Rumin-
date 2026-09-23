#!/usr/bin/env bash
# End-to-end smoke test for RUMIN.
#
#   1. creates a throwaway SQLite database,
#   2. applies the Alembic migrations and loads the illustrative sample dataset,
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
