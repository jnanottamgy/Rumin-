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
| IDs | Reference-data IDs are readable slugs with a kind prefix: `co_…`, `ind_…`, `cty_…`, `var_…`, `rel_…` (pattern `^[a-z]{2,4}_[a-z0-9_]{2,59}$`). Datasets, series and instruments have lowercase slugs (`worldbank-wdi`, `wb-ind-fp-cpi-totl-zg`, `xnse-reliance`). Scenario and ingestion-job IDs are UUIDs. Knowledge-graph keys are `type:record-id` for nodes and `e-` plus 16 hex characters for edges ([below](#knowledge-graph)). Path and query IDs are validated against their pattern (422 otherwise). |
| Data values | Observation values, prices and review ranges are **exact decimal strings in plain notation** (`"5.649"`, `"0.000000000000000001"`), never JSON numbers, so no digit is lost to floating point. A missing value is `null`, never `0`. |
| Dates | Calendar dates (periods, trade dates, the provider's last update) are `YYYY-MM-DD`; they have no time zone. |
| Pagination | List endpoints take `limit` (1–500, default 100) and `offset` (default 0) and return `{items, total, limit, offset}`. |
| Time | Timestamps are ISO 8601 in UTC, e.g. `2026-09-23T11:46:58.387307Z`. |
| Knowledge labels | Relationships carry `epistemic_category: "assumption"` and `evidence_level`; scenario shocks carry `epistemic_category: "scenario_input"`; economic series carry `epistemic_category: "observation"`. Simulation inputs carry `knowledge` (`scenario_input`, `historical_data`, `user_input`, `assumption`, `setting`) and `source` (`user`, `default`, `stored_observation`); simulation outputs carry `kind` (`derived` or `simulated`). |
| Request IDs | Every response has an `X-Request-ID` header (a safe incoming value is reused, otherwise one is generated). Error bodies repeat it, and every log line for the request includes it. |

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
| `GET /api/v1/scenarios` | Saved scenario drafts, most recently updated first. | 200 |
| `POST /api/v1/scenarios` | Create a draft. Returns it with a `Location` header. | 201 |
| `GET /api/v1/scenarios/{scenario_id}` | One scenario. | 200 / 404 |
| `PUT /api/v1/scenarios/{scenario_id}` | Replace a scenario's name, description and shocks. | 200 / 404 |
| `DELETE /api/v1/scenarios/{scenario_id}` | Delete a scenario. | 204 / 404 |
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

Scenario **drafts** still cannot be run: they have `status: "draft"` and `latest_run:
null` until the Scenario Lab connects them to the engine (Phase 5). Models are run through
the separate, append-only [simulation endpoints](#simulation).

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

A scenario is a name, an optional description and 1–10 **shocks** — changes to economic
variables:

```json
{
  "name": "Oil price shock",
  "description": "Brent crude rises 30 %.",
  "shocks": [
    { "variable_id": "var_brent_crude", "change_type": "percent_change", "value": 30, "note": "" }
  ]
}
```

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
| Each variable at most once per scenario | Two changes to one variable are ambiguous; combine them. |
| Names 1–120 characters, no control characters; description ≤ 2,000; note ≤ 500 | Storage and display limits. |

Example exchange:

```http
POST /api/v1/scenarios
Content-Type: application/json

{"name": "Oil price shock", "description": "Brent crude rises 30 %.",
 "shocks": [{"variable_id": "var_brent_crude", "change_type": "percent_change", "value": 30}]}
```

```http
HTTP/1.1 201 Created
Location: /api/v1/scenarios/fc32a422-91e1-4d5f-8797-ddedfcbf79f9
X-Request-ID: 8bea91f6743f4e19aaa1313c4c8255c6

{
  "id": "fc32a422-91e1-4d5f-8797-ddedfcbf79f9",
  "name": "Oil price shock",
  "description": "Brent crude rises 30 %.",
  "status": "draft",
  "shocks": [
    { "variable_id": "var_brent_crude", "change_type": "percent_change", "value": 30.0,
      "note": "", "epistemic_category": "scenario_input" }
  ],
  "latest_run": null,
  "created_at": "2026-09-23T11:46:58.387307Z",
  "updated_at": "2026-09-23T11:46:58.387317Z"
}
```

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
| 405 | `method_not_allowed` | E.g. `PATCH /api/v1/network`, `DELETE /api/v1/simulations/{id}` |
| 409 | `conflict` | A simulation model version whose code no longer matches its stored definition |
| 413 | `payload_too_large` | Body larger than `RUMIN_MAX_REQUEST_BODY_BYTES` (64 KiB) |
| 422 | `validation_error` | Invalid body, query or path values, invalid JSON, wrong content type, unknown fields |
| 500 | `internal_error` | Unexpected failure. The response never contains a stack trace; the log has it under the request ID. |
| 503 | `service_unavailable` | The database is unreachable |

The codes 401, 403 and 429 (`unauthorized`, `forbidden`, `rate_limited`) are reserved in
the envelope for later phases; no endpoint returns them yet.

## Security headers and limits

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and
`Referrer-Policy: no-referrer`; JSON responses also carry
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. CORS allows only the
origins listed in `RUMIN_CORS_ORIGINS`, never `*` and never with credentials. See
[security.md](security.md).

There is **no authentication** yet: anyone who can reach the API can read all stored data,
create and delete scenarios, and create simulation runs and analyses (which cannot be
changed or deleted). Do not expose it beyond your own machine.
