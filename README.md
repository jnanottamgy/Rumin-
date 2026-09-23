# RUMIN

**Financial intelligence and economic simulation.** RUMIN maps how companies, industries,
countries and economic variables connect, lets you define scenarios on that network, and
labels everything it shows as one of five kinds of knowledge: observation, assumption,
scenario input, simulated output or uncertainty.

> **Status: Phase 1 — foundation and system architecture.** This build contains the
> platform's skeleton: API, database, domain model, an interactive 2D financial network, a
> Scenario Lab that saves *inputs only*, and honest placeholders for what comes later.
>
> - The sample data is **illustrative**. Companies are fictional; countries, ISIC
>   industries and economic-variable definitions are real concepts with references. There
>   are **no prices, financial figures or time series** in the database.
> - There is **no simulation engine** (Phase 4) and **no AI analyst** (Phase 7). Nothing in
>   the product presents a forecast or a simulated result.
> - There is **no authentication** yet (Phase 10). Run it locally only.
>
> Nothing in RUMIN is investment advice.

## What this build contains

| Module | State | What works |
|---|---|---|
| Landing page | Available | What RUMIN is, the five kinds of knowledge, what exists in this build, the roadmap |
| Overview (dashboard) | Available | Live workspace figures from the API, network preview, recent drafts, system status |
| Financial Universe | Available (2D) | Interactive network: selection with highlighting and dimming, hover details, search, filters, legend, pan/zoom, deep links, keyboard access, table view |
| Scenario Lab | Foundation | Named drafts with variable changes, validated against published limits; saved as drafts, **not simulated** |
| AI Analyst | Planned (Phase 7) | A page explaining what it will do; no model is connected and no requests are made |
| System & settings | Available | API, database, migration and dataset status; capabilities; theme and motion preferences |
| REST API | Available | Versioned (`/api/v1`), validated, consistent errors, OpenAPI docs |

## Quick start

Prerequisites: **Python 3.11+** with [uv](https://docs.astral.sh/uv/), **Node.js 22.22+**
with npm. Docker is optional (only for a local PostgreSQL).

```bash
cp .env.example .env    # optional: the defaults work for local development
make install            # backend (uv) and frontend (npm) dependencies
make migrate            # create the SQLite database (backend/rumin.db)
make seed               # load the illustrative sample dataset
make backend            # terminal 1 → API on http://127.0.0.1:8000 (docs: /docs)
make frontend           # terminal 2 → web client on http://127.0.0.1:5173
```

Without `make` (e.g. on Windows), run the same commands directly:

```bash
# Backend — in backend/
uv sync --extra dev
uv run alembic upgrade head
uv run python -m app.db.seed
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
| Create a migration | — | `uv run alembic revision --autogenerate -m "describe change"` (backend/) |
| Load sample data | `make seed` | `uv run python -m app.db.seed` (backend/) |
| Validate the dataset only | — | `uv run python -m app.db.seed --validate-only` |
| Replace loaded data | — | `uv run python -m app.db.seed --reset` (also deletes scenarios) |
| All unit and API tests | `make test` | `uv run pytest` (backend/), `npm test` (frontend/) |
| End-to-end smoke test | `make smoke` | `scripts/smoke_test.sh` |
| Lint and format checks | `make lint` | `uv run ruff check . && uv run ruff format --check .`, `npm run lint` |
| Type checks | `make typecheck` | `uv run mypy app tests`, `npm run typecheck` |
| Everything CI runs | `make check` | — |
| Production build (web) | — | `npm run build` (frontend/) → `frontend/dist/` |
| Regenerate the API contract | `make openapi` | `uv run python -m app.openapi_export` (backend/) |
| Regenerate frontend API types | `make api-types` | `npm run generate:api` (frontend/) |
| Local PostgreSQL | `make db-up` / `make db-down` | `docker compose up -d db` |

### Using PostgreSQL

SQLite is the default for development; PostgreSQL is the production target. Both run the
same migrations and the same test suite.

```bash
make db-up                                  # PostgreSQL 16 on 127.0.0.1:5432
cd backend && uv sync --extra dev --extra postgres
export RUMIN_DATABASE_URL=postgresql+psycopg://rumin:change-me-local-only@localhost:5432/rumin
uv run alembic upgrade head && uv run python -m app.db.seed
```

Run the backend tests against PostgreSQL with an empty, disposable database:
`RUMIN_TEST_DATABASE_URL=postgresql+psycopg://… uv run pytest`.

## Repository layout

```
backend/            FastAPI application, SQLAlchemy models, Alembic migrations, pytest suite
  app/api/          HTTP routes (health, /api/v1/…)
  app/core/         settings, logging, errors, middleware
  app/data/         the illustrative sample dataset (JSON)
  app/db/           engine/session, column types, validated seed loader
  app/domain/       enums, relationship-type registry, scenario rules
  app/models/       ORM models
  app/schemas/      Pydantic request/response schemas (the API contract)
  app/services/     query and business logic
  migrations/       Alembic revisions
frontend/           React + TypeScript web client (Vite)
  src/app/          router, theme, module registry
  src/components/   shared UI primitives
  src/features/     network (model, layout, renderer, filters…) and scenarios
  src/pages/        one component per route
  tests/            unit and page tests; tests/integration runs against a live API
docs/               architecture, API, data model, testing, roadmap and more
  api/openapi.json  committed API contract (the frontend's types are generated from it)
scripts/            smoke_test.sh
```

## Documentation

- [Architecture](docs/architecture.md) and [technology decisions](docs/decisions.md)
- [Setup](docs/setup.md) and [environment variables](docs/environment.md)
- [API reference](docs/api.md) (interactive: `/docs` on a running API)
- [Data model](docs/data-model.md) and [data dictionary](docs/data-dictionary.md)
- [Design system](docs/design-system.md)
- [Testing](docs/testing.md)
- [Security](docs/security.md)
- [Known limitations](docs/known-limitations.md)
- [Roadmap](docs/roadmap.md)
- [Phase 1 report](docs/phases/phase-1-report.md)

## Licence

No licence has been chosen yet. Until the owners add one, all rights are reserved.
