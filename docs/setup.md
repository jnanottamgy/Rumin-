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
**and deletes all scenarios** (it never touches provider data); `--validate-only` checks
the file without touching the database.

### Financial data (Phase 2)

```bash
uv run python -m app.ingestion catalog              # the series catalogue: no network needed
uv run python -m app.ingestion run worldbank-wdi    # needs HTTPS access to api.worldbank.org
uv run python -m app.ingestion jobs                 # what ran, and how it went
```

`catalog` loads the *definitions* of the eleven World Bank series (nothing is fetched).
`run` retrieves them — two requests per series, one per second — and prints a summary with
the dataset's attribution; the Data Explorer (<http://127.0.0.1:5173/data>) then shows the
values with their source and freshness. Without internet access the run is recorded as
failed and the Data Explorer explains it; nothing else is affected. To import prices from a
file you are licensed to use, see [price files](data/price-files.md); for the pipeline and
troubleshooting, see [ingestion](data/ingestion.md).

### Knowledge graph (Phase 3)

```bash
uv run python -m app.graph build     # build (or rebuild) the graph from what is stored
uv run python -m app.graph status    # the latest build, and whether the sources changed since
```

The build needs no network: it reads the sample dataset, the series catalogue and any
imported instruments, and prints a validation report. Run it again after loading or
changing data; rebuilding unchanged sources changes nothing. The explorer is at
<http://127.0.0.1:5173/graph>. See [the knowledge graph](graph/README.md).

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
uv run python -m app.ingestion catalog
```

The credentials come from `POSTGRES_*` in `.env` (defaults shown). They are for a local,
disposable database only. Any PostgreSQL 16 server works equally well; the Docker file is a
convenience.

> The compose file was validated with `docker compose config`, but the image could not be
> pulled in the environment Phases 1 and 2 were built in (Docker Hub was not reachable). The
> PostgreSQL path itself was verified against a local PostgreSQL 16 server: migrations,
> seeding, ingestion and the full backend test suite pass. CI runs the backend tests on
> PostgreSQL 16.

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
| The Data Explorer says **"The series catalogue has not been loaded"** | Run `uv run python -m app.ingestion catalog` in `backend/`. |
| **"The last retrieval failed"** / every series `provider_unavailable` | The machine cannot reach `api.worldbank.org` (firewall, proxy or sandbox). Allow outbound HTTPS to it (`HTTPS_PROXY` is honoured) and run `make ingest` again. More in [ingestion](data/ingestion.md#troubleshooting). |
| `✗ Database error … run: make migrate` from an ingestion command | The schema is missing or older than the code: `uv run alembic upgrade head`. |
| The Knowledge Graph page says **"The knowledge graph has not been built yet"** | Run `uv run python -m app.graph build` in `backend/` (or `make graph`), then reload the page. |
| The Knowledge Graph page says **"The graph is older than its sources"** | Data changed after the last build. Rebuild it with `make graph`. On a running API the notice can take up to 30 seconds to appear; it clears as soon as a new build finishes. |
| `✗ Graph build #n … is still running` | Another build is in progress. Wait for it; a build whose process died is closed automatically after an hour. |
| Start again from scratch | Stop the API, delete `backend/rumin.db`, then migrate, seed, load the catalogue and build the graph again. |
