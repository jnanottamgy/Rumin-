# Phase 1 report — Foundation & system architecture

Status: **complete for local use**, with the gaps listed under
[Known limitations](#9-known-limitations). Nothing described here as working is
untested; where something could not be verified, that is stated.

> **Update (23 September 2026, during Phase 2).** This report is kept as written at the end
> of Phase 1, with two corrections since:
>
> - The CI workflow has now run on GitHub. Run #1 on `ed637b6` passed.
> - The Phase 2 licence review rejected FRED as a data source. Its API terms prohibit
>   storing FRED content in a database, so the World Bank Indicators API was used instead
>   ([decision 13](../decisions.md#13-world-bank-indicators-as-the-first-provider-fred-rejected)).
>
> The "Phase 2 next steps" below were superseded by the
> [Phase 2 report](phase-2-report.md).

## 1. What was built

- **API** (FastAPI): health and readiness probes; versioned read endpoints for entities,
  industries, variables, relationships, the relationship-type registry and the network
  projection; scenario drafts (create, read, list, replace, delete); a system-status
  endpoint that states which capabilities exist and which are planned. Consistent error
  envelope, request IDs, security headers, body-size limit, strict CORS, OpenAPI docs.
- **Database**: SQLAlchemy 2.0 models and an Alembic migration for 9 tables; SQLite for
  development, PostgreSQL 16 verified; integrity enforced by constraints.
- **Domain model**: companies, industries, countries and economic variables (joined-table
  inheritance); seven economic relationship types with a registry of meanings; derived
  structural links; scenario rules per variable; the five epistemic categories.
- **Sample dataset**: 30 entities and 41 relationships — real countries, ISIC industries
  and variable definitions with references; fictional companies; illustrative
  relationships with written rationales; no numeric financial data. Validated loader.
- **Web client** (React, TypeScript, Vite): landing page; Overview dashboard with live
  figures; Financial Universe (interactive 2D network with selection, dimming, hover,
  search, filters, legend, pan/zoom, deep links, keyboard access, table view, phone
  layout); Scenario Lab (validated drafts, "not simulated"); AI Analyst placeholder (no
  model, no requests); System page. Light and dark themes from one token file.
- **Quality**: 125 backend tests, 117 frontend tests, 19 integration tests, an end-to-end
  smoke script, a CI workflow, a Makefile, and documentation.

## 2. Files created

187 new files, about 29,600 lines (including lock files, the OpenAPI snapshot and test
fixtures):

| Area | Files |
|---|---|
| Repository | `.gitignore`, `.editorconfig`, `.env.example`, `Makefile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `scripts/smoke_test.sh` |
| Backend | `pyproject.toml`, `uv.lock`, `alembic.ini`, `migrations/` (env, template, `0001_initial_schema`), `app/` (api, core, data, db, domain, models, schemas, services, `main.py`, `openapi_export.py`), `tests/` (conftest + 9 modules) |
| Frontend | `package.json`, `package-lock.json`, `vite.config.ts`, `vitest.integration.config.ts`, `tsconfig.json`, `biome.json`, `index.html`, `public/favicon.svg`, `src/` (app, components, features/network, features/scenarios, hooks, layouts, lib, pages, services, styles, types), `tests/` (setup, utilities, fixtures, 11 unit/page suites, integration suite) |
| Documentation | `docs/`: architecture, decisions, setup, environment, api, data-model, data-dictionary, design-system, testing, security, known-limitations, roadmap, this report; `docs/api/openapi.json` |

## 3. Files modified

- `README.md` — replaced the one-line placeholder from the initial commit with the project
  README. No other pre-existing file was changed or deleted.

## 4. Technology decisions

Python 3.11+ / FastAPI / Pydantic v2 / SQLAlchemy 2.0 / Alembic / uv; React 19 /
TypeScript (strict) / Vite / React Router / d3-force (layout only) / plain CSS with design
tokens; pytest, Vitest, Testing Library; Ruff, mypy (strict), Biome. Rationale and
trade-offs: [decisions.md](../decisions.md).

## 5. Architecture

Layered API (routes → schemas → services → domain → persistence) over SQLite/PostgreSQL;
a web client whose network model and layout are pure, renderer-agnostic TypeScript (ready
for a Three.js renderer); a committed OpenAPI contract from which the client's types are
generated and against which live responses are checked. Details:
[architecture.md](../architecture.md).

## 6. API endpoints

`GET /health`, `GET /health/ready`, `GET /api/v1/entities`, `GET /api/v1/entities/{id}`,
`GET /api/v1/industries`, `GET /api/v1/variables`, `GET /api/v1/relationships`,
`GET /api/v1/relationship-types`, `GET /api/v1/network`, `GET|POST /api/v1/scenarios`,
`GET|PUT|DELETE /api/v1/scenarios/{id}`, `GET /api/v1/system`; interactive docs at
`/docs`. There is deliberately no simulate/run endpoint. Reference: [api.md](../api.md).

## 7. Database models

`datasets`, `entities` (+ `companies`, `industries`, `countries`, `economic_variables`),
`relationships`, `scenarios`, `scenario_shocks`. Reference:
[data-model.md](../data-model.md) and [data-dictionary.md](../data-dictionary.md).

## 8. Testing results

| Check | Result |
|---|---|
| Backend tests, SQLite | 125 passed |
| Backend tests, PostgreSQL 16 | 125 passed |
| Frontend unit and page tests | 117 passed (11 files) |
| Integration suite against a live, freshly seeded API (`scripts/smoke_test.sh`) | 19 passed |
| Ruff lint + format, mypy strict (53 files) | clean |
| Biome lint + format, TypeScript strict | clean |
| OpenAPI snapshot, generated API types | in sync |
| Production build | succeeds |
| Manual review in Chromium (desktop and phone sizes, both themes) | no console errors |

Two defects were found by the new tests and fixed: the network layout depended on the
order in which edges arrived, and one heading's accessible name ran two words together. A
contrast audit found text-field borders below 3 : 1; a dedicated token now meets it.

## 9. Known limitations

No simulation engine, no observed data, no AI analyst, no authentication, illustrative
sample only, 2D only, not containerised, no automated browser tests, CI not yet observed
running on GitHub, Docker image not pulled in the build environment, no licence chosen.
Full list: [known-limitations.md](../known-limitations.md).

## 10. Security

Validated inputs with unknown fields rejected, body-size limit, an error envelope that
never leaks internals, security headers and a strict CSP on API responses, explicit CORS
without credentials, parameterised SQL, database-enforced integrity, no secrets in the
repository, no third-party requests from the web client. Not yet: authentication, rate
limiting, deployment hardening, dependency scanning. Details: [security.md](../security.md).

## 11. Performance

| Measure | Value |
|---|---|
| Initial JavaScript (React, router, layout engine, landing page) | 346 kB, 111 kB gzipped |
| Route chunks, loaded on demand | Universe 18.8 kB (5.8 kB gz), Scenario Lab 21.4 kB (7.1), Overview 7.9 kB (2.9), System 7.5 kB (2.4), Analyst 3.9 kB (1.7), shared network UI 12.4 kB (4.9) |
| CSS | 28.9 kB global (8.5 kB gz) plus small per-route files |
| Fonts | self-hosted, subset per script; an English page loads ≈ 220 kB of WOFF2 once, then from cache |
| Network model + layout (30 nodes, 71 edges) | ≈ 17 ms median, ≈ 100 ms on the first, un-optimised run; computed once per dataset and shared by all views |
| `GET /api/v1/network` | 3 database queries whatever the graph size; ≈ 5 ms server time on SQLite; 49 kB of JSON |
| Test suites | backend ≈ 2 s, frontend ≈ 8 s |

Headroom and next steps: responses are not compressed by the API (a reverse proxy should
do it); for graphs in the thousands, move the layout to a Web Worker and rendering to
canvas/WebGL.

## 12. Phase 2 next steps

Observation storage with vintages; source connectors for the variables already defined
(FRED, RBI, MoSPI) with licences reviewed and API keys kept server-side; data-quality
checks and visible retrieval dates; a time-series API and charts; a policy for real
company data; dataset governance. Early follow-ups: choose a licence, add dependency
scanning and browser end-to-end tests to CI, decide the authentication model. Details:
[roadmap.md](../roadmap.md).
