#!/usr/bin/env bash
# Restore RUMIN's production database from a backup made by scripts/backup.sh (Phase 10).
#
# This REPLACES the whole database with the backup's contents. The API and the web server
# are stopped first, so nothing is written during the restore; the database is dropped and
# recreated, so nothing made after the backup survives; then both are started again.
#
# If the backup was taken under an older release, either run that release's images
# (rollback) or bring the schema forward with the migrations (docs/deployment.md).
#
# Usage: scripts/restore.sh BACKUP.dump --yes [--env-file PATH]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env.production"
BACKUP=""
CONFIRMED=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --yes) CONFIRMED=1; shift ;;
    -*) echo "usage: $0 BACKUP.dump --yes [--env-file PATH]" >&2; exit 2 ;;
    *) BACKUP="$1"; shift ;;
  esac
done
[[ -f "${BACKUP}" ]] || { echo "error: no backup file '${BACKUP}'" >&2; exit 2; }
[[ -f "${ENV_FILE}" ]] || { echo "error: no env file at ${ENV_FILE}" >&2; exit 2; }
if [[ "${CONFIRMED}" -ne 1 ]]; then
  echo "This replaces the whole database with ${BACKUP}. Add --yes to go ahead." >&2
  exit 2
fi

COMPOSE=(docker compose -f "${ROOT}/compose.production.yml" --env-file "${ENV_FILE}")

echo "==> Checking the backup"
"${COMPOSE[@]}" exec -T db pg_restore --list < "${BACKUP}" > /dev/null

echo "==> Stopping the web server and the API"
"${COMPOSE[@]}" stop web api

echo "==> Replacing the database"
# Dropped and created by the superuser; restored by `rumin`, so it owns what it restores.
"${COMPOSE[@]}" exec -T db dropdb -U postgres --if-exists --force rumin
"${COMPOSE[@]}" exec -T db createdb -U postgres --owner=rumin rumin
"${COMPOSE[@]}" exec -T db psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q \
  -c "REVOKE ALL ON DATABASE rumin FROM PUBLIC" -c "GRANT CONNECT, TEMPORARY ON DATABASE rumin TO rumin"
"${COMPOSE[@]}" exec -T db pg_restore -U rumin -d rumin --no-owner --exit-on-error \
  < "${BACKUP}"

echo "==> Ending every session"
# Sessions that had been ended after the backup was taken would otherwise come back.
"${COMPOSE[@]}" exec -T db psql -U rumin -d rumin -v ON_ERROR_STOP=1 -q \
  -c "UPDATE user_sessions SET revoked_at = now() WHERE revoked_at IS NULL"

echo "==> Starting the API and the web server"
"${COMPOSE[@]}" up -d api web
ORIGIN="$(grep -E '^RUMIN_PUBLIC_ORIGIN=' "${ENV_FILE}" | cut -d= -f2- || true)"
echo "Restored ${BACKUP}. Everyone must sign in again; passwords changed since the backup are"
echo "back to their earlier values. Check readiness: curl -fsS ${ORIGIN:-https://<host>}/health/ready"
