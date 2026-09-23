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
| IDs | Reference-data IDs are readable slugs with a kind prefix: `co_…`, `ind_…`, `cty_…`, `var_…`, `rel_…` (pattern `^[a-z]{2,4}_[a-z0-9_]{2,59}$`). Datasets, series and instruments have lowercase slugs (`worldbank-wdi`, `wb-ind-fp-cpi-totl-zg`, `xnse-reliance`). Scenario and ingestion-job IDs are UUIDs. Path and query IDs are validated against their pattern (422 otherwise). |
| Data values | Observation values, prices and review ranges are **exact decimal strings in plain notation** (`"5.649"`, `"0.000000000000000001"`), never JSON numbers, so no digit is lost to floating point. A missing value is `null`, never `0`. |
| Dates | Calendar dates (periods, trade dates, the provider's last update) are `YYYY-MM-DD`; they have no time zone. |
| Pagination | List endpoints take `limit` (1–500, default 100) and `offset` (default 0) and return `{items, total, limit, offset}`. |
| Time | Timestamps are ISO 8601 in UTC, e.g. `2026-09-23T11:46:58.387307Z`. |
| Knowledge labels | Relationships carry `epistemic_category: "assumption"` and `evidence_level`; scenario shocks carry `epistemic_category: "scenario_input"`; economic series carry `epistemic_category: "observation"`. |
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

There is also **no endpoint that runs or simulates a scenario**: no simulation engine exists
yet (Phase 4). Scenarios have `status: "draft"` and `latest_run: null`, and the API never
returns a simulated value.

### Structural links in `/api/v1/network`

Economic relationships are curated records (`category: "economic"`). The network also
contains **structural links** (`category: "structural"`) derived at query time from entity
fields — `in_industry` (company → its industry), `domiciled_in` (company → its country) and
`measured_for` (variable → its country). They are facts about how the sample records are
classified, not economic assumptions, and have no polarity, strength or evidence level.

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
| 405 | `method_not_allowed` | E.g. `PATCH /api/v1/network` |
| 413 | `payload_too_large` | Body larger than `RUMIN_MAX_REQUEST_BODY_BYTES` (64 KiB) |
| 422 | `validation_error` | Invalid body, query or path values, invalid JSON, wrong content type, unknown fields |
| 500 | `internal_error` | Unexpected failure. The response never contains a stack trace; the log has it under the request ID. |
| 503 | `service_unavailable` | The database is unreachable |

The codes 401, 403, 409 and 429 (`unauthorized`, `forbidden`, `conflict`, `rate_limited`)
are reserved in the envelope for later phases; no endpoint returns them yet.

## Security headers and limits

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and
`Referrer-Policy: no-referrer`; JSON responses also carry
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. CORS allows only the
origins listed in `RUMIN_CORS_ORIGINS`, never `*` and never with credentials. See
[security.md](security.md).

There is **no authentication** yet: anyone who can reach the API can read all stored data
and create and delete scenarios. Do not expose it beyond your own machine.
