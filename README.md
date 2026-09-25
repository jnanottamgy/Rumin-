# RUMIN

**Financial intelligence and economic simulation.** RUMIN maps how companies, industries,
countries and economic variables connect, stores the historical data that describes them,
connects every record it holds in a knowledge graph that says why each connection exists,
runs documented, versioned models on those connections with every step explained and
reproducible, and labels everything it shows as one of five kinds of knowledge:
observation, assumption, scenario input, simulated output or uncertainty.

> **Status: Phase 8 — 3D Financial Universe** (on top of the Phase 1 foundation, the Phase 2
> data infrastructure, the Phase 3 knowledge graph, the Phase 4 simulation engine, the Phase 5
> Scenario Lab, Phase 6 Financial Intelligence and the Phase 7 AI Analyst).
>
> - **The knowledge graph in three dimensions.** The 3D universe shows every record and
>   relationship the graph holds, each kind on its own layer — height says what a record is,
>   never how large or important it is — with the evidence behind every line one click away.
>   A stored scenario execution can be laid over it: what it changed, which relationships a
>   model propagated or only cited, which ones no model simulates, and its stored results. It
>   computes nothing, and a list view shows the same records without WebGL.
> - **Answers that cite their evidence.** The AI Analyst answers questions about RUMIN's
>   records in plain language, through 17 read-only tools over the services below, and every
>   figure it writes cites the record it came from, shown beside the answer. An answer, or a
>   part of one, whose figures are not in its evidence is not shown. By default RUMIN
>   composes every answer itself, with no language model; a Claude model can be configured
>   and is held to the same check. It does not forecast, hold live data or make investment
>   decisions, and it never saves or executes a scenario.
> - **Findings with their evidence, not summaries.** Financial Intelligence reads what RUMIN
>   stores and answers what changed, who is exposed and through which relationships, what
>   the stored simulations say and what drives them. Each answer is a finding from one of 19
>   documented rules, with the chain of observations, calculations, relationships and
>   simulations it rests on and an evidence grade (its weakest link, not a probability). No
>   text is generated, nothing is ranked or recommended, and nothing is a forecast.
> - **Scenarios are calculations, not forecasts.** The Scenario Lab asks *what happens if
>   something changes?* and answers with the models that apply — five narrow models, chosen
>   by what each declares and what the knowledge graph states — on figures you enter and
>   assumptions they state. It shows the modelled pathway from each change to each line,
>   stores every execution with its model runs and hashes, and re-executes any execution to
>   check it reproduces. No parameter has been estimated from data and no result has been
>   back-tested.
> - **The knowledge graph connects the records RUMIN holds, not the economy.** Every edge
>   has an evidence status (evidence-backed, analyst-created, model assumption or
>   unverified) and the records that explain it. No edge is a measured effect, a
>   correlation or a causal finding, and no edge has been empirically validated.
> - **Historical data, never live.** RUMIN retrieves a curated set of annual World Bank
>   indicators (World Development Indicators, CC BY 4.0) from the command line, and imports
>   daily prices only from CSV files **you are licensed to use**. It ships **no price data**
>   and connects to **no market feed**. Every value keeps its source, licence, retrieval time
>   and revision history.
> - The network's sample data is **illustrative**: its companies are fictional; countries,
>   ISIC industries and variable definitions are real concepts with references.
> - There is **no probabilistic simulation** (Phase 9): stress cases and sensitivity move
>   magnitudes, one at a time. A language model for the AI Analyst is optional and has **not
>   been verified against the live API** (no key was available where RUMIN was built).
> - There is **no authentication** yet (Phase 10): run it locally only. For that reason the
>   API is read-only for data and for the graph, scenario versions, executions and
>   simulation runs are append-only, and ingestion and graph builds start from the command
>   line.
>
> Nothing in RUMIN is investment advice.

## What this build contains

| Module | State | What works |
|---|---|---|
| Landing page | Available | What RUMIN is, the five kinds of knowledge, what exists in this build, the roadmap |
| Overview (dashboard) | Available | Live workspace figures from the API, network preview, the latest findings with their grades, recent scenarios, system and data status |
| Financial Universe | Available (2D network; **3D universe, Phase 8**) | The 2D network of the sample dataset: selection, hover details, search, filters, legend, pan/zoom, deep links, keyboard access, table view. The **3D universe** of the knowledge graph (`/universe/3d`): strata by kind, the graph's own marks, the whole build within a budget, neighbourhoods and paths, the node and evidence panels, overlays of stored executions, a keyboard model and a list twin, links with the 2D explorer, the Scenario Lab and the Analyst ([guide](docs/universe/README.md)) |
| **Knowledge Graph** | Available (Phase 3) | The graph of every record RUMIN holds (9 node types, 18 relationship types): aggregate map, search by name or code, neighbourhoods on a radial layout, step-by-step expansion, filters by type and evidence, the evidence behind every edge, shortest paths, history, table view |
| **Graph build** | Available (command line) | Builds the graph from the stored records with entity resolution (flag, never merge), 26 validation rules and a validation report; rebuilding unchanged sources changes nothing |
| **Data Explorer** | Available (Phase 2) | Stored series and prices with their source, licence, freshness and quality; exact-value tables; accessible charts; revision history; ingestion runs |
| **Data ingestion** | Available (command line) | World Bank series (throttled, retried, validated, versioned) and licensed price-file import, each recorded as a job |
| **Simulation** | Preview (Phase 4) | The airline fuel-cost model: inputs labelled by kind of knowledge and checked on the server; results with the pathway through the knowledge graph, month-by-month figures, the accounting bridge, Shapley contributions, a sensitivity tornado, every calculation step, and provenance with a reproducibility check; stored runs reopened and varied |
| **Simulation engine** | Available (API) | Five versioned, hashed models (airline fuel cost, foreign-currency revenue and costs, floating-rate interest, crude- and gas-linked costs); exact decimals; timed changes; propagation only along confirmed graph relationships; append-only runs with explanations, provenance and verification; one-at-a-time sensitivity |
| **Financial Intelligence** | Available (Phase 6) | A ledger of findings from 19 documented rules, each opening into its evidence chain and grade; observed changes, revisions, trends, volatility and unusual moves against configurable thresholds; exposure through validated graph relationships (a companies × variables matrix); drivers of simulated results from stored contributions; model interpretation of observed changes; dossiers per company and industry; a structured brief for an analyst; stored, fingerprinted analyses that say when they are stale ([guide](docs/intelligence/README.md)) |
| **Scenario Lab** | Available (Phase 5) | Templates built on implemented models; versioned scenarios; a plan saying which models apply and why; a live preview; background executions with recorded stages; the modelled pathway with graph context kept apart; baseline against scenario; months with a replay; stress cases; sensitivity; *what caused this?*; history, reproducibility checks and comparisons ([guide](docs/scenario-lab/README.md)) |
| **AI Analyst** | Available (Phase 7) | Questions answered from RUMIN's records through 17 allowlisted, read-only tools; every figure cited and checked against its evidence, sources shown in a margin beside the answer; tables, series charts, relationship paths and scenario cards; what-ifs previewed (never stored) and handed to the Scenario Lab; follow-ups and clarifications; conversations kept, exported or deleted. RUMIN's grounded composer answers by default; a Claude model is optional ([guide](docs/analyst/README.md)) |
| System & settings | Available | API, database, migration and data status; capabilities; theme and motion preferences |
| REST API | Available | Versioned (`/api/v1`), validated, consistent errors, OpenAPI docs, compressed responses; data and graph endpoints are read-only; intelligence reads write nothing; scenario versions, executions, simulation runs and stored analyses are append-only; the Analyst writes only its own conversations |

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
make graph              # build the knowledge graph from what is stored (no network)
make backend            # terminal 1 → API on http://127.0.0.1:8000 (docs: /docs)
make frontend           # terminal 2 → web client on http://127.0.0.1:5173
```

`make ingest` contacts `api.worldbank.org` (two requests per series, at most one per second). If
the provider cannot be reached, the run is recorded as failed and the Data Explorer says so;
nothing else is affected. To try the Scenario Lab, open <http://127.0.0.1:5173/scenarios>,
start from a template, enter your (hypothetical) company figures and **Execute**
([more](docs/setup.md#scenario-lab-phase-5)). Then open <http://127.0.0.1:5173/intelligence> to
see what RUMIN can say about the workspace and each company, finding by finding, with the
evidence each one rests on ([more](docs/setup.md#financial-intelligence-phase-6)). To try one model on its own, open
<http://127.0.0.1:5173/simulation>, choose **Fill a hypothetical example** and **Run
simulation** ([more](docs/setup.md#simulation-phase-4)). To import prices from a file you are licensed to use, see
[Price files](docs/data/price-files.md).

Without `make` (e.g. on Windows), run the same commands directly:

```bash
# Backend — in backend/
uv sync --extra dev
uv run alembic upgrade head
uv run python -m app.db.seed
uv run python -m app.ingestion catalog
uv run python -m app.ingestion run worldbank-wdi
uv run python -m app.graph build
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
| Build the knowledge graph | `make graph` | `uv run python -m app.graph build` (backend/) |
| Graph status (current or stale) | `make graph-status` | `uv run python -m app.graph status` |
| What a build would do (writes nothing) | — | `uv run python -m app.graph validate` |
| Recent builds, one build's report | — | `uv run python -m app.graph builds`, `… report [BUILD]` |
| Score the AI Analyst on its evaluation set | — | `uv run python -m app.analyst.evaluation [--json]` (backend/) |
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

The graph commands exit with `0` (success, warnings allowed), `1` (the build failed, or
`validate` found something a build would reject) or `2` (nothing could run: another build
is running, the database is not migrated, or the requested build does not exist).

If a run fails, `make ingest-jobs` and `… job <id>` show which series failed and why. The
[troubleshooting table](docs/data/ingestion.md#troubleshooting) lists the usual causes and
fixes. Provider settings (base URL, pacing, timeouts, retries) are optional
[environment variables](docs/environment.md#data-ingestion-phase-2); no provider needs a key.

The AI Analyst needs no configuration: RUMIN's grounded composer answers by default, offline.
To have a Claude model answer instead, set `RUMIN_ANALYST_PROVIDER=anthropic`,
`RUMIN_ANTHROPIC_API_KEY` and `RUMIN_ANALYST_MODEL` (RUMIN writes no model identifier into its
code; choose one when deploying) — see [the AI Analyst's settings](docs/environment.md#ai-analyst-phase-7).
Its answers are held to the same grounding check, and RUMIN answers whenever one fails.

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
  app/analyst/      the AI Analyst: question policy, vocabulary and router, conversation
                    focus, the tool registry and tools, evidence ledger, answer blocks,
                    grounded composer, grounding check, providers, orchestrator, worker pool,
                    evaluation set
  app/api/          HTTP routes (health, /api/v1/…)
  app/core/         settings, logging, errors, middleware
  app/data/         the illustrative sample network and the series catalogue (JSON)
  app/db/           engine/session, exact-decimal and UTC column types, seed loader
  app/domain/       enums, relationship-type and graph-type registries, scenario rules
  app/graph/        knowledge graph: construction rules, entity resolution, validation,
                    persistence, build command, algorithms, read interface
  app/ingestion/    providers, HTTP (throttling, retries), normalisation, quality rules,
                    persistence with revisions, job tracking, command line
  app/intelligence/ financial intelligence: exact statistics, thresholds, the evidence
                    model, validated graph slices, exposure, changes and revisions, drivers,
                    signals, the 19 insight rules, model interpretation, the brief
  app/models/       ORM models
  app/scenario_lab/ the Scenario Lab: scenario specification and validation, planner,
                    scenario profiles, executor and runner, aggregation, pathways,
                    explanations, sensitivity, comparison, templates
  app/schemas/      Pydantic request/response schemas (the API contract)
  app/services/     query and business logic
  app/simulation/   simulation engine: model registry and models, exact decimals, units,
                    validation, propagation, execution, sensitivity, explanations,
                    persistence
  migrations/       Alembic revisions
frontend/           React + TypeScript web client (Vite)
  src/app/          router, theme, module registry
  src/components/   shared UI primitives
  src/features/     network, graph (the explorer), data (chart, tables, provenance,
                    freshness), simulation (the preview: form, pathway, charts, panels),
                    scenarioLab (builder, pathway, results, timeline, views), intelligence
                    (the ledger, evidence chains, exposure matrix, drivers, signals, history),
                    analyst (notes, answer blocks, the evidence margin, conversations, export),
                    universe (the 3D view: strata, layout, scene, camera, names, overlays, the
                    canvas host and the lazily loaded Three.js renderer)
  src/pages/        one component per route
  tests/            unit and page tests; tests/integration runs against a live API
docs/               architecture, API, data model, data pipeline, testing, roadmap and more
  api/openapi.json  committed API contract (the frontend's types are generated from it)
scripts/            smoke_test.sh (backend/scripts and frontend/scripts: graph, Scenario Lab,
                    Financial Intelligence and 3D universe measurements, fixture capture from
                    a real backend, including the Analyst's and the universe's)
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
- Knowledge graph: [overview](docs/graph/README.md) · [concepts](docs/graph/concepts.md) ·
  [architecture](docs/graph/architecture.md) · [relationship types](docs/graph/relationship-types.md) ·
  [provenance](docs/graph/provenance.md) · [limitations](docs/graph/limitations.md) ·
  [performance](docs/graph/performance.md) · [Phase 4 integration](docs/graph/phase-4-integration.md)
- Simulation: [overview](docs/simulation/README.md) ·
  [architecture](docs/simulation/architecture.md) ·
  [the airline fuel-cost model](docs/simulation/airline-fuel-cost.md) ·
  [numbers and units](docs/simulation/numbers-and-units.md) ·
  [graph integration](docs/simulation/graph-integration.md) ·
  [provenance](docs/simulation/provenance.md) · [sensitivity](docs/simulation/sensitivity.md) ·
  [model registry](docs/simulation/registry.md) · [the preview](docs/simulation/preview.md) ·
  [limitations](docs/simulation/limitations.md)
- Scenario Lab: [overview](docs/scenario-lab/README.md) ·
  [architecture](docs/scenario-lab/architecture.md) · [the pathway](docs/scenario-lab/pathway.md) ·
  [the interface](docs/scenario-lab/interface.md) · [performance](docs/scenario-lab/performance.md) ·
  [limitations](docs/scenario-lab/limitations.md)
- Financial Intelligence: [overview](docs/intelligence/README.md) ·
  [architecture](docs/intelligence/architecture.md) · [evidence](docs/intelligence/evidence.md) ·
  [insight rules](docs/intelligence/rules.md) · [signals and thresholds](docs/intelligence/signals.md) ·
  [exposure](docs/intelligence/exposure.md) · [changes](docs/intelligence/changes.md) ·
  [drivers](docs/intelligence/drivers.md) · [stored analyses](docs/intelligence/stored-analyses.md) ·
  [the brief](docs/intelligence/brief.md) · [the interface](docs/intelligence/interface.md) ·
  [performance](docs/intelligence/performance.md) · [limitations](docs/intelligence/limitations.md)
- AI Analyst: [overview](docs/analyst/README.md) ·
  [architecture](docs/analyst/architecture.md) · [tools](docs/analyst/tools.md) ·
  [evidence and grounding](docs/analyst/evidence.md) · [providers](docs/analyst/providers.md) ·
  [conversations](docs/analyst/conversations.md) · [guardrails](docs/analyst/guardrails.md) ·
  [the interface](docs/analyst/interface.md) · [evaluation](docs/analyst/evaluation.md) ·
  [limitations](docs/analyst/limitations.md)
- 3D universe: [overview](docs/universe/README.md) ·
  [architecture](docs/universe/architecture.md) · [encoding](docs/universe/encoding.md) ·
  [interaction](docs/universe/interaction.md) · [scenario overlays](docs/universe/overlays.md) ·
  [accessibility](docs/universe/accessibility.md) · [performance](docs/universe/performance.md) ·
  [limitations](docs/universe/limitations.md)
- [Design system](docs/design-system.md)
- [Testing](docs/testing.md)
- [Security](docs/security.md)
- [Known limitations](docs/known-limitations.md)
- [Roadmap](docs/roadmap.md)
- Phase reports: [Phase 1](docs/phases/phase-1-report.md) ·
  [Phase 2 plan](docs/phases/phase-2-plan.md) · [Phase 2 report](docs/phases/phase-2-report.md) ·
  [Phase 3 plan](docs/phases/phase-3-plan.md) · [Phase 3 report](docs/phases/phase-3-report.md) ·
  [Phase 4 plan](docs/phases/phase-4-plan.md) · [Phase 4 report](docs/phases/phase-4-report.md) ·
  [Phase 5 plan](docs/phases/phase-5-plan.md) · [Phase 5 report](docs/phases/phase-5-report.md) ·
  [Phase 6 plan](docs/phases/phase-6-plan.md) · [Phase 6 report](docs/phases/phase-6-report.md) ·
  [Phase 7 plan](docs/phases/phase-7-plan.md) · [Phase 7 report](docs/phases/phase-7-report.md) ·
  [Phase 8 plan](docs/phases/phase-8-plan.md) · [Phase 8 report](docs/phases/phase-8-report.md)

## Licence

No licence has been chosen yet. Until the owners add one, all rights are reserved. Data
retrieved from providers remains under the provider's licence (for the World Bank: CC BY
4.0, with the attribution shown next to the data).
