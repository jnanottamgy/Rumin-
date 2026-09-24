# Phase 5 plan — Scenario Lab

Written before implementation, after inspecting Phases 1–4 and running their checks. It
records what was found, what was decided and why, and the order of work. The Phase 5
report will record what was delivered.

## 1. Inspection of Phases 1–4

**Verified state before any change** (commit `0db7ec1`, CI run #9 green): `make check`
passed with 596 backend tests (SQLite) and 245 frontend tests. The smoke test also passed:
a fresh database, the graph built and rebuilt with no change, then 47 integration tests
against the live API.

| | Finding |
|---|---|
| **Reusable as it is** | *Phase 1:* scenario drafts (`scenarios`, `scenario_shocks`) with shocks on economic variables, validated by the published change rules (percent changes for levels, percentage points for rates). *Phase 2:* exact decimals, stored observations with provenance. *Phase 3:* the graph states which variables affect which companies and industries (`affects_costs`, `affects_revenue`, `affects_financing`, `influences`), each with an evidence status; `GraphReader` gives bounded access. *Phase 4:* the registry, validation, `prepare`/`execute`, Shapley contributions, append-only runs with provenance, verification from snapshots, one-at-a-time sensitivity |
| **Missing for a Scenario Lab** | Drafts cannot be run, have no history (PUT overwrites) and hold floats. Only **one model** exists, so nothing can be composed. Every change is a **permanent** step from month 1, so a change cannot last a limited time or start later. The engine treats every scenario input as a percentage change, so a **rate** (percentage points) cannot be shocked. Models declare what they compute, but not which scenarios they apply to or how their outputs combine with other models' |
| **Constraints** | A released model's definition hash is pinned; any change is a new version, and the engine version is part of every inputs hash (verification recomputes it), so engine extensions must leave existing results unchanged. No authentication (runs stay local). 64 KiB request bodies. No new dependencies |
| **Installed skills** | `frontend-design` (visual direction, plan-then-build, restraint) and `dataviz` (form, colour validation, marks, interaction) apply to the Lab and are used. `financial-calculator` shares the "show your work" principle. `run`, `code-review` and `security-review` are used for verification. The artifact builders, generative-art, theme and Anthropic-brand skills do not apply to RUMIN's own design system. No 3D skill is installed, and 3D is Phase 8: the Lab stays 2D |

## 2. What the Scenario Lab is

A structured environment for asking *what happens if X changes*: build a scenario (the
changes, the company, its figures, the assumptions, the timing), see which models apply
and why, execute them, and explore the modelled pathway, the baseline against the
scenario, the months, the stress cases and the sensitivities, down to each equation. It is
not a chatbot and generates no text: every explanation is assembled from what the engine
computed and stored.

## 3. Models

Composition needs more than one model. The new models are narrow, exact, documented,
checked by hand and anchored in relationships the knowledge graph already states:

| Model | Question | Shocks | Graph anchor |
|---|---|---|---|
| `airline_fuel_cost` **1.1.0** | 1.0.0 plus the change's timing (start month, duration) and a monthly exchange-rate factor | Brent, jet fuel, USD/INR | Brent → *influences* → jet fuel (transmission); jet fuel → *affects costs of* → air transport |
| `fx_exposure` 1.0.0 | Revenue and costs invoiced in US dollars, and hedges | USD/INR | USD/INR → *affects revenue/costs of* → Kovalent, Deltrin, Aerisca, Skyvara |
| `floating_rate_interest` 1.0.0 | Interest on floating-rate debt linked to the RBI repo rate or US short-term rates | repo, Fed funds (percentage points) | repo / Fed funds → *affects financing of* → Gridwell, Trakvel, Lumeric |
| `crude_linked_costs` 1.0.0 | Operating costs priced off crude oil (feedstock, diesel) | Brent | Brent → *affects costs of* → refining, land transport |
| `gas_linked_costs` 1.0.0 | Operating costs priced off natural gas | Henry Hub | Henry Hub → *affects costs of* → Lumeric |

`airline_fuel_cost` 1.0.0 stays registered unchanged, so its runs remain verifiable. A demand
(volume) model is **not** added in this phase. Combining a volume change with models that
hold volumes fixed (fuel consumption) would be wrong, and a supply-chain model has no data
to stand on. Neither gets a template (§ 9).

**Engine extensions**, which leave every existing result unchanged:

- A change can **start** in a given month and last a given number of months. Each shock
  carries a window; propagation respects it. Models declare which inputs set it; the new
  fields are omitted from the canonical definition when unset, so existing definition
  hashes do not change.
- A scenario input in **percentage points** is a *level* shock, not a log-change. It is
  applied at its own node and never carried along a log-linear rule.

## 4. Scenario architecture

### The scenario object

A scenario has a stable identity and immutable, numbered **versions**. Saving never
overwrites: each save that changes anything is a new version. Executions refer to a
version, so an executed scenario's inputs can never change after the fact.

```
Scenario (id, name)
 └── Version n (immutable, hashed)
      ├── Changes        shocks on graph variables: direction and magnitude, % or pp
      ├── Timing         start month, duration, horizon
      ├── Subject        the company in the knowledge graph (optional)
      ├── Company        shared figures: reporting currency, revenue, operating costs
      ├── Markets        shared baselines: the exchange rate (typed or stored data)
      ├── Models         per model: auto / include / exclude, its own inputs and assumptions
      ├── Constraints    evidence required of graph relationships; stored market data only
      └── Stress cases   up to five alternative magnitudes of the same changes
Execution (append-only once finished)
 ├── Plan             models used and why, inputs, graph relationships, profile hashes
 ├── Model runs       one Phase 4 run per model (stored, verifiable)
 ├── Graph snapshot   from each run
 ├── Data snapshot    from each run
 └── Results          lines, baseline vs scenario, months, pathway, stress cases, hashes
```

Validation on save covers form and domain rules: the Phase 1 change rules, known variables,
models, inputs, a company node, and plain decimals. Whether a version can be **executed**
is the plan's job. It lists exactly what is missing, per model, and never fills anything in.

### Scenario profiles: how a model declares applicability

Next to its definition, each registered model has a **scenario profile** (kept out of the
definition so released hashes stay fixed; hashed separately and recorded with every
execution). It declares:

- **Changes it responds to:** the graph variable, the change type (percent or percentage
  points) and the model input it maps to. Nothing is converted: a Brent change in US
  dollars per barrel is not accepted by a model that needs a percentage.
- **Shared inputs** it takes from the scenario: company figures and market baselines,
  defined once for every model with the same meaning and unit.
- **Graph exposure** it needs when a company is chosen: e.g. the graph must state that
  Brent affects the costs of the company or of its industry.
- **Lines it contributes to:** each output mapped to revenue, operating costs or interest
  expense, with an **item** (jet fuel, US-dollar costs other than fuel, crude-linked
  inputs, …) and the variables driving it.

### Planning

For a version, the planner lists every registered model with a status and reasons:

- *not applicable*: no change reaches it, or the graph does not state the company's exposure;
- *applicable*: included by default, or excluded by the user;
- *blocked*: missing inputs, a constraint, or a conflict.

Two models may never claim the same (driver, line, item). When two included models could
touch the same costs through different drivers (e.g. crude-linked costs paid in dollars
and a currency change), the plan warns that the cross effect is not captured. The plan also
previews the **affected entities**: companies whose exposure to the changed variables the
graph states (directly or through their industry, bounded traversal), marked with the model
that covers each, or "no model".

### Execution

An execution runs asynchronously on a bounded worker pool. Its recorded states:

| State | What happens |
|---|---|
| `queued` | Accepted, waiting for a worker |
| `validating` | The plan is rebuilt; every included model's inputs are validated and its graph relationships confirmed (`prepare`). All or nothing |
| `simulating` | Each model is executed (Phase 4 `execute`: its transmission, equations, contributions) and stored as a Phase 4 run; stress cases are evaluated |
| `propagating` | The impact is traced across the scenario's pathway: changes → graph variables → company drivers → lines, month by month |
| `aggregating` | Lines, baseline vs scenario, margins, coverage, the timeline and its events, stress-case lines, hashes |
| `completed` / `failed` / `cancelled` | Terminal |

Each transition is stored with its time, so the page shows the real progression. The
animation replays **simulated months**, never pretend computation. Limits: 2 concurrent
executions per API process, 8 queued (then 429), 20 s timeout, cooperative cancellation,
and executions interrupted by a restart are marked failed.

### Aggregation (the lab's equations, recorded as steps)

| # | Line | Equation |
|---|---|---|
| AG1 | Change in revenue | Σ models' revenue contributions (fare recovery, US-dollar revenue, price recovery) |
| AG2 | Change in operating costs | Σ models' cost contributions (fuel, US-dollar costs, linked inputs) |
| AG3 | Change in operating profit | AG1 − AG2 (checked against Σ each model's own operating-profit change) |
| AG4 | Change in interest expense | Σ interest contributions |
| AG5 | Change in profit before tax | AG3 − AG4 |
| AG6 | Operating margin | baseline (R − O)/R; scenario over the horizon with AG1 and AG2 |
| AG7 | Interest coverage | operating profit ÷ interest, baseline and scenario, when an interest model runs |

Every line has a monthly series (the timeline) and a per-model, per-change breakdown. All
models share one currency and horizon, so lines add without conversion. **Cash flow is not
shown.** No model covers working capital or tax, so a cash-flow figure would be invented.

### Pathways, timeline, comparison, stress, sensitivity, explanation

- **Pathway:** the scenario's changes → graph variables → context (industry, company) →
  model drivers → lines → margin. Every link says what it is: a transmission rule (with
  coefficient, lag, edge, evidence status), a cited relationship (context, not used to
  compute), a model equation, or an aggregation. The graph's other relationships around
  the changed variables are listed as not modelled. Groups collapse by model.
- **Timeline:** monthly values per line and model. Events derived from the run (the change
  starts and ends, lags elapse, hedges expire, fares and loans reprice), all labelled
  simulated.
- **Comparison:** 2–6 executions side by side: key lines, absolute and percentage
  differences against a chosen reference, assumptions and models that differ, pathways.
  No ranking. Different currencies or horizons are shown but not differenced.
- **Stress cases:** alternative magnitudes of the same changes (a multiple, or explicit
  values), evaluated with the same models and assumptions; invalid cases are refused, not
  clipped.
- **Sensitivity:** one input at a time across the whole composition (changes, assumptions,
  figures), ranked by an aggregated line. It is labelled as sensitivity, distinct from
  scenario and stress analysis. There is **no stochastic simulation**: nothing is called
  Monte Carlo (Phase 9).
- **Explanation:** for each line, the models and outputs behind it, then each model's
  inputs → equations → intermediate steps → graph pathway → output, with its version,
  assumptions, data and graph snapshots, and limitations, from stored runs.

## 5. Persistence (migration `0005`)

| Table | Change |
|---|---|
| `scenarios` | Adds `current_version` and `template_id` |
| `scenario_versions` | New: immutable versions (spec, spec hash, lineage, note) |
| `scenario_shocks` | Now belong to a version; values read as exact decimals |
| `scenario_executions` | New: state, stages with times, plan, results, errors, hashes |
| `scenario_execution_runs` | New: the Phase 4 runs of an execution (`RESTRICT`) |
| `scenario_sensitivity_analyses` | New: append-only analyses of an execution |

Existing drafts become version 1 of themselves. A scenario with executions cannot be
deleted (409).

## 6. API (following the existing conventions)

| Brief | Implemented | Why |
|---|---|---|
| `POST/GET /scenarios`, `GET /scenarios/{id}` | Same; responses gain versions and the latest execution | The Phase 1 resource evolves |
| `PATCH /scenarios/{id}` | `PUT /scenarios/{id}` saves a new version (optional `base_version`, 409 if stale) | The API replaces whole documents; a new version is never partial |
| `POST /scenarios/{id}/duplicate` | Same (201) | — |
| — | `GET /scenarios/{id}/versions`, `…/versions/{n}` | History |
| — | `POST /scenarios/plan`, `POST /scenarios/preview` | The builder's live plan and what-if values; nothing stored |
| `POST /scenarios/{id}/run` | `POST /scenarios/{id}/executions` (202, `Location`) | Creation by posting to a collection (ADR 40); asynchronous |
| `GET /scenarios/{id}/results`, `/pathways`, `/explanation` | `GET /scenario-executions/{id}`, `…/results`, `…/pathways`, `…/explanation` | Results belong to an execution, not to a changing scenario |
| — | `POST /scenario-executions/{id}/cancel`, `…/verify`, `…/sensitivity` | Cancellation, reproducibility, sensitivity |
| `POST /scenarios/compare` | `GET /scenario-comparisons?execution_id=…` | A read-only computation over stored executions |
| `GET /scenario-templates` | Same, plus `GET /scenario-templates/{id}` | — |

## 7. Frontend

The Scenario Lab page is rebuilt as a workspace: controls on the left, the impact
pathway in the centre, live results on the right, and the timeline and execution strip
at the bottom. It stacks on narrow screens. Views cover templates, the plan, results,
months, comparison, stress and sensitivity, explanation, and history. The design is
planned with `frontend-design` and `dataviz` and reviewed from screenshots. One
orchestrated motion follows real state: stages as the server reports them, then a replay
of simulated months. No new dependencies.

## 8. Templates (all on implemented models)

Crude oil shock on an airline; jet fuel price shock; rupee depreciation; policy-rate rise;
crude oil shock on crude-linked costs; natural gas price shock (energy); oil, rupee and
rates together. Each states its required and optional inputs, models, validation rules,
expected outputs and suggested stress cases. Demand and supply-chain templates are not
offered: no model supports them.

## 9. Out of scope

Stochastic simulation and parameter estimation (Phase 9), demand and supply-chain models,
per-change timing (one timing per scenario), cash-flow and tax effects, authentication and
quotas (Phase 10), 3D (Phase 8).

## 10. Order of work

1. This plan.
2. Engine extensions (timing windows, level shocks) and the models, checked by hand.
3. Migration `0005`, scenario versions, profiles, templates, planner.
4. Executor, runner, aggregation, pathways, explanation, stress, sensitivity, comparison.
5. API, OpenAPI snapshot, generated types, system capabilities.
6. The Scenario Lab frontend, with the `frontend-design` and `dataviz` skills.
7. Tests (including every Phase 1–4 suite), performance, browser review.
8. Documentation, report, push, CI.
