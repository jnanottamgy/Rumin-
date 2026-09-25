# Environment variables

One `.env` file at the repository root configures both applications; copy
[`.env.example`](../.env.example) to start. `.env` files are git-ignored. **Every variable
is optional**: the defaults run a local workspace on SQLite.

- The **backend** reads variables prefixed `RUMIN_`. Precedence, highest first: the process
  environment, then `backend/.env`, then `.env` at the repository root. Invalid values stop
  the API at start-up with a clear message rather than running misconfigured.
- The **frontend** build exposes only `VITE_`-prefixed variables to browser code. They end
  up in the JavaScript bundle and are therefore **public** — never put a secret in one.

## Backend

| Variable | Default | Meaning |
|---|---|---|
| `RUMIN_ENVIRONMENT` | `development` | `development`, `test` or `production`. Reported by `/api/v1/system` and in logs. **`production` refuses to start** on SQLite, with local or `http://` CORS origins, or with `RUMIN_SESSION_COOKIE_SECURE=false`, naming each problem; it turns `RUMIN_DOCS_ENABLED` off unless set, and makes session cookies `Secure` (Phase 10). |
| `RUMIN_DATABASE_URL` | `sqlite:///backend/rumin.db` (absolute path) | SQLAlchemy URL. PostgreSQL: `postgresql+psycopg://user:password@host:5432/db` (install the `postgres` extra). |
| `RUMIN_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed to call the API directly. `*` is rejected; origins must start with `http://` or `https://`. Credentials are never allowed. |
| `RUMIN_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` for the `app` loggers. Each request is logged as `METHOD path -> status (ms)` with its request ID. |
| `RUMIN_LOG_FORMAT` | `text` | `text`, or `json` for one JSON object per line (time, level, logger, request ID, message, the request's method, path, status and duration, any exception) for the app and uvicorn alike. The production image sets `json`. |
| `RUMIN_DOCS_ENABLED` | `true` (`false` in production unless set) | Serve `/docs`, `/redoc` and `/openapi.json`. |
| `RUMIN_MAX_REQUEST_BODY_BYTES` | `65536` | Larger request bodies are rejected with 413 (limits 1 KiB – 10 MiB). |
| `RUMIN_SCENARIO_EXECUTION_MODE` | `thread` | How Scenario Lab executions run: `thread` (on the bounded background pool; the request answers 202 at once) or `inline` (inside the request that creates them — the tests use it). |
| `RUMIN_SCENARIO_MAX_CONCURRENT` | `2` | Executions running at once in one API process (1 – 8). |
| `RUMIN_SCENARIO_MAX_QUEUED` | `8` | Executions waiting for a place (0 – 64); beyond that `POST …/executions` answers 429 and stores nothing. |
| `RUMIN_SCENARIO_TIMEOUT_SECONDS` | `20` | Time limit of one execution, checked between stages and models (1 – 120). |

### Data ingestion (Phase 2)

Read by the ingestion command line (`python -m app.ingestion`); the API never contacts a
provider. See [providers](data/providers.md).

| Variable | Default | Meaning |
|---|---|---|
| `RUMIN_WORLDBANK_BASE_URL` | `https://api.worldbank.org/v2` | The World Bank Indicators API. Must use `https://` (plain `http://` is accepted only for `localhost`, for a local test server). |
| `RUMIN_WORLDBANK_MIN_INTERVAL_SECONDS` | `1.0` | Minimum seconds between two World Bank requests (0.1 – 60). |
| `RUMIN_PROVIDER_TIMEOUT_SECONDS` | `20` | Seconds allowed for one response (1 – 120). |
| `RUMIN_PROVIDER_MAX_ATTEMPTS` | `4` | Attempts per request including the first (1 – 6), so by default at most 3 retries of temporary failures. |
| `RUMIN_MAX_IMPORT_FILE_BYTES` | `10485760` | Largest price file accepted (1 KiB – 100 MiB). |
| `RUMIN_STORE_SOURCE_BODIES` | `true` | Keep the exact bytes of every response and imported file (gzip). With `false`, only their SHA-256 and metadata are kept. |

Outbound requests honour the standard `HTTPS_PROXY` environment variable.

### AI Analyst (Phase 7)

Read by the API. None is needed: RUMIN's grounded composer answers by default, offline. See
[providers](analyst/providers.md) and [guardrails](analyst/guardrails.md).

| Variable | Default | Meaning |
|---|---|---|
| `RUMIN_ANALYST_PROVIDER` | `grounded` | `grounded` (RUMIN composes every answer; no language model) or `anthropic` (a Claude model through the official SDK, held to the same grounding check; RUMIN answers whenever it fails or is not ready). |
| `RUMIN_ANTHROPIC_API_KEY` | — | The API key for `anthropic`. **A secret**: never logged, never returned by the API. RUMIN reads only this variable: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` in the environment are ignored, and a set `ANTHROPIC_CUSTOM_HEADERS` stops the provider (RUMIN answers instead). |
| `RUMIN_ANALYST_MODEL` | — | The model to call. RUMIN writes no model identifier into its code: choose one when deploying (100 characters at most). |
| `RUMIN_ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Must use `https://` (plain `http://` only for `localhost`). |
| `RUMIN_ANALYST_THINKING` | `adaptive` | `adaptive` or `off`. |
| `RUMIN_ANALYST_MAX_TOKENS` | `4096` | Output tokens per model request (512 – 32,000). |
| `RUMIN_ANALYST_REQUEST_TIMEOUT_SECONDS` | `60` | Per model request (5 – 300). |
| `RUMIN_ANALYST_MAX_RETRIES` | `2` | Retries of a model request that failed transiently (a server error, overloaded, rate-limited, timed out or unreachable), by RUMIN and only while the turn's time allows (0 – 5). |
| `RUMIN_ANALYST_MAX_MODEL_REQUESTS` | `6` | Model requests per question (1 – 12). |
| `RUMIN_ANALYST_DAILY_TOKEN_BUDGET` | `2000000` | Input + output tokens a day across all questions; beyond it RUMIN answers (0 turns the model off). |
| `RUMIN_ANALYST_DEADLINE_SECONDS` | `90` | Time allowed for one question (5 – 300). |
| `RUMIN_ANALYST_MAX_TOOL_CALLS` | `12` | Tool calls per question (1 – 32). |
| `RUMIN_ANALYST_MAX_QUESTION_CHARS` | `2000` | Longest question accepted (100 – 8,000); longer ones get 422 and are not stored. |
| `RUMIN_ANALYST_MAX_TURNS_PER_SESSION` | `200` | Questions per conversation (1 – 1,000). |
| `RUMIN_ANALYST_EXECUTION_MODE` | `thread` | `thread` (the bounded pool; asking answers 202) or `inline` (inside the request; the tests use it). |
| `RUMIN_ANALYST_MAX_CONCURRENT` | `2` | Questions answered at once in one API process (1 – 8). |
| `RUMIN_ANALYST_MAX_QUEUED` | `8` | Questions waiting (0 – 64); beyond that asking answers 429 and stores nothing. |

### Accounts, sessions and metrics (Phase 10)

| Variable | Default | Meaning |
|---|---|---|
| `RUMIN_SESSION_COOKIE_NAME` | `rumin_session` | The session cookie's name (letters, digits, `_`, `-`). The production stack uses `__Host-rumin_session`, which browsers bind to the exact host, `https` and path `/`. |
| `RUMIN_SESSION_COOKIE_SECURE` | unset (on in production, off otherwise) | Send the cookie only over `https`. Production refuses `false`. |
| `RUMIN_SESSION_IDLE_MINUTES` | `120` | A session ends after this long without a request (5 – 1,440). |
| `RUMIN_SESSION_MAX_HOURS` | `12` | …and in any case this long after signing in (1 – 336). |
| `RUMIN_LOGIN_MAX_FAILURES` | `5` | Failed sign-ins for one account from one client address, within the lock window, before that address must wait for that account (3 – 20). The account's owner elsewhere is not affected. Counted in the API process's memory. |
| `RUMIN_LOGIN_LOCK_MAX_MINUTES` | `15` | That window, and how long an account-wide lock lasts (1 – 1,440). |
| `RUMIN_LOGIN_ACCOUNT_MAX_FAILURES` | `50` | Failed sign-ins for one account from anywhere, since its last successful sign-in, before the account itself is locked (10 – 100; NIST SP 800-63B allows at most 100). The count starts again when the lock ends. Stored in the database. |
| `RUMIN_LOGIN_CLIENT_MAX_FAILURES` | `20` | Failed sign-ins (and wrong current passwords) from one client address, within the window, before it must wait (5 – 1,000). Counted in the API process's memory; a successful sign-in does not clear it. |
| `RUMIN_LOGIN_CLIENT_WINDOW_SECONDS` | `600` | That window (60 – 86,400). |
| `RUMIN_METRICS_ALLOWED_CLIENTS` | empty | Comma-separated client addresses that may read `GET /metrics` without signing in (an internal scraper). Administrators can always read it. |

Behind a reverse proxy, the client address is the one the proxy passes in
`X-Forwarded-For`, trusted from the addresses in uvicorn's `FORWARDED_ALLOW_IPS` (the
production image runs uvicorn with `--proxy-headers`; see
[deployment](deployment.md#settings)). The production stack's own settings file is
[`deploy/production.env.example`](../deploy/production.env.example).

## Frontend

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Base URL of the API **as seen by the browser**. Empty means same-origin requests (recommended: the dev server proxies, and production should put both behind one origin). If set, add the web origin to `RUMIN_CORS_ORIGINS`. Public. |
| `RUMIN_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the Vite dev server forwards `/api`, `/health`, `/docs` and `/openapi.json`. Read by Node only; never reaches the browser. |

## Local PostgreSQL (`docker-compose.yml`)

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_USER` | `rumin` | Database user created by the container |
| `POSTGRES_PASSWORD` | `change-me-local-only` | Its password — for a local, disposable database only |
| `POSTGRES_DB` | `rumin` | Database created by the container |

## Tests and tooling

| Variable | Used by | Meaning |
|---|---|---|
| `RUMIN_TEST_DATABASE_URL` | backend `pytest` | Run the backend suite against this (empty, disposable) database instead of a temporary SQLite file. |
| `RUMIN_API_URL` | `npm run test:integration` | The running API the frontend integration suite calls, e.g. `http://127.0.0.1:8765`. |
| `RUMIN_SMOKE_PORT` | `scripts/smoke_test.sh` | Port for the temporary API (default `8765`). |
| `RUMIN_TEST_EMAIL`, `RUMIN_TEST_PASSWORD` | the integration and launch suites | The administrator the suites sign in as; `scripts/smoke_test.sh` and `scripts/e2e.sh` create one with a random password for each run. |
| `RUMIN_E2E_URL` | `npx playwright test` | The running RUMIN the launch suite opens (`scripts/e2e.sh` sets it; default `http://127.0.0.1:4173`). |
| `RUMIN_E2E_INSECURE` | the launch suite | `1` accepts a self-signed certificate (a local production stack). |
| `RUMIN_E2E_API_PORT`, `RUMIN_E2E_WEB_PORT` | `scripts/e2e.sh` | Ports for its temporary API and preview server (defaults `8766`, `4174`). |
| `RUMIN_EXTRA_CA` | `scripts/deployment_check.sh` | A CA bundle passed to the image builds as a BuildKit secret, for a network whose proxy re-signs TLS. Not kept in the images. |
| `RUMIN_BACKUP_DIR` | `scripts/backup.sh` | Where backups are written (default `backups/`, git-ignored). |

## Secrets

In production RUMIN has three secrets of its own — `POSTGRES_PASSWORD` (the API's database
role) and `POSTGRES_ADMIN_PASSWORD` (the `postgres` superuser) in `.env.production`
(git-ignored; keep it owner-only), and the TLS private key — and one optional one:
`RUMIN_ANTHROPIC_API_KEY`, for a Claude model to answer the AI Analyst's questions.
Sessions need no signing secret (tokens are random and stored hashed). It belongs in the backend's environment or the deployment's secret
store — never in `VITE_` variables, the database or the repository. It is held as a secret
value (never printed in settings, logs or errors), sent only to the configured Anthropic
base URL, and never returned by the API: the capabilities endpoint says only whether a model
is ready and, if not, which setting is missing. The World Bank needs no API key and price files
are local. The local PostgreSQL password above is a placeholder for a disposable development
database (and the CI job's password is for its throwaway database container); the
passwords the smoke test, the launch suite and the deployment check use are random, made
for one run. When providers that
need keys arrive (MoSPI is next), their keys follow the same rule
(`RUMIN_<PROVIDER>_API_KEY`). The HTTP layer strips credential-like query parameters from
every URL it logs or stores.
