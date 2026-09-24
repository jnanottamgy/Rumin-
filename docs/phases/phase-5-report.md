# Phase 5 report — Scenario Lab

**Status: implemented and verified, locally and in CI.** RUMIN now has a
Scenario Lab. It asks *what happens if something changes?*, chooses the models that apply
from what each model declares and what the knowledge graph states, executes them through
the Phase 4 engine on a bounded background pool, and shows the **modelled pathway** from
each change to each line — with baseline against scenario, the simulated months, stress
cases, one-at-a-time sensitivity, an explanation of every figure from what was stored,
versions, history, reproducibility checks and comparisons. The plan written before
implementation is in [phase-5-plan.md](phase-5-plan.md); the documentation is in
[`docs/scenario-lab/`](../scenario-lab/README.md).

> **What a scenario is not.** An execution is the arithmetic consequence of the changes,
> figures and assumptions it shows, with everything else held constant. It is **not a
> forecast**, not a probability and **not investment advice**. No parameter has been
> estimated from data and no result has been back-tested. Company figures always come from
> the user; the sample companies are fictional.

## At a glance

| | In this build |
|---|---|
| **Implemented** | Versioned scenarios (migration `0005`: versions, executions, their model runs, sensitivity analyses); validation of every field; a planner with five statuses and reasons; four new models and airline 1.1.0; engine extensions (timed changes, percentage-point shocks); a bounded runner with recorded stages, cancellation, time limits and recovery; the Lab's equations AG0–AG7; stress cases; pathways; explanations; sensitivity; comparisons; templates; 26 scenario endpoints; the Scenario Lab interface; compressed responses; tests, benchmarks and documentation |
| **Models** | `airline_fuel_cost` 1.0.0 (unchanged) and 1.1.0, `fx_exposure` 1.0.0, `floating_rate_interest` 1.0.0, `crude_linked_costs` 1.0.0, `gas_linked_costs` 1.0.0 |
| **Templates** | 7, each built on implemented models: crude oil on an airline, jet fuel, rupee depreciation, a policy-rate rise, crude-linked costs, natural gas, and oil, rupee and rates together. Demand and supply-chain shocks are listed as **not offered**, with the reason |
| **Historical data** | Market baselines can come from stored data (the exchange rate as the latest stored World Bank annual average), with a constraint to require it. As in Phase 4, no World Bank value was retrievable where this was built, so every execution here used typed figures |
| **Hypothetical data** | The reference example — "oil, rupee and rates" on the fictional Aerisca Airways — uses round figures chosen to be checked by hand, labelled hypothetical wherever they appear |
| **Fabricated data** | **None.** Nothing is filled in: a missing figure blocks the plan; a stress value outside a variable's limits is refused, not clipped; unmodelled lines are not shown |
| **Not built** | Demand and supply-chain models; paths other than step changes; probabilistic simulation (Phase 9); authentication, retention, a shared job queue (Phase 10) |

## 1. Inspection of Phases 1–4

Before any change, `make check` passed on commit `0db7ec1` (596 backend tests, 245 frontend
tests), the smoke test passed with 47 integration tests, and CI run #9 was green on the same
commit ([plan, section 1](phase-5-plan.md#1-inspection-of-phases-14)). What Phase 5 reuses
rather than rebuilds: the variables and their published change rules (Phase 1), exact
decimals and stored observations with provenance (Phase 2), the graph's stated exposures
and `GraphReader` (Phase 3), and the whole engine — registry, validation, `prepare` and
`execute`, Shapley contributions, append-only runs with provenance and verification,
sensitivity (Phase 4). Every Lab execution stores ordinary Phase 4 runs, which open and
verify on their own.

Two Phase 1 behaviours were replaced because the brief forbids them: scenario drafts were
overwritten on save (now immutable versions; the drafts became version 1 of themselves in
migration `0005`), and the drafts page could not run anything (now the Lab).

## 2. What was built

| Layer | Change |
|---|---|
| Engine | `app/simulation/`: a change's start and duration, lag-shifted windows, percentage-point shocks applied as level changes at their own node (never carried along log-linear rules); four new models; airline 1.1.0. Every released definition hash and every Phase 4 result is unchanged (pinned tests); the engine version stays 1.0.0 |
| Scenario Lab | `app/scenario_lab/` (14 modules): specification and hashing, validation, profiles, the planner, graph queries, the executor and runner, aggregation, pathways, explanation, sensitivity, comparison, templates. `LAB_VERSION` 1.0.0 |
| Persistence | Migration `0005_scenario_lab`: `scenario_versions`, `scenario_executions`, `scenario_execution_runs`, `scenario_sensitivity_analyses`; `scenarios` and `scenario_shocks` extended; Phase 1 drafts converted ([data model](../data-model.md)) |
| API | 26 operations under `/scenarios`, `/scenario-executions`, `/scenario-templates`, `/scenario-comparisons` ([API](../api.md#scenario-lab)); responses gzip-compressed over 1 KiB; the OpenAPI snapshot (68 paths) and generated frontend types regenerated |
| Frontend | `features/scenarioLab/` and `pages/ScenarioLabPage.tsx` replace the Phase 1 editor: library, builder, live preview, execution strip, pathway canvas, results, timeline with replay, and eight views ([interface](../scenario-lab/interface.md)) |
| Tests | 116 more backend tests (712); the Phase 1 editor's 38 frontend tests replaced by 57 for the Lab (264 in all); integration 49; fixtures captured from a real backend |
| Tools | `backend/scripts/capture_lab_fixtures.py`, `backend/scripts/benchmark_lab.py`, `frontend/scripts/measure-lab.mjs` |
| Documentation | [`docs/scenario-lab/`](../scenario-lab/README.md) (6 pages), four model pages, ADRs 43–53, this report, and updates across the existing docs |
| Dependencies | **None added** |

## 3. Architecture

A scenario has a stable identity and immutable, numbered versions; saving never overwrites
(409 on a stale base version), and an executed scenario cannot be deleted. The planner lists
every model as included, blocked, available, excluded or not applicable, with reasons and
fields; a model is included by default only when a company is chosen **and** the graph
states the exposure it needs. A plan executes only if every change is simulated by an
included model, none is blocked, no two models claim the same line item, and every stress
case is valid.

`POST /scenarios/{id}/executions` validates and plans again, reserves a place on the pool
(429 when full), stores the execution as queued and answers 202. The executor moves through
**validating → simulating → propagating → aggregating**, storing each stage's times as it
happens; cancellation and the 20-second limit are checked between stages and models; the
results and every model run are stored in one transaction; a final execution never changes
(every change of state is a conditional update that applies only while the execution is not
final). Unfinished executions are marked failed when the server restarts; that recovery
assumes one API process. Full detail:
[architecture](../scenario-lab/architecture.md); decisions 43–53.

## 4. Models and composition

| Model | Answers | Changes | Contributes to |
|---|---|---|---|
| [Airline fuel cost](../simulation/airline-fuel-cost.md) 1.1.0 | an airline's fuel bill, hedges and fare recovery | Brent (via jet fuel, β, lag), jet fuel, USD/INR | operating costs (fuel), revenue (fare recovery) |
| [Foreign-currency revenue and costs](../simulation/fx-exposure.md) 1.0.0 | revenue and costs invoiced in US dollars, and their hedges | USD/INR | revenue, operating costs |
| [Floating-rate interest](../simulation/floating-rate-interest.md) 1.0.0 | interest on debt linked to the repo rate or US short-term rates, after repricing | RBI repo rate, Fed funds (pp) | interest expense |
| [Crude-oil-linked costs](../simulation/crude-linked-costs.md) 1.0.0 | costs priced off crude (feedstock, diesel), net of hedges and recovery | Brent | operating costs, revenue |
| [Natural-gas-linked costs](../simulation/gas-linked-costs.md) 1.0.0 | costs priced off natural gas (fuel, feedstock), net of hedges and recovery | Henry Hub | operating costs, revenue |

Models combine only through the line items their **scenario profiles** declare, from a
closed list; the Lab adds them into lines (AG1–AG5) and metrics (AG6–AG7) and checks
operating profit against each model's own figure. Baselines are the user's annual figures ×
horizon ÷ 12, held constant (AG0). A line no included model reaches is not shown; profit
before tax appears only with an interest model; cash flow never appears.

The reference example (worked by hand, and reproduced by the integration suite on a live
API): Brent +20 %, USD/INR +5 %, repo +0.5 pp on Aerisca Airways over 12 months →
revenue +6,925,000, operating costs +13,250,000, operating profit −6,325,000, interest
+375,000, **profit before tax −6,700,000 INR (−17.63 %)**; operating margin 16.67 % →
14.23 %, interest coverage 4.17× → 3.53× ([details](../scenario-lab/README.md#the-reference-example)).

## 5. Graph integration

The graph is used in three ways, kept apart everywhere they appear:

1. **Applicability.** Stated exposures (direct, or through the company's industry) decide
   whether a model is included by default — never an amount. These relationships are served
   as `context_only` and shown in each model's lane header ("Why it applies"), with the
   caveat that a connection is not evidence of causation.
2. **Transmission.** The engine carries a change only along relationships a model declares
   and the graph confirms (Phase 4's rule): crude → jet fuel, with β and a lag that are model
   assumptions. A relationship recorded as a model assumption makes every dependent result
   say so.
3. **Context and ties.** The plan lists the companies the graph ties to the changes (within
   two `influences` hops, at most 200) and which ties a model covers; the pathway lists the
   graph's other relationships from the changed variables as **not modelled** (eleven in the
   reference example), never following them.

The evidence constraint refuses relationships that are only assumptions, when chosen.

## 6. Frontend

The Lab follows the brief's layout — controls left, pathway centre, results right, execution
and months along the bottom — as an instrument: bone and charcoal surfaces, hairline rules,
monospaced figures, sky blue reserved for changes, propagated relationships and the one
emphasised series. What is shown is always labelled a **live preview** (computed by the
backend while editing, never stored) or a **stored execution**. No animation pretends that
work is happening: stages appear as the server records them, the preview dims while
computing, and the month replay steps through stored values. The pathway was reworked after
visual review (four columns, graph context moved to lane headers, two-line labels, β and lag
on the variable they reach) so it fits a 1,440 px screen. Every Lab page was reviewed from
screenshots in both themes and at phone width, and checked for sideways scrolling at seven
widths ([interface](../scenario-lab/interface.md)).

**Skills.** The installed `dataviz` skill was applied to the timeline, stress bars and
tornado (one emphasised series, grey context, thin marks, hairline axes, no second y-scale,
tables beside charts); the Lab introduces no new colour, so the Phase 4 validated
series/baseline pair is used. The plan also named the `frontend-design` skill: **it was not
available to invoke in this session**, so its direction (plan, then build with restraint) was
followed by hand from the brief's design section.

## 7. API and database

26 operations ([API](../api.md#scenario-lab)): scenarios (list, create, read, save a
version, delete if never executed, duplicate, versions, restore, plan), preview and plan
without saving, executions (start, list, read, results, pathways, explanation, cancel,
verify, sensitivity), templates and comparisons. Status codes follow the existing
conventions: 202 for an accepted execution, 409 for conflicts with stored state, 422 with
field paths for invalid input, 429 when the pool is full. Four new tables; versions,
executions, their runs and analyses are append-only once final, protected by restricting
foreign keys.

## 8. Tests

| Suite | Tests | New in Phase 5 |
|---|---|---|
| Backend (SQLite; also run on PostgreSQL 16) | 712 | timing and rate shocks (14), the four models against hand calculations (23), the Lab — specification, validation, profiles, planner, aggregation against the reference, stress, pathways, stages, cancellation, time limit, runner capacity and recovery, final states never overwritten, sensitivity, comparison, tampering (52), the API (25); one migration and one compression test; the existing OpenAPI and scenario tests updated |
| Frontend unit and pages | 264 | the draft model (11), pathway layout on the captured pathway (9), formatting (7), the Lab's pages against captured fixtures (14), every Lab fixture checked against the contract (16) |
| Integration (live API) | 49 | a template through the builder's draft code; eight invalid inputs refused on the builder's fields; templates; a plan before figures; **a background execution matching the hand calculation**, reproduced, and protected from deletion |

`make check` (lint, format, types, both suites, the OpenAPI snapshot) and the smoke test pass;
the backend suite passes on PostgreSQL 16. See [testing](../testing.md).

## 9. Performance

On this machine (4 vCPUs, SQLite and PostgreSQL 16 locally): a plan takes 32 ms (SQLite) to
68 ms (PostgreSQL); a live preview 54–87 ms (large scenario 87–128 ms); an inline execution
121–225 ms (large 207–299 ms); a background execution from request to completed 185–475 ms;
reads 6–31 ms; the default sensitivity analysis 25–47 ms. Compression cuts the reference
preview from 115 KB to 15 KB. In Chromium on the production build, a saved scenario's pathway
is drawn 360 ms after navigation, and an edit shows its new preview after 545 ms (450 ms of
which is the deliberate pause). The pathway layout takes about 0.1 ms. The Lab's route
chunk is 111 KB of JavaScript (31 KB gzip). Full tables: [performance](../scenario-lab/performance.md).

## 10. Verification against the brief

| Brief | Status |
|---|---|
| §1 Build on the existing systems; verify Phase 4 first | ✓ section 1 |
| §2 The modelled pathway, not only a number; not a chatbot | ✓ [pathway](../scenario-lab/pathway.md); no generated text anywhere |
| §3 Builder: name, description, entity, variable, change, magnitude, direction, start, duration, currency, assumptions, constraints; several changes; every input validated; kinds of knowledge distinguished | ✓ — **except the demand −15 % example**: no model simulates volumes, so it is refused and its template listed as not offered (decision 43) |
| §4 Versioned object; save, duplicate, edit, version, reset, execute, compare; executed history never destroyed | ✓ (reset = *Discard changes* / *Start over*, and restoring a version); versions immutable, final executions changed by nothing (conditional updates, tested) |
| §5 Registry; models declare applicability; no automatic execution of every model; the plan and models used shown | ✓ profiles, planner, Plan tab |
| §6 Pathway with expand/collapse; type, evidence, source, simulation use, assumptions, coefficient, lag; no implied causation; only engine-supported pathways | ✓ |
| §7 Baseline against scenario: absolute, %, direction, units, currency, period; no unsupported outputs | ✓ unmodelled lines hidden, cash flow never shown |
| §8 Timeline; future values labelled simulated | ✓ |
| §9 Base / stress / extreme comparison without ranking | ✓ stress cases (templates suggest Base, Stress, Extreme) and executions compared; nothing ranked |
| §10 Sliders, low/base/high, stress, tornado; invalid combinations prevented; no false Monte Carlo | ✓ one-at-a-time, labelled as not Monte Carlo |
| §11 Templates only on implemented models | ✓ 7 offered, 2 refused with reasons |
| §12 Explainability chain; no invented explanations | ✓ assembled from stored runs |
| §13 History, reopen, reproducible | ✓ verification by re-execution and hashes |
| §14 Skills | ✓ `dataviz`; `frontend-design` unavailable (section 6); no dependency added |
| §15 Layout; no fake animation | ✓ |
| §16 Visual direction | ✓ reviewed from screenshots in both themes |
| §17 Limits, timeouts, cancellation, responsive UI, states | ✓ |
| §18 API adapted to conventions | ✓ 202/409/422/429, POST to collections |
| §19 Testing; Phases 1–4 still pass | ✓ section 8 |
| §20 Integrity | ✓ nothing fabricated, invented, filled in or presented as certain |

## 11. Limitations

The Lab's list is in [scenario-lab/limitations.md](../scenario-lab/limitations.md). The most
important: five narrow models with fixed volumes (no demand or supply-chain scenarios); partial
statements (no cash flow, tax or balance sheet); constant baselines; step changes sharing one
timing; deterministic results only; no second-round effects; illustrative data and assumed
relationships; an in-process worker pool whose start-up recovery assumes one API process; no
authentication.

## 12. Technical debt

1. **The plan is recomputed on every preview**, including the graph reads that dominate its
   time; it could be cached per graph build.
2. **The worker pool is per process, and recovery assumes one API process**: a second
   process's start-up would mark the first one's running executions interrupted (they stop
   and store nothing; no final execution changes). Several processes need a shared queue
   with leases.
3. **The page polls** executions; fine for sub-second executions, wasteful for long ones.
4. **The Simulation page still infers presentation from output names** (decision 41); the Lab
   reads profiles instead.
5. **The page runs only the default sensitivity analysis**; the API accepts chosen quantities
   and points, but the page offers no editor for them.
6. **Fixtures are large** (about 520 KB of captured JSON, regenerable by script).
7. **No browser end-to-end tests in CI**; the Lab's flows are covered in jsdom and by the live
   integration suite, and were checked by hand in Chromium.
8. **The plan's company ties** read the graph once per variable hop; fine for the sample
   network, to be measured on larger graphs.

## 13. Recommendations for Phase 6

1. **Indicators computed from stored executions** — stressed margins and coverage, dominant
   sensitivities, exposures by change — each traceable to its execution.
2. **Exposure sizes with provenance** (shares of dollar revenue, fuel costs, floating-rate
   debt) as sourced records, so templates can propose figures a user confirms.
3. **Reports assembled from stored records**, not generated narrative.
4. **Monthly market data** (exchange and policy rates, fuel prices) from licensed sources, so
   baselines can come from stored data.
5. **Cache plans per graph build and add a shared execution queue** before multi-process
   deployment.

See also the [roadmap](../roadmap.md#recommendations-for-phase-6-financial-intelligence).

## Quality gates

| Gate | Status |
|---|---|
| **Inspection first** | ✓ baseline checks on `0db7ec1` before any change |
| **Core workflow** | ✓ build, plan, preview, save, execute, explore, compare, verify |
| **Integrity** | ✓ no fabricated data; refusals instead of repairs; kinds of knowledge labelled |
| **Tests** | ✓ `make check`, the smoke test and the PostgreSQL run pass locally |
| **CI** | ✓ Runs **#10** (`c141c06`, the Scenario Lab), **#11** (`2087603`, discard changes) and **#13** (`fe16b65`, the last code change) passed all three jobs: backend on SQLite and PostgreSQL 16, frontend, and the smoke test. Run **#12** (`e952554`, final executions guarded) failed one frontend page test on a slow runner; its causes (a wait that could never succeed, one-second limits, 10 ms polling) were reproduced under CPU load and fixed in `fe16b65` |
| **Documentation** | ✓ [`docs/scenario-lab/`](../scenario-lab/README.md), model pages, ADRs 43–53 and updates across the docs |

What remains unverified is stated above: the parameters have never been estimated or
back-tested, no live World Bank value was available, the product has no authentication, and
the browser flows are not yet automated in CI.
