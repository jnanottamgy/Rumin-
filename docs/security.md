# Security

## Posture

RUMIN is a **local, single-user application**. It has **no authentication or
authorisation**: anyone who can reach the API can read all stored data and create, change
or delete scenarios. Run it on your own machine (the dev servers bind to `127.0.0.1`) and
do not expose it to a network until Phase 10 adds access control. **This build has not had
a security review and is not production-secure.**

It stores no personal data and no credentials. Since Phase 2 it stores **third-party data
under licences** — World Bank indicators (CC BY 4.0) and any price files a user imports
under their own licence — together with the exact responses and files received. Respect
those licences when sharing a database or its exports.

## What is in place

### Input and output

- **Every input is validated** against an explicit schema before any code uses it: types,
  lengths, ranges, patterns (IDs), enumerations; request bodies with unknown fields are
  rejected; non-finite numbers (`NaN`, `Infinity`) and control characters in names are
  rejected; only JSON bodies are accepted.
- **Request bodies are capped** (`RUMIN_MAX_REQUEST_BODY_BYTES`, 64 KiB), enforced on the
  declared `Content-Length` and while streaming chunked bodies.
- **Errors never leak internals.** Every failure returns the same envelope with a generic
  message for unexpected errors; the stack trace goes to the server log under the request
  ID, not to the client.
- **SQL** goes through SQLAlchemy with bound parameters; the only literal SQL is constant
  (`SELECT 1` for readiness, SQLite pragmas).
- **Referential integrity** is enforced by the database (foreign keys, also on SQLite;
  CHECK and UNIQUE constraints), so bad data cannot be stored even by a buggy code path.

### HTTP

- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy:
  no-referrer` on every response; `Content-Security-Policy: default-src 'none';
  frame-ancestors 'none'` on API responses (the interactive docs pages get no CSP, as
  Swagger UI and ReDoc load their own assets; disable them with `RUMIN_DOCS_ENABLED=false`).
- **CORS**: only origins listed in `RUMIN_CORS_ORIGINS`; `*` is refused at start-up;
  credentials are never allowed. In development the browser uses the same origin through
  the Vite proxy, so CORS is not even exercised.
- **Request IDs** on every response and log line, for tracing incidents.

### Web client

- React escapes all rendered text; the code never injects raw HTML
  (`dangerouslySetInnerHTML` is not used).
- External links open with `rel="noopener noreferrer"`; reference URLs in datasets must be
  `https://` (the seed loader rejects anything else).
- No cookies, no analytics, no third-party requests: fonts are self-hosted. `localStorage`
  holds only the theme and motion preferences.
- Only `VITE_`-prefixed variables reach the bundle, and none is secret.

### Data ingestion (Phase 2)

- **No HTTP entry point.** Ingestion starts only from the command line, on the machine that
  holds the database. The API is read-only for data (`POST /api/v1/ingestion-jobs` answers
  405), so no anonymous client can make RUMIN call a provider or write data. An
  authenticated trigger comes with Phase 10.
- **No user-controlled URLs.** Provider URLs are built from validated parts only: indicator
  codes, ISO 3166-1 country codes and period formats are checked against patterns before
  they reach a URL. The base URL is configuration and must be `https://` (`http://` only
  for `localhost`, for test servers).
- **Bounded work per request.** Responses over 20 MB and results over 20 pages are refused;
  requests time out (20 s); retries are bounded (4 attempts) and a provider's `Retry-After`
  is honoured only up to 60 s; after 3 consecutive outages the run stops calling the
  provider.
- **Safe parsing.** JSON is parsed with numbers as `Decimal` (no float surprises); values
  are validated before storage; nothing from a response is executed or rendered as HTML.
- **Credentials never stored or logged.** URLs are redacted (`api_key`, `key`, `token`, …)
  before they are logged or stored in captures; job messages never contain response
  bodies or stack traces; imported files are recorded by name only (a full path can reveal
  a local user name).
- **Price files.** Size-limited (10 MB), read as UTF-8 by the standard `csv` module, with
  a strict column set; the manifest is validated with unknown fields rejected, `https://`
  links only, identifiers checked (ISIN check digit, MIC, currency); identifiers are never
  merged across instruments.
- **Stored bytes are not served.** The API returns capture metadata (hash, size, time,
  sanitised URL), never the stored bodies.

### Read API (Phase 2)

- Path and query identifiers are validated against strict patterns; enumerations are
  checked; free-text search is length-limited, control characters are refused, and LIKE
  wildcards are escaped.
- Pagination is capped (`limit` ≤ 500).
- Licence and terms links shown in the web client come from the validated catalogue or
  manifest (`https://` only) and open with `rel="noopener noreferrer"`.

### Secrets and supply chain

- **No secrets exist yet**, and none are in the repository: `.env` files are git-ignored,
  `.env.example` holds placeholders only, and the World Bank needs no key. The local
  PostgreSQL password (`change-me-local-only`) and the CI database password are for
  disposable databases. Future provider keys belong in the backend environment or a secret
  store (see [environment](environment.md#secrets)).
- Dependencies are pinned by lock files (`backend/uv.lock`, `frontend/package-lock.json`)
  and installed with `--frozen` / `npm ci`. **Phase 2 added no dependencies** (HTTP, CSV,
  gzip and hashing come from the Python standard library; the chart is hand-written SVG).
  `npm audit` reported no known vulnerabilities when Phase 2 was built; the Python
  dependencies were not audited with a tool (`pip-audit` was not available).
- CI runs with read-only repository permissions.

## Not yet in place

These are deliberate gaps, listed so nobody assumes otherwise:

| Gap | Planned |
|---|---|
| Authentication, user accounts, roles, per-user scenarios | Phase 10 |
| Inbound rate limiting and abuse protection (outbound provider requests are throttled) | Phase 10 (and at the reverse proxy) |
| An authenticated way to start ingestion | Phase 10 |
| A formal security review | Before any hosted or multi-user use |
| TLS termination, deployment hardening, a Content-Security-Policy for the web client's HTML (it needs a hash for the small inline theme script in `index.html`) | Phase 10, with deployment |
| Audit log of changes | With authentication |
| Automated dependency and secret scanning in CI (e.g. `pip-audit`, `npm audit`, secret scanning) | Next: cheap to add once the repository's CI is running |
| Backups and retention policy | With a production database |

## Reporting a problem

Report suspected vulnerabilities privately to the repository owners rather than in a public
issue.
