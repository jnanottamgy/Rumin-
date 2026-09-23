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
| `RUMIN_ENVIRONMENT` | `development` | `development`, `test` or `production`. Reported by `/api/v1/system` and in logs. In Phase 1 it does not change behaviour by itself: production hardening such as `RUMIN_DOCS_ENABLED=false` is set explicitly. |
| `RUMIN_DATABASE_URL` | `sqlite:///backend/rumin.db` (absolute path) | SQLAlchemy URL. PostgreSQL: `postgresql+psycopg://user:password@host:5432/db` (install the `postgres` extra). |
| `RUMIN_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed to call the API directly. `*` is rejected; origins must start with `http://` or `https://`. Credentials are never allowed. |
| `RUMIN_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` for the `app` loggers. Each request is logged as `METHOD path -> status (ms)` with its request ID. |
| `RUMIN_DOCS_ENABLED` | `true` | Serve `/docs`, `/redoc` and `/openapi.json`. Set to `false` for a public deployment if the API surface should not be browsable. |
| `RUMIN_MAX_REQUEST_BODY_BYTES` | `65536` | Larger request bodies are rejected with 413 (limits 1 KiB – 10 MiB). |

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

## Secrets

Phase 1 has no secrets: no API keys, no third-party services, no authentication. The only
credential anywhere is the local PostgreSQL password above, which is a placeholder for a
disposable development database (and a CI-only password inside the CI job's throwaway
database container). When later phases add real credentials (data providers, an AI
provider, authentication), they belong in the deployment's secret store and in the
backend's environment — never in `VITE_` variables, never in the repository.
