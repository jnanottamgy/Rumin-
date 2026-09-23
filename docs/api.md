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
| IDs | Reference-data IDs are readable slugs with a kind prefix: `co_…`, `ind_…`, `cty_…`, `var_…`, `rel_…` (pattern `^[a-z]{2,4}_[a-z0-9_]{2,59}$`). Scenario IDs are UUIDs. |
| Pagination | List endpoints take `limit` (1–500, default 100) and `offset` (default 0) and return `{items, total, limit, offset}`. |
| Time | Timestamps are ISO 8601 in UTC, e.g. `2026-09-23T11:46:58.387307Z`. |
| Knowledge labels | Relationships carry `epistemic_category: "assumption"` and `evidence_level`; scenario shocks carry `epistemic_category: "scenario_input"`. |
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
| `GET /api/v1/system` | Service version and environment, database and migration state, dataset provenance and counts, and a list of capabilities marked available or planned (with the phase). | 200 |

There is deliberately **no endpoint that runs or simulates a scenario**: no simulation
engine exists yet (Phase 4). Scenarios have `status: "draft"` and `latest_run: null`, and
the API never returns a simulated value.

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
are reserved in the envelope for later phases; no Phase 1 endpoint returns them.

## Security headers and limits

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and
`Referrer-Policy: no-referrer`; JSON responses also carry
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. CORS allows only the
origins listed in `RUMIN_CORS_ORIGINS`, never `*` and never with credentials. See
[security.md](security.md).

There is **no authentication** in Phase 1: anyone who can reach the API can create and
delete scenarios. Do not expose it beyond your own machine.
