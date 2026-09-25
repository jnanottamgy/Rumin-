#!/usr/bin/env bash
# Back up RUMIN's production database (Phase 10).
#
# Writes a pg_dump archive (custom format) of the database to backups/ — or
# $RUMIN_BACKUP_DIR — named with the UTC time, readable only by its owner, and checks it by
# reading its table of contents back. Take one before every upgrade, and on a schedule.
#
# A backup holds everything: scenarios and results, and also the accounts (password
# hashes, never passwords) and the security audit trail (with client addresses). Keep
# copies encrypted and off this host (docs/deployment.md).
#
# Usage: scripts/backup.sh [--env-file PATH]   (default: .env.production)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env.production"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    *) echo "usage: $0 [--env-file PATH]" >&2; exit 2 ;;
  esac
done
[[ -f "${ENV_FILE}" ]] || { echo "error: no env file at ${ENV_FILE}" >&2; exit 2; }

COMPOSE=(docker compose -f "${ROOT}/compose.production.yml" --env-file "${ENV_FILE}")
DIR="${RUMIN_BACKUP_DIR:-${ROOT}/backups}"
umask 077
mkdir -p "${DIR}"
FILE="${DIR}/rumin-$(date -u +%Y%m%dT%H%M%SZ).dump"

"${COMPOSE[@]}" exec -T db pg_dump -U rumin -d rumin --format=custom --no-owner \
  > "${FILE}.partial"
# An archive whose table of contents cannot be read is not a backup.
"${COMPOSE[@]}" exec -T db pg_restore --list < "${FILE}.partial" > /dev/null
mv "${FILE}.partial" "${FILE}"
echo "Backup written: ${FILE} ($(du -h "${FILE}" | cut -f1))"
