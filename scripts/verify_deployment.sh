#!/usr/bin/env bash
# Checks a running production stack from the outside (Phase 10): redirects, TLS, security
# headers and CSP, caching, what is never served, the session cookie, the cross-site and
# rate limits, client addresses, logs, and the containers' users, file systems and ports.
#
# Usage: scripts/verify_deployment.sh BASE_URL ENV_FILE ADMIN_EMAIL ADMIN_PASSWORD_FILE
#   [--project NAME] [--insecure]   (--insecure: accept a self-signed certificate)
# Prints PASS/FAIL per check and exits 1 if any failed.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${1:?base URL, e.g. https://rumin.example.org}"
ENV_FILE="${2:?env file}"
EMAIL="${3:?administrator e-mail}"
PASSWORD_FILE="${4:?file holding the administrator password}"
shift 4
PROJECT=""
CURL=(curl -s --max-time 20 --noproxy '*')
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --insecure) CURL+=(-k); shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
COMPOSE=(docker compose -f "${ROOT}/compose.production.yml" --env-file "${ENV_FILE}")
[[ -n "${PROJECT}" ]] && COMPOSE+=(-p "${PROJECT}")
HTTP_BASE="$(grep -E '^RUMIN_HTTP_PORT=' "${ENV_FILE}" | cut -d= -f2)"
HOST="$(echo "${BASE}" | sed -E 's#^https://([^:/]+).*#\1#')"
ORIGIN="${BASE%/}"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
pass=0
fail=0
check() {
  if eval "$2"; then echo "PASS  $1"; pass=$((pass + 1)); else echo "FAIL  $1"; fail=$((fail + 1)); fi
}
code() { "${CURL[@]}" -o /dev/null -w '%{http_code}' "$@"; }
container() { "${COMPOSE[@]}" ps -q "$1"; }

# --- Transport and the web app ---------------------------------------------------------------
H="$("${CURL[@]}" -D - -o /dev/null "http://${HOST}:${HTTP_BASE:-80}/scenarios")"
check "plain HTTP redirects to the https origin" \
  "echo \"\$H\" | grep -q '^HTTP/1.1 301' && echo \"\$H\" | grep -qi '^location: ${ORIGIN}/scenarios'"
H="$("${CURL[@]}" -D - -o "${WORK}/index.html" "${ORIGIN}/")"
check "the app is served over HTTP/2 and TLS" "echo \"\$H\" | grep -q '^HTTP/2 200'"
for header in "strict-transport-security: max-age=31536000" "x-content-type-options: nosniff" \
  "x-frame-options: DENY" "referrer-policy: no-referrer" "cross-origin-opener-policy: same-origin" \
  "content-security-policy: default-src 'self'; script-src 'self'" "cache-control: no-cache" \
  "permissions-policy: camera=()"; do
  check "header ${header}" "echo \"\$H\" | grep -qiF \"${header}\""
done
check "the server does not name its version" "! echo \"\$H\" | grep -qi '^server: nginx/'"
check "index.html has no inline script" "! grep -q '<script>' '${WORK}/index.html'"
check "a page path falls back to the app" "[ \"\$(code '${ORIGIN}/scenarios/anything')\" = 200 ]"
ASSET="$(grep -o '/assets/[^"]*\.js' "${WORK}/index.html" | head -1)"
H="$("${CURL[@]}" -D - -o /dev/null "${ORIGIN}${ASSET}")"
check "hashed files are cached for a year" \
  "echo \"\$H\" | grep -qi 'cache-control: public, max-age=31536000, immutable'"
check "files are compressed when asked" \
  "\"\${CURL[@]}\" -H 'Accept-Encoding: gzip' -D - -o /dev/null '${ORIGIN}${ASSET}' | grep -qi 'content-encoding: gzip'"
check "source maps are not served" "[ \"\$(code '${ORIGIN}${ASSET}.map')\" = 404 ]"
for path in /metrics /docs /redoc /openapi.json; do
  check "${path} is not served" "[ \"\$(code '${ORIGIN}${path}')\" = 404 ]"
done
check "an invented HTTP method is refused by the web server" \
  "[ \"\$(code -X INVENTED '${ORIGIN}/health')\" = 405 ]"
HOSTPORT="${ORIGIN#https://}"
[[ "${HOSTPORT}" == *:* ]] || HOSTPORT="${HOSTPORT}:443"
check "TLS 1.2 without forward secrecy is refused" \
  "! openssl s_client -connect '${HOSTPORT}' -servername '${HOST}' -tls1_2 -cipher AES128-GCM-SHA256 < /dev/null 2> /dev/null | grep -q 'Cipher is AES128-GCM-SHA256'"
check "TLS 1.2 with forward secrecy is accepted" \
  "openssl s_client -connect '${HOSTPORT}' -servername '${HOST}' -tls1_2 < /dev/null 2> /dev/null | grep -Eq 'Cipher is ECDHE-'"

# --- The API through the web server ---------------------------------------------------------
check "liveness answers" "\"\${CURL[@]}\" '${ORIGIN}/health' | grep -q '\"status\":\"ok\"'"
check "readiness says ready" "\"\${CURL[@]}\" '${ORIGIN}/health/ready' | grep -q '\"status\":\"ready\"'"
check "the API refuses a request without a session" "[ \"\$(code '${ORIGIN}/api/v1/network')\" = 401 ]"
H="$("${CURL[@]}" -D - -o /dev/null "${ORIGIN}/api/v1/network")"
check "API answers carry HSTS and the web server's request ID" \
  "echo \"\$H\" | grep -qi 'strict-transport-security' && echo \"\$H\" | grep -Eqi '^x-request-id: [0-9a-f]{32}'"
BODY="$(python3 -c 'import json,sys; print(json.dumps({"email": sys.argv[1], "password": open(sys.argv[2]).read().strip()}))' "${EMAIL}" "${PASSWORD_FILE}")"
# The password goes to curl on its standard input, never as an argument (visible to `ps`).
H="$(printf '%s' "${BODY}" | "${CURL[@]}" -D - -o /dev/null -H "Origin: ${ORIGIN}" -H 'Content-Type: application/json' --data-binary @- "${ORIGIN}/api/v1/auth/login")"
COOKIE="$(echo "$H" | grep -i '^set-cookie:' | sed -E 's/^[Ss]et-[Cc]ookie: ([^;]*).*/\1/' | tr -d '\r')"
SETCOOKIE="$(echo "$H" | grep -i '^set-cookie:')"
check "signing in sets a __Host- cookie: Secure, HttpOnly, SameSite=Lax, Path=/" \
  "echo \"\$SETCOOKIE\" | grep -qi '__Host-rumin_session=' && echo \"\$SETCOOKIE\" | grep -qi 'secure' && echo \"\$SETCOOKIE\" | grep -qi 'httponly' && echo \"\$SETCOOKIE\" | grep -qi 'samesite=lax' && echo \"\$SETCOOKIE\" | grep -qi 'path=/'"
check "the sign-in answer is not cached" "echo \"\$H\" | grep -qi 'cache-control: no-store'"
check "signed in, the API answers" "[ \"\$(code -H \"Cookie: \${COOKIE}\" '${ORIGIN}/api/v1/network')\" = 200 ]"
check "a change sent from another site is refused" \
  "[ \"\$(code -H \"Cookie: \${COOKIE}\" -H 'Origin: https://evil.example' -H 'Content-Type: application/json' -d '{}' '${ORIGIN}/api/v1/analyst/sessions')\" = 403 ]"
check "a change sent from the site itself is accepted" \
  "[ \"\$(code -H \"Cookie: \${COOKIE}\" -H 'Origin: ${ORIGIN}' -H 'Content-Type: application/json' -d '{\"title\":\"Deployment check\"}' '${ORIGIN}/api/v1/analyst/sessions')\" = 201 ]"
head -c 200000 /dev/zero | tr '\0' 'a' > "${WORK}/large.json"
check "a body over 128 KiB is refused" \
  "[ \"\$(code -H \"Cookie: \${COOKIE}\" -H 'Origin: ${ORIGIN}' -H 'Content-Type: application/json' --data-binary @'${WORK}/large.json' '${ORIGIN}/api/v1/scenarios')\" = 413 ]"

WEB_ADDRESSES="$(docker inspect "$(container web)" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}')"
CLIENT="$("${CURL[@]}" -H "Cookie: ${COOKIE}" "${ORIGIN}/api/v1/audit-events?limit=5" | python3 -c 'import json,sys; print(json.load(sys.stdin)["items"][0]["client"] or "")')"
check "the API records the client's address, not the web server's (${CLIENT})" \
  "[ -n \"\${CLIENT}\" ] && ! echo \"\${WEB_ADDRESSES}\" | grep -qw \"\${CLIENT}\""
check "metrics are readable inside the stack by an administrator" \
  "\"\${COMPOSE[@]}\" exec -T api python -c \"import urllib.request as u; r=u.Request('http://127.0.0.1:8000/metrics', headers={'Cookie': '\${COOKIE}'}); assert 'rumin_security_events_total' in u.urlopen(r).read().decode()\""

# Last among the API checks: it spends this address's sign-in allowance.
CODES=""
for _ in $(seq 1 10); do
  CODES="${CODES} $(code -H "Origin: ${ORIGIN}" -H 'Content-Type: application/json' -d '{"email":"nobody@rumin.invalid","password":"not the password"}' "${ORIGIN}/api/v1/auth/login")"
done
check "rapid sign-in attempts are slowed (${CODES# })" "echo \"\${CODES}\" | grep -q 429"

# --- The containers -------------------------------------------------------------------------
check "API log lines are JSON with 32-hex request IDs" \
  "\"\${COMPOSE[@]}\" logs --no-log-prefix api 2>/dev/null | grep '\"http\"' | tail -1 | python3 -c 'import json,sys; assert len(json.loads(sys.stdin.read())[\"request_id\"]) == 32'"
check "the API runs as an unprivileged user" "[ \"\$(\"\${COMPOSE[@]}\" exec -T api id -u)\" = 10001 ]"
check "the web server runs as an unprivileged user" "[ \"\$(\"\${COMPOSE[@]}\" exec -T web id -u)\" = 101 ]"
check "the API's file system is read-only" "! \"\${COMPOSE[@]}\" exec -T api touch /app/written 2>/dev/null"
check "the web server's file system is read-only" \
  "! \"\${COMPOSE[@]}\" exec -T web touch /usr/share/nginx/html/written 2>/dev/null"
check "the API's database role is not a superuser" \
  "[ \"\$(\"\${COMPOSE[@]}\" exec -T db psql -U postgres -tAc \"SELECT rolsuper OR rolcreaterole OR rolcreatedb FROM pg_roles WHERE rolname = 'rumin'\")\" = f ]"
check "the database publishes no port" \
  "[ \"\$(docker inspect \"\$(container db)\" --format '{{json .HostConfig.PortBindings}}')\" = '{}' ]"

echo "passed ${pass}, failed ${fail}"
[[ "${fail}" -eq 0 ]]
