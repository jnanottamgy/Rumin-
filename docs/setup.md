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
uv run python -m app.auth create-user --email you@example.org --name "Your Name" --role admin
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`create-user` asks for the password twice at a hidden prompt (at least 12 characters; common
passwords and your own e-mail address or name are refused). That first administrator
creates everyone else in the web app, under **People**.

Check it:

```bash
curl http://127.0.0.1:8000/health          # {"status":"ok",…}
curl http://127.0.0.1:8000/health/ready    # 200 once migrated and seeded, otherwise 503
```

Interactive API documentation: <http://127.0.0.1:8000/docs> (Swagger UI) and `/redoc`.

**Every `/api/v1` route except signing in needs a session** (Phase 10). To call the API with
`curl`, sign in once and keep the cookie; the examples below pass it with `-b cookies.txt`:

```bash
API=http://127.0.0.1:8000/api/v1
read -rsp 'Password: ' PW; echo
printf '{"email": "you@example.org", "password": "%s"}' "$PW" |
  curl -s -c cookies.txt -H 'Content-Type: application/json' --data @- $API/auth/login
unset PW
curl -s -b cookies.txt $API/auth/session        # who you are and what your role allows
```

`printf` is a shell built-in, so the password never appears in the process list. The cookie
file holds a live session: delete it (or `curl -s -b cookies.txt -X POST $API/auth/logout`)
when you are done.

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

### Simulation (Phase 4)

Nothing else to load: migration `0004` creates the tables and the first model is
registered in code. **Build the knowledge graph first** (above): a crude-oil change reaches
jet fuel only through the relationship the graph confirms, so without a build a crude
shock is refused (changes to jet fuel or the exchange rate still run).

In the browser, open <http://127.0.0.1:5173/simulation>, choose **Fill a hypothetical
example** (round numbers, not any airline's figures), then **Check inputs** or **Run
simulation**. Every run is stored and has its own address.

Through the API, with the same hypothetical example saved as `example.json`:

```json
{
  "model_id": "airline_fuel_cost",
  "inputs": {
    "crude_oil_change": { "value": "10" },
    "jet_fuel_price": { "value": "750", "unit": "usd_per_kilolitre" },
    "fx_rate": { "value": "80" },
    "reporting_currency": { "value": "INR" },
    "annual_revenue": { "value": "300000000" },
    "annual_operating_costs": { "value": "250000000" },
    "annual_fuel_consumption": { "value": "1000", "unit": "kilolitre" },
    "hedge_ratio": { "value": "50" },
    "hedge_months": { "value": "3" },
    "fare_pass_through": { "value": "40" },
    "fare_pass_through_lag": { "value": "2" }
  }
}
```

```bash
API=http://127.0.0.1:8000/api/v1
curl -s -b cookies.txt $API/simulation-models/airline_fuel_cost                 # inputs, equations, assumptions
curl -s -b cookies.txt -X POST $API/simulations/validate -H 'Content-Type: application/json' -d @example.json
curl -s -b cookies.txt -X POST $API/simulations -H 'Content-Type: application/json' -d @example.json
curl -s -b cookies.txt $API/simulations/<run id>/explanation                     # every step, the pathway
curl -s -b cookies.txt -X POST $API/simulations/<run id>/verify                  # re-execute, compare hashes
```

The run's change in operating profit is −3,550,000 INR over 12 months
([worked by hand](simulation/airline-fuel-cost.md#worked-example-checked-by-hand)). See
[the simulation engine](simulation/README.md) and [the API](api.md#simulation).

### Scenario Lab (Phase 5)

Nothing else to load: migration `0005` creates the tables (and turns any Phase 1 drafts
into version 1 of themselves), the five models are registered in code, and executions run
on a background pool inside the API process (settings in
[environment variables](environment.md#backend)). **Build the knowledge graph first**: the
graph's stated exposures decide which models apply to a company, and the crude → jet fuel
relationship carries a crude change to the airline model.

In the browser, open <http://127.0.0.1:5173/scenarios>, start from a template (for example
*Oil, rupee and rates together*), choose the company, enter the figures the plan asks for —
hypothetical ones are fine — and **Save and execute**. The execution's stages, the
pathway, the results and every tab are then available, and the execution has its own
address.

Through the API, with the backend tests' reference scenario (`backend/tests/scenario_support.py`,
hypothetical round figures) saved as `reference.json`:

```bash
API=http://127.0.0.1:8000/api/v1
curl -s -b cookies.txt $API/scenario-templates                                   # what can be started
curl -s -b cookies.txt -X POST $API/scenarios/plan -H 'Content-Type: application/json' -d @reference.json
curl -s -b cookies.txt -X POST $API/scenarios/preview -H 'Content-Type: application/json' -d @reference.json
curl -s -b cookies.txt -X POST $API/scenarios -H 'Content-Type: application/json' -d @reference.json
curl -s -b cookies.txt -X POST $API/scenarios/<scenario id>/executions -H 'Content-Type: application/json' -d '{}'
curl -s -b cookies.txt $API/scenario-executions/<execution id>                   # poll: queued → … → completed
curl -s -b cookies.txt $API/scenario-executions/<execution id>/results
curl -s -b cookies.txt -X POST $API/scenario-executions/<execution id>/verify    # re-execute, compare hashes
```

Its profit before tax changes by −6,700,000 INR over 12 months
([worked by hand](scenario-lab/README.md#the-reference-example)). See
[the Scenario Lab](scenario-lab/README.md) and [the API](api.md#scenario-lab).

### Financial Intelligence (Phase 6)

Nothing to load or configure: migration `0006` creates the one table it writes (stored
analyses), and every other answer is computed from what is already stored. What it can say
depends on what is there. **Build the knowledge graph** for exposure findings, **execute a
scenario** for simulated findings, and **retrieve series** (`make ingest`) for observed
changes, revisions, trends, volatility and unusual moves. Without them, the workspace says
exactly what it cannot compute and why.

In the browser, open <http://127.0.0.1:5173/intelligence>: the findings ledger, the exposure
map, observed series, simulated impacts and relationship changes. Choose a company in the
left rail for its dossier. Open any finding to see the evidence chain it rests on. Change the
thresholds with *Thresholds*: they go into the address, so the view can be linked. *Store
this analysis* keeps a snapshot that later says whether it is still current.

Through the API:

```bash
API=http://127.0.0.1:8000/api/v1
curl -s -b cookies.txt $API/intelligence/methods                                  # rules, signals, thresholds, grades
curl -s -b cookies.txt $API/intelligence/overview                                 # the workspace
curl -s -b cookies.txt "$API/intelligence/overview?relative_change_percent=3&trend_significance=0.10"
curl -s -b cookies.txt $API/intelligence/entities/company:co_aerisca_airways      # a dossier
curl -s -b cookies.txt $API/intelligence/entities/company:co_aerisca_airways/brief
curl -s -b cookies.txt -X POST $API/intelligence/analyses -H 'Content-Type: application/json' \
  -d '{"scope": "entity", "entity": "company:co_aerisca_airways", "label": "First look"}'
curl -s -b cookies.txt $API/intelligence/analyses/<analysis id>                   # as stored, with freshness
```

Two scripts in `backend/scripts/` support development. `benchmark_intelligence.py` times the
API on the sample network and on SYNTHETIC networks of up to 20,000 companies
([performance](intelligence/performance.md)). `capture_intelligence_fixtures.py` regenerates
the frontend's fixtures from a fresh backend ([testing](testing.md)). See [Financial
Intelligence](intelligence/README.md) and [the API](api.md#financial-intelligence).

### AI Analyst (Phase 7)

Nothing to configure: migration `0007` creates its three tables, and RUMIN's grounded composer
answers offline, with no language model. Like Financial Intelligence, what it can answer
depends on what is stored: **build the knowledge graph** for exposure and connections,
**execute a scenario** for stored results (and so that a what-if can reuse its company's
figures), and **retrieve series** for stored values.

In the browser, open <http://127.0.0.1:5173/analyst> and ask, or pick a suggested question.
Each answer shows its sources beside it; *How this was answered* lists the tool calls. A
what-if offers *Open in the Scenario Lab*, where it opens as an unsaved draft.

Through the API:

```bash
API=http://127.0.0.1:8000/api/v1
curl -s -b cookies.txt $API/analyst/capabilities                                   # provider, tools, limits, suggestions
SESSION=$(curl -s -b cookies.txt -X POST $API/analyst/sessions -H 'Content-Type: application/json' -d '{}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -s -b cookies.txt -X POST $API/analyst/sessions/$SESSION/turns -H 'Content-Type: application/json' \
  -d '{"question": "Which companies are exposed to the USD/INR exchange rate?"}'
curl -s -b cookies.txt $API/analyst/sessions/$SESSION                              # the conversation, answered
```

To have a **Claude model** answer instead, set in `.env` (or the process environment):

```bash
RUMIN_ANALYST_PROVIDER=anthropic
RUMIN_ANTHROPIC_API_KEY=…            # your key; a secret, never logged or returned
RUMIN_ANALYST_MODEL=…                # a model your key can use; RUMIN names none in its code
```

and restart the API. The page's header then says *Language model configured*. Each answer is
still checked against its evidence, and RUMIN answers whenever the model fails, a limit is
reached or its draft does not pass. Only `RUMIN_`-prefixed settings are read:
`ANTHROPIC_API_KEY` in the environment is ignored. Score the result with
`uv run python -m app.analyst.evaluation` before relying on it ([evaluation](analyst/evaluation.md)).

`backend/scripts/capture_analyst_fixtures.py` regenerates the frontend's fixtures from a fresh
backend ([testing](testing.md)). See [the AI Analyst](analyst/README.md) and
[the API](api.md#ai-analyst).

## 3. Frontend

```bash
cd frontend
npm ci
npm run dev                          # http://127.0.0.1:5173
```

Sign in with the account created in step 2; the browser keeps the session in an `HttpOnly`
cookie. **Getting started** (`/guide`) lists starter tasks.

The dev server proxies `/api`, `/health`, `/docs` and `/openapi.json` to
`RUMIN_API_PROXY_TARGET` (default `http://127.0.0.1:8000`), so the browser only ever talks
to one origin.

Production build: `npm run build` writes static files to `frontend/dist/`. For a team, use
the production images and the nginx configuration in [deployment](deployment.md): they serve
the build with its security headers and pass `/api` and `/health` to the API with the
browser's own `Host` (a proxy that rewrites it makes every change look cross-site).

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
make check             # lint, types, backend + frontend tests, OpenAPI snapshot
make smoke             # fresh database → live API → frontend integration suite
make e2e               # the built app in Chromium on a desktop and a phone (axe, workflows)
make audit             # pip-audit, npm audit, the secret scan (network and Docker)
make deployment-check  # the production images and stack, end to end (Docker)
```

See [testing.md](testing.md).

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The web client says **"Could not reach the RUMIN API"** | The API is not running, or not on `RUMIN_API_PROXY_TARGET`. Start it (step 2) and press *Try again*. |
| **"No dataset is loaded"** | Run `uv run python -m app.db.seed` in `backend/`. |
| A simulation with a crude-oil change is refused because **the knowledge graph does not confirm** the relationship | Build the graph (`make graph`), or rebuild it if the page says it is stale. |
| A run is refused with **409: a changed model needs a new version number** | The code of a model version that has already run was changed. Give the change a new version ([changing a model](simulation/registry.md#changing-a-model)); on a disposable development database you can start from a fresh one instead. |
| `/health/ready` returns **503** | The response lists which check failed: database unreachable, migrations not at head (`alembic upgrade head`), or no dataset (seed). |
| **CORS errors** in the browser console | Only happens when the web client calls the API cross-origin (`VITE_API_BASE_URL` set). Add the web origin to `RUMIN_CORS_ORIGINS`. |
| The API answers **401 "Sign in to continue."** | Every `/api/v1` route needs a session: sign in (web app), or use the cookie from `…/auth/login` with `curl` (step 2). |
| **"Too many sign-in attempts"** or **"Too many failed attempts from this address"** (429) | Repeated wrong passwords. Wait the time the message gives, or set a new password: `uv run python -m app.auth set-password --email …`. |
| Every change answers **403 "Requests that change data must come from RUMIN's own pages."** | The request's `Origin` differs from the API's own: a proxy in front rewrote the `Host` header (the dev server must not use `changeOrigin`), or you opened the app under one host name and the API under another. |
| Buttons such as **Execute** or **Run simulation** are disabled, with a note | Your role is *viewer*: you read and preview, but only analysts and administrators store. An administrator can change the role under **People**. |
| **413 Payload Too Large** | Request bodies are limited to `RUMIN_MAX_REQUEST_BODY_BYTES` (64 KiB). |
| `ModuleNotFoundError: psycopg` | Install the PostgreSQL extra: `uv sync --extra dev --extra postgres`. |
| Port 8000 or 5173 already in use | Pass another port: `uvicorn … --port 8001` and set `RUMIN_API_PROXY_TARGET`; `npm run dev -- --port 5174` (then add that origin to `RUMIN_CORS_ORIGINS` if you call the API cross-origin). |
| The Data Explorer says **"The series catalogue has not been loaded"** | Run `uv run python -m app.ingestion catalog` in `backend/`. |
| **"The last retrieval failed"** / every series `provider_unavailable` | The machine cannot reach `api.worldbank.org` (firewall, proxy or sandbox). Allow outbound HTTPS to it (`HTTPS_PROXY` is honoured) and run `make ingest` again. More in [ingestion](data/ingestion.md#troubleshooting). |
| `✗ Database error … run: make migrate` from an ingestion command | The schema is missing or older than the code: `uv run alembic upgrade head`. |
| The Knowledge Graph page says **"The knowledge graph has not been built yet"** | Run `uv run python -m app.graph build` in `backend/` (or `make graph`), then reload the page. |
| The Knowledge Graph page says **"The graph is older than its sources"** | Data changed after the last build. Rebuild it with `make graph`. On a running API the notice can take up to 30 seconds to appear; it clears as soon as a new build finishes. |
| `✗ Graph build #n … is still running` | Another build is in progress. Wait for it; a build whose process died is closed automatically after an hour. |
| Financial Intelligence says **"No series or instrument has two or more stored values"** | Nothing observed can be compared yet. Retrieve series (`make ingest`) or import a licensed price file; exposure and simulated findings do not need them. |
| Every exposure finding is graded **assumed**, and *Only relationships backed by a cited source* shows nothing | Expected with the sample network: every exposure relationship in it is a model assumption ([evidence](intelligence/evidence.md)). |
| A stored analysis says **Stale** | Something it read has changed since (the graph, stored values or executions). It still shows what it concluded then; store a new one for the current state. |
| The AI Analyst answers **"Which variable do you mean?"** or **"…outside what RUMIN's records can answer"** | It reads the phrasings it was written for ([limitations](analyst/limitations.md)). Pick a choice, name the company, variable or series as RUMIN does, or try a suggested question. |
| The Analyst's header says **the configured language model is not ready** | `RUMIN_ANALYST_PROVIDER=anthropic` is set without `RUMIN_ANTHROPIC_API_KEY` or `RUMIN_ANALYST_MODEL` (the message names which). RUMIN answers meanwhile. |
| An answer carries **"Answered by RUMIN's grounded composer"** | The language model's answer was not used; the notice says why (an API error, a refusal, a limit, or a draft that failed the grounding check). |
| **429** when asking | Every worker is busy and the queue is full (`RUMIN_ANALYST_MAX_CONCURRENT`, `RUMIN_ANALYST_MAX_QUEUED`). Nothing was stored; ask again shortly. |
| Start again from scratch | Stop the API, delete `backend/rumin.db`, then migrate, seed, load the catalogue, build the graph and create your account again. |
