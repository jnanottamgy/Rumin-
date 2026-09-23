# Security

## Posture

Phase 1 is a **local, single-user foundation**. It has **no authentication or
authorisation**: anyone who can reach the API can read the reference data and create,
change or delete scenarios. Run it on your own machine (the dev servers bind to
`127.0.0.1`) and do not expose it to a network until Phase 10 adds access control.

It stores no personal data, no credentials, no market data and no third-party data values.
The only user-created content is scenario drafts (names, descriptions, notes, numbers).

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

### Secrets and supply chain

- **No secrets exist in Phase 1**, and none are in the repository: `.env` files are
  git-ignored, `.env.example` holds placeholders only. The local PostgreSQL password
  (`change-me-local-only`) and the CI database password are for disposable databases.
- Dependencies are pinned by lock files (`backend/uv.lock`, `frontend/package-lock.json`)
  and installed with `--frozen` / `npm ci`. `npm install` reported no known
  vulnerabilities when Phase 1 was built.
- CI runs with read-only repository permissions.

## Not yet in place

These are deliberate Phase 1 gaps, listed so nobody assumes otherwise:

| Gap | Planned |
|---|---|
| Authentication, user accounts, roles, per-user scenarios | Phase 10 |
| Rate limiting and abuse protection | Phase 10 (and at the reverse proxy) |
| TLS termination, deployment hardening, a Content-Security-Policy for the web client's HTML (it needs a hash for the small inline theme script in `index.html`) | Phase 10, with deployment |
| Audit log of changes | With authentication |
| Automated dependency and secret scanning in CI (e.g. `pip-audit`, `npm audit`, secret scanning) | Next: cheap to add once the repository's CI is running |
| Backups and retention policy | With a production database |

## Reporting a problem

Report suspected vulnerabilities privately to the repository owners rather than in a public
issue.
