# Testing

| Suite | Tool | Tests | Runs against | Command |
|---|---|---|---|---|
| Backend | pytest | 125 | the FastAPI app with a real, migrated database (SQLite; PostgreSQL optional) | `uv run pytest` in `backend/` |
| Frontend unit and pages | Vitest + Testing Library (jsdom) | 117 | the real route table, with `fetch` replaced by a fake API serving recorded responses | `npm test` in `frontend/` |
| Integration | Vitest (Node) | 19 | a live API: the frontend's real service layer over HTTP | `npm run test:integration` with `RUMIN_API_URL` |
| End-to-end smoke | `scripts/smoke_test.sh` | — | fresh database → migrate → seed → start API → integration suite | `make smoke` |

`make check` runs linting, formatting checks, type checks, both unit suites and the
OpenAPI snapshot check — everything CI runs except the smoke test. CI
(`.github/workflows/ci.yml`) runs all of it, the backend suite a second time on
PostgreSQL 16, and the smoke test.

## Backend (`backend/tests/`)

Each test gets an application built by `create_app()` with its own settings and a database
created **by the real Alembic migrations** (not `create_all`), so the schema under test is
the one production gets.

| Module | Tests | Covers |
|---|---|---|
| `test_health.py` | 5 | Liveness never touches the database; readiness is 200 when migrated and seeded, and 503 naming the failing check (migrations missing, no dataset, database unreachable) |
| `test_reference_data.py` | 18 | Entities, industries, variables, relationships: ordering, kind filters, pagination and out-of-range limits, 404 envelope, malformed IDs rejected before querying, ISIC classifications, published scenario rules, relationships labelled as assumptions, the type registry |
| `test_network.py` | 7 | Counts match the dataset, every edge connects existing nodes, structural links mirror entity records, degrees, the dataset labelled illustrative, undirected edges flagged, an empty but valid network without data |
| `test_scenarios.py` | 36 | Create, read, list, replace, delete (a draft never has results); shape validation (blank, long or control-character names, 0 or 11 inputs, bad types, unknown fields such as `status`), non-finite numbers, invalid JSON, JSON content type required; domain rules (unknown or non-variable entities, duplicates, percent changes to rates, the five value limits); every problem reported at once; a rejected update changes nothing; oversized bodies, declared or chunked |
| `test_seed.py` | 19 | The sample passes every integrity rule and the honesty rules (labelled illustrative, companies fictional, real entities cite references, no evidence claimed, no numeric financial figures); each integrity rule catches its violation; unknown fields rejected; loading is idempotent and `--reset` replaces data |
| `test_domain.py` | 21 | Every edge type is registered with a meaning; rates accept only percentage-point changes; limit checks, including decimal places despite binary floating point |
| `test_errors_and_security.py` | 13 | Error envelope for unknown routes (404), wrong methods (405), crashes (500, no internals) and database outages (503); request IDs generated or safely reused; security headers and CSP; docs can be disabled; CORS allows configured origins and refuses others; unsafe CORS settings rejected |
| `test_migrations.py` | 3 | Migrated schema equals the models exactly; downgrade to empty and upgrade again; foreign keys enforced on SQLite |
| `test_openapi.py` | 3 | The committed `docs/api/openapi.json` matches the application; errors are documented with the shared envelope; no simulate/run endpoint exists |

Run against PostgreSQL (use an empty, disposable database — the suite drops and recreates
the schema):

```bash
RUMIN_TEST_DATABASE_URL=postgresql+psycopg://rumin:secret@localhost:5432/rumin_test uv run pytest
```

## Frontend (`frontend/tests/`)

Page tests render the **real route table** (`createMemoryRouter(routes)`) inside the real
theme provider, and replace only `fetch`: `tests/utils/api.ts` serves responses captured
from the running API (`tests/fixtures/*.json`) and records every request, so tests assert
exactly what the app sent. The fixtures are themselves checked against the OpenAPI
contract, so they cannot silently drift from the API.

| Area | Tests | Covers |
|---|---|---|
| `lib/apiClient` | 12 | Success, error envelope → typed `ApiError`, non-JSON, unreachable, timeout, caller cancellation, accepted non-2xx, 204, base URL |
| `lib/contract` | 7 | Fixtures conform to the contract; the checker catches missing fields, wrong types, bad enum values, nested unions |
| `hooks/useApiResource` | 6 | Loading → success, request sharing, error and reload, refresh keeps data, no cross-key data, data from a save |
| `network/model` | 14 | Integrity validation (dangling edges, duplicates, self-loops, unknown types, malformed records), indexes, neighbourhoods, filters, search |
| `network/layout` | 9 | Finite, deterministic positions (independent of input order), column order, spacing, empty graph, portrait transpose |
| `network/panZoom` | 7 | Zoom keeps the cursor point fixed, limits, fit-to-view maths |
| `scenarios/scenarioModel` | 30 | Number parsing, published limits, per-field validation, payload conversion, server-error mapping, editor state, unsaved-changes tracking |
| `app/navigation` | 8 | Landing, navigation between modules, 404, live workspace status, AI Analyst inert, System capabilities, theme persistence |
| `pages/universe` | 11 | Exactly the API's nodes and links drawn; selection highlights neighbours and dims the rest; Escape and close reset; keyboard selection; search; filters never leave dangling links; table view; phone layout; inconsistent data refused; unreachable API and retry |
| `pages/scenarioLab` | 9 | Validation before sending (no request made), published limits, exact save payload, "nothing was simulated", server 422 mapped to fields, network failure, worked example, edit and delete, missing scenario |
| `pages/dashboard` | 4 | Loading state, live figures from the API, preview → Universe link, unreachable API and recovery |

## Integration (`frontend/tests/integration/`)

Runs the frontend's own service layer (`services/api.ts`) against a live API — no mocks:

- every response type matches the committed OpenAPI contract;
- the live network passes the frontend's integrity check and yields a finite layout;
- a scenario the Scenario Lab considers valid round-trips (create, read, list, replace,
  delete, then 404);
- **eight invalid inputs** (a fall of 100 % or more, above the maximum, zero, too many
  decimals, a rate moved more than 25 points, a percent change on a rate, an unknown
  variable, the same variable twice) plus a blank name are each rejected **both** by the
  browser's validation and by the server, and the server's error lands on the same form
  field;
- unknown fields and malformed JSON get the standard error envelope; CORS admits the dev
  origin and refuses others.

It creates and deletes scenarios, so point it only at a disposable database — which is
what `scripts/smoke_test.sh` provides.

## Manual and visual checks

Every page was rendered in Chromium (via Playwright) and reviewed from screenshots, with no
console errors, across desktop (1440 × 900, 1280 × 800) and phone (390 × 844) sizes and
both themes — not every page in every combination. Interactions were exercised in the
real browser too: selection and dimming, deep links (`/universe?focus=…`), the portrait
network on phones, and the scenario save flow. These checks are not automated yet (see
[known-limitations.md](known-limitations.md)).

## Conventions

- Test behaviour through public interfaces: HTTP for the backend, rendered pages and user
  events for the frontend. Query by role and label, as assistive technology does.
- A bug found in development gets a test first. Phase 1 examples: the layout depended on
  edge order; a heading's accessible name ran two words together; both were found by this
  suite and fixed.
- Never weaken a test to make it pass; never skip one.
