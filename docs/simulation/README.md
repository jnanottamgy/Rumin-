# The simulation engine

Phase 4 adds RUMIN's computational core: versioned models that turn stated inputs and
assumptions into results, with every step recorded, every result explained and every run
reproducible. This folder documents it. The plan written before implementation is
[phase-4-plan.md](../phases/phase-4-plan.md); the report on what was delivered is
[phase-4-report.md](../phases/phase-4-report.md). Phase 5 added four models, a second
version of the airline model and two engine extensions, so that the
[Scenario Lab](../scenario-lab/README.md) can run several models on one scenario
([phase-5-plan.md](../phases/phase-5-plan.md)).

> **What a simulation is, and is not.** A run is the arithmetic consequence of the inputs
> and assumptions it shows, with everything else held constant. It is **not a forecast**,
> not a probability and **not investment advice**. Every model's parameters are stated
> assumptions with defaults; none has been estimated from data.

| Page | What it covers |
|---|---|
| [Architecture](architecture.md) | Modules, the flow of a run, where each responsibility lives, safeguards |
| [The airline fuel-cost model](airline-fuel-cost.md) | Why this domain; inputs, equations E1–E19, assumptions, limitations, validation rules, a worked example checked by hand; what version 1.1.0 changes |
| [Foreign-currency revenue and costs](fx-exposure.md) | Revenue and costs in US dollars at the month's exchange rate, with hedges: inputs, equations E1–E14, rules, a worked example |
| [Floating-rate interest costs](floating-rate-interest.md) | Interest on debt linked to the repo rate or US short-term rates, changed in percentage points: inputs, equations E1–E7, rules, a worked example |
| [Crude-oil-linked costs](crude-linked-costs.md) | Costs priced off Brent crude, with hedges and price recovery: inputs, equations E1–E14, rules, a worked example |
| [Natural-gas-linked costs](gas-linked-costs.md) | The same template for costs priced off Henry Hub natural gas |
| [Numbers, units and currencies](numbers-and-units.md) | Exact decimals, rounding, magnitude limits, unit conversions, currencies, percentages, frequencies, stored observations |
| [Graph integration](graph-integration.md) | How a shock may travel through the knowledge graph, and only there: transmission rules, confirmation, depth, cycles, contributions |
| [Explainability and provenance](provenance.md) | What a run stores, the hashes, re-execution, explanations, Shapley contributions, the accounting bridge |
| [Sensitivity analysis](sensitivity.md) | One-at-a-time analysis: modes, limits, skipped points, ranking |
| [Model registry and adding a model](registry.md) | The registered models and versions, definitions, definition hashes, Scenario Lab profiles, and a step-by-step guide to adding a model or a version |
| [The Simulation preview](preview.md) | The page: layout, encodings, charts, accessibility, motion and the design review |
| [Limitations](limitations.md) | What the engine and the first model cannot do, and the technical debt |

## Models

Five models are registered, all deterministic, monthly and `preview`; every company figure
comes from the user. [The registry](registry.md#registered-models) lists their modules,
changes and Scenario Lab profiles.

| Model | Versions | What it answers |
|---|---|---|
| [`airline_fuel_cost`](airline-fuel-cost.md) | 1.0.0, 1.1.0 (default) | What a change in crude oil, jet fuel and the exchange rate does to an airline's fuel bill and operating profit, month by month, with hedging and fare pass-through |
| [`fx_exposure`](fx-exposure.md) | 1.0.0 | What a change in the exchange rate does to revenue and costs invoiced in US dollars, month by month, with hedges |
| [`floating_rate_interest`](floating-rate-interest.md) | 1.0.0 | What a change in the repo rate or US short-term rates does to interest on floating-rate debt, profit before tax and interest coverage, month by month |
| [`crude_linked_costs`](crude-linked-costs.md) | 1.0.0 | What a change in the price of crude oil does to operating costs priced off it and to operating profit, month by month, with hedging and price recovery |
| [`gas_linked_costs`](gas-linked-costs.md) | 1.0.0 | What a change in the price of natural gas does to operating costs priced off it and to operating profit, month by month, with hedging and price recovery |

## In one picture

```
 inputs (typed text)            model definition (code, versioned, hashed)
        │                                   │
        ▼                                   ▼
 validation ── units, ranges, currencies, stored observations ──► resolved inputs
        │                                                          (each labelled)
        ▼
 graph context ── latest build: transmission rules confirmed?
        │         entity a company the model accepts?
        ▼
 propagation (transmission engine) ─► compute (every step recorded) ─► outputs
        │                                                                 │
        ▼                                                                 ▼
 Shapley contributions · accounting bridge (checked) · inputs hash · result hash
        │
        ▼
 stored run (append-only) ─► explanation · provenance · verify · sensitivity
```

Every calculation happens on the server. The frontend collects text and shows what the
engine returned; it never computes a financial figure.

## Timing and rate changes (Phase 5)

Two engine extensions let a model time its changes and change a rate. A model that uses
neither is evaluated exactly as before: `ENGINE_VERSION` is still `1.0.0`, and
`airline_fuel_cost` 1.0.0 keeps its definition hash.

- **Timing windows.** A definition may name two integer settings, `shock_start_input` and
  `shock_duration_input`; every Phase 5 model, and `airline_fuel_cost` 1.1.0, names
  `shock_start_month` and `shock_duration_months`. Every change of a run then takes effect
  in the start month S and lasts D months, from S to S + D − 1, or to the end of the
  horizon when D = 0; afterwards the changed variables return to their baselines. The
  transmission engine applies each change only inside its window, and a path's lags move
  both ends of the window. Each transmission path records its first and last month. The
  run rate a model reads (`Propagation.final`) is the change while it lasts, whatever the
  duration. A definition without timing inputs keeps permanent changes from month 1, and
  the two fields are left out of its canonical JSON, so definitions released before them
  keep their hashes.
- **Percentage-point changes are level shocks.** A scenario input that changes a graph
  variable must be in `percent_change` or `percentage_points`. A percent change enters the
  engine as a log-change, ln(1 + x/100), which log-linear transmission rules carry. A
  change in percentage points (a rate, as in the floating-rate interest model) is a level
  shock: it is applied at its own node, in percentage points, and never carried along a
  log-linear rule; its transmission path has the kind `level`. A definition with a rule
  that starts or ends at a node shocked in percentage points is refused when it is built.

## Where to find it

| Layer | Location |
|---|---|
| Engine | `backend/app/simulation/` |
| Models | `backend/app/simulation/models/`: `airline_fuel_cost.py` (1.0.0), `airline_fuel_cost_1_1.py` (1.1.0), `fx_exposure.py`, `floating_rate_interest.py`, `commodity_linked_costs.py` (both commodity models) and `common.py` (the inputs and statements several models share) |
| Scenario Lab profiles | `backend/app/scenario_lab/profiles.py` |
| Tables | `backend/app/models/simulation.py`, migration `0004_simulation_engine` |
| API | `backend/app/api/v1/simulations.py`, `backend/app/services/simulation.py`, `backend/app/schemas/simulation.py` |
| Page | `frontend/src/pages/SimulationPage.tsx`, `frontend/src/features/simulation/` (route `/simulation`) |
| Tests | `backend/tests/test_simulation_*.py` (the Phase 5 models in `test_simulation_models.py`; timing, level shocks and airline 1.1.0 in `test_simulation_timing.py`), `frontend/tests/simulation/`, `frontend/tests/pages/simulation.test.tsx`, `frontend/tests/integration/simulation.integration.test.ts` |
