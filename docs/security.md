# Security

## Posture

RUMIN is a **local, single-user application**. It has **no authentication or
authorisation**: anyone who can reach the API can read all stored data, create scenarios
and new versions of them, delete scenarios that were never executed, execute scenarios, add
simulation runs and analyses, and read, ask in and delete AI Analyst conversations (and,
when a language model is configured, spend its token budget). Run it on your own machine (the dev servers bind to `127.0.0.1`) and
do not expose it to a network until Phase 10 adds access control. **This build has not had
a formal security review and is not production-secure.** The AI Analyst (Phase 7) had an
internal review by an independent review agent before it was pushed; its findings and fixes
are listed [below](#the-internal-review-of-the-ai-analyst). That is not a substitute for a
formal review.

It stores no credentials, and no personal data beyond what a person types into an AI
Analyst question (kept with the conversation until it is deleted). Since Phase 2 it stores **third-party data
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
  it. RUMIN returns no secrets and has no sessions, so compression does not expose a secret
  to length-based attacks; this is to be reviewed with authentication (Phase 10).

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

### Secrets and supply chain

- **One optional secret**: `RUMIN_ANTHROPIC_API_KEY`, for the Analyst's language model
  (above). None is in the repository: `.env` files are git-ignored, `.env.example` holds
  placeholders only, no model identifier or key appears in code, fixtures or docs, and the
  World Bank needs no key. The local PostgreSQL password (`change-me-local-only`) and the CI
  database password are for disposable databases. Future provider keys belong in the
  backend environment or a secret store (see [environment](environment.md#secrets)).
- Dependencies are pinned by lock files (`backend/uv.lock`, `frontend/package-lock.json`)
  and installed with `--frozen` / `npm ci`. Phases 2 to 6 added no dependencies (HTTP, CSV,
  gzip, hashing, threads and exact decimals come from the Python standard library, response
  compression from Starlette; the charts, the graph algorithms, the layouts, the simulation
  engine, the Scenario Lab and the intelligence statistics are written in the project).
  **Phase 7 added one: the official `anthropic` SDK** (1.8.0), which brought `jiter`,
  `docstring-parser` and `sniffio` into the lock file; it is imported only by the Anthropic
  provider. When Phase 7 was built (2026-09-24), `pip-audit` (run through `uvx`, not a
  project dependency) found no known vulnerabilities in the locked Python dependencies, and
  `npm audit` reported none (the frontend's dependencies did not change).
- CI runs with read-only repository permissions.

## Not yet in place

These are deliberate gaps, listed so nobody assumes otherwise:

| Gap | Planned |
|---|---|
| Authentication, user accounts, roles, per-user scenarios | Phase 10 |
| Inbound rate limiting and abuse protection (outbound provider requests are throttled; scenario executions are bounded by the worker pool, 429 when full) | Phase 10 (and at the reverse proxy) |
| An authenticated way to start ingestion or a graph build, or to edit relationships (with review and an audit trail) | Phase 10 |
| A formal security review | Before any hosted or multi-user use |
| TLS termination, deployment hardening, a Content-Security-Policy for the web client's HTML (it needs a hash for the small inline theme script in `index.html`) | Phase 10, with deployment |
| Audit log of changes | With authentication |
| Limits on how many simulation runs, scenario versions, executions, sensitivity analyses, stored intelligence analyses and Analyst conversations can be stored, and a retention policy for them | With authentication (Phase 10) |
| Per-user Analyst conversations and token budgets; a budget shared across API processes | Phase 10 |
| Automated dependency and secret scanning in CI (e.g. `pip-audit`, `npm audit`, secret scanning) | Next: cheap to add once the repository's CI is running |
| Backups and retention policy | With a production database |

## Reporting a problem

Report suspected vulnerabilities privately to the repository owners rather than in a public
issue.
