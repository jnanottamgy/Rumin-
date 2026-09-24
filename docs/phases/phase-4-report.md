# Phase 4 report — Simulation engine

**Status: implemented and verified, locally and in CI.** RUMIN now has a simulation
engine. It runs versioned, documented models on validated inputs with exact arithmetic,
and records every calculation step. It carries a change through the knowledge graph only
along relationships a model declares and the graph confirms. Every run is stored with
what is needed to explain and reproduce it. The first model, an airline fuel-cost shock,
is served by a new API and shown on a new Simulation page. The plan written before
implementation is in [phase-4-plan.md](phase-4-plan.md); the full documentation is in
[`docs/simulation/`](../simulation/README.md).

> **What a simulation is not.** A run is the arithmetic consequence of the inputs and
> assumptions it shows, with everything else held constant. It is **not a forecast**, not
> a probability and **not investment advice**. No parameter has been estimated from data
> and no result has been back-tested. The company figures always come from the user.

## At a glance

| | In this build |
|---|---|
| **Implemented functionality** | The `app/simulation/` package: exact decimals, units, typed model definitions with SHA-256 hashes, a versioned registry, input validation, controlled propagation, execution with every step recorded, Shapley contributions, an accounting bridge, one-at-a-time sensitivity, explanations and append-only persistence (migration `0004`, 4 tables). 12 API endpoints. The Simulation page (`/simulation`). Tests, benchmarks and documentation |
| **Model selected** | `airline_fuel_cost` 1.0.0 (status `preview`): how a change in crude oil, jet fuel or the exchange rate reaches one airline's fuel cost, operating profit and margin, through hedging and a lagged fare pass-through |
| **Historical data** | One input can come from stored data: the exchange rate, as the latest annual World Bank average, with its full provenance. **None is stored where Phase 4 was built**, because the World Bank retrieval was blocked there, so every run here used typed figures |
| **User inputs** | The airline's revenue, operating costs, fuel consumption, reporting currency and the baseline jet fuel price. RUMIN holds no company accounts |
| **Assumptions** | Six model parameters with neutral defaults and written rationales: the crude-to-jet-fuel elasticity β = 1 and its lag of 0 months, no hedging (0 %, 0 months) and no fare pass-through (0 %, 0 months) unless the user enters them |
| **Derived and simulated outputs** | 19 outputs, each labelled: 7 `derived` (from the inputs alone, e.g. the baseline margin) and 12 `simulated` (under the scenario), plus 7 monthly series |
| **Sample and hypothetical data** | The page's example is labelled hypothetical: round numbers chosen to be checked by hand, not market data or any airline's figures. The graph's airlines are fictional, and the relationship the model relies on is an illustrative model assumption. Test observations are synthetic and named so |
| **Fabricated data** | **None.** No figure is invented. Missing inputs are refused, never filled in, and every default is an assumption labelled as one |
| **Planned functionality** | Scenario drafts connected to models, run comparison and saved results (Phase 5); estimated parameters and Monte Carlo (Phase 9); retention and quotas with authentication (Phase 10) ([roadmap](../roadmap.md#simulation-follow-ups)) |

## 1. Inspection of Phases 1–3

Before any change, the existing application and checks were run on commit `b065261`.
`make check` passed with 450 backend and 202 frontend tests; the smoke test passed with 39
integration tests; CI run #7 had passed on the same commit
([plan, section 1](phase-4-plan.md#1-inspection-of-phases-13)). What Phase 4 reuses:

- **Phase 1:** the variable definitions and their units, the published scenario limits,
  and the design system (including the glyph for simulated output).
- **Phase 2:** the exact-decimal conventions (`DecimalString`, `NUMERIC(38, 18)`), and
  stored observations with their provenance.
- **Phase 3:** the graph channels (Brent crude → *influences* → jet fuel → *affects costs
  of* → air transport; airlines → *operates in* → air transport), `GraphReader`, build IDs
  and fingerprints, and the freshness check.

Nothing in Phases 1–3 was restructured. The scenario, data and graph APIs keep their
contracts, apart from wording that no longer says no engine exists. The system report
lists the engine as available and Monte Carlo as planned for Phase 9.

## 2. What changed

| Layer | Change |
|---|---|
| Engine | `backend/app/simulation/` (13 modules and the first model): [architecture](../simulation/architecture.md) |
| Persistence | Migration `0004_simulation_engine`: `simulation_model_versions`, `simulation_runs`, `simulation_run_steps`, `simulation_sensitivity_analyses`, all append-only ([data model](../data-model.md#phase-4-simulation-runs)) |
| API | `app/api/v1/simulations.py`, `app/services/simulation.py`, `app/schemas/simulation.py`; the OpenAPI snapshot and generated frontend types regenerated; a test that fails if two schemas share a name |
| Frontend | `frontend/src/features/simulation/` and `pages/SimulationPage.tsx`: the Simulation page at `/simulation` and `/simulation/runs/{id}`, in the navigation; one new colour token (`--viz-baseline`) |
| Tests | 146 new backend tests, 43 new frontend unit and page tests, 8 new integration tests |
| Documentation | 10 pages in [`docs/simulation/`](../simulation/README.md), ADRs 33–42, this report and updates across the existing docs |
| Dependencies | **None added** |

## 3. The model selected

Five domains were compared on data available, financial relevance, mathematical clarity,
validation potential and extensibility
([plan, section 2](phase-4-plan.md#2-the-domain-an-airline-fuel-cost-shock)). The airline
fuel-cost shock won because it uses the most of what RUMIN already holds (graph channels,
variable units, a historical exchange-rate series). Its core is an accounting identity
(volume × price × exchange rate), and it still exercises unit conversion, currencies,
frequencies, lags and propagation through the graph. The closest alternative, interest
rates on financing costs, lacked data (RUMIN holds one annual lending rate).

**The model** ([full specification](../simulation/airline-fuel-cost.md)):

- 17 inputs: 3 scenario changes, 2 market baselines, 5 company figures, 6 assumptions
  and 1 setting.
- 19 equations (E1–E19), each with its terms, units, scope and the assumptions and
  limitations it rests on; 8 assumptions (A1–A8) and 7 limitations (L1–L7).
- 11 validation rules: 8 refuse a run, 3 record a warning.
- One transmission rule (T1: Brent crude → jet fuel, elasticity β, lag in months) and
  three supporting relationships it cites but never follows (S1–S3).

**Checked by hand.** The page's hypothetical example has a fuel bill of 5,000,000 INR a
month (1,000 kL a year at 750 USD per kL and 80 INR per USD), revenue of 300,000,000 and
operating costs of 250,000,000. Half the fuel is hedged for three months, and 40 % of
fuel-cost changes are passed on to fares after two months. Crude oil rises 10 %:

| Result | Value | By hand |
|---|---|---|
| Gross fuel-cost change | +6,000,000 | 12 × 500,000 |
| Hedging effect | −750,000 | 3 months × 50 % × 500,000 |
| Fuel-cost change | +5,250,000 | 6,000,000 − 750,000 |
| Fare recovery | +1,700,000 | 40 % × (3 × 250,000 + 7 × 500,000) |
| Change in operating profit | **−3,550,000** | 1,700,000 − 5,250,000; the bridge closes |
| Operating margin | 16.67 % → 15.40 % (−1.27 points) | 46,450,000 / 301,700,000 |
| Steady-state change in operating profit | −3,600,000 a year | 6,000,000 × (1 − 40 %) |
| Revenue change that would offset the fuel cost | 1.75 % | 5,250,000 / 300,000,000 |

The backend tests, the integration suite and the page tests all assert these values.
Doubling the crude rise to 20 % gives −7,100,000 in the sensitivity analysis, exactly
twice the result.

## 4. Architecture decisions

Recorded in full as [ADRs 33–42](../decisions.md#33-one-narrow-domain-first-an-airline-fuel-cost-shock):

| # | Decision | In one line |
|---|---|---|
| 33 | One narrow domain first | The airline fuel-cost shock; the registry takes the next model without engine changes |
| 34 | Models are code, versioned and hashed | No formula language and no `eval`; a released version's hash is pinned by a test and checked at run time (409) |
| 35 | Exact decimals, refused rather than repaired | 34 digits, half-even, traps; values out of range, too precise, in an unlisted unit or missing are refused with a reason |
| 36 | The graph carries shocks only through declared rules | Coefficients and lags are inputs; simple paths, depth ≤ 4, ≤ 500 paths; other edges listed as "not used" |
| 37 | Shapley values for contributions | Order-independent credits that add up to the total, whatever the interaction |
| 38 | Runs are append-only and verifiable from their own snapshot | 405 on change or delete; verification re-executes from what the run stored |
| 39 | One-at-a-time sensitivity; points outside a range are skipped | Exact and explainable; Monte Carlo deferred until inputs have estimated distributions |
| 40 | Runs are created by `POST /simulations` | The existing convention of posting to a collection, not `/run` |
| 41 | The browser calculates nothing | Every figure shown is a decimal string from the server, only formatted |
| 42 | Still no new dependencies | `decimal` and `hashlib` from the standard library; everything else written and tested here |

## 5. Graph integration

Graph edges are not equations ([graph integration](../simulation/graph-integration.md)).
The model **declares** its one transmission rule. The engine follows the edge only when:

- the latest completed build holds it as a current edge that passed the graph's
  validation (a flagged edge is refused, and tested);
- the scenario needs it.

The elasticity and the lag come from the model's inputs, never from the edge. Propagation
is log-linear along simple paths, so a cycle cannot feed a shock back into itself. Depth
and path count are bounded, and every path is recorded with its contribution. A crude
shock without a confirming edge is refused with the reason, while changes that act
directly (jet fuel, the exchange rate) still run. The `influences` edge is a model
assumption in the graph, so every run that depends on it carries a warning saying so.
The graph's other relationships around the model's variables are listed as "not used by
this model". The proposal written in Phase 3
([Phase 4 integration](../graph/phase-4-integration.md#how-phase-4-followed-it)) was
followed point by point.

## 6. Explainability, provenance and reproducibility

A run stores its definition hash, every input (value, unit, kind of knowledge, source,
default and rationale), the graph and data snapshots, every calculation step (99 for 12
months, 267 for 36), the outputs, monthly series, contributions, the bridge,
transmission paths and warnings, and the inputs and result hashes
([provenance](../simulation/provenance.md)).

- **Identical inputs, identical outputs.** Five runs of the example through the API
  gave one inputs hash and one result hash. The tests check this in the engine, through
  the API on SQLite and PostgreSQL, and against the live API, including that `10` and
  `10.00` hash the same.
- **Verification** re-executes a run from its stored snapshot alone and compares hashes.
  It works even after the graph has been deleted (tested).
- **Explanations are structured data**, never generated prose: each equation with its
  terms and the assumptions behind it; every step, month by month; the pathway from
  inputs through graph variables to results; Shapley contributions; the bridge; each
  parameter against its default.

## 7. Sensitivity analysis

One-at-a-time analysis around a stored run: default, absolute, relative or listed
values for up to 8 inputs, 7 points each, 60 evaluations and 10 seconds
([sensitivity](../simulation/sensitivity.md)). A point outside an input's range, or one
the model refuses, is skipped and listed with the reason, never clipped. Every point
reports every output. Inputs are ranked by the spread of a chosen metric, and each
analysis is stored with its own hash. Runs already record `random_seed` (`null`), ready
for a probabilistic analysis that is deliberately not built.

## 8. API

| Method and path | Purpose |
|---|---|
| `GET /api/v1/simulation-models` | Registered models, with version, status, definition hash and run count |
| `GET /api/v1/simulation-models/{model_id}` | The full definition (`?version=`), with the graph edge that confirms each rule |
| `POST /api/v1/simulations/validate` | A validation report; stores nothing |
| `POST /api/v1/simulations` | Run and store (201 with `Location`); 422 with one detail per problem; 409 if a version's code changed |
| `GET /api/v1/simulations` | Stored runs, newest first, with their headline (`?model_id=`, paginated) |
| `GET /api/v1/simulations/{run_id}` | A stored run |
| `GET …/{run_id}/explanation`, `GET …/{run_id}/provenance` | The structured explanation; the provenance record |
| `POST …/{run_id}/verify` | Re-execute from the snapshot and compare hashes; stores nothing |
| `POST …/{run_id}/sensitivity`, `GET …/{run_id}/sensitivity`, `GET …/{run_id}/sensitivity/{analysis_id}` | Run and store an analysis (201); list and read them |

`PUT`, `PATCH` and `DELETE` on runs answer 405. Details: [API reference](../api.md#simulation).

## 9. The Simulation preview

The page is a preview, not the Scenario Lab ([the preview](../simulation/preview.md)).
It has the form on the left, grouped by kind of knowledge, with every unit, range, default
and rationale, and server-side checking whose problems appear beside their fields. Results
are on the right: a hero figure and headline tiles, then baseline against scenario, and
tabs for the pathway and months, contributions, sensitivity, the calculation, inputs and
assumptions, and provenance. Stored runs have their own address and can be reopened and
varied. It follows RUMIN's design system (bone white and charcoal, sky blue for emphasis
only) and the installed frontend-design and dataviz skills.

It has one orchestrated moment: a new run's change travels down the pathway once, and
nothing moves under reduced motion. Every chart has a table or is one. The one new colour
was validated by script as a pair in both themes. The page was reviewed in Chromium at
desktop and phone sizes in both themes, and the review's findings were fixed; the last,
found while writing this report, was the dark baseline grey falling to 2.9 : 1 on the
raised surface. The page's code is a lazily loaded chunk of 69.9 kB (20.4 kB gzipped).

## 10. Performance

Measured on the development container (4 vCPUs, Python 3.11, SQLite):

| Operation | Time |
|---|---|
| Execute one shock over 12 months | 2.4 ms (median) |
| Execute three shocks over 12 months (8 Shapley evaluations) | 4.4 ms |
| Execute three shocks over 36 months (267 steps) | 9.1 ms |
| Default sensitivity analysis (7 inputs, 15 evaluations) | 7.0 ms |
| 50-evaluation analysis over 36 months | 39 ms |
| `POST /api/v1/simulations` end to end, including validation, the graph checks and storing 99 steps | 18–29 ms |

A 12-month run returns about 15 kB and stores about 16–17 kB of JSON. The limits
(horizon, depth, paths, evaluations, deadline) keep every request small; the largest
fixed cost is the graph freshness check, cached for 30 seconds.

## 11. Tests

| Suite | Result |
|---|---|
| Backend (pytest) | **596 passed** on SQLite and on PostgreSQL 16 (146 new: numbers 31, transmission 10, model 78, API 25; OpenAPI 2) |
| Frontend (Vitest) | **245 passed** (43 new: formatting 6, form 7, pathway layout 6, Simulation page 13, simulation fixtures against the contract 11) |
| Integration (live API) | **47 passed** (8 new, including the example checked against the hand calculation), inside the smoke test |
| Smoke test | Passed: fresh database, graph built and rebuilt with no change, then the integration suite |
| Lint, format, types, build, OpenAPI snapshot, generated types | Clean |
| CI | Run **#8** (`71183c5`: the engine and the preview) passed all three jobs: backend on SQLite and PostgreSQL 16, frontend, and the smoke test |

The tests pin the released model's definition hash. They check every mechanism against
round inputs worked by hand, every validation rule, the contributions adding up, and
that the engine never calls `eval`, `exec` or `compile`. They also check limits refused
whole, append-only storage enforced by the database, and a run reproduced from its
snapshot. Details: [testing](../testing.md).

## 12. Security

([security](../security.md#simulation-engine-phase-4)) There is no executable input:
models are code and nothing is evaluated from text. Inputs are validated against the
definition: strict number types, bounded lengths, ranges, decimal places, units and
currency codes, and unknown inputs refused. An exact-decimal context traps overflow and
invalid operations. Work per request is bounded, runs are append-only, and running a model
makes no outbound request. There is still no authentication, so anyone who can reach the
API can add runs, and nothing limits how many (Phase 10). `npm audit` and `pip-audit`
report no known vulnerabilities.

## 13. Verification against the brief

| Check | Evidence |
|---|---|
| The simulation works end to end | The smoke test runs the example through the live API; the page runs it in the browser; CI passes |
| The mathematics is validated | Every mechanism checked by hand with round inputs (section 3); invariants tested (no change, no effect; full hedge; full pass-through; the bridge closes; contributions add up) |
| Results are explainable and reproducible | Structured explanations; identical hashes for identical inputs; verification from the snapshot |
| Provenance is preserved | Every input's source, stored observations with licence and capture, the graph build and edges, the model's definition hash |
| Graph integration is controlled | Declared rules only, confirmed and validated edges, bounded paths, coefficients from assumptions |
| Sensitivity analysis works | Default and custom analyses stored and ranked; skipped points listed; limits enforced |
| Frontend and backend are connected | The page uses the API through the generated types; the integration suite runs the page's own form code against the live API |
| Existing features still work | Every Phase 1–3 test passes; the few that changed were updated for wording that said no engine exists. The network, data and graph APIs keep their contracts |
| No fabricated financial data | Company figures come from the user; the example is labelled hypothetical; defaults are labelled assumptions; missing data is refused, never filled in |

## 14. Limitations

The full list is in [limitations](../simulation/limitations.md). In short:

- There is one narrow, deterministic model.
- Parameters are assumptions, not estimates.
- Dynamics are simple: monthly steps and permanent shocks.
- Only one relationship travels through the graph.
- Little stored data is used.
- Scenario drafts are not connected to the engine, and runs cannot be compared.
- There is no authentication, rate limiting or retention policy.

## 15. Technical debt

- The page finds baseline-and-scenario pairs and monthly series by naming convention
  (`baseline_x` / `scenario_x`). A second model should declare its presentation instead.
- Sensitivity re-evaluates the whole model at every point: cheap now, not for a large
  model.
- The explanation returns every step at once (about 54 kB for 12 months and 101 kB for
  36).
- The pathway layout is a simple layered layout without crossing minimisation.
- Validating and running pay for the graph freshness check when its 30-second cache
  expires ([graph follow-up 1](../roadmap.md#graph-follow-ups)).
- The browser review is manual; no end-to-end browser test runs in CI.

## 16. Recommendations for Phase 5

1. **Declare presentation in the model definition** before the Scenario Lab builds on
   the page, so that views do not depend on output names.
2. **Connect scenario drafts to models.** Map a draft's changes on graph variables to a
   model's scenario inputs, refusing any change no input accepts, and record the mapping
   with the run.
3. **Compare runs.** Show two or more stored runs side by side, with the differences in
   inputs, assumptions and results, and whether their hashes match.
4. **Save company figures once.** Let a set of figures be entered once and reused, each
   still labelled as the user's figure, with its own history.
5. **Add bounded two-way sensitivity** where interactions matter, still deterministic and
   under the same limits.
6. **Automate the browser flow** (Playwright in CI) for checking, running, reopening and
   varying a run.
7. **Keep Monte Carlo for Phase 9**, when inputs have estimated distributions; the
   `random_seed` field is ready for it.

## Quality gates

| Gate | Status |
|---|---|
| **Inspection:** existing application and tests run first; systems reused | ✓ `make check` and the smoke test on `b065261` before any change; Phase 1–3 conventions, `GraphReader` and stored observations reused |
| **Core:** versioned models, validated inputs, explicit assumptions and parameters, deterministic calculations, sensitivity, explainable outputs, snapshots, provenance, graph integration, reproducible execution, API, preview UI | ✓ sections 3–9 |
| **Domain:** one narrow, documented domain | ✓ the airline fuel-cost shock ([model](../simulation/airline-fuel-cost.md)) |
| **Registry and layers:** IDs, versions, inputs, parameters, equations, units, validation, assumptions, limitations, status; typed schemas; no financial calculation in the frontend | ✓ [registry](../simulation/registry.md); ADR 41 |
| **Numbers:** every equation documented and tested; units, currency, frequency, periods, percentages, conversions, ranges and outputs validated; no silent conversion or invented data; kinds of knowledge distinguished; no predictions or advice | ✓ [numbers and units](../simulation/numbers-and-units.md); ADR 35 |
| **Graph:** declared, validated relationships only; direction, coefficients, lags, depth, cycles, contributions, provenance | ✓ section 5; ADR 36 |
| **Runs:** full records; identical inputs give identical outputs; structured explanations | ✓ section 6; ADR 38 |
| **Sensitivity:** one at a time, with limits; Monte Carlo prepared, not built | ✓ section 7; ADR 39 |
| **API and persistence:** endpoints; models, runs, snapshots, outputs and provenance persisted by migration; history never overwritten | ✓ section 8; migration `0004`; 405 on change or delete |
| **Frontend:** a preview, not the Scenario Lab; restrained design; visualisations only for real data | ✓ section 9; [the preview](../simulation/preview.md) |
| **Safeguards:** depth, sensitivity combinations, time, payload, overflow, invalid inputs; no `eval` | ✓ [security](../security.md#simulation-engine-phase-4); tested |
| **Documentation:** architecture, registry, equations, assumptions, provenance, API, testing, adding models, limitations | ✓ [`docs/simulation/`](../simulation/README.md) (10 pages), plus updates to the README, API, architecture, data model, data dictionary, decisions, design system, security, setup, testing, known limitations and roadmap |

What remains unverified is stated above. The parameters have never been estimated or
back-tested, no live World Bank value was available to run with, and the product has no
authentication.
