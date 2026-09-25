# API reference

The RUMIN API is a JSON-over-HTTP API built with FastAPI. This page summarises it; the
complete, authoritative contract is the OpenAPI document:

- live: `GET /openapi.json`, browsable at `/docs` (Swagger UI) and `/redoc`;
- committed: [`docs/api/openapi.json`](api/openapi.json). A backend test fails if the
  running application's schema differs from this file, and the frontend's TypeScript types
  are generated from it (`npm run generate:api`), so server, contract and client cannot
  drift apart unnoticed.

Regenerate after changing an endpoint or schema: `make api-types` (or
`uv run python -m app.openapi_export` in `backend/`, then `npm run generate:api` in
`frontend/`).

## Conventions

| Topic | Rule |
|---|---|
| Versioning | Application endpoints live under `/api/v1`. Breaking changes will get a new prefix (`/api/v2`); additive changes (new fields, new endpoints) do not. Health probes are unversioned, as infrastructure expects. |
| Format | Requests and responses are JSON (`application/json`). Request bodies with any other content type are rejected. |
| Unknown fields | Request bodies with fields the contract does not define are rejected (422), so typos never pass silently. |
| IDs | Reference-data IDs are readable slugs with a kind prefix: `co_…`, `ind_…`, `cty_…`, `var_…`, `rel_…` (pattern `^[a-z]{2,4}_[a-z0-9_]{2,59}$`). Datasets, series and instruments have lowercase slugs (`worldbank-wdi`, `wb-ind-fp-cpi-totl-zg`, `xnse-reliance`). Scenario, scenario-execution, sensitivity-analysis, stored-analysis and ingestion-job IDs are UUIDs; insight ids are `ins-` plus 16 hex characters, stable for the same rule, subject and facts; scenario versions are numbered 1, 2, 3 … within their scenario; scenario templates have lowercase slugs (`crude_oil_airline`). Knowledge-graph keys are `type:record-id` for nodes and `e-` plus 16 hex characters for edges ([below](#knowledge-graph)). Path and query IDs are validated against their pattern (422 otherwise). |
| Data values | Observation values, prices, review ranges and the numbers of simulation, Scenario Lab and Financial Intelligence responses (scenario changes and thresholds included) are **exact decimal strings in plain notation** (`"5.649"`, `"0.000000000000000001"`), never JSON numbers, so no digit is lost to floating point. A missing value is `null`, never `0`. Requests to the simulation and scenario endpoints may send a number as a decimal string or a JSON number. |
| Dates | Calendar dates (periods, trade dates, the provider's last update) are `YYYY-MM-DD`; they have no time zone. |
| Pagination | List endpoints take `limit` (1–500, default 100) and `offset` (default 0) and return `{items, total, limit, offset}`. |
| Time | Timestamps are ISO 8601 in UTC, e.g. `2026-09-23T11:46:58.387307Z`. |
| Knowledge labels | Relationships carry `epistemic_category: "assumption"` and `evidence_level`; scenario shocks carry `epistemic_category: "scenario_input"`; economic series carry `epistemic_category: "observation"`. Simulation inputs carry `knowledge` (`scenario_input`, `historical_data`, `user_input`, `assumption`, `setting`) and `source` (`user`, `default`, `stored_observation`); simulation outputs carry `kind` (`derived` or `simulated`). Scenario Lab lines, metrics, months and stress cases carry `knowledge: "simulated"`. Financial Intelligence insights carry an `evidence` block: `grade` (the weakest step of the chain: `observed`, `documented`, `curated`, `simulated`, `assumed`, `unverified`), `conditional_on_simulation` and the grade's statement. |
| Request IDs | Every response has an `X-Request-ID` header (a safe incoming value is reused, otherwise one is generated). Error bodies repeat it, and every log line for the request includes it. |
| Compression | A response body of 1 KiB (1,024 bytes) or more is gzip-compressed when the request's `Accept-Encoding` includes `gzip` (`Content-Encoding: gzip`, `Vary: Accept-Encoding`); smaller responses, and clients that do not accept gzip, get the body as it is. |

## Endpoints

| Method and path | Purpose | Success |
|---|---|---|
| `GET /health` | Liveness: the process is serving. Does not touch the database. | 200 |
| `GET /health/ready` | Readiness: database reachable, migrations at head, dataset loaded. Lists the failing checks otherwise. | 200 / 503 |
| `GET /api/v1/entities` | All entities; filter with `?kind=company\|industry\|country\|economic_variable`. | 200 |
| `GET /api/v1/entities/{entity_id}` | One entity with its kind-specific fields. | 200 / 404 |
| `GET /api/v1/industries` | Industries (ISIC Rev. 4 divisions). | 200 |
| `GET /api/v1/variables` | Economic variables, each with the `scenario_rules` it accepts. | 200 |
| `GET /api/v1/relationships` | Curated relationships; filter with `?type=` and/or `?entity_id=` (either end). | 200 |
| `GET /api/v1/relationship-types` | The relationship-type registry: labels, direction, polarity, allowed entity kinds. | 200 |
| `GET /api/v1/network` | Graph projection for visualisation: nodes (entity + degree), economic edges, structural links derived from entity records, relationship types, dataset summary. | 200 |
| `GET /api/v1/scenarios` | Scenarios, most recently updated first: each with its newest version's changes and company, its latest execution (or `null`) and its number of executions. Paginated. | 200 |
| `POST /api/v1/scenarios` | Create a scenario: stores version 1 and simulates nothing. Returns it with a `Location` header. | 201 / 422 |
| `GET /api/v1/scenarios/{scenario_id}` | One scenario: its newest version's content, every version (newest first), its latest execution and number of executions. | 200 / 404 |
| `PUT /api/v1/scenarios/{scenario_id}` | Save the body as a **new version**; earlier versions never change. A body equal to the newest version adds none; a stale `base_version` is refused ([below](#versions)). | 200 / 404 / 409 / 422 |
| `DELETE /api/v1/scenarios/{scenario_id}` | Delete a scenario that has never been executed; an executed one is kept (409). | 204 / 404 / 409 |
| `GET /api/v1/system` | Service version and environment, database and migration state, reference-dataset provenance and counts, stored provider data (`data`: series, observations, instruments, price rows, flagged values, last job), and capabilities marked available or planned (with the phase). | 200 |

**Provider data (Phase 2, read-only)**

| Method and path | Purpose | Success |
|---|---|---|
| `GET /api/v1/providers` | Data providers with their terms: licensing, commercial use, rate-limit policy, coverage, limitations. | 200 |
| `GET /api/v1/providers/{provider_id}` | One provider. | 200 / 404 |
| `GET /api/v1/datasets` | Every dataset — the curated network (`kind: curated`) and provider data (`kind: provider`) — with licence, attribution, the provider's last update and the latest ingestion job. Filter `?kind=`. | 200 |
| `GET /api/v1/datasets/{dataset_id}` | One dataset. | 200 / 404 |
| `GET /api/v1/economic-series` | Series with coverage (`first_period`, `last_period`), counts, the latest reported value and the last retrieval's outcome. Filters: `dataset_id`, `country_iso3`, `measure_type`, `frequency`, `has_data`, `q` (name or code); `sort`: `name`, `-name`, `last_period`, `-last_period`, `provider_code`. | 200 |
| `GET /api/v1/economic-series/{series_id}` | One series, with its dataset (licence, attribution), provider name, flagged and revised counts, and last job. | 200 / 404 |
| `GET /api/v1/economic-series/{series_id}/observations` | Values in period order, with `period_end`, the provider's literal (`raw_value`), status, quality, flags, revision, `retrieved_at` and the capture it came from. `start`/`end` (dates), `include_missing` (default true), `include_revisions` (default false). The page also carries the series' unit and the dataset's licence. | 200 / 404 |
| `GET /api/v1/instruments` | Instruments declared by imported price files. Filters: `exchange_mic`, `instrument_type`, `dataset_id`. | 200 |
| `GET /api/v1/instruments/{instrument_id}` | One instrument and the datasets holding its prices. | 200 / 404 |
| `GET /api/v1/instruments/{instrument_id}/prices` | Daily prices from **one** dataset, in date order. `dataset_id` is required when the instrument has prices from several datasets (422 otherwise — sources are never blended). `start`, `end`, `include_revisions`. | 200 / 404 / 422 |
| `GET /api/v1/ingestion-jobs` | Ingestion runs, newest first. Filters: `status`, `dataset_id`, `provider_id`. | 200 |
| `GET /api/v1/ingestion-jobs/{job_id}` | One run: each target's outcome and error code, issue counts by rule, and the stored responses or files (metadata only). | 200 / 404 |
| `GET /api/v1/source-captures/{capture_id}` | Metadata of a stored response or file: sanitised URL or file name, time, HTTP status, size, SHA-256, whether the bytes are stored. The bytes themselves are never served. | 200 / 404 |
| `GET /api/v1/data-quality/issues` | Rejected records (with what the source sent), flagged values and notes, newest first. Filters: `job_id`, `series_id`, `instrument_id`, `rule`, `severity`, `outcome`. | 200 |
| `GET /api/v1/data-quality/rules` | The published quality rules: what each checks, its severity and outcome. | 200 |

There is deliberately **no endpoint that starts ingestion**: without authentication, it
would let anyone make the server call providers and write data. Ingestion runs from the
command line ([ingestion](data/ingestion.md)); `POST /api/v1/ingestion-jobs` answers 405.

A scenario's versions, plans, previews and executions, comparisons of executions and
scenario templates are listed under [Scenario Lab](#scenario-lab) (Phase 5). An execution
runs a scenario version through the model registry and stores each model's run as an
ordinary run of the [simulation endpoints](#simulation).

Findings about the workspace and each company, with their evidence, and stored analyses are
listed under [Financial intelligence](#financial-intelligence) (Phase 6). Conversations with
the AI Analyst are under [AI Analyst](#ai-analyst) (Phase 7).

### Structural links in `/api/v1/network`

Economic relationships are curated records (`category: "economic"`). The network also
contains **structural links** (`category: "structural"`) derived at query time from entity
fields — `in_industry` (company → its industry), `domiciled_in` (company → its country) and
`measured_for` (variable → its country). They are facts about how the sample records are
classified, not economic assumptions, and have no polarity, strength or evidence level.

`/api/v1/network` is the Phase 1 view of the sample network, used by the Financial
Universe page. The knowledge graph below is the Phase 3 graph of every record RUMIN holds,
with provenance on every edge.

## Knowledge graph

Read-only endpoints under `/api/v1/graph` (Phase 3). The graph is built from the command
line (`make graph`); the API has **no write endpoint**, and `POST`, `PUT`, `PATCH` and
`DELETE` answer 405. Concepts, node and edge models and algorithms are documented in
[`docs/graph/`](graph/README.md).

| Method and path | Purpose | Success |
|---|---|---|
| `GET /api/v1/graph/overview` | The latest build (validation counts, changes), whether it is **current** or **stale** against its sources, the metrics with their definitions and limitations, a type-level map (node counts per type, edge counts between types) and notes on what the graph is not. `build` is `null` and `freshness.status` is `not_built` before the first build. | 200 |
| `GET /api/v1/graph/types` | The vocabulary: node types, edge types (meaning, endpoints, direction, allowed evidence statuses, caveat), evidence-status definitions, identifier schemes, construction rules and validation rules. | 200 |
| `GET /api/v1/graph/nodes` | Search. `q` (1–100 characters) matches names, subtitles and identifiers, case-insensitively; an exact identifier comes first. Filters: `type` (repeatable), `nature`, `related_to` (nodes with an edge to this node); `sort`: `name` or `-degree`. Each result says how it matched and whether its name is `ambiguous` (shared by several nodes). | 200 |
| `GET /api/v1/graph/nodes/{node_id}` | One node: identifiers with the record that stated each, source records, relationships by type and direction, entity-resolution decisions, quality issues, live data status for series and instruments, and for companies and industries the variables linked by assumed-effect edges (`direct` or `via_industry`). | 200 / 404 |
| `GET /api/v1/graph/nodes/{node_id}/neighborhood` | The nodes within `depth` hops and every edge among them. `depth` 1–3 (default 1), `max_nodes` 2–200 (default 60), `edge_type`, `node_type`, `evidence_status` (all repeatable), `direction` (`any`, `out`, `in`), `include_illustrative`. Reports `truncated`, `unexplored_count`, `unexplored_by_type` and `queries`. | 200 / 404 |
| `GET /api/v1/graph/edges` | Current edges. Filters: `type`, `evidence_status` (repeatable), `node` (either end), `illustrative`. Paginated. | 200 |
| `GET /api/v1/graph/edges/{edge_id}` | One edge and **why it exists**: an `explanation` paragraph, every evidence record, the status's definition, the type's meaning and its `caveat` (what it does not mean). | 200 / 404 |
| `GET /api/v1/graph/paths` | Shortest paths in hops between `from` and `to`: `max_depth` 1–6 (default 4), `limit` 1–10 (default 3), `direction`, `edge_type`, `evidence_status`, `include_illustrative`. Reports `found`, `length`, `nodes_explored`, `budget_exhausted` (the 5,000-node search budget ran out) and a `note` that a path is not a causal chain. | 200 / 404 |
| `GET /api/v1/graph/components` | Connected components (direction ignored), largest first, with their composition and a small sample of nodes. `limit` 1–50 (default 10). | 200 / 404 |
| `GET /api/v1/graph/builds` | Every build, newest first, with validation counts and changes. Paginated. | 200 |
| `GET /api/v1/graph/builds/{build_id}` | One build's report: counts, changes, the datasets and versions read, metrics, issue counts by rule, resolution decisions by outcome, and a safe error summary if it failed. | 200 / 404 |
| `GET /api/v1/graph/issues` | Validation issues of a build (default: the latest), including entity-resolution candidates flagged for review. Filters: `build_id`, `rule`, `severity`, `node`. Paginated. | 200 |

**Keys.** Node keys are `type-prefix:record-id`, lower-case:
`^(country|currency|sector|industry|company|variable|series|instrument|market):[a-z0-9][a-z0-9_.-]{0,95}$`
(for example `company:co_deltrin_refining`, `currency:inr`, `sector:isic4-c`). URL-encode
the colon in paths if your client needs it. Edge keys are `e-` plus 16 hexadecimal
characters. Anything else is rejected with 422 before the database is queried.

**Limits.** Every traversal is bounded, and anything out of range is rejected with 422
rather than clamped: depth ≤ 3, ≤ 200 nodes per neighbourhood, paths ≤ 6 hops, ≤ 10
paths, at most 9 node types, 18 edge types and 4 evidence statuses per filter. A path
search also stops after visiting 5,000 nodes and says so (`budget_exhausted: true`), which
is different from "no path".

**Before the first build**, the endpoints that need a graph (a node, a neighbourhood, an
edge, paths, components) answer 404 with the message "No knowledge graph has been built
yet. Run: make graph". The overview answers 200 with `freshness.status: "not_built"`.

Example: why does an edge exist?

```http
GET /api/v1/graph/edges/e-dff724fccf21ee64
```

```json
{
  "id": "e-dff724fccf21ee64",
  "type": "affects_costs",
  "category": "economic",
  "source": "variable:var_usd_inr",
  "target": "company:co_deltrin_refining",
  "directed": true,
  "label": "affects costs of",
  "evidence_status": "model_assumption",
  "is_illustrative": true,
  "valid_from": null,
  "valid_to": null,
  "historical": false,
  "qualifiers": {
    "polarity": "positive",
    "strength": "strong",
    "evidence_level": "illustrative",
    "rationale": "Deltrin (fictional) imports crude oil priced in U.S. dollars, so a weaker rupee raises its input costs in rupees."
  },
  "explanation": "USD/INR exchange rate — affects costs of → Deltrin Refining. Rule R01 curated_relationship built it from relationships/rel_usd_inr_costs_deltrin (dataset rumin-sample, 1.0.0): … Evidence status: Model assumption. … Illustrative: it involves the fictional sample network or sample data, so it says nothing about the real world.",
  "evidence": [
    {
      "rule": "R01 curated_relationship",
      "source_kind": "reference_dataset",
      "source_table": "relationships",
      "source_record_id": "rel_usd_inr_costs_deltrin",
      "dataset_id": "rumin-sample",
      "dataset_version": "1.0.0",
      "statement": "Curated relationship rel_usd_inr_costs_deltrin: var_usd_inr affects_costs co_deltrin_refining, evidence level 'illustrative'. …",
      "transformation": "Copied as an edge of the same type; the description, rationale, assumed polarity and illustrative strength are kept unchanged.",
      "derivation": "direct",
      "citation": null,
      "retrieved_at": null,
      "recorded_at": "2026-09-23T14:38:11.984881Z",
      "…": "…"
    }
  ],
  "evidence_status_label": "Model assumption",
  "caveat": "An assumed effect, not a measured one: it says nothing about size or timing, and entities of the same kind can be affected very differently. A connection is not evidence of causation.",
  "…": "…"
}
```

(Abridged: `source_node`, `target_node`, the status definition, the type's description and
the build IDs are omitted. Deltrin Refining is a fictional company.)

## Simulation

Versioned models, input validation, deterministic runs and their explanations (Phase 4).
Runs and sensitivity analyses are **append-only**: created by `POST`, never replaced or
deleted (`PUT`, `PATCH` and `DELETE` answer 405). Everything is documented in
[`docs/simulation/`](simulation/README.md).

| Method and path | Purpose | Success |
|---|---|---|
| `GET /api/v1/simulation-models` | The latest version of every registered model: status, definition hash, versions, number of stored runs. | 200 |
| `GET /api/v1/simulation-models/{model_id}` | The full definition (`?version=` for an older one): inputs with units, ranges, defaults, rationales and any stored series each can come from (with its latest value); equations; outputs; transmission rules with the graph edge that confirms each; assumptions, limitations, validation rules; the graph's freshness. | 200 / 404 |
| `POST /api/v1/simulations/validate` | Checks inputs without running or storing anything. Always 200: `valid`, `errors` and `warnings` (each with its field), every input resolved and labelled, the graph snapshot, and the inputs hash a run would have. | 200 |
| `POST /api/v1/simulations` | Runs a model and stores the run. Invalid inputs: 422 with one detail per problem, nothing stored. A model version whose code no longer matches its stored definition: 409. | 201 / 409 / 422 |
| `GET /api/v1/simulations` | Stored runs, newest first, with their headline results; filter `?model_id=`. | 200 |
| `GET /api/v1/simulations/{run_id}` | A run: inputs (each with its kind of knowledge and source), outputs, monthly series, contributions, bridge, warnings, limitations, hashes, times. | 200 / 404 |
| `GET /api/v1/simulations/{run_id}/explanation` | Equations used, every step, the input-to-output pathway, contributions, parameters against defaults, assumptions, limitations, warnings. | 200 / 404 |
| `GET /api/v1/simulations/{run_id}/provenance` | Model version and definition hash, engine version, hashes, stored observations used, the graph snapshot, every transmission path. | 200 / 404 |
| `POST /api/v1/simulations/{run_id}/verify` | Re-executes the run from its stored snapshot and compares the hashes; stores nothing. | 200 / 404 |
| `POST /api/v1/simulations/{run_id}/sensitivity` | A one-at-a-time sensitivity analysis, stored with the run (empty body: the model's defaults). | 201 / 404 / 409 / 422 |
| `GET /api/v1/simulations/{run_id}/sensitivity` | The run's analyses, newest first. | 200 / 404 |
| `GET /api/v1/simulations/{run_id}/sensitivity/{analysis_id}` | One analysis. | 200 / 404 |
| `GET /api/v1/simulation-models/{model_id}/verification` | The model version's [verification register](simulation/verification.md), run now (`?version=`, default the model's default version): each check — reference case, property, documented limits, reproducibility — with its detail, `passed`/`failed`/`total`, and what is **not** verified. Stores nothing. | 200 / 404 |

The brief's suggested `POST /simulations/run` is `POST /simulations`: the API creates
resources by posting to the collection, as `POST /scenarios` does.

**Inputs** are an object keyed by input ID. Values are exact decimal strings or JSON
numbers; text inputs are strings; quantities name their unit; an input may ask for a stored
observation instead of a value. Inputs left out take the model's default (and are recorded
as defaults):

```http
POST /api/v1/simulations
Content-Type: application/json

{"model_id": "airline_fuel_cost", "label": "Example: crude +10 %",
 "inputs": {
   "crude_oil_change": {"value": "10"},
   "jet_fuel_price": {"value": "750", "unit": "usd_per_kilolitre"},
   "fx_rate": {"value": "80"},
   "reporting_currency": {"value": "INR"},
   "annual_revenue": {"value": "300000000"},
   "annual_operating_costs": {"value": "250000000"},
   "annual_fuel_consumption": {"value": "1000", "unit": "kilolitre"},
   "hedge_ratio": {"value": "50"}, "hedge_months": {"value": "3"},
   "fare_pass_through": {"value": "40"}, "fare_pass_through_lag": {"value": "2"}}}
```

```http
HTTP/1.1 201 Created
Location: /api/v1/simulations/51b90c67-3fe5-48a8-bbc1-f0186430e3c9

{
  "id": "51b90c67-3fe5-48a8-bbc1-f0186430e3c9",
  "model_id": "airline_fuel_cost",
  "model_version": "1.0.0",
  "status": "completed",
  "outputs": [
    {"id": "operating_profit_change", "label": "Change in operating profit (horizon)",
     "value": "-3550000", "unit": "INR", "kind": "simulated", "equation": "E14", "…": "…"},
    "…"
  ],
  "inputs": [
    {"id": "crude_oil_change", "value": "10", "knowledge": "scenario_input", "source": "user", "…": "…"},
    {"id": "crude_pass_through", "value": "1", "knowledge": "assumption", "source": "default", "…": "…"},
    "…"
  ],
  "bridge": {"steps": ["…"], "total": {"output": "operating_profit_change", "value": "-3550000"}},
  "inputs_hash": "ca04cbff…", "result_hash": "4d5f06b9…", "random_seed": null,
  "note": "A deterministic calculation from the inputs and assumptions shown, holding everything else constant. It is not a forecast and not investment advice.",
  "…": "…"
}
```

(Abridged. The figures are the Simulation page's hypothetical example — round numbers, not
data. A stored exchange rate is requested with `"fx_rate": {"source": "stored_observation"}`.)

A refused run lists every problem, with the field as `inputs.<id>`:

```json
{"error": {"code": "validation_error", "message": "The simulation inputs are invalid.",
  "details": [
    {"location": "body", "field": "inputs.annual_revenue", "message": "Annual revenue is required.", "type": "required"},
    {"location": "body", "field": "inputs.hedge_ratio", "message": "Hedge ratio must be at most 100 %.", "type": "input_range"}
  ], "request_id": "…"}}
```

Detail types: `unknown_input`, `required`, `input_range`, `unit_choice`,
`observation_matches`, `no_stored_observation`, the model's own rules
(`usd_rate_is_one`, `fuel_share_exceeds_costs`, `channel_confirmed`, `entity_is_airline`),
`numerical_limit` and `transmission_limit` (a calculation outside the engine's range),
`unknown_model`, `deprecated_model`, and for sensitivity requests `invalid_number` and
`sensitivity_limit`.

## Scenarios

A scenario is a stable identity with immutable, numbered **versions**. The body of
`POST /scenarios`, `PUT /scenarios/{id}`, `POST /scenarios/plan` and
`POST /scenarios/preview` is one version's content: a name, an optional description and
1–10 **shocks** — changes to economic variables — and, optionally, the company, figures,
timing, models, assumptions, constraints, stress cases and note that the
[Scenario Lab](#scenario-lab) uses (field by field in the
[data dictionary](data-dictionary.md#scenario-content)). The smallest body:

```json
{
  "name": "Oil price shock",
  "description": "Brent crude rises 30 %.",
  "shocks": [
    { "variable_id": "var_brent_crude", "change_type": "percent_change", "value": "30", "note": "" }
  ]
}
```

A value may be sent as a decimal string or as a JSON number (`30`); it is returned as an
exact decimal string (`"30"`).

What each variable accepts is published on the variable itself (`GET /api/v1/variables`),
so a client can validate before sending, exactly as the server will:

```json
"scenario_rules": [
  { "change_type": "percent_change", "minimum": -100, "minimum_exclusive": true, "maximum": 1000, "unit_label": "%" },
  { "change_type": "absolute_change", "minimum": -1000000, "minimum_exclusive": false, "maximum": 1000000, "unit_label": "USD per barrel" }
]
```

| Rule | Why |
|---|---|
| `percent_change` must be greater than −100 % and at most +1,000 % | A price cannot fall by 100 % or more; the cap catches typing errors. |
| Rates, inflation and policy rates accept only `absolute_change`, in percentage points, within ±25 pp | "Increase the repo rate by 10 %" is ambiguous (10 % of 6.5 %, or 10 points?). Points are not. |
| Other `absolute_change` values within ±1,000,000 of the variable's unit | Guards against nonsense input. |
| A change of zero is rejected | It has no effect; remove the shock instead. |
| At most 4 decimal places | Values are stored as `NUMERIC(14, 4)`; nothing is rounded silently. |
| Each variable at most once per version | Two changes to one variable are ambiguous; combine them. |
| Names 1–120 characters, no control characters; description ≤ 2,000; note ≤ 500 | Storage and display limits. |

Every other field and its limits are in the
[data dictionary](data-dictionary.md#scenario-content).

`POST /api/v1/scenarios` answers `201 Created` with a `Location` header and the scenario,
which has `latest_execution: null` and `executions: 0` until it is executed. Example: the
reference scenario of the backend tests (`backend/tests/scenario_support.py`) after one
execution, abridged from `frontend/tests/fixtures/lab/scenario.json` (captured from a
running backend). Aerisca Airways is a fictional company and its figures are hypothetical
round numbers.

```http
GET /api/v1/scenarios/f5a5b9a1-87b4-4fe8-8dc3-dc2979e4ba8e
```

```json
{
  "id": "f5a5b9a1-87b4-4fe8-8dc3-dc2979e4ba8e",
  "name": "Oil, rupee and rates on Aerisca",
  "description": "",
  "status": "draft",
  "template_id": null,
  "current_version": 1,
  "shocks": [
    { "variable_id": "var_brent_crude", "change_type": "percent_change", "value": "20",
      "note": "", "epistemic_category": "scenario_input" },
    { "variable_id": "var_usd_inr", "change_type": "percent_change", "value": "5", "…": "…" },
    { "variable_id": "var_rbi_repo_rate", "change_type": "absolute_change", "value": "0.5", "…": "…" }
  ],
  "spec": {
    "entity": "company:co_aerisca_airways",
    "timing": { "start_month": 1, "duration_months": 0, "horizon_months": 12 },
    "company": { "reporting_currency": "INR", "annual_revenue": "300000000",
                 "annual_operating_costs": "250000000" },
    "markets": { "fx_rate": { "value": "80", "unit": null, "source": null, "series_id": null } },
    "models": {
      "floating_rate_interest": { "mode": "include", "inputs": { "…": "…" },
                                  "assumptions": { "repo_repricing_lag": "3" } },
      "…": "…"
    },
    "constraints": { "evidence": "any", "stored_market_data": false },
    "stress_cases": [
      { "name": "Half", "scale": "0.5", "changes": {} },
      { "name": "Double", "scale": "2", "changes": {} }
    ]
  },
  "versions": [
    { "version": 1, "name": "Oil, rupee and rates on Aerisca",
      "spec_hash": "c868ca0c9d2786aed631c6c651b935d099a22c88318a729d5a5e016a99725615",
      "note": "", "derived_from": null, "created_at": "2026-09-24T03:27:57.079462Z",
      "executions": 1 }
  ],
  "latest_execution": {
    "id": "348bd1e1-ea11-4851-bbf6-78389f1512c1",
    "version": 1,
    "status": "completed",
    "headline": [
      { "id": "profit_before_tax", "label": "Profit before tax", "change": "-6700000",
        "percent_change": "-17.6315789474", "currency": "INR" },
      { "id": "operating_profit", "label": "Operating profit", "change": "-6325000",
        "percent_change": "-12.65", "currency": "INR" }
    ],
    "models": ["airline_fuel_cost", "fx_exposure", "floating_rate_interest"],
    "error": null,
    "…": "…"
  },
  "executions": 1,
  "created_at": "2026-09-24T03:27:57.078245Z",
  "updated_at": "2026-09-24T03:27:57.078250Z"
}
```

## Scenario Lab

Versioned scenarios executed through the model registry (Phase 5). For a scenario version
the Lab plans which registered models apply and why, runs each of them through the Phase 4
engine, stores each model's run as an ordinary [simulation run](#simulation), and combines
the models into lines, metrics, months, an impact pathway and stress cases. Results,
pathways and explanations are read from what an execution and its runs stored; no text is
generated. Executions and their sensitivity analyses are **append-only**: an execution
never changes once final, and neither can be deleted (`DELETE` answers 405). How the Lab
works: [`docs/scenario-lab/`](scenario-lab/README.md); every field:
[data dictionary](data-dictionary.md#scenario-lab).

Besides the five scenario endpoints [above](#endpoints):

| Method and path | Purpose | Success |
|---|---|---|
| `POST /api/v1/scenarios/plan` | Plan a scenario body without saving it: which models apply and why, what each still needs, which changes no included model simulates, the stress cases and the companies the knowledge graph ties to the changes. Stores nothing; `executable` says whether it could run and `issues` say why not. | 200 / 422 |
| `POST /api/v1/scenarios/preview` | The plan and, when it is executable, the results and pathway computed by the same engine — never stored ([below](#plans-and-previews)). | 200 / 422 |
| `POST /api/v1/scenarios/{scenario_id}/duplicate` | A new scenario whose version 1 copies a version of this one (`version`, default the newest; `name`, default "*name* (copy)"), recording where it came from. Returns it with a `Location` header. | 201 / 404 / 422 |
| `GET /api/v1/scenarios/{scenario_id}/versions` | Every version, newest first (a list, not paginated): number, name, spec hash, note, origin, number of executions. | 200 / 404 |
| `GET /api/v1/scenarios/{scenario_id}/versions/{version}` | One version in full: its changes and content. | 200 / 404 |
| `POST /api/v1/scenarios/{scenario_id}/versions/{version}/restore` | Save that version's content as the newest version. Nothing is deleted or rewritten. | 200 / 404 / 409 |
| `GET /api/v1/scenarios/{scenario_id}/plan` | The plan of a saved version (`?version=`, default the newest). | 200 / 404 |
| `POST /api/v1/scenarios/{scenario_id}/executions` | Execute a version (`{"version": n}`, or `{}` for the newest): refused with every reason if it cannot run (422) or when the runner is full (429); otherwise queued and followed at `Location` ([below](#executions)). | 202 / 404 / 422 / 429 |
| `GET /api/v1/scenarios/{scenario_id}/executions` | The scenario's executions of every version, newest first, with their status and headline results. Paginated. | 200 / 404 |
| `GET /api/v1/scenario-executions/{execution_id}` | An execution: its status and every stage with its times, the plan it ran, the Phase 4 runs it stored, headline, hashes, the error if it failed; `poll_after_ms` while it is not final. | 200 / 404 |
| `GET /api/v1/scenario-executions/{execution_id}/results` | Baseline against scenario for every modelled line, the metrics, what is not modelled, each model's key outputs and hashes, the months and their events, the stress cases, the Lab's steps and equations. | 200 / 404 / 409 |
| `GET /api/v1/scenario-executions/{execution_id}/pathways` | The impact pathway: typed nodes and links from each change to each line, grouped by model, and the graph relationships no included model simulates. | 200 / 404 / 409 |
| `GET /api/v1/scenario-executions/{execution_id}/explanation` | What caused a line or metric (`?target=`, default `operating_profit`): the Lab's equation and terms, each change's contribution and, per model, its inputs, equations, worked steps, graph relationships, transmission paths, data snapshot, assumptions and limitations, from the stored runs. 404 when no included model produces the target. | 200 / 404 / 409 / 422 |
| `POST /api/v1/scenario-executions/{execution_id}/cancel` | Ask a queued or running execution to stop ([below](#cancellation)). | 202 / 404 / 409 |
| `POST /api/v1/scenario-executions/{execution_id}/verify` | Re-execute every model from its stored run (never from current data), recombine them and compare both hashes. Stores nothing. | 200 / 404 / 409 |
| `POST /api/v1/scenario-executions/{execution_id}/sensitivity` | A one-at-a-time sensitivity analysis across the execution, stored, with a `Location` header ([below](#sensitivity)). | 201 / 404 / 409 / 422 |
| `GET /api/v1/scenario-executions/{execution_id}/sensitivity` | The execution's analyses, newest first (`{"items": […]}`, not paginated). | 200 / 404 |
| `GET /api/v1/scenario-executions/{execution_id}/sensitivity/{analysis_id}` | One analysis. | 200 / 404 |
| `GET /api/v1/scenario-executions/{execution_id}/analysis-targets` | What the execution can vary — its changes, shared figures and each model's inputs, with values, ranges, units and default variations — the lines and metrics, and the analysis limits (Phase 9, [below](#advanced-analyses)). | 200 / 404 / 409 |
| `POST /api/v1/scenario-executions/{execution_id}/analyses` | Run and store a `monte_carlo` or `joint_sensitivity` analysis, with a `Location` header. | 201 / 404 / 409 / 422 / 429 |
| `GET /api/v1/scenario-executions/{execution_id}/analyses` | The execution's analyses, newest first (`{"items": […]}`, a summary each). | 200 / 404 |
| `GET /api/v1/scenario-executions/{execution_id}/analyses/{analysis_id}` | One analysis: request, configuration, results, hashes. | 200 / 404 |
| `POST /api/v1/scenario-executions/{execution_id}/analyses/{analysis_id}/verify` | Recompute it from the stored runs and request and compare both hashes. Stores nothing. | 200 / 404 / 409 |
| `GET /api/v1/scenario-comparisons` | 2–6 completed executions side by side ([below](#comparisons)). | 200 / 404 / 409 / 422 |
| `GET /api/v1/scenario-templates` | Templates built on implemented models, and those not offered, with the reason. | 200 |
| `GET /api/v1/scenario-templates/{template_id}` | One template: its changes and models, required and optional inputs, validation rules, expected outputs and the scenario body to start from ([below](#templates)). | 200 / 404 |

### Versions

`PUT /api/v1/scenarios/{id}` saves the body as version *n* + 1; no version is ever changed.
A body whose content equals the newest version's (the same spec hash; the `note` is not
part of it) adds no version and returns the scenario as it is. Send `base_version`, the
version the edit started from: if a newer version has been saved since, the save is
refused with **409** instead of overwriting it.

```http
PUT /api/v1/scenarios/{scenario_id}
Content-Type: application/json

{"base_version": 1, "name": "Oil, rupee and rates on Aerisca", "shocks": ["…"], "…": "…"}
```

```http
HTTP/1.1 409 Conflict

{"error": {"code": "conflict",
  "message": "Version 2 was saved after the version you edited (1). Reload the scenario before saving, so no change is lost.",
  "details": [], "request_id": "…"}}
```

`POST …/versions/{version}/restore` saves an earlier version's content as the newest
version (`derived_from: {"kind": "restore", …}`), and `POST …/duplicate` starts a new
scenario from a version (`"kind": "duplicate"`). A scenario that has been executed cannot
be deleted: `DELETE` answers **409** ("This scenario has been executed, so it is kept: its
executions must stay reproducible. Duplicate it to start a new line of work."). A scenario
that has never been executed is deleted with all its versions (204).

### Plans and previews

A **plan** (`POST /api/v1/scenarios/plan` for a body, `GET /api/v1/scenarios/{id}/plan`
for a saved version) lists every Scenario Lab model with its status — `included`,
`blocked`, `available`, `excluded` or `not_applicable` — and its reasons, which included
models simulate each change, and every problem with the field it concerns. It answers 200
for any well-formed body; whether the scenario could run is `executable`, and nothing is
filled in to make it so.

A **preview** (`POST /api/v1/scenarios/preview`) returns the plan and, when the scenario is
executable, the results and pathway, computed by the same code as an execution. It is
computed for each request and **never stored**: no version, execution or run is written,
`stored` is `false` and `results.execution_id` is `null`. It is meant for live values while
editing; execute the scenario to keep a reproducible record. A well-formed body that cannot
be calculated (a numerical limit) is refused with 422. The airline template as the Lab
opens it, before any figure is entered (abridged from
`frontend/tests/fixtures/lab/preview-needs-figures.json`):

```http
POST /api/v1/scenarios/preview
Content-Type: application/json

{"name": "Crude oil shock on an airline", "template_id": "crude_oil_airline",
 "shocks": [{"variable_id": "var_brent_crude", "change_type": "percent_change", "value": "20"}],
 "entity": "company:co_aerisca_airways"}
```

```json
{
  "plan": {
    "executable": false,
    "errors": 7,
    "issues": [
      "…",
      { "code": "required", "message": "Annual revenue is required.", "severity": "error",
        "field": "company.annual_revenue", "model_id": "airline_fuel_cost" },
      "…"
    ],
    "models": [
      { "model_id": "airline_fuel_cost", "mode": "auto", "status": "blocked", "…": "…" },
      "…",
      { "model_id": "crude_linked_costs", "mode": "auto", "status": "available", "…": "…" },
      "…"
    ],
    "…": "…"
  },
  "results": null,
  "pathway": null,
  "stored": false,
  "note": "Computed from the scenario as it stands and not stored. Execute the scenario to keep a reproducible record."
}
```

### Executions

`POST /api/v1/scenarios/{id}/executions` first rebuilds the plan of the version. If the
plan is not executable, the request is refused with **422**, one detail per reason, and
nothing is stored:

```json
{"error": {"code": "validation_error",
  "message": "The scenario cannot be executed as it stands; nothing was stored.",
  "details": [
    "…",
    {"location": "body", "field": "company.annual_revenue", "message": "Annual revenue is required.", "type": "required"},
    "…"
  ], "request_id": "…"}}
```

It then reserves a place on the runner. When every worker is busy and the queue is full,
it answers **429** (`rate_limited`) and stores nothing; try again when an execution has
finished. Otherwise the execution is stored as `queued` and handed to a worker, and the
answer is **202 Accepted** with its `Location`:

```http
POST /api/v1/scenarios/{scenario_id}/executions
Content-Type: application/json

{}
```

```http
HTTP/1.1 202 Accepted
Location: /api/v1/scenario-executions/{execution_id}

{"status": "queued", "stages": [], "plan": null, "runs": [], "headline": [],
 "results_available": false, "poll_after_ms": 400, "…": "…"}
```

Follow it with `GET` at `Location`, waiting `poll_after_ms` milliseconds between requests:
400 while the execution is not final, `null` once it is. The 202 body is the execution as
stored at that moment: normally `queued` with the default thread runner (a worker may
already have moved it on), and already final in `inline` mode. The status moves forward
through the stages and ends `completed`, `failed` or `cancelled`; `stages` records each
stage's start and end as it happens:

| Stage | Work |
|---|---|
| `validating` | The plan is rebuilt; every included model's inputs are validated, stored data resolved and graph relationships confirmed. All or nothing. |
| `simulating` | Each model is executed by the Phase 4 engine; the stress cases are evaluated with the same models and assumptions. |
| `propagating` | Each change is followed through the models' runs, month by month. |
| `aggregating` | The Lab's equations combine the models into lines, metrics, the timeline and the stress cases; each model's run is stored as a Phase 4 run, and the results with their hashes, in one transaction. |

A completed execution of the reference scenario (abridged from
`frontend/tests/fixtures/lab/execution.json`):

```json
{
  "id": "348bd1e1-ea11-4851-bbf6-78389f1512c1",
  "scenario_id": "f5a5b9a1-87b4-4fe8-8dc3-dc2979e4ba8e",
  "version": 1,
  "status": "completed",
  "duration_ms": 95,
  "inputs_hash": "f6de3e60b25529da5405788ece8ab094fcbb2ff65a19f20c96c66310e77cd15b",
  "result_hash": "45fe9f3bf9a5d69b0f49f5e01ae5f6ebf291fc8e3f94635f5d6072c8e8dce622",
  "headline": [
    { "id": "profit_before_tax", "label": "Profit before tax", "change": "-6700000",
      "percent_change": "-17.6315789474", "currency": "INR" },
    "…"
  ],
  "error": null,
  "lab_version": "1.0.0",
  "stages": [
    { "stage": "validating", "started_at": "2026-09-24T03:27:57.129892Z",
      "finished_at": "2026-09-24T03:27:57.160953Z",
      "detail": "Rebuilding the plan and validating every model's inputs" },
    { "stage": "simulating", "…": "…", "detail": "Executing 3 models and 2 stress cases" },
    "…"
  ],
  "plan": { "executable": true, "…": "…" },
  "runs": [
    { "position": 0, "model_id": "airline_fuel_cost", "model_version": "1.1.0",
      "run_id": "39413e33-5972-4106-b818-6a92770b59bc" },
    "…"
  ],
  "results_available": true,
  "poll_after_ms": null,
  "…": "…"
}
```

Each run is an ordinary Phase 4 run: `GET /api/v1/simulations/{run_id}` reads it and
`POST /api/v1/simulations/{run_id}/verify` re-executes it. A failed execution has an
`error` (`code`, `message`, `details`): `plan_blocked` (the plan rebuilt at `validating`
was not executable; `details` lists why), `timeout`, `interrupted`,
`model_version_conflict`, `internal_error` or a numerical code. A failed or cancelled
execution stores no runs and no results.

**Limits.** Executions run on a bounded pool of worker threads in each API process, at
most `RUMIN_SCENARIO_MAX_CONCURRENT` at once with at most `RUMIN_SCENARIO_MAX_QUEUED`
waiting. A request beyond that is refused with 429 before anything is stored, so nothing
waits without bound. When an API process starts, it marks every execution that is not
final as `failed` (`interrupted`). Run **one API process**: with several, each has its own
pool and limits, and a process that starts would also mark another live process's
executions interrupted. That run then stops and stores nothing; every change of state
applies only while an execution is not final, so a final execution never changes.

| Setting | Default | Allowed | Meaning |
|---|---|---|---|
| `RUMIN_SCENARIO_EXECUTION_MODE` | `thread` | `thread`, `inline` | `thread`: executions run on the pool. `inline`: in the request that creates them (the tests use it), so the 202 body is already final. |
| `RUMIN_SCENARIO_MAX_CONCURRENT` | 2 | 1–8 | Executions running at once, per API process. |
| `RUMIN_SCENARIO_MAX_QUEUED` | 8 | 0–64 | Executions waiting for a worker, per API process. |
| `RUMIN_SCENARIO_TIMEOUT_SECONDS` | 20 | 1–120 | Time limit of one execution, checked between stages and between models; past it, the execution fails (`timeout`). |

With the defaults, the eleventh execution requested while ten are running or waiting is
refused:

```json
{"error": {"code": "rate_limited",
  "message": "10 executions are running or waiting (the limit is 10). Try again when one has finished.",
  "details": [], "request_id": "…"}}
```

### Cancellation

`POST /api/v1/scenario-executions/{id}/cancel` sets `cancel_requested` and answers **202**
with the execution. The execution stops at its next checkpoint (between stages and between
models) and ends `cancelled`, with `error.code: "cancelled"`; it stores no runs and no
results. A request that arrives after the last checkpoint cannot stop it: the execution
completes. Cancelling an execution that is already final is refused with **409** (for
example "The execution is already completed; it cannot change.").

### Results, pathways and explanations

Results, pathways, explanations, verification, new sensitivity analyses and comparisons
need a **completed** execution; for any other they answer **409** (for example "The
execution is queued: results exist only for a completed execution."). They are read from
what the execution and its runs stored, so they cannot drift from the calculation. The
results of the reference scenario (abridged from
`frontend/tests/fixtures/lab/results.json`; amounts in INR over 12 months):

```json
{
  "execution_id": "348bd1e1-ea11-4851-bbf6-78389f1512c1",
  "currency": "INR",
  "horizon_months": 12,
  "lines": [
    "…",
    { "id": "profit_before_tax", "label": "Profit before tax", "equation": "AG5",
      "baseline": "38000000", "change": "-6700000", "scenario": "31300000",
      "percent_change": "-17.6315789474", "direction": "down", "effect": "reduces_profit",
      "by_change": { "var_brent_crude": "-5637500", "var_rbi_repo_rate": "-375000",
                     "var_usd_inr": "-687500" },
      "monthly": ["-150000", "-780000", "-655000", "-381666.6666666667", "…"],
      "knowledge": "simulated", "…": "…" }
  ],
  "metrics": [
    { "id": "operating_margin", "baseline": "0.1666666667", "scenario": "0.1422986072",
      "change": "-0.0243680595", "change_unit": "ratio_points", "knowledge": "simulated",
      "…": "…" },
    "…"
  ],
  "not_modelled": [
    { "id": "cash_flow", "label": "Cash flow",
      "reason": "No model covers working capital, tax or investment, so a cash-flow figure would be invented." }
  ],
  "timeline": {
    "events": [
      { "month": 1, "label": "The changes take effect", "model_id": "scenario" },
      { "month": 2, "label": "The crude oil change reaches jet fuel (1-month lag)",
        "model_id": "airline_fuel_cost" },
      "…"
    ],
    "…": "…"
  },
  "stress_cases": [
    { "name": "Half", "scale": "0.5",
      "changes": { "var_brent_crude": "10", "var_usd_inr": "2.5", "var_rbi_repo_rate": "0.25" },
      "lines": ["…"], "metrics": ["…"], "knowledge": "simulated" },
    "…"
  ],
  "note": "Simulated values: deterministic calculations from the changes, figures and assumptions shown, holding everything else constant. They are not forecasts, not guaranteed and not investment advice.",
  "…": "…"
}
```

The **pathway** (`GET …/pathways`) has typed nodes — `change`, `variable`, `context`,
`driver`, `line`, `metric` — and typed links — `applies`, `transmission`, `equation`,
`aggregation`, `cited` — each saying how it was used (`simulation`: `applied`,
`propagated`, `computed`, `aggregated` or `context_only`). A `context_only` link is a
relationship the knowledge graph states and the Lab cites as the reason a model applies; it
carries no value. The graph's other relationships from the changed variables are listed in
`unmodelled`, never followed. A transmission link (abridged from
`frontend/tests/fixtures/lab/pathway.json`):

```json
{ "id": "airline_fuel_cost:variable:var_brent_crude→airline_fuel_cost:variable:var_jet_fuel",
  "kind": "transmission", "simulation": "propagated", "label": "influences (β, lag)",
  "group": "airline_fuel_cost", "rule": "T1", "coefficient": "1", "lag_months": 1,
  "edge": { "edge_key": "e-ea305310288a3f88", "edge_type": "influences",
            "evidence_status": "model_assumption", "is_illustrative": true, "…": "…" },
  "window": { "first_month": 2, "last_month": null }, "…": "…" }
```

The **explanation** (`GET …/explanation?target=`) takes one of `revenue`,
`operating_costs`, `operating_profit`, `interest_expense`, `profit_before_tax`,
`operating_margin` or `interest_coverage` (422 otherwise; 404 when no included model
produces it). **Verification** (`POST …/verify`) re-executes each model from its stored run
— its stored inputs, observations and graph snapshot, never current data — recombines them
and compares the inputs and result hashes (`reproduced`). A model version that is no longer
registered with the same definition cannot be re-executed; the answer says so.

### Stress cases

A version may carry up to five stress cases: alternative magnitudes of **the same
changes**. Each is named (1–60 characters, unique ignoring case) and has **either** a
`scale` — every change × a multiple above 0 and at most 10, at most 4 decimal places —
**or** explicit `changes` for some of the scenario's own changes (the others keep their
value; a stress case cannot add a variable). Every resulting value must satisfy the
variable's change rules, checked when the version is saved (422), and each included
model's input ranges and rules, checked by the plan (a plan error, so the scenario cannot
be executed). An invalid case is refused with its field, never clipped:

```json
{"location": "body", "field": "stress_cases[0].scale",
 "message": "The multiple must be above 0 and at most 10.", "type": "stress_case"}
```

Stress cases are evaluated in the `simulating` stage with the same models and assumptions,
and reported beside the scenario in `results.stress_cases`, each with its own lines and
metrics. They are not ranked.

### Sensitivity

`POST /api/v1/scenario-executions/{id}/sensitivity` analyses a completed execution **one
quantity at a time**. Each chosen quantity — a change (`change:<variable>`), a figure
shared by every model (`shared:<input>`, e.g. `shared:fx_rate`) or one model's input or
assumption (`model:<model>:<input>`) — is moved on its own while everything else keeps the
execution's value; every model that uses it is re-evaluated and the chosen `metric` is
recombined: a line's change or a metric's value, by default profit before tax when interest
is modelled and operating profit otherwise. The quantities are then ranked by the spread
they cause. This is sensitivity analysis, **not** a stochastic or Monte Carlo simulation:
no probabilities are involved, and a spread says how much the result depends on a quantity,
not how likely any value is.

Each item names its `target` and a `mode`: `default` (the variation the model defines for
that input), `absolute` or `relative` (± `step`; a relative step must be below 100 %), or
`values` (up to 7 explicit values). An empty body analyses the scenario's changes and then
the models' default assumptions, up to eight. At most 8 quantities, 7 points each and 60
evaluations, within 10 seconds: a request beyond these limits is refused with 422
(`sensitivity_limit`). A point outside an input's range, or one that breaks a model's own
rules, is skipped with the reason, never clipped. The analysis is stored and never
changed; 409 if a model version the execution used is no longer registered with the same
definition. Since Phase 9 each analysis records its `method_version`: `1.1.0` passes the varied
revenue, operating costs and interest expense to the margins and coverage; an analysis stored
before (`1.0.0`) that ranked operating margin or interest coverage by one of them carries
`caveats` saying the metric did not move with it.

```http
POST /api/v1/scenario-executions/348bd1e1-ea11-4851-bbf6-78389f1512c1/sensitivity
Content-Type: application/json

{"metric": null, "inputs": []}
```

```http
HTTP/1.1 201 Created
Location: /api/v1/scenario-executions/348bd1e1-ea11-4851-bbf6-78389f1512c1/sensitivity/79ea15c4-f849-47de-8ea2-a29b7cec7d7d

{
  "id": "79ea15c4-f849-47de-8ea2-a29b7cec7d7d",
  "metric": "profit_before_tax",
  "metric_kind": "line_change",
  "base": "-6700000",
  "items": [
    { "target": "change:var_brent_crude", "label": "Crude oil price change", "kind": "change",
      "base_value": "20", "mode": "absolute", "step": "10",
      "points": [
        { "role": "low", "value": "10", "metric": "-3812500", "delta": "2887500", "skipped": null },
        { "role": "high", "value": "30", "metric": "-9587500", "delta": "-2887500", "skipped": null }
      ],
      "range": { "low": "-9587500", "high": "-3812500", "spread": "5775000" }, "…": "…" },
    "…"
  ],
  "ranking": [
    { "target": "change:var_brent_crude", "label": "Crude oil price change", "spread": "5775000" },
    { "target": "model:airline_fuel_cost:fare_pass_through",
      "label": "Fare pass-through (Airline fuel cost)", "spread": "3940000" },
    "…"
  ],
  "evaluations": 15,
  "method": "one_at_a_time",
  "note": "One quantity is moved at a time while everything else keeps the execution's value. The spread shows how much the result depends on it, not how likely any value is. This is sensitivity analysis, not a stochastic (Monte Carlo) simulation.",
  "…": "…"
}
```

### Advanced analyses

Phase 9 ([advanced analysis](scenario-lab/advanced-analysis.md)). `POST
/api/v1/scenario-executions/{id}/analyses` takes one of two bodies, told apart by `kind`.
**Two quantities together** — a grid with the interaction term, no probability involved:

```http
POST /api/v1/scenario-executions/{id}/analyses
Content-Type: application/json

{"kind": "joint_sensitivity", "metric": "operating_profit",
 "rows": {"target": "change:var_brent_crude"},
 "columns": {"target": "change:var_usd_inr", "mode": "values", "values": ["0", "10"]}}
```

Each axis is an item as in [sensitivity](#sensitivity) (its default variation, a step, or
listed values); the executed value is always added and an axis holds at most seven values,
so at most 7 × 7 cells, within 10 seconds. The result
holds `rows` and `columns` (with their values), `cells[row][column]` — `metric`, `delta`
(from the execution), `interaction`, `skipped` (the reason, or `null`) — and a `summary`
(largest interaction and change, `additive`, `tolerance`, skipped cells).

**Monte Carlo** — draws from distributions the user states:

```http
POST /api/v1/scenario-executions/{id}/analyses
Content-Type: application/json

{"kind": "monte_carlo", "metric": "profit_before_tax", "draws": 500, "seed": 20260925,
 "threshold": "-10000000",
 "quantities": [
   {"target": "change:var_brent_crude",
    "distribution": {"kind": "triangular", "low": "-10", "mode": "20", "high": "60"}},
   {"target": "change:var_usd_inr",
    "distribution": {"kind": "uniform", "low": "0", "high": "10"}},
   {"target": "model:floating_rate_interest:repo_repricing_lag",
    "distribution": {"kind": "discrete", "values": ["0", "3", "6"], "weights": ["1", "2", "1"]}}
 ]}
```

`draws` 100–2,000 (default 500); `seed` 0 to 2⁵³ − 1, chosen and recorded when `null`;
`threshold` optional; 1–8 quantities, one distribution each (`uniform`, `triangular`, or
`discrete` with 2–12 values and optional positive weights). Every endpoint must lie in the
input's range with its decimals, and a whole-month input takes a discrete distribution; a
problem is refused with 422 (`analysis_limit`, or `invalid_number` for a value that is not a
decimal) naming the field, e.g. `quantities[0]`. The result (`monte_carlo`) holds the
`accepted` and `rejected` draws, `rejections` by rule with an example, the `quantities`
(distribution, its mean and standard deviation, the accepted draws' mean, the rank
correlation), a `summary` (mean, standard deviation, standard error, minimum, maximum,
percentiles with intervals and exact coverage, shares), the `histogram`, `convergence`
(checkpoints, the two halves, `halves_flagged`), every line and metric in `outputs`, and
`notes`. Fewer than 100 accepted draws, or a run past 20 seconds: 422, nothing stored.

Every analysis returns its `request`, a `config` (the execution's result hash; each run's
model, version, definition hash, run id, inputs hash, graph build and fingerprint; versions;
generator, sampler version, seed, draws), `evaluations`, `duration_ms`, `inputs_hash`,
`result_hash` and a `note` saying what kind of analysis it is. `POST …/verify` answers
`reproduced`, whether each hash matches, both result hashes and a message. At most two
analyses compute at once per API process: a third is refused with 429 (`rate_limited`),
nothing stored. 409: the execution has not completed, or a model version it used is no
longer registered with the same definition.

### Comparisons

`GET /api/v1/scenario-comparisons?execution_id=…&execution_id=…` compares 2–6 completed
executions (`reference`: the one to difference against, by default the first). It returns
their changes and models, every line and metric side by side, the inputs and assumptions
that differ, the pathway links that differ and each execution's latest sensitivity
ranking. Differences against the reference are computed only between executions with the
same currency and horizon (`comparable`); the others are shown side by side, not
differenced. **A comparison never ranks or recommends executions**: which result is
preferable depends on an objective the user has not stated. It is computed for each request
and not stored. Fewer than two different executions or more than six, or a `reference` that
is not one of them: 422; an unknown execution: 404; one that has not completed: 409.

The reference execution against the same scenario with the Brent change alone and the
airline model only (abridged from `frontend/tests/fixtures/lab/comparison.json`):

```json
{
  "reference": "348bd1e1-ea11-4851-bbf6-78389f1512c1",
  "comparable": { "348bd1e1-ea11-4851-bbf6-78389f1512c1": true,
                  "7aefb335-44f1-4765-9de7-979353449061": true },
  "lines": [
    { "id": "revenue", "label": "Revenue", "values": [
        { "execution_id": "348bd1e1-ea11-4851-bbf6-78389f1512c1", "change": "6925000",
          "modelled": true, "difference": null, "…": "…" },
        { "execution_id": "7aefb335-44f1-4765-9de7-979353449061", "change": "3500000",
          "modelled": true, "difference": { "absolute": "-3425000", "percent": "-49.4584837545" },
          "…": "…" } ] },
    "…"
  ],
  "note": "Executions are shown side by side and differenced against the reference only when their currency and horizon match. Nothing is ranked or recommended: which result is preferable depends on an objective you have not stated.",
  "…": "…"
}
```

### Templates

`GET /api/v1/scenario-templates` lists seven templates, each built on implemented models —
`crude_oil_airline`, `jet_fuel_airline`, `rupee_depreciation`, `policy_rate_rise`,
`crude_linked_costs`, `natural_gas` and `oil_rupee_rates` — with the companies the
knowledge graph suggests for each, and under `unsupported` the templates that are not
offered, with the reason (`demand` and `supply_chain`: no registered model simulates
them). `GET /api/v1/scenario-templates/{template_id}` adds the required and optional
inputs, validation rules and expected outputs, all derived from the models' definitions,
and `scenario`: a body to start from, with the template's changes, models and stress cases
and no company figures (RUMIN never fills those in). An unknown or unsupported template
answers 404.

## Financial intelligence

Structured, explainable findings from what RUMIN stores: observations, the knowledge graph,
Scenario Lab executions and their runs (Phase 6). Every **insight** is produced by a
documented rule and carries its evidence chain (ordered steps, each with a basis and
references to stored records), facts, entities, relationships, period, models, assumptions,
limitations, sources, next steps, and an evidence grade: the weakest step, not a
probability. Reads compute from the current store and **write nothing**. Stored analyses are
**append-only** (`DELETE` answers 405). No text is generated, nothing is ranked or
recommended, and simulated values say they are not forecasts. How it works:
[`docs/intelligence/`](intelligence/README.md); every field:
[data dictionary](data-dictionary.md#financial-intelligence).

| Method and path | Purpose | Success |
|---|---|---|
| `GET /api/v1/intelligence/overview` | The workspace: every finding in order (observed data, simulations, relationships and exposure, coverage), counts by grade and kind, the gathered next steps, the exposure matrix (the first 200 companies by name × variables), observed series with their signals, instruments, relationship changes, the latest simulated impact per company, and coverage (with `truncated`). | 200 / 422 |
| `GET /api/v1/intelligence/insights` | The workspace's insights, or one entity's (`entity`), filtered by `kind`, `rule` and `grade` (at least this grade). `{scope, subject, build, thresholds, items, total}`. | 200 / 404 / 422 |
| `GET /api/v1/intelligence/changes` | What changed, each in its own list: observed changes that meet their thresholds, revisions, relationship changes between the latest two builds, and execution changes (simulated), with notes. | 200 / 422 |
| `GET /api/v1/intelligence/methods` | The modules (question, inputs, method, limitations), the signal definitions, the insight rules, the thresholds with defaults, bounds and reasons, the evidence grades and their statements. | 200 |
| `GET /api/v1/intelligence/entities` | Companies (the first 200 by name) and industries with their stated exposure (paths, variables, channels, directness, weakest evidence) and each company's latest simulated headline; `kind` filters. | 200 / 422 |
| `GET /api/v1/intelligence/entities/{entity_key}` | The dossier of a company or industry: its exposure map, stored executions, the drivers of the latest one and of the previous one of the same scenario, related series with their signals, model interpretations of observed changes (and those not interpreted, with the reason), signals, and every insight. `evidence=evidence_backed` keeps only cited relationships. | 200 / 404 / 422 |
| `GET /api/v1/intelligence/entities/{entity_key}/brief` | The entity brief `rumin.intelligence.brief/1`: structured facts with references and narration rules, for a language-model analyst ([brief](intelligence/brief.md)). | 200 / 404 / 422 |
| `GET /api/v1/intelligence/entities/{entity_key}/exposure` | The exposure map alone: paths (direct, via the industry, upstream), counterparties, context, series coverage, flagged edges not used. | 200 / 404 / 422 |
| `GET /api/v1/intelligence/entities/{entity_key}/signals` | Exposure breadth, dependency and scenario sensitivity, each with its definition, method, inputs, period, thresholds, evidence and limitations. | 200 / 404 / 422 |
| `GET /api/v1/intelligence/entities/{entity_key}/drivers` | The latest completed execution's stored contributions per change (amounts, shares of the change, points of the baseline, effects per unit, unattributed), the stored sensitivity ranking, assumptions, entered figures, what is not modelled. | 200 / 404 / 422 |
| `GET /api/v1/intelligence/variables/{variable_key}/exposure` | The companies the graph states the variable reaches, found by walking downstream from it through the whole graph: the first 200 by name with their paths through it, the `total` and whether the list is `truncated`. | 200 / 404 / 422 |
| `GET /api/v1/intelligence/series/{series_id}` | A stored series: its latest values (at most 400), changes, detected changes, trend, volatility, unusual change and revisions; for a series recorded as a related measure, the variable and the companies it reaches (`reached`, the first 200 by name; `reached_total`). | 200 / 404 / 422 |
| `GET /api/v1/intelligence/instruments/{instrument_id}` | The same for an instrument's closing prices, per price dataset (sources are never blended). | 200 / 404 / 422 |
| `POST /api/v1/intelligence/analyses` | Compute an entity or workspace analysis and store it with its thresholds, a fingerprint of what it read and hashes of both. Returns it with a `Location` header. | 201 / 404 / 422 |
| `GET /api/v1/intelligence/analyses` | Stored analyses, newest first; `scope` and `entity` filter. Paginated. | 200 / 422 |
| `GET /api/v1/intelligence/analyses/{analysis_id}` | One stored analysis exactly as stored, with `freshness`: `current`, or `stale` with what changed since (`graph`, `data`, `executions`, `engine_version`, `subject`, `scope`). | 200 / 404 |

`entity_key` is a graph key (`company:co_aerisca_airways`, `industry:ind_air_transport`); any
other node type answers 422. `variable_key` must be an economic variable
(`variable:var_usd_inr`).

### Thresholds

Every read that tests values accepts threshold overrides as query parameters:
`relative_change_percent`, `point_change`, `price_move_percent`, `anomaly_score`,
`trend_significance` (0.10, 0.05 or 0.01), `volatility_high_percentile`,
`dependency_share_percent`, `min_history`, `window`. A stored analysis takes them in its body
under `thresholds` (at most 20). Every result returns the thresholds it used, defaults
included. Invalid values are all reported at once, as a 422 with code `validation_error`
and one detail per problem (`location` `query` or `body`, `field` the threshold's name,
prefixed `thresholds.` in a body, `type` `invalid_threshold`):

```json
{"error": {"code": "validation_error", "message": "Some thresholds are invalid.",
  "details": [{"location": "query", "field": "relative_change_percent",
               "message": "Change in a level or exchange rate must be between 0.1 and 100 (percent).",
               "type": "invalid_threshold"}], "request_id": "…"}}
```

Defaults, bounds and reasons: `GET /api/v1/intelligence/methods`, or
[signals and thresholds](intelligence/signals.md#thresholds).

### An insight

Abridged, from the sample's dossier of the fictional Aerisca Airways:

```json
{
  "id": "ins-…", "rule": "E01", "kind": "exposure",
  "headline": "Aerisca Airways is exposed to Brent crude oil price",
  "statement": "The knowledge graph states that Brent crude oil price reaches Aerisca Airways's costs through Jet fuel price (U.S. Gulf Coast) (assumed to transmit), which reaches it through its industry, Air transport.",
  "subject": {"kind": "graph_node", "id": "company:co_aerisca_airways", "label": "Aerisca Airways"},
  "period": {"kind": "graph_build", "label": "Build #1", "start": null, "end": null},
  "evidence": {"grade": "assumed", "conditional_on_simulation": false, "includes_observations": false,
               "statement": "Rests on at least one relationship recorded as a model assumption: …",
               "weakest_step": 1},
  "chain": [
    {"basis": "record", "text": "Knowledge-graph build #1", "refs": [{"kind": "graph_build", "id": "1", "label": "Build #1"}]},
    {"basis": "relationship", "text": "Brent crude oil price influences Jet fuel price (U.S. Gulf Coast)",
     "evidence_status": "model_assumption", "refs": [{"kind": "graph_edge", "id": "e-…"}]},
    …
  ],
  "facts": [{"label": "Paths", "value": "1", "unit": "count", "basis": "calculation"}, …],
  "limitations": ["… A connection is not evidence of causation.", …],
  "next_steps": [{"action": "find_evidence", "text": "Recorded as model assumptions: “…”. Look for a cited source before relying on them.", "target": {"kind": "graph_edge", "id": "e-…"}}]
}
```

Next-step actions are `run_template`, `run_scenario`, `run_sensitivity`, `ingest_series`,
`find_evidence`, `model_gap` and `review_revision` ([rules](intelligence/rules.md#next-steps)).

### Stored analyses

`POST /api/v1/intelligence/analyses` takes `{"scope": "entity", "entity": "company:…"}` or
`{"scope": "workspace"}`, and optionally `thresholds`, `evidence` and `label` (at most 200
characters). An entity analysis without `entity`, or a workspace analysis with one, is
refused (422); an unknown entity answers 404; nothing is stored in either case. The response
is the analysis as stored: `entity` (the dossier) or `workspace` (the overview), with
`thresholds`, `inputs` (the fingerprint), `inputs_hash`, `result_hash`, `insight_count`,
`duration_ms` and `freshness`. Reading it back never recomputes it
([stored analyses](intelligence/stored-analyses.md)).

## AI Analyst

Questions answered from RUMIN's records through the Analyst's read-only tools, each figure
citing the evidence it came from (Phase 7). A **session** is a conversation; a **turn** is one
question and its answer. Asking answers `202` with the turn **queued**; read it again every
`poll_after_ms` until its `status` is `completed` or `failed`. Its tool calls appear as they
are recorded. The Analyst writes only its own conversations: it never saves or executes a
scenario. How it works: [`docs/analyst/`](analyst/README.md).

| Method and path | Purpose | Success |
|---|---|---|
| `GET /api/v1/analyst/capabilities` | The provider (`configured`, `active`, `ready`, the `reason` it is not ready, the `model` when one is configured), the 17 tools, the limits (and tokens used today), suggested questions built from the data, the kinds of knowledge and notes on what the Analyst does not do. Never the key. | 200 |
| `GET /api/v1/analyst/sessions` | Conversations, most recently updated first, each with its title, number of questions and its latest question. Paginated (`limit`, `offset`). | 200 |
| `POST /api/v1/analyst/sessions` | Start a conversation; `{"title": …}` is optional (≤ 120 characters; the first question titles it otherwise). Returns it with a `Location` header. | 201 / 422 |
| `GET /api/v1/analyst/sessions/{session_id}` | One conversation: its focus and every turn, in order, with answers and tool calls. | 200 / 404 |
| `PUT /api/v1/analyst/sessions/{session_id}` | Rename: `{"title": …}` (1–120 characters). | 200 / 404 / 422 |
| `DELETE /api/v1/analyst/sessions/{session_id}` | Delete a conversation and everything in it; refused while one of its questions is being answered. | 204 / 404 / 409 |
| `POST /api/v1/analyst/sessions/{session_id}/turns` | Ask: `{"question": …}` (1 to `RUMIN_ANALYST_MAX_QUESTION_CHARS` characters, 2,000 by default). Answers `202` with the queued turn and a `Location` header. `409` while the previous question is being answered or when the conversation is full; `429` (`rate_limited`) when every worker is busy and the queue is full, before anything is stored. | 202 / 404 / 409 / 422 / 429 |
| `GET /api/v1/analyst/sessions/{session_id}/turns/{turn_id}` | One turn: `status` (`queued`, `running`, `completed`, `failed`), the answer when completed, the error when failed (a fixed message, never internals), the tool calls so far, the provider that answered and any fallback, token usage, timings and `poll_after_ms` while not final. | 200 / 404 |

### An answer

Abridged, from the frontend's fixtures (the grounded composer on the sample network, with the
REFERENCE scenario's HYPOTHETICAL figures):

```json
{
  "status": "answered",
  "intent": "what_if",
  "headline": "Operating profit −5,500,000 INR under Brent crude oil price +20 % (preview, not stored)",
  "blocks": [
    {"type": "text", "role": "answer",
     "text": "Operating costs: +9,000,000 INR (+3.60 %) against a baseline of 250,000,000 INR [E2]."},
    {"type": "scenario", "status": "preview", "title": "Preview: Brent crude oil price +20 %",
     "lines": [{"id": "operating_costs", "label": "Operating costs", "currency": "INR",
                "baseline": "250000000", "change": "9000000", "percent_change": "3.6",
                "citations": ["E2"]}, …],
     "draft": {"name": "Analyst preview", "shocks": [{"variable_id": "var_brent_crude", …}], …},
     "notes": ["Computed on request and not stored. …", "Not modelled: Interest expense, Profit before tax. …"]},
    {"type": "notice", "kind": "not_stored", "title": "Computed now, not stored", "text": "…"}
  ],
  "evidence": [
    {"id": "E2", "tool": "preview_scenario", "call": 1, "kind": "preview",
     "title": "Preview for Aerisca Airways: Brent crude oil price 20 %",
     "period": "12 months simulated", "currency": "INR", "models": ["airline_fuel_cost 1.1.0"],
     "values": {"operating_costs.change": "9000000", "operating_costs.percent_change": "3.6", …}, …}
  ],
  "follow_ups": ["What about 30%?", …],
  "provider": "grounded",
  "grounding": {"passed": true, "figures_checked": 14, "citations_checked": 12, "problems": []}
}
```

Block types are `text` (roles `answer`, `detail`, `interpretation`, `general`, `policy`),
`table`, `series`, `paths`, `scenario` (statuses `stored`, `preview`, `plan`), `notice` (kinds
`missing_data`, `assumption`, `limitation`, `conflict`, `policy`, `not_stored`,
`illustrative`, `fallback`) and `clarification`. Answer statuses are `answered`, `partial`,
`no_data`, `clarification`, `declined`, `unsupported` and `failed`. Every value is an exact
decimal string.

## Provider data example

```http
GET /api/v1/economic-series/wb-ind-fp-cpi-totl-zg/observations?start=2022-01-01
```

```json
{
  "items": [
    {
      "id": 812,
      "period_label": "2023",
      "period_start": "2023-01-01",
      "period_end": "2023-12-31",
      "value": "5.649",
      "raw_value": "5.649",
      "status": "reported",
      "quality_status": "validated",
      "provider_flags": null,
      "revision": 1,
      "is_current": true,
      "superseded_at": null,
      "retrieved_at": "2026-09-23T13:01:06Z",
      "last_confirmed_at": "2026-09-23T13:01:06Z",
      "retrieved_by_job_id": "db8de720-d69c-45c6-a23f-f3973546ec40",
      "capture_id": 17
    }
  ],
  "total": 1, "limit": 100, "offset": 0,
  "series": { "id": "wb-ind-fp-cpi-totl-zg", "unit": "% change on previous year", "frequency": "annual", "…": "…" },
  "dataset": { "id": "worldbank-wdi", "license": "CC BY 4.0", "attribution": "The World Bank: …", "…": "…" }
}
```

The numbers in this example illustrate the format only; they are not World Bank values.

## Errors

Every error — validation, not found, wrong method, oversized body, database outage,
unexpected crash — uses the same envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The scenario inputs are invalid.",
    "details": [
      {
        "location": "body",
        "field": "shocks[0].value",
        "message": "The change must be greater than -100 %.",
        "type": "invalid_change"
      }
    ],
    "request_id": "40244fdf784f47ba8591853f2a25064f"
  }
}
```

`details` lists every problem found (not just the first), with `field` in a path notation
a form can map back to its inputs (`name`, `shocks[1].variable_id`, …) and `location`
saying where the value came from (`body`, `query`, `path`).

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | Malformed request that is not a validation problem |
| 404 | `not_found` | Unknown route or ID |
| 405 | `method_not_allowed` | E.g. `PATCH /api/v1/network`, `DELETE /api/v1/simulations/{id}`, `DELETE /api/v1/scenario-executions/{id}` |
| 409 | `conflict` | The request conflicts with stored state: a scenario save based on an older version than the newest (`base_version`) or made at the same moment as another save; deleting an executed scenario; cancelling a final execution; results, pathways, explanations, verification, sensitivity analysis or comparison of an execution that has not completed; a sensitivity analysis of an execution whose model version is no longer registered with the same definition; a simulation model version whose code no longer matches its stored definition |
| 413 | `payload_too_large` | Body larger than `RUMIN_MAX_REQUEST_BODY_BYTES` (64 KiB) |
| 422 | `validation_error` | Invalid body, query or path values, invalid JSON, wrong content type, unknown fields; a scenario that cannot be executed as it stands |
| 429 | `rate_limited` | `POST /api/v1/scenarios/{id}/executions` while every execution worker is busy and the queue is full; `POST /api/v1/scenario-executions/{id}/analyses` while two analyses are computing; nothing is stored ([Scenario Lab](#executions), [advanced analyses](#advanced-analyses)) |
| 500 | `internal_error` | Unexpected failure. The response never contains a stack trace; the log has it under the request ID. |
| 503 | `service_unavailable` | The database is unreachable |

The codes 401 and 403 (`unauthorized`, `forbidden`) are reserved in the envelope for later
phases; no endpoint returns them yet.

## Security headers and limits

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and
`Referrer-Policy: no-referrer`; JSON responses also carry
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. CORS allows only the
origins listed in `RUMIN_CORS_ORIGINS`, never `*` and never with credentials. See
[security.md](security.md).

There is **no authentication** yet: anyone who can reach the API can read all stored data,
create scenarios (and delete those never executed), start or cancel scenario executions
(bounded per process, [above](#executions)), and create simulation runs, sensitivity
analyses, grids and Monte Carlo analyses (bounded, two at once per process). Runs, analyses and final executions cannot be changed, and none of them can be
deleted through the API. Do not expose it beyond your own machine.
