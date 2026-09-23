# Security

## Posture

RUMIN is a **local, single-user application**. It has **no authentication or
authorisation**: anyone who can reach the API can read all stored data, create, change or
delete scenarios, and add simulation runs and analyses. Run it on your own machine (the dev servers bind to `127.0.0.1`) and
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

### Knowledge graph (Phase 3)

- **Read-only API.** The twelve graph endpoints are `GET` only; `POST`, `PUT`, `PATCH` and
  `DELETE` answer 405 (tested). Nothing over HTTP can create, change or delete a node,
  an edge or a build. Builds run only from the command line, one at a time; a build left
  `running` by a dead process is closed after an hour by the next one.
- **Validated parameters.** Node keys must match
  `^(country|…|market):[a-z0-9][a-z0-9_.-]{0,95}$` and edge keys `^e-[0-9a-f]{16}$` before
  the database is queried. Types, statuses, directions and severities are enumerations.
  Repeated filters are capped (9 node types, 18 edge types, 4 statuses). Search text is 1
  to 100 characters with control characters refused and LIKE wildcards escaped. Invalid
  input is rejected with 422, never clamped or passed on (tested with injection-shaped
  keys such as `Robert'); DROP TABLE graph_nodes;--`).
- **Bounded work per request.** Depth ≤ 3, ≤ 200 nodes per neighbourhood, paths ≤ 6 hops
  and ≤ 10 paths, a 5,000-node budget per path search, ≤ 50 components, pagination ≤ 500.
  Traversal queries touch only the current frontier, in chunks of at most 400 keys.
  Components, degree and metrics are read from what the last build stored. **One request
  reads whole tables**: the overview's freshness check reads and hashes every source
  record, at most once every 30 seconds per API process (about 6 s of work at 20,000
  companies, [performance](graph/performance.md)). Without rate limiting, this is the
  graph's largest cost an anonymous client can trigger.
- **Safe failures.** Errors use the standard envelope. A failed build rolls back its graph
  changes and stores only "The build failed with an internal error and changed nothing.
  Details are in the server log."; the stack trace goes to the log.
- **Validated relationship data.** Relationships are validated when the sample dataset is
  loaded (Phase 1), and again by the build: an edge of an unknown type, between the wrong
  kinds of node, pointing the wrong way, without evidence, with a status its type does not
  allow, or mixing fiction and fact is rejected and recorded as an issue
  ([construction](graph/construction.md#validation)).
- **Safe rendering.** The explorer renders text through React (no raw HTML anywhere in the
  client). A citation becomes a link only if it is an `http(s)` URL, and reference links are
  validated as `https://` when the dataset is loaded. The `focus`, `from` and `to` address
  parameters are checked against the node-key pattern before use.

### Simulation engine (Phase 4)

- **No executable input.** Models are Python code registered in the repository. There is
  no formula language, and nothing from a request is evaluated (no `eval`, `exec`,
  templates or expression parser). An equation changes only through a reviewed code
  change, and a change to a released model's definition fails CI (its pinned hash) and is
  refused at run time (409).
- **Validated input, never repaired.** Model IDs and versions match patterns; at most 40
  inputs, each ID matching `^[a-z][a-z0-9_]{1,63}$`; values are exact decimal strings of at
  most 128 characters or strict JSON numbers (a string is never coerced into a number);
  exponents, separators and symbols are refused. Ranges, decimal places, units and
  currency codes are checked against the model definition, and unknown inputs are
  refused. Nothing is clipped, rounded, converted or filled in silently: each problem is
  reported (422) with the field it concerns.
- **Numerical safety.** One exact-decimal context traps overflow, invalid operations and
  division by zero. Inputs are bounded by their definitions (amounts at most 10¹⁵), and
  every step value and output must stay below 10²⁰. A trapped error becomes a 422 with the
  reason, never a stack trace or a stored run.
- **Bounded work per request.** Horizon ≤ 36 months; propagation depth ≤ 4 and ≤ 500
  paths, simple paths only (a cycle cannot loop); contributions for ≤ 6 simultaneous
  changes (64 evaluations); sensitivity ≤ 8 inputs, ≤ 7 points each, ≤ 60 evaluations and
  10 seconds, refused whole when over a limit; lists paginated (≤ 500); the 64 KiB body
  limit. Validating and running read the graph's freshness, which shares the 30-second
  cache described above.
- **Append-only writes.** The API adds runs and sensitivity analyses; `PUT`, `PATCH` and
  `DELETE` on a run answer 405 (tested). Verification stores nothing. A run's model
  version and a sensitivity analysis's run are protected by restricting foreign keys.
- **No outbound requests.** Running a model never contacts a provider: a stored
  observation is read from the database, with its provenance.
- **Honest output.** Every input is labelled with what it is and where it came from, and
  every run carries the note that it is a deterministic calculation from stated inputs,
  not a forecast or investment advice.

### Secrets and supply chain

- **No secrets exist yet**, and none are in the repository: `.env` files are git-ignored,
  `.env.example` holds placeholders only, and the World Bank needs no key. The local
  PostgreSQL password (`change-me-local-only`) and the CI database password are for
  disposable databases. Future provider keys belong in the backend environment or a secret
  store (see [environment](environment.md#secrets)).
- Dependencies are pinned by lock files (`backend/uv.lock`, `frontend/package-lock.json`)
  and installed with `--frozen` / `npm ci`. **Phases 2, 3 and 4 added no dependencies**
  (HTTP, CSV, gzip, hashing and exact decimals come from the Python standard library; the
  charts, the graph algorithms, the layouts and the simulation engine are written in the
  project). When Phase 4 was built (2026-09-23), `npm audit` reported no known
  vulnerabilities, and `pip-audit` (run through `uvx`, not a project dependency) found
  none in the locked Python dependencies.
- CI runs with read-only repository permissions.

## Not yet in place

These are deliberate gaps, listed so nobody assumes otherwise:

| Gap | Planned |
|---|---|
| Authentication, user accounts, roles, per-user scenarios | Phase 10 |
| Inbound rate limiting and abuse protection (outbound provider requests are throttled) | Phase 10 (and at the reverse proxy) |
| An authenticated way to start ingestion or a graph build, or to edit relationships (with review and an audit trail) | Phase 10 |
| A formal security review | Before any hosted or multi-user use |
| TLS termination, deployment hardening, a Content-Security-Policy for the web client's HTML (it needs a hash for the small inline theme script in `index.html`) | Phase 10, with deployment |
| Audit log of changes | With authentication |
| Limits on how many simulation runs and analyses can be stored, and a retention policy for them | With authentication (Phase 10) |
| Automated dependency and secret scanning in CI (e.g. `pip-audit`, `npm audit`, secret scanning) | Next: cheap to add once the repository's CI is running |
| Backups and retention policy | With a production database |

## Reporting a problem

Report suspected vulnerabilities privately to the repository owners rather than in a public
issue.
