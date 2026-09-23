# The simulation engine

Phase 4 adds RUMIN's computational core: versioned models that turn stated inputs and
assumptions into results, with every step recorded, every result explained and every run
reproducible. This folder documents it. The plan written before implementation is
[phase-4-plan.md](../phases/phase-4-plan.md); the report on what was delivered is
[phase-4-report.md](../phases/phase-4-report.md).

> **What a simulation is, and is not.** A run is the arithmetic consequence of the inputs
> and assumptions it shows, with everything else held constant. It is **not a forecast**,
> not a probability and **not investment advice**. The first model's parameters are stated
> assumptions with defaults; none has been estimated from data.

| Page | What it covers |
|---|---|
| [Architecture](architecture.md) | Modules, the flow of a run, where each responsibility lives, safeguards |
| [The airline fuel-cost model](airline-fuel-cost.md) | Why this domain; inputs, equations E1–E19, assumptions, limitations, validation rules, a worked example checked by hand |
| [Numbers, units and currencies](numbers-and-units.md) | Exact decimals, rounding, magnitude limits, unit conversions, currencies, percentages, frequencies, stored observations |
| [Graph integration](graph-integration.md) | How a shock may travel through the knowledge graph, and only there: transmission rules, confirmation, depth, cycles, contributions |
| [Explainability and provenance](provenance.md) | What a run stores, the hashes, re-execution, explanations, Shapley contributions, the accounting bridge |
| [Sensitivity analysis](sensitivity.md) | One-at-a-time analysis: modes, limits, skipped points, ranking |
| [Model registry and adding a model](registry.md) | Definitions, versions, definition hashes, and a step-by-step guide to adding a model or a version |
| [The Simulation preview](preview.md) | The page: layout, encodings, charts, accessibility, motion and the design review |
| [Limitations](limitations.md) | What the engine and the first model cannot do, and the technical debt |

## In one picture

```
 inputs (typed text)            model definition (code, versioned, hashed)
        │                                   │
        ▼                                   ▼
 validation ── units, ranges, currencies, stored observations ──► resolved inputs
        │                                                          (each labelled)
        ▼
 graph context ── latest build: transmission rules confirmed? entity an airline?
        │
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

## Where to find it

| Layer | Location |
|---|---|
| Engine | `backend/app/simulation/` |
| First model | `backend/app/simulation/models/airline_fuel_cost.py` |
| Tables | `backend/app/models/simulation.py`, migration `0004_simulation_engine` |
| API | `backend/app/api/v1/simulations.py`, `backend/app/services/simulation.py`, `backend/app/schemas/simulation.py` |
| Page | `frontend/src/pages/SimulationPage.tsx`, `frontend/src/features/simulation/` (route `/simulation`) |
| Tests | `backend/tests/test_simulation_*.py`, `frontend/tests/simulation/`, `frontend/tests/pages/simulation.test.tsx`, `frontend/tests/integration/simulation.integration.test.ts` |
