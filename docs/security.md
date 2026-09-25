# Security

## Posture

RUMIN is a **multi-user application for one team** (Phase 10). People sign in with accounts
an administrator creates; the backend enforces three roles — *viewer*, *analyst*, *admin* —
and ownership on every route; a production deployment (Docker Compose, nginx with TLS and a
strict Content-Security-Policy, PostgreSQL on an internal network) is built and checked end
to end on one machine ([deployment](deployment.md)). **RUMIN has not had a formal,
independent security assessment (such as a penetration test) and has not run on a public
network.** The AI Analyst (Phase 7) and the accounts and deployment (Phase 10) were each
read by an independent review agent that tried to break them; the findings and fixes are
listed below. That is not a substitute for a formal assessment. What this means for a
launch is in the [readiness assessment](phases/phase-10-report.md#launch-readiness).

RUMIN holds **personal data**: accounts (names, e-mail addresses, password hashes), sessions
(token hashes), the security audit trail (client addresses), and whatever people type into
questions and scenarios — see [privacy](privacy.md). It also stores **third-party data under
licences** — World Bank indicators (CC BY 4.0) and any price files a user imports under
their own licence — together with the exact responses and files received. Respect those
licences when sharing a database or its exports.

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
  the Vite proxy, and in production the web server serves the app and the API from one
  origin, so the list is empty and CORS is not even exercised.
- **The web app's own responses** (production, nginx): a Content-Security-Policy that allows
  scripts, styles, fonts and connections from RUMIN's origin only (`default-src 'self';
  script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self';
  connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self';
  frame-ancestors 'none'` — no inline script, no `eval`), HSTS for a year, `nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy:
  same-origin` and a Permissions-Policy that turns off camera, microphone, location,
  payment and USB. `vite preview` sends the same policy, read from the same file, so the
  launch suite runs under it.
- **Request IDs** on every response and log line, for tracing incidents.

### Web client

- React escapes all rendered text; the code never injects raw HTML
  (`dangerouslySetInnerHTML` is not used).
- External links open with `rel="noopener noreferrer"`; reference URLs in datasets must be
  `https://` (the seed loader rejects anything else).
- **One cookie**, the session: `HttpOnly` (no script can read it), `SameSite=Lax`, `Secure`
  in production and there named `__Host-rumin_session` (bound to the exact host, `https`
  and path `/`). No analytics, no third-party requests: fonts are self-hosted, and served as
  files, never inlined (the policy allows no `data:` fonts). `localStorage` holds only
  preferences: theme, motion, the 3D page's view and the dismissed welcome card.
- Only `VITE_`-prefixed variables reach the bundle, and none is secret.

### Data ingestion (Phase 2)

- **No HTTP entry point.** Ingestion starts only from the command line, on the machine that
  holds the database. The API is read-only for data (`POST /api/v1/ingestion-jobs` answers
  405), so no client can make RUMIN call a provider or write data. Phase 10 kept it that
  way: starting a retrieval over HTTP, even for an administrator, is not offered.
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
  companies, [performance](graph/performance.md)). Since Phase 10 it needs a session, and
  the web server limits requests per address.
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

### Scenario Lab (Phase 5)

- **Nothing executable, nothing repaired.** A scenario is a typed specification: 1–10
  changes on known variables within their published limits (at most four decimal places),
  1–36 months, at most 10 models of known ids with at most 20 inputs and 20 assumptions
  each, at most 5 stress cases (a multiple above 0 and at most 10, or values within the
  variables' limits), names and notes of bounded length without control characters.
  Unknown fields are refused. Every figure is an exact decimal checked against the model's
  definition; nothing is clipped or filled in, and each problem is reported with its field.
- **Bounded execution.** Executions run on a thread pool of 2 with at most 8 waiting
  (`RUMIN_SCENARIO_MAX_CONCURRENT`, `RUMIN_SCENARIO_MAX_QUEUED`); a request beyond that is
  refused with **429** before anything is stored. Each execution has a time limit (20 s,
  `RUMIN_SCENARIO_TIMEOUT_SECONDS`) and can be cancelled; both are checked between stages
  and models, and a failed, cancelled or timed-out execution stores nothing but its state
  and reason. An execution interrupted by a server stop is marked failed at the next start.
  Previews, plans, sensitivity analyses (≤ 8 quantities, ≤ 7 points, ≤ 60 evaluations and a
  deadline) and comparisons (2–6 executions) are bounded in the same way.
- **History cannot be rewritten.** Versions are immutable; a save from a stale version is
  refused (409); an executed scenario cannot be deleted (409); executions, their model runs
  and results never change once final; the model runs are protected by restricting foreign
  keys. Verification re-executes from what an execution stored and stores nothing.
- **No outbound requests.** Planning and executing read the graph and stored observations
  from the database; nothing contacts a provider.
- **Compressed responses.** Responses over 1 KiB are gzip-compressed when the client accepts
  it. Reviewed with authentication (Phase 10): the session token travels only in the
  sign-in answer's `Set-Cookie` header and no response body carries a secret, so compression
  gives a length-based attack (BREACH) nothing to recover.

### Financial Intelligence (Phase 6)

- **Reads write nothing.** Every intelligence read computes its analysis from the store and
  changes no table. The only write is a stored analysis, `POST /intelligence/analyses`, and
  stored analyses are **append-only**: no code path updates or deletes one, and the API has no
  route that could (`DELETE` answers 405). Their hashes (`inputs_hash`, `result_hash`) let a
  reader check that a snapshot is unchanged.
- **Validated, bounded input.** Entity and variable keys are checked against the graph's key
  pattern (at most 128 characters); a key that is not a company, industry or economic
  variable is refused (422), an unknown one answers 404. Thresholds are exact decimals or
  integers matched by pattern, then checked against their documented bounds; every problem is
  reported with its field and nothing is clipped. A stored analysis takes at most 20
  thresholds, a label of at most 200 characters of plain text, and no unknown fields.
- **Bounded work.** The workspace reads the first 200 companies; values per series, revisions,
  executions per entity, graph changes and served histories each have a stated limit
  ([architecture](intelligence/architecture.md#bounds)). The one computation beyond reading,
  the model interpretation of an observed change, runs the stored scenario's models once per
  related series as an unstored preview, under the engine's own limits.
- **No language model and no outbound requests.** No text is generated: rules fill templates
  with computed values. Nothing contacts a provider or any external service. The entity
  brief is prepared for an analyst but sent nowhere by Financial Intelligence itself.

### AI Analyst (Phase 7)

The details are in [guardrails](analyst/guardrails.md); in short:

- **The model cannot act.** Whoever drafts an answer reaches RUMIN only through an
  **allowlist** of 17 tools, each with a strict input model (unknown fields refused, keys
  matched by pattern, bounded numbers and lists). 16 read; `preview_scenario` computes a
  what-if that is **never stored**. There is no SQL, code, shell, file, network or write
  tool. Tools call the same services the pages call, with the same limits, so the Analyst
  reaches nothing the API does not already serve. Every call carries an access context for
  Phase 10's per-user checks.
- **Nothing unsupported is shown.** Every answer passes the grounding check (every figure,
  date, period and version in the evidence its sentence cites, as a value of its own kind —
  a percentage, percentage points, an amount in its currency; anything that looks like a
  figure but cannot be read exactly fails; citations exist; no predictive, causal or
  advisory phrasing). A language model's draft that fails is discarded and RUMIN answers
  instead; a part of RUMIN's own draft that fails is withheld. Follow-up questions are checked
  before they are offered. A tool's arguments are never copied into evidence, so a model
  cannot write the evidence it cites.
- **Prompt injection.** Questions carrying instructions aimed at the Analyst (to ignore its
  rules, reveal its prompt or configuration, act as another system, or containing SQL or
  shell fragments) are declined before any tool runs, also when written in full-width
  letters or with invisible characters. Stored text reaches a model only as data inside a
  tool result, every string of it cleaned first: invisible characters (control,
  zero-width, bidirectional, tag) removed, length capped, instruction-like text withheld. The
  model's own answer is validated against its schema and cleaned of invisible characters.
- **The key.** `RUMIN_ANTHROPIC_API_KEY` is a secret value in the settings (never printed,
  and left out of the provider configuration's `repr`), sent only to the configured base URL
  (`https://`, or `http://` to this machine only, with the host parsed), never logged, never
  stored, never returned: the capabilities endpoint says only whether a model is ready and
  which setting is missing. RUMIN passes its own key, base URL, timeout and retry settings to the SDK, so the
  process environment's `ANTHROPIC_*` variables are never used; if `ANTHROPIC_CUSTOM_HEADERS`
  is set, the provider refuses to start rather than send headers RUMIN did not choose. Tests
  prove each of these.
- **Bounded work and cost.** Question length (2,000 characters by default), questions per
  conversation (200), one pending question per conversation, a bounded pool (2 answering, 8
  waiting; 429 beyond, before anything is stored), a deadline per question (90 s) that every
  model request's timeout and retries respect, tool calls per question (12, counting calls
  to tools that do not exist), tool arguments (4,000 characters), a time limit per tool
  call, model requests per question (6), output tokens per request (4,096) and model tokens
  per day (2,000,000, cached tokens included; beyond it RUMIN answers without the model). A
  turn that fails in any way ends *failed*; one left pending by a stopped process expires.
- **Privacy.** Conversations are stored so they can be reopened, and deleted with everything
  in them. Logs record ids, intents, tool names, statuses, counts, tokens and timings, never
  the question, the answer or a secret (a test reads the logs of a turn). A failed database
  statement is logged without its parameters, and the SDK's debug logging is held at
  warnings. A failed turn stores a fixed message; the stack trace goes only to the server log.
- **The browser.** Answers are rendered as text, never as HTML. Links in answers are
  followed only when, resolved as the browser would resolve them, they stay on RUMIN's own
  origin (`//host`, `/\host` and links with tabs or line breaks are not followed). A what-if handed to the Scenario Lab
  travels in the router's state (not the URL), is checked for shape before use, and is never
  saved without the person's action.
- **No model is called unless configured.** The default provider makes no outbound request.
  No request to a language model was made while RUMIN was built (no key was available).

#### The internal review of the AI Analyst

Before the Analyst was pushed, an independent review agent read its code and tried to break
it (the grounding check, the tools, the provider, the service, the API and the page). Every
finding was verified against the code and fixed, with a test:

| Finding | Severity | Fix |
|---|---|---|
| A model's search words were copied into evidence text, so it could plant a date, year or quotation and then cite it | Medium | Evidence holds only what RUMIN read; search evidence names the search, not its words |
| Figures in other forms were not read: `$5m`, `5B`, `5 trillion`, `INR900 crore`, `Rs.900 crore`, `.75%`, `5-45%`, `+/-99%`, `five hundred crore`, `½`, `5 000`, `(5)`, `–5`; `3%` could match a count of 3 | Medium | More forms read (currencies, scales, dash minus, accounting brackets); anything unreadable fails; figures match only values of their kind (`value_units`) |
| Follow-up questions from a model were shown unchecked | Medium | Checked like a question and like the answer's text; the rest dropped |
| A failure while storing an answer left the turn *running*, blocking its conversation; a malformed `submit_answer` or a NUL in the model's text could cause it | Medium | Every claimed turn ends completed or failed; abandoned turns expire; `submit_answer` is validated; invisible characters removed |
| A failed SQL statement's parameters (the question) reached the logs; two simultaneous questions answered 500 | Low | `hide_parameters`; 409 |
| A model request could outlive the turn's deadline (60 s × 3 attempts) | Low | Each attempt's timeout ends at the deadline; retries only while it allows; RUMIN's fallback has its own budget |
| Calls to unknown tool names were not counted against the limit; arguments were stored whatever their size | Low | Counted first; arguments capped |
| Some stored text reached the model uncleaned; format characters (tags, soft hyphens) were kept | Low | Every string of a tool result cleaned; every invisible character removed; screening on folded forms |
| `http://localhost.attacker.example` passed the base-URL check | Low | The URL is parsed; only this machine may use `http://` |
| The provider configuration's `repr` included the key | Low | Left out |
| `/\evil.example` passed the browser's internal-link check | Low | Links are resolved as the browser resolves them and must stay on RUMIN's origin |
| The token budget ignored cached tokens; several API processes would each apply their own limits | Info | Cached tokens counted; per-process limits documented ([limitations](analyst/limitations.md#system)) |

### 3D universe (Phase 8)

- **No new server surface.** The universe reads the graph API and stored executions through
  the existing read-only endpoints; Phase 8 changed no backend code, schema or route.
- **Untrusted text is never HTML.** Names written on the canvas are set with `textContent`
  on elements the page creates; tooltips and panels are React text. Node names come from the
  database and could hold markup; none is interpreted.
- **Bounded work in the browser.** The whole build is read only within the budget (≤ 500
  nodes, ≤ 2,500 edges, at most six requests, then a notice); neighbourhoods and paths keep
  the graph API's limits; names are capped at 36; the pixel ratio at 2; remembered
  positions at 6,000.
- **GPU resources are released.** On leaving the page every geometry, material and mesh is
  disposed and the WebGL context is released; a lost context falls back to the list.
- **A question handed to the Analyst is only text.** *Ask the Analyst about it* puts a
  drafted question in the Analyst's box through the router's state; it is read as a string,
  and nothing is sent until the reader sends it.

### Advanced analysis (Phase 9)

- **Strict, closed input.** Analysis bodies refuse unknown fields; the `kind` is one of two;
  distributions are data from a closed set (uniform, triangular, discrete) with decimal
  strings checked against each input's range and decimals before any draw; targets must be
  quantities the execution actually has. Nothing is parsed as an expression or evaluated.
- **Bounded work.** 100–2,000 draws, at most 8 quantities and 12 discrete values, a 7 × 7
  grid, deadlines (20 s, 10 s) after which nothing is stored, and **at most two analyses
  computing at once per API process**: a third request is refused with **429** before any
  work, so a burst cannot tie up every thread. The measured worst case is about 6 s.
- **Append-only and verifiable.** Analyses cannot be updated or deleted through the API;
  each stores its configuration and hashes, and *verify* recomputes and compares, storing
  nothing. A tampered stored request is detected (a test changes one and expects *not
  reproduced*).
- **Seeds.** The server chooses a seed with `secrets.randbits(53)` when none is given. The
  draws themselves use Python's Mersenne Twister, which is reproducible and **not
  cryptographic** — correct for simulation, never used for anything secret.
- **The register runs no user input.** `GET …/verification` runs fixed, hypothetical
  checks through the engine in memory; it takes only a model id and version.
- No dependency was added, and no schema or route lets a client change a stored result.

### Accounts, sessions and access (Phase 10)

- **Accounts are created by administrators**, never by self-registration: a name, an e-mail
  address, a role and a temporary password, which its owner must replace before any other
  request (403 `password_change_required`). Accounts are deactivated, never deleted, so
  authorship survives.
- **Passwords** are hashed with Argon2id (`argon2-cffi`'s defaults, RFC 9106's low-memory
  profile: three passes over 64 MiB, four lanes; a salt per hash), upgraded at the next
  sign-in if the parameters rise. The policy follows NIST SP 800-63B: 12 to 128 characters,
  no composition rules, common passwords and one's own e-mail address or name refused.
  Passwords are never logged, returned or accepted as command-line arguments.
- **Sessions**: 256 random bits in the cookie, stored only as their SHA-256 hash; a new token
  at every sign-in (no fixation); ended after 120 idle minutes and in any case after 12
  hours; ended at once by signing out, deactivation, *sign out everywhere*, and — for the
  other sessions — a password change. The account is read on every request, so a role
  change or deactivation applies to the next one.
- **Guessing is slowed** in layers: a client address that fails 20 times in 10 minutes must
  wait (wrong current passwords when changing a password count too); an address that fails 5
  times in 15 minutes **for one account** must wait for that account — its owner, signing in
  from anywhere else, is not locked out by someone else's guesses; an account that fails 50
  times from anywhere since its last successful sign-in is locked for 15 minutes (NIST SP
  800-63B's limit is 100), and its count starts again when the lock ends; the web server
  allows 10 sign-in requests a minute per address (burst 5). Failures are counted in one
  statement, so simultaneous guesses cannot overwrite each other's count, and a successful
  sign-in never clears the address's failures. A wrong password and an unknown account get
  one message, cost the same Argon2 work, and pass through the first two layers alike; only
  the account-wide lock, reached after 50 failures, answers differently for an existing
  account (known).
- **Roles and ownership are enforced by the backend on every route**, and a test walks the
  route table so a new route cannot be left open: a *viewer* reads the workspace and uses
  the Analyst; an *analyst* also creates and runs scenarios, simulations and analyses; an
  *admin* also manages people. Only a record's owner or an administrator changes it;
  **Analyst conversations are private to their owner, administrators included**. The last
  active administrator cannot be demoted or deactivated, even by two administrators demoting
  each other at the same moment (the administrators' rows are locked, and the count is
  checked again after the change). The interface only mirrors these rules (disabled
  controls say why), and it returns after signing in only to a page on RUMIN's own origin,
  resolved as the browser resolves a link.
- **API answers are never cached** (`Cache-Control: no-store`), so people, the audit trail
  and conversations do not stay in a shared browser's cache.
- **Cross-site requests**: a request that changes data (`POST`, `PUT`, `PATCH`, `DELETE`
  under `/api/`) is refused (403) when its `Origin` is not RUMIN's own or the browser marks
  it `Sec-Fetch-Site: cross-site`; `SameSite=Lax` and JSON-only bodies are further layers.
- **An audit trail** records every sign-in, failure, lock, sign-out and change to a person or
  their sessions, with the client address and request ID — never a password or token, and
  not the e-mail address typed for an unknown account. Administrators read it in *People*.

### Deployment and operations (Phase 10)

- **Production refuses development settings**: the API does not start on SQLite, with local
  or `http://` CORS origins, or with insecure cookies, and turns the API documentation off.
- **Containers**: unprivileged users (10001, 101), read-only file systems, every capability
  dropped, `no-new-privileges`; the database has no published port and sits on a network
  with no route out; logs are rotated.
- **The database role**: the API connects as `rumin`, which owns its database and nothing
  else — not a superuser, it cannot create roles or databases or run programs on the
  database server. The `postgres` superuser is used only inside the database container, for
  restores.
- **The web server** terminates TLS 1.2 (forward-secret AEAD suites only) and 1.3 over
  HTTP/2, redirects plain HTTP, sends the headers above, hides its version, refuses methods
  RUMIN does not answer, limits requests per address (20 a second with a burst of 60 on the
  API and the health probes, 64 connections), caps bodies at 128 KiB (the API's own limit is
  64 KiB), overwrites `X-Forwarded-For` and `X-Forwarded-Proto` with what it saw, adds a
  request ID, and serves neither `/metrics`, the API documentation nor source maps (the
  image contains none).
- **Metrics** (`/metrics`) answer administrators and listed scraper addresses only; labels are
  route templates and a fixed set of methods (anything else counts as `OTHER`), never paths,
  people or addresses, so a client cannot make them grow.
- **Logs** are JSON lines with the request ID; never a body, query string, cookie, password,
  token, question or answer. Control characters in a logged path or origin are escaped, so a
  request cannot forge a log line.
- **Backups** are owner-only files that hold everything, password hashes and the audit trail
  included: encrypt them and keep them off the host. A restore ends every session (sessions
  ended after the backup would otherwise come back).
- **CI** runs `pip-audit` on the locked Python dependencies, `npm audit` (high and critical)
  and gitleaks over the whole history on every push, with a narrow allowance for graph
  identifiers in API fixtures that the default rules mistake for keys.
- `scripts/verify_deployment.sh` checks a running stack from outside (43 checks, among them
  the TLS suites, the refused methods and the database role), passing passwords to `curl` on
  its standard input, never as arguments; the launch suite runs the built app under the
  production Content-Security-Policy.

#### The internal review of Phase 10

Before the phase was closed, an independent review agent read the accounts, sessions, access
checks, middleware, metrics, the web app's session handling and the deployment, and tried to
break them (it reproduced its first six findings on a throwaway database). Every finding was
checked against the code and fixed, with a test or a deployment check:

| Finding | Severity | Fix |
|---|---|---|
| The HTTP method a client sends became a metrics label kept for the life of the process, so invented methods (8 KB each, through nginx, on `/health`) grew memory and `/metrics` without bound | Medium | Unknown methods count as `OTHER`; nginx refuses them (405) and rate-limits the health probes |
| Failed sign-ins were counted with a read and a write, so simultaneous guesses overwrote each other's count and never reached the lock | Medium | One `UPDATE … RETURNING` counts each failure |
| The account lock refused even the right password and failures never decayed, so one request per lock period from one address kept any account (every administrator) locked | Medium | The lock that one address can cause now applies to that address only; the account-wide lock needs 50 failures from anywhere and its count restarts when it ends |
| A successful sign-in cleared the address's failures, so an insider could interleave sign-ins with guesses at other accounts | Low | Only that account's window from that address is cleared |
| The return-after-sign-in guard allowed tabs and line breaks, which URL parsers drop: `/<tab>/evil.example` became a link to another site | Low | `next` is resolved as a browser resolves a link and kept only on RUMIN's origin |
| Text logs printed the decoded path, so `%0A` could forge a log line | Low | Control characters escaped in every logged path and origin |
| `verify_deployment.sh` passed the administrator's password to `curl` as an argument | Low | Standard input, in both scripts |
| Two administrators demoting each other at the same moment could leave none | Low | Administrators' rows locked, the count checked again after the change |
| The API connected to PostgreSQL as a superuser | Low | A `rumin` role that owns only its database; a deployment check verifies it |
| TLS 1.2 accepted suites without forward secrecy | Low | Forward-secret AEAD suites only; deployment checks both ways |
| The System page and capability still said authentication was not implemented; API answers could be cached; a restore revived ended sessions; the dev proxy passed a client-chosen `X-Forwarded-For`; `Password1234!` passed the policy; the launch suite's output could reach the web image's build context | Info | Each corrected (the policy now refuses a common word or one's own name wrapped in digits and symbols) |

It also confirmed as sound: every `/api/v1` router but signing in is protected and the
route-walking test holds; writes check role and ownership; no conversation can be read by
another person; tokens, cookies, expiry and revocation; the cross-site checks, including
`null` and sibling-subdomain origins; nginx overwriting the forwarded headers and refusing
`/metrics`; errors that echo no input; owner-only backups; non-root, read-only containers.

The bundled `security-review` skill was then run on the whole Phase 10 change. It reported no
High or Medium vulnerability; its one Low candidate, scored 5 out of 10 by its own check (below
its bar of 8), was fixed anyway: `verify_deployment.sh` put the administrator's session cookie
on `curl` and `docker compose exec` command lines and never signed it out. The cookie now stays
in a file only its owner can read, and the session is signed out when the script ends.

### Secrets and supply chain

- **Secrets**: in production, `POSTGRES_PASSWORD` and `POSTGRES_ADMIN_PASSWORD` in
  `.env.production` (git-ignored, kept owner-only), the TLS private key, and optionally
  `RUMIN_ANTHROPIC_API_KEY` for the Analyst's language model (above). Sessions need no
  signing secret: tokens are random and stored hashed. None is in the repository: `.env`
  files are git-ignored, `.env.example` and `deploy/production.env.example` hold placeholders
  only, no model identifier or key appears in code, fixtures or docs, and the World Bank
  needs no key. The local PostgreSQL password (`change-me-local-only`), the CI database
  password and the passwords the test suites generate are for disposable databases. Future
  provider keys belong in the backend environment or a secret store (see
  [environment](environment.md#secrets)).
- Dependencies are pinned by lock files (`backend/uv.lock`, `frontend/package-lock.json`)
  and installed with `--frozen` / `npm ci`. Phases 2 to 6 added no dependencies (HTTP, CSV,
  gzip, hashing, threads and exact decimals come from the Python standard library, response
  compression from Starlette; the charts, the graph algorithms, the layouts, the simulation
  engine, the Scenario Lab and the intelligence statistics are written in the project).
  **Phase 7 added one: the official `anthropic` SDK** (1.8.0), which brought `jiter`,
  `docstring-parser` and `sniffio` into the lock file; it is imported only by the Anthropic
  provider. When Phase 7 was built (2026-09-24), `pip-audit` (run through `uvx`, not a
  project dependency) found no known vulnerabilities in the locked Python dependencies, and
  `npm audit` reported none (the frontend's dependencies did not change). **Phase 8 added
  `three`** (0.186) to the frontend, with `@types/three` for development only; the renderer
  that imports it is a separate chunk loaded only by the 3D page. `npm audit` reported no
  vulnerability after the addition. **Phase 9 added none**: sampling, percentiles, exact
  binomial coverage and rank correlations are written in the project on the standard
  library (`random`, `secrets`, `decimal`, `fractions`). **Phase 10 added `argon2-cffi`**
  (25.1, with its bindings) for password hashing, and for development only
  `@playwright/test` and `playwright-core` (1.56.1, pinned to the pre-installed browser) and
  `@axe-core/playwright` (4.13.0) for the launch suite. Since Phase 10, `pip-audit`,
  `npm audit` and the secret scan run in CI on every push; they reported nothing on the
  last run. The images are built on tagged base images (`python:3.11-slim-bookworm`,
  `node:22.23.3-alpine`, `nginxinc/nginx-unprivileged:1.30.5-alpine`, `postgres:16-alpine`),
  not pinned by digest.
- CI runs with read-only repository permissions.

## Not yet in place

Deliberate gaps, listed so nobody assumes otherwise:

| Gap | Why it matters | When |
|---|---|---|
| A formal, independent security assessment (penetration test) | Internal reviews and automated checks are not one | Before any public launch |
| Single sign-on and multi-factor authentication | A stolen password is enough to sign in | Recommended before a public or limited external launch; the accounts are built so an identity provider can be added |
| E-mail password recovery | Administrators must reset passwords by hand | With a mail service |
| Several workspaces, separation between clients or engagements | Every member reads every scenario | One deployment per workspace until then ([privacy](privacy.md)) |
| Limits shared across API processes (throttles, queues, the Analyst's budget) | A second process would split them | The deployment runs one process (ADR 95) |
| Quotas and retention for stored records (scenarios, runs, analyses, conversations, audit events) per person | A signed-in person can fill the database | Next |
| Starting a retrieval or a graph build over HTTP, or editing relationships with review | Only the command line on the host can | Next |
| Base images pinned by digest, and image scanning | A changed base image would go unnoticed | Next |
| Memory limits on the containers | A leak or a burst could exhaust the host | Once memory use is measured under load |
| Protection beyond per-address limits (a WAF, DDoS protection) | Public exposure | With a public launch |
| Encryption at rest inside RUMIN | Disks and backups are the host's to encrypt | Host responsibility |

## Reporting a problem

Report suspected vulnerabilities privately to the repository owners rather than in a public
issue.
