# Setup

This guide takes a fresh clone to a running RUMIN workspace. The short version is in the
[README](../README.md#quick-start).

## Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Python | 3.11 or newer | the API (`backend/`) |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | recent | Python dependencies and virtual environment (`backend/uv.lock`) |
| Node.js + npm | Node 22.22 or newer | the web client (`frontend/`) |
| Docker (optional) | with Compose | a local PostgreSQL (`docker-compose.yml`) |
| make (optional) | any | shortcuts in the `Makefile`; every target is also a plain command |

The versions this build was developed and tested with: Python 3.11, Node 22.22, npm 10,
PostgreSQL 16, Chromium (for the visual checks).

## 1. Configure (optional)

```bash
cp .env.example .env
```

One `.env` at the repository root serves both applications. Every variable is optional —
the defaults run a local workspace on SQLite. See [environment.md](environment.md).

## 2. Backend

```bash
cd backend
uv sync --extra dev                 # creates backend/.venv from uv.lock
uv run alembic upgrade head         # creates backend/rumin.db (SQLite)
uv run python -m app.db.seed        # loads the illustrative sample dataset
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check it:

```bash
curl http://127.0.0.1:8000/health          # {"status":"ok",…}
curl http://127.0.0.1:8000/health/ready    # 200 once migrated and seeded, otherwise 503
```

Interactive API documentation: <http://127.0.0.1:8000/docs> (Swagger UI) and `/redoc`.

The seed loader validates the dataset file before writing anything and is idempotent:
running it again with an unchanged file does nothing. `--reset` replaces the loaded data
**and deletes all scenarios**; `--validate-only` checks the file without touching the
database.

## 3. Frontend

```bash
cd frontend
npm ci
npm run dev                          # http://127.0.0.1:5173
```

The dev server proxies `/api`, `/health`, `/docs` and `/openapi.json` to
`RUMIN_API_PROXY_TARGET` (default `http://127.0.0.1:8000`), so the browser only ever talks
to one origin.

Production build: `npm run build` writes static files to `frontend/dist/`. Serve them with
any static web server that forwards `/api` and `/health` to the API (or set
`VITE_API_BASE_URL` at build time and allow that origin in `RUMIN_CORS_ORIGINS`).

## 4. PostgreSQL (optional)

SQLite needs no server and is the default. To develop or test against PostgreSQL — the
production target — start one locally:

```bash
docker compose up -d db              # PostgreSQL 16, bound to 127.0.0.1:5432
cd backend
uv sync --extra dev --extra postgres # adds the psycopg driver
export RUMIN_DATABASE_URL=postgresql+psycopg://rumin:change-me-local-only@localhost:5432/rumin
uv run alembic upgrade head
uv run python -m app.db.seed
```

The credentials come from `POSTGRES_*` in `.env` (defaults shown). They are for a local,
disposable database only. Any PostgreSQL 16 server works equally well; the Docker file is a
convenience.

> The compose file was validated with `docker compose config`, but the image could not be
> pulled in the environment Phase 1 was built in (Docker Hub was not reachable). The
> PostgreSQL path itself was verified against a local PostgreSQL 16 server: migrations,
> seeding and the full backend test suite pass. CI runs the backend tests on PostgreSQL 16.

## 5. Verify everything

```bash
make check    # lint, types, backend + frontend tests, OpenAPI snapshot
make smoke    # fresh database → live API → frontend integration suite
```

See [testing.md](testing.md).

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The web client says **"Could not reach the RUMIN API"** | The API is not running, or not on `RUMIN_API_PROXY_TARGET`. Start it (step 2) and press *Try again*. |
| **"No dataset is loaded"** | Run `uv run python -m app.db.seed` in `backend/`. |
| `/health/ready` returns **503** | The response lists which check failed: database unreachable, migrations not at head (`alembic upgrade head`), or no dataset (seed). |
| **CORS errors** in the browser console | Only happens when the web client calls the API cross-origin (`VITE_API_BASE_URL` set). Add the web origin to `RUMIN_CORS_ORIGINS`. |
| **413 Payload Too Large** | Request bodies are limited to `RUMIN_MAX_REQUEST_BODY_BYTES` (64 KiB). |
| `ModuleNotFoundError: psycopg` | Install the PostgreSQL extra: `uv sync --extra dev --extra postgres`. |
| Port 8000 or 5173 already in use | Pass another port: `uvicorn … --port 8001` and set `RUMIN_API_PROXY_TARGET`; `npm run dev -- --port 5174` (then add that origin to `RUMIN_CORS_ORIGINS` if you call the API cross-origin). |
| Start again from scratch | Stop the API, delete `backend/rumin.db`, then migrate and seed again. |
