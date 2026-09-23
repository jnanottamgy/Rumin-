# RUMIN

**Financial intelligence and economic simulation.** RUMIN maps how companies, industries,
countries and economic variables connect, stores the historical data that describes them,
lets you define scenarios on that network, and labels everything it shows as one of five
kinds of knowledge: observation, assumption, scenario input, simulated output or
uncertainty.

> **Status: Phase 2 — financial data infrastructure** (on top of the Phase 1 foundation).
>
> - **Historical data, never live.** RUMIN retrieves a curated set of annual World Bank
>   indicators (World Development Indicators, CC BY 4.0) from the command line, and imports
>   daily prices only from CSV files **you are licensed to use**. It ships **no price data**
>   and connects to **no market feed**. Every value keeps its source, licence, retrieval time
>   and revision history.
> - The network's sample data is **illustrative**: its companies are fictional; countries,
>   ISIC industries and variable definitions are real concepts with references.
> - There is **no simulation engine** (Phase 4) and **no AI analyst** (Phase 7).
> - There is **no authentication** yet (Phase 10): run it locally only. For that reason the
>   API is read-only for data, and ingestion starts from the command line.
>
> Nothing in RUMIN is investment advice.

## What this build contains

| Module | State | What works |
|---|---|---|
| Landing page | Available | What RUMIN is, the five kinds of knowledge, what exists in this build, the roadmap |
| Overview (dashboard) | Available | Live workspace figures from the API, network preview, recent drafts, system and data status |
| Financial Universe | Available (2D) | Interactive network: selection, hover details, search, filters, legend, pan/zoom, deep links, keyboard access, table view |
| **Data Explorer** | Available (Phase 2) | Stored series and prices with their source, licence, freshness and quality; exact-value tables; accessible charts; revision history; ingestion runs |
| **Data ingestion** | Available (command line) | World Bank series (throttled, retried, validated, versioned) and licensed price-file import, each recorded as a job |
| Scenario Lab | Foundation | Named drafts with variable changes, validated against published limits; **not simulated** |
| AI Analyst | Planned (Phase 7) | A page explaining what it will do; no model is connected |
| System & settings | Available | API, database, migration and data status; capabilities; theme and motion preferences |
| REST API | Available | Versioned (`/api/v1`), validated, consistent errors, OpenAPI docs; data endpoints are read-only |

## Quick start

Prerequisites: **Python 3.11+** with [uv](https://docs.astral.sh/uv/), **Node.js 22.22+**
with npm. Docker is optional (only for a local PostgreSQL).

```bash
cp .env.example .env    # optional: the defaults work for local development
make install            # backend (uv) and frontend (npm) dependencies
make migrate            # create the SQLite database (backend/rumin.db)
make seed               # load the illustrative sample network
make catalog            # load the series catalogue (definitions only; nothing is fetched)
make ingest             # retrieve the World Bank series — needs internet access
make backend            # terminal 1 → API on http://127.0.0.1:8000 (docs: /docs)
make frontend           # terminal 2 → web client on http://127.0.0.1:5173
```

`make ingest` contacts `api.worldbank.org` (two requests per series, at most one per second). If
the provider cannot be reached, the run is recorded as failed and the Data Explorer says so;
nothing else is affected. To import prices from a file you are licensed to use, see
[Price files](docs/data/price-files.md).

Without `make` (e.g. on Windows), run the same commands directly:

```bash
# Backend — in backend/
uv sync --extra dev
uv run alembic upgrade head
uv run python -m app.db.seed
uv run python -m app.ingestion catalog
uv run python -m app.ingestion run worldbank-wdi
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend — in frontend/
npm ci
npm run dev
```

The Vite dev server proxies `/api` and `/health` to the backend, so the browser talks to
one origin and no API URL has to be configured.

## Commands

| Task | Command (from the repository root) | Direct equivalent |
|---|---|---|
| Install everything | `make install` | `uv sync --extra dev` (backend/), `npm ci` (frontend/) |
| Start the API | `make backend` | `uv run uvicorn app.main:app --reload` (backend/) |
| Start the web client | `make frontend` | `npm run dev` (frontend/) |
| Apply migrations | `make migrate` | `uv run alembic upgrade head` (backend/) |
| Load the sample network | `make seed` | `uv run python -m app.db.seed` (backend/) |
| Load the series catalogue | `make catalog` | `uv run python -m app.ingestion catalog` |
| Validate the catalogue only | — | `uv run python -m app.ingestion catalog --check` |
| Retrieve World Bank series | `make ingest` | `uv run python -m app.ingestion run worldbank-wdi [--series ID …] [--start 2000] [--end 2024]` |
| Import a licensed price file | — | `uv run python -m app.ingestion import-prices --manifest M.json --file prices.csv` |
| Blank price-file manifest | — | `uv run python -m app.ingestion manifest-template` |
| Recent ingestion runs | `make ingest-jobs` | `uv run python -m app.ingestion jobs`, then `… job <id>` |
| All unit and API tests | `make test` | `uv run pytest` (backend/), `npm test` (frontend/) |
| End-to-end smoke test | `make smoke` | `scripts/smoke_test.sh` |
| Lint and format checks | `make lint` | `uv run ruff check . && uv run ruff format --check .`, `npm run lint` |
| Type checks | `make typecheck` | `uv run mypy app tests`, `npm run typecheck` |
| Everything CI runs | `make check` | — |
| Production build (web) | — | `npm run build` (frontend/) → `frontend/dist/` |
| Regenerate the API contract | `make openapi` | `uv run python -m app.openapi_export` (backend/) |
| Regenerate frontend API types | `make api-types` | `npm run generate:api` (frontend/) |
| Local PostgreSQL | `make db-up` / `make db-down` | `docker compose up -d db` |

The ingestion commands exit with `0` (completed, possibly with warnings), `1` (failed),
`3` (partially failed), `130` (cancelled) or `2` (not started: bad input, another run in
progress, or the database is not migrated).

If a run fails, `make ingest-jobs` and `… job <id>` show which series failed and why. The
[troubleshooting table](docs/data/ingestion.md#troubleshooting) lists the usual causes and
fixes. Provider settings (base URL, pacing, timeouts, retries) are optional
[environment variables](docs/environment.md#data-ingestion-phase-2); no provider needs a key.

### Using PostgreSQL

SQLite is the default for development; PostgreSQL is the production target. Both run the
same migrations and the same test suite. Data values are exact on both (`NUMERIC(38, 18)`
on PostgreSQL, a canonical decimal string on SQLite).

```bash
make db-up                                  # PostgreSQL 16 on 127.0.0.1:5432
cd backend && uv sync --extra dev --extra postgres
export RUMIN_DATABASE_URL=postgresql+psycopg://rumin:change-me-local-only@localhost:5432/rumin
uv run alembic upgrade head && uv run python -m app.db.seed && uv run python -m app.ingestion catalog
```

Run the backend tests against PostgreSQL with an empty, disposable database:
`RUMIN_TEST_DATABASE_URL=postgresql+psycopg://… uv run pytest`.

## Repository layout

```
backend/            FastAPI application, SQLAlchemy models, Alembic migrations, pytest suite
  app/api/          HTTP routes (health, /api/v1/…)
  app/core/         settings, logging, errors, middleware
  app/data/         the illustrative sample network and the series catalogue (JSON)
  app/db/           engine/session, exact-decimal and UTC column types, seed loader
  app/domain/       enums, relationship-type registry, scenario rules
  app/ingestion/    providers, HTTP (throttling, retries), normalisation, quality rules,
                    persistence with revisions, job tracking, command line
  app/models/       ORM models
  app/schemas/      Pydantic request/response schemas (the API contract)
  app/services/     query and business logic
  migrations/       Alembic revisions
frontend/           React + TypeScript web client (Vite)
  src/app/          router, theme, module registry
  src/components/   shared UI primitives
  src/features/     network, scenarios, data (chart, tables, provenance, freshness)
  src/pages/        one component per route
  tests/            unit and page tests; tests/integration runs against a live API
docs/               architecture, API, data model, data pipeline, testing, roadmap and more
  api/openapi.json  committed API contract (the frontend's types are generated from it)
scripts/            smoke_test.sh
```

## Documentation

- [Architecture](docs/architecture.md) and [technology decisions](docs/decisions.md)
- [Setup](docs/setup.md) and [environment variables](docs/environment.md)
- [API reference](docs/api.md) (interactive: `/docs` on a running API)
- [Data model](docs/data-model.md) and [data dictionary](docs/data-dictionary.md)
- Financial data: [architecture](docs/data/architecture.md) ·
  [providers and licensing](docs/data/providers.md) ·
  [ingestion pipeline](docs/data/ingestion.md) · [data quality](docs/data/quality.md) ·
  [price files](docs/data/price-files.md)
- [Design system](docs/design-system.md)
- [Testing](docs/testing.md)
- [Security](docs/security.md)
- [Known limitations](docs/known-limitations.md)
- [Roadmap](docs/roadmap.md)
- Phase reports: [Phase 1](docs/phases/phase-1-report.md) ·
  [Phase 2 plan](docs/phases/phase-2-plan.md) · [Phase 2 report](docs/phases/phase-2-report.md)

## Licence

No licence has been chosen yet. Until the owners add one, all rights are reserved. Data
retrieved from providers remains under the provider's licence (for the World Bank: CC BY
4.0, with the attribution shown next to the data).
