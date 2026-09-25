# Scenario Lab

The Scenario Lab answers *what happens if something changes?* — a 20 % rise in Brent crude,
a 10 % weaker rupee, a repo rate 1.5 percentage points higher — for a company whose figures
you enter. It chooses the models that apply from what each model declares and what the
knowledge graph states, runs them through the Phase 4 simulation engine, and shows the
**modelled pathway** from each change to each line of the result, not only a final number.

It is an instrument, not a chatbot: it generates no text. Every figure is computed by the
backend from stated inputs and assumptions, and every explanation is assembled from what
the engine computed and stored.

| | |
|---|---|
| **Where** | `/scenarios` in the web app; `/api/v1/scenarios…`, `/scenario-executions…`, `/scenario-templates…`, `/scenario-comparisons` in the API |
| **Backend** | `backend/app/scenario_lab/` (spec, validation, planner, executor, runner, aggregation, pathways, explanation, evaluation, sensitivity, joint grids, Monte Carlo, sampling and summaries, comparison, templates), `backend/app/services/scenarios.py`, `backend/app/services/scenario_lab.py`, `backend/app/services/scenario_analyses.py` |
| **Frontend** | `frontend/src/pages/ScenarioLabPage.tsx`, `frontend/src/features/scenarioLab/` |
| **Models** | five registered models (six versions) — see [the registry](../simulation/registry.md) |
| **Data** | migration `0005`: scenarios with immutable versions, executions, their model runs and sensitivity analyses; migration `0008`: stored grids and Monte Carlo analyses — see [the data model](../data-model.md) |

## What you can do

1. **Start** from a template built on implemented models, from a blank scenario, or from a
   saved one. Templates that no model can support (a demand shock, a supply-chain
   disruption) are listed as *not offered*, with the reason.
2. **Describe the changes** — each a variable of the knowledge graph, a direction and a
   magnitude in the variable's own unit (a percentage for prices and exchange rates,
   percentage points for rates), within the limits the API publishes for it. Choose when
   they start and how long they last, and the horizon (1–36 months).
3. **Describe the company** — optionally a company of the knowledge graph (its stated
   exposures decide which models apply by default), and the figures the models need:
   reporting currency, annual revenue and operating costs, the exchange rate (typed, or the
   latest stored World Bank value), and each model's own figures and assumptions. RUMIN
   never fills a figure in.
4. **See the plan** — every model, whether it is included, available, excluded, blocked or
   not applicable, and why; which change each model simulates; what is still missing.
5. **Watch a live preview** — the backend computes the scenario as you edit (not stored,
   labelled as a preview).
6. **Execute** — the execution runs in the background, moves through recorded stages
   (validating, simulating, propagating, aggregating) and is stored with its model runs and
   hashes. Every execution can be re-executed from what it stored to check it reproduces.
7. **Explore** the result: the pathway, baseline against scenario, the simulated months
   (with a replay), stress cases, *what caused this?* for every line and metric, the history
   of versions and executions, and comparisons between executions.
8. **Analyse** a stored execution (Phase 9): sensitivity to chosen quantities one at a time
   or **two together** (with their interaction), and a **Monte Carlo** analysis under
   distributions you state, with a recorded seed; each included model's
   [verification register](../simulation/verification.md) in the plan. See
   [advanced analysis](advanced-analysis.md).

## The reference example

The example used throughout the tests and these documents is **"oil, rupee and rates" on
Aerisca Airways**, a *fictional* airline of RUMIN's sample network, with **hypothetical
round figures** chosen so every result can be checked by hand
(`backend/tests/scenario_support.py`):

| Change | Model it reaches | Effect over 12 months (INR) |
|---|---|---|
| Brent crude +20 % | Airline fuel cost (via jet fuel, β = 1, 1-month lag) | fuel +12,450,000, fare recovery +4,925,000 (hedges 40 % for 6 months, half passed to fares after 2 months) |
| USD/INR +5 % | Airline fuel cost and Foreign-currency revenue and costs | US-dollar revenue +2,000,000, US-dollar costs +800,000 |
| RBI repo rate +0.5 pp | Floating-rate interest (repricing after 3 months) | interest +375,000 |

| Line | Baseline | Change |
|---|---|---|
| Revenue | 300,000,000 | +6,925,000 |
| Operating costs | 250,000,000 | +13,250,000 |
| Operating profit | 50,000,000 | −6,325,000 |
| Interest expense | 12,000,000 | +375,000 |
| Profit before tax | 38,000,000 | **−6,700,000 (−17.63 %)** |

Operating margin moves from 16.67 % to 14.23 %; interest coverage from 4.17× to 3.53×. Cash
flow is not shown: no model covers working capital, tax or investment.

## Read next

- [Architecture](architecture.md) — the scenario object and its versions, the plan, the
  execution and its stages, the Lab's equations, stress cases, sensitivity, comparison,
  reproducibility, limits.
- [The pathway](pathway.md) — what each node and link means, graph context versus graph
  transmission, what is listed as not modelled, the month replay.
- [Advanced analysis](advanced-analysis.md) — the four kinds of analysis; one at a time,
  two together and Monte Carlo on a stored execution: mathematics, reproducibility, limits,
  API, performance.
- [The interface](interface.md) — layout, controls, preview versus stored execution, the
  views, accessibility and design choices.
- [Performance](performance.md) — measured times and sizes.
- [Limitations](limitations.md) — what the Lab does not do.
- The models: [airline fuel cost](../simulation/airline-fuel-cost.md),
  [foreign-currency revenue and costs](../simulation/fx-exposure.md),
  [floating-rate interest](../simulation/floating-rate-interest.md),
  [crude-oil-linked costs](../simulation/crude-linked-costs.md),
  [natural-gas-linked costs](../simulation/gas-linked-costs.md).
- [The API](../api.md#scenario-lab), [the Phase 5 report](../phases/phase-5-report.md) and
  [the Phase 9 report](../phases/phase-9-report.md).
