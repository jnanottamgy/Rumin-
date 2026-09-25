#!/usr/bin/env bash
# The production deployment, checked end to end on this machine (Phase 10).
#
#   1. builds both images,
#   2. starts a throwaway stack (project "rumin-check": its own containers and volume, a
#      self-signed certificate for localhost, ports 18080 and 18443) and sets it up as
#      docs/deployment.md does: migrations, sample data, graph, an administrator,
#   3. checks it from outside with scripts/verify_deployment.sh,
#   4. backs up, changes the data, restores, and checks that the change is gone,
#   5. switches to another release's image tag and back (the rollback mechanics),
#   6. removes the stack, its volume and the certificate, whatever the outcome.
#
# Needs Docker with Compose v2, openssl, curl and python3. Nothing is sent anywhere.
# Behind a proxy that re-signs TLS: RUMIN_EXTRA_CA=/path/to/ca-bundle.crt
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="rumin-check"
HTTP_PORT="${RUMIN_CHECK_HTTP_PORT:-18080}"
HTTPS_PORT="${RUMIN_CHECK_HTTPS_PORT:-18443}"
ORIGIN="https://localhost:${HTTPS_PORT}"
WORK="$(mktemp -d)"
export COMPOSE_PROJECT_NAME="${PROJECT}"
COMPOSE=(docker compose -f "${ROOT}/compose.production.yml" --env-file "${WORK}/check.env")

cleanup() {
  "${COMPOSE[@]}" down --volumes --remove-orphans > /dev/null 2>&1 || true
  rm -rf "${WORK}"
}
trap cleanup EXIT

mkdir -p "${WORK}/tls" "${WORK}/backups"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost" \
  -keyout "${WORK}/tls/privkey.pem" -out "${WORK}/tls/fullchain.pem" 2> /dev/null
chmod 755 "${WORK}" "${WORK}/tls"
chmod 644 "${WORK}/tls/privkey.pem" "${WORK}/tls/fullchain.pem" # the throwaway key only
cat > "${WORK}/check.env" <<ENV
RUMIN_VERSION=check
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_ADMIN_PASSWORD=$(openssl rand -hex 24)
RUMIN_SERVER_NAME=localhost
RUMIN_PUBLIC_ORIGIN=${ORIGIN}
RUMIN_HTTP_PORT=${HTTP_PORT}
RUMIN_HTTPS_PORT=${HTTPS_PORT}
RUMIN_TLS_DIR=${WORK}/tls
ENV
python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "${WORK}/admin.pw"

SECRET=()
if [[ -n "${RUMIN_EXTRA_CA:-}" ]]; then SECRET=(--secret "id=extra_ca,src=${RUMIN_EXTRA_CA}"); fi
echo "==> Building the images"
docker build --quiet "${SECRET[@]}" -t rumin-api:check "${ROOT}/backend"
docker build --quiet "${SECRET[@]}" -f "${ROOT}/frontend/Dockerfile" -t rumin-web:check "${ROOT}"

echo "==> First start, as docs/deployment.md describes"
"${COMPOSE[@]}" up -d --wait db
run() { "${COMPOSE[@]}" run --rm -T api "$@"; }
run alembic upgrade head
run python -m app.db.seed > /dev/null
run python -m app.ingestion catalog > /dev/null
run python -m app.graph build > /dev/null
run python -m app.auth create-user --email admin@rumin.test --name "Deployment check" \
  --role admin --password-stdin < "${WORK}/admin.pw"
"${COMPOSE[@]}" up -d --wait --no-build

echo "==> Checking the running stack from outside"
"${ROOT}/scripts/verify_deployment.sh" "${ORIGIN}" "${WORK}/check.env" admin@rumin.test \
  "${WORK}/admin.pw" --project "${PROJECT}" --insecure

echo "==> Backup, a change, and a restore"
CURL=(curl -sk --max-time 20 --noproxy '*')
sign_in() {
  local body cookie
  body="$(python3 -c 'import json,sys; print(json.dumps({"email": "admin@rumin.test", "password": open(sys.argv[1]).read().strip()}))' "${WORK}/admin.pw")"
  # The verification spent this address's burst of sign-ins: wait for the next slot.
  for _ in $(seq 1 12); do
    cookie="$(printf '%s' "${body}" | "${CURL[@]}" -D - -o /dev/null -H "Origin: ${ORIGIN}" \
      -H 'Content-Type: application/json' --data-binary @- "${ORIGIN}/api/v1/auth/login" |
      grep -i '^set-cookie:' |
      sed -E 's/^[Ss]et-[Cc]ookie: ([^;]*).*/\1/' | tr -d '\r' || true)"
    # Kept in a file only its owner can read, never on a command line.
    if [[ -n "${cookie}" ]]; then
      (umask 077 && printf 'Cookie: %s\n' "${cookie}" > "${WORK}/session.header")
      return 0
    fi
    sleep 7
  done
  echo "error: could not sign in" >&2
  return 1
}
scenario() {
  "${CURL[@]}" -H @"${WORK}/session.header" -H "Origin: ${ORIGIN}" -H 'Content-Type: application/json' \
    -d "{\"name\":\"$1\",\"description\":\"Deployment check (HYPOTHETICAL)\",\"note\":\"\",\"shocks\":[{\"variable_id\":\"var_brent_crude\",\"change_type\":\"percent_change\",\"value\":\"5\",\"note\":\"\"}]}" \
    "${ORIGIN}/api/v1/scenarios" > /dev/null
}
names() {
  "${CURL[@]}" -H @"${WORK}/session.header" "${ORIGIN}/api/v1/scenarios" |
    python3 -c 'import json,sys; print(",".join(sorted(i["name"] for i in json.load(sys.stdin)["items"])))'
}
sign_in
scenario "Kept by the backup"
RUMIN_BACKUP_DIR="${WORK}/backups" "${ROOT}/scripts/backup.sh" --env-file "${WORK}/check.env"
scenario "Made after the backup"
[[ "$(names)" == "Kept by the backup,Made after the backup" ]] || { echo "error: setup" >&2; exit 1; }
"${ROOT}/scripts/restore.sh" "$(ls "${WORK}"/backups/*.dump)" --yes --env-file "${WORK}/check.env"
"${COMPOSE[@]}" up -d --wait --no-build
sign_in
RESTORED="$(names)"
[[ "${RESTORED}" == "Kept by the backup" ]] || {
  echo "error: after the restore the scenarios are '${RESTORED}'" >&2
  exit 1
}
echo "PASS  the restore brings back exactly what the backup held"

echo "==> Rollback: another release's images, then back"
docker tag rumin-api:check rumin-api:check-previous
docker tag rumin-web:check rumin-web:check-previous
RUMIN_VERSION=check-previous "${COMPOSE[@]}" up -d --wait --no-build
[[ "$(docker inspect "$("${COMPOSE[@]}" ps -q api)" --format '{{.Config.Image}}')" == "rumin-api:check-previous" ]]
"${CURL[@]}" "${ORIGIN}/health/ready" | grep -q '"status":"ready"'
"${COMPOSE[@]}" up -d --wait --no-build
[[ "$(docker inspect "$("${COMPOSE[@]}" ps -q api)" --format '{{.Config.Image}}')" == "rumin-api:check" ]]
echo "PASS  switching the release's image tag and back keeps the stack ready"
docker image rm rumin-api:check-previous rumin-web:check-previous > /dev/null

echo "==> Deployment check passed"
