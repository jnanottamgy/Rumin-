# Phase 4 plan — Simulation engine

Written before implementation, after inspecting Phases 1–3 and running their checks.
It records what was found, what was decided and why, and the order of work. The Phase 4
report will record what was delivered.

## 1. Inspection of Phases 1–3

**Verified state before any change** (commit `b065261`): `make check` passed with 450
backend tests (SQLite), 202 frontend tests, lint, types and the OpenAPI snapshot. The
end-to-end smoke test also passed: a fresh database, the knowledge graph built twice
with no change on the rebuild, and 39 integration tests against the live API. CI run #7
passed on the same commit.

| | Finding |
|---|---|
| **Usable as it is** | *Phase 1:* variable definitions with units (Brent crude in USD per barrel, jet fuel in USD per US gallon, USD/INR in INR per USD). Published scenario-change limits (percent change > −100 % and ≤ 1,000 %, at most 4 decimals). Scenario drafts with shocks on variables. *Phase 2:* exact decimals everywhere (`DecimalString`, `canonical_decimal`, `decimal_fits`). The World Bank series `wb-ind-pa-nus-fcrf` (official exchange rate, INR per USD, annual average), linked to the USD/INR variable with the difference stated. Stored observations carry their provenance. *Phase 3:* the knowledge graph states the channels an airline fuel-cost model needs: Brent crude → *influences* → jet fuel; jet fuel → *affects costs of* → air transport; USD/INR → *affects costs of* → Aerisca Airways and Skyvara Air; both airlines → *operates in* → air transport. `GraphReader` gives typed access to them with their evidence status. The `simulated_output` knowledge category already has a glyph in the design system |
| **Missing, as expected** | No simulation of any kind: the `simulation_engine` capability says "planned for Phase 4". Graph edges carry no magnitudes (ADR 25), so no coefficient can be read from the graph. No variable has a stored value in this environment (the World Bank run was blocked). RUMIN holds **no company financial data** by policy (Phase 1 tests forbid numeric financial figures in the sample) |
| **Constraints** | No authentication (so runs are local-only, like scenario drafts). Request bodies are capped at 64 KiB. There is a strict "no fabricated data" rule, so company figures must come from the user and every default must be an explicit, labelled assumption |
| **Out of scope** | The full Scenario Lab workflow (Phase 5), Monte Carlo (prepared for, not built), 3D (Phase 8), real-time data (never) |

## 2. The domain: an airline fuel-cost shock

Five candidates were compared on the brief's five criteria:

| Candidate | Data available | Financial relevance | Mathematical clarity | Validation potential | Extensibility |
|---|---|---|---|---|---|
| **Airline fuel-cost shock** (crude oil, jet fuel, the rupee) | **Best.** The graph states a two-hop channel (crude → jet fuel → airlines) and the currency channel. The World Bank INR/USD series provides a historical baseline. The variables have defined units | **High.** Fuel is a large, volatile airline cost; a weaker rupee raises the cost of dollar-priced fuel | Clear identity: volume × price × exchange rate, with hedging and fare pass-through | Strong: closed-form cases and invariants (no shock → no change; fully hedged → no price effect; full pass-through → no profit effect) | The same structure fits refiners (crude), chemicals (gas) and logistics (diesel) |
| Interest-rate impact on financing costs | Weak: only the World Bank lending rate, annual | High | Very clear (debt × Δrate) | Good | Moderate |
| Currency depreciation and imported costs | Good (FX series) | High | Clear | Good | Part of the airline model |
| Generic commodity impact | Needs data RUMIN lacks | Varies | Unclear without a specific cost structure | Weak | High, but premature |
| Manufacturing input-cost shock | No data | Moderate | Needs input-output tables | Weak | High |

**Choice: the airline fuel-cost shock.** It uses the most of what RUMIN already holds (graph
channels, variable units, a historical FX baseline) and exercises every requirement:

- units and explicit conversions (litres, US gallons, US barrels);
- currencies (USD-priced fuel in a reporting currency);
- frequency (annual figures on a monthly grid);
- time lags (crude pass-through, hedge expiry, fare pass-through);
- multi-hop propagation through validated graph relationships.

The model stays narrow: one airline, one fuel, everything else held constant.

## 3. Architecture

A new backend package `app/simulation/`, with separate modules:

| Module | Responsibility |
|---|---|
| `decimal_math.py` | One exact-decimal context (34 significant digits, half-even rounding, traps on overflow and invalid operations), `ln`/`exp`, bounds checks, output rounding |
| `units.py` | Volume units with exact litre factors (US gallon = 3.785411784 L; US barrel = 42 US gallons), currency codes, conversions that record themselves as steps |
| `definitions.py` | Typed, frozen model definitions: inputs, parameters, equations, units, validation rules, assumptions, limitations, transmission rules, outputs, status. Each has a canonical JSON form and a SHA-256 **definition hash** |
| `registry.py` | The versioned model registry, where (model, version) points to a definition and its compute function |
| `models/airline_fuel_cost.py` | The first model, version 1.0.0 |
| `validation.py` | Generic input validation against a definition: types, units, currency, percentage format, ranges, decimals, required fields and cross-field rules. Resolution of stored observations and graph channel checks |
| `transmission.py` | A general propagation engine: direction, coefficients (log-elasticities), lags in months, maximum depth, simple paths only (cycle protection), a path budget, and a contribution for every path |
| `engine.py` | Validate → resolve → propagate → compute (recording every step) → contributions → hashes |
| `sensitivity.py` | One-at-a-time analysis (low / base / high, relative variations, explicit values) under resource limits |
| `explain.py` | Structured explanations: equations, steps, pathway, contributions, assumptions, provenance, limitations |
| `graph_context.py` | Reads the knowledge graph through `GraphReader`: confirms transmission edges, checks the entity, and records the graph snapshot |
| `persistence.py` | Model-version sync, run and analysis storage (append-only) |

The API (`app/api/v1/simulations.py`), schemas and services follow the existing layering.
The frontend only renders definitions and results. **No calculation happens in the browser.**

### Numbers

All arithmetic uses `Decimal` in one context, so results are identical on every
machine. Inputs arrive as exact decimal strings (JSON numbers are accepted and read
through their shortest representation). Outputs are rounded half-even to 10 decimal
places and served as plain decimal strings, following the Phase 2 convention.

### Graph integration (controlled)

Graph edges are not equations. A model **declares** the transmission rules it accepts:
edge type, source node, target node, coefficient parameter and lag parameter. The engine
follows an edge only when:

1. a rule declares it;
2. the latest completed graph build contains it as a current, validated edge;
3. the shock actually needs it.

Coefficients and lags come from the model's parameters (documented assumptions), never
from the graph. A missing edge blocks the run with an explanation. Every edge used is
recorded with its evidence status and the build it came from. The airline model declares
one propagation rule: Brent crude → *influences* → jet fuel, with elasticity β and a lag.
Other graph edges are listed as "not used by this model". Examples are Brent → India CPI
and the fed funds rate → USD/INR.

### Reproducibility and provenance

- The **inputs hash** is SHA-256 over the model ID, version, definition hash, engine
  version and the normalised inputs with defaults resolved.
- The **result hash** is SHA-256 over the canonical outputs.
- Identical inputs give identical hashes, and a verify endpoint re-executes a stored run
  and compares them.
- Runs store the input snapshot (each value with its category and source: user, default
  assumption or stored observation with its provenance), the parameters, the
  assumptions, the graph snapshot, every intermediate step, the outputs, the warnings,
  the limitations, the timestamps and `random_seed: null`. The model is deterministic;
  the field is ready for Monte Carlo.

### Persistence (migration `0004`)

| Table | Holds |
|---|---|
| `simulation_model_versions` | One row per (model, version): the definition snapshot and its hash. A code change that alters a registered version's definition without a version bump is refused |
| `simulation_runs` | Append-only runs: model version, input snapshot and hash, parameters, assumptions, graph and data snapshots, outputs, contributions, result hash, warnings, limitations, timings |
| `simulation_run_steps` | Every calculation step: equation, period, inputs and output with units |
| `simulation_sensitivity_analyses` | Append-only analyses of a run: request, results, ranked summary, evaluation count |

No update or delete paths exist. A new run never overwrites an old one.

### API (adapted to existing conventions)

| Suggested | Implemented | Why |
|---|---|---|
| `GET /simulation-models` | `GET /api/v1/simulation-models`, `GET /api/v1/simulation-models/{id}` | As suggested, plus the full definition |
| `POST /simulations/validate` | `POST /api/v1/simulations/validate` | As suggested; returns a validation report (200) without storing anything |
| `POST /simulations/run` | `POST /api/v1/simulations` | The codebase creates resources by `POST` to the collection (as `POST /scenarios` does); 201 with `Location` |
| `GET /simulations/{run_id}`, `/explanation`, `/provenance` | Same | — |
| `POST /simulations/{run_id}/sensitivity` | Same (201), plus `GET` for stored analyses | — |
| — | `GET /api/v1/simulations` (list), `POST /api/v1/simulations/{run_id}/verify` | Listing runs; checking reproducibility |

### Safeguards

- Propagation depth ≤ 4, and at most 500 transmission paths.
- Horizon ≤ 36 months.
- Sensitivity: ≤ 8 inputs, ≤ 7 points each, ≤ 60 evaluations and a 10-second deadline.
- The existing 64 KiB body limit.
- Decimal traps plus explicit magnitude bounds on inputs and outputs.
- No `eval`, and no user-supplied formulas: equations are Python functions registered in code.

## 4. The airline fuel-cost model (v1.0.0)

**Inputs, by category** (each labelled in the API and the UI):

- *Scenario inputs*:
  - crude oil change (%, on the Brent variable);
  - additional jet fuel change beyond crude (%, on the jet fuel variable);
  - change in reporting currency per USD (%, on USD/INR when the currency is INR).
- *Historical data or user input*:
  - baseline jet fuel price (USD per US gallon, US barrel or kilolitre);
  - baseline exchange rate (reporting currency per USD). It can come from the stored
    World Bank annual average, with a warning that it is an annual average, not a
    current rate.
- *User inputs (the airline)*:
  - reporting currency;
  - annual revenue;
  - annual operating costs;
  - annual fuel consumption (kilolitres, US gallons or US barrels);
  - optionally, the airline's node in the graph.
- *Assumptions (defaults, each with its rationale)*:
  - crude-to-jet-fuel elasticity β = 1 (a constant proportional refining margin);
  - pass-through lag of 0 months;
  - hedge ratio 0 % and hedge cover of 0 months (no hedging unless entered);
  - fare pass-through 0 % and fare lag of 0 months (no recovery unless entered).
- *Setting*: horizon of 12 months (1–36).

**Equations** (month *m* = 1 … *H*, shocks applied from month 1):

- Convert the consumption to the price's volume unit (exact factors). Baseline
  benchmark fuel cost *B* = volume × price (USD) × exchange rate, and the fuel share
  *B*/operating costs must be at most 1.
- Monthly baseline *b₀* = *B*/12 (even consumption).
- Jet fuel log-change ℓⱼ(m) = β·ln(1+c)·[m > L] + ln(1+s). Exchange rate factor 1+x.
- Hedged share hₘ = h while m ≤ hedge months. Hedges fix the USD price at the baseline;
  the exchange rate is not hedged.
- Scenario monthly cost *b₁(m)* = *b₀*·(1+x)·[hₘ + (1−hₘ)·exp(ℓⱼ(m))].
- Change Δb(m) = b₁ − b₀.
- Fare recovery Δr(m) = φ·Δb(m − L_f).
- Operating profit change Δπ(m) = Δr − Δb.
- Aggregates over the horizon: totals, baseline and scenario operating margin, the
  steady-state annual effect, and the revenue change that would offset the fuel cost.

**Explanations**:

- **Shapley attribution** of every output total across the non-zero shocks (crude,
  jet fuel margin, currency). It is exact, order-independent, and sums to the total.
- An **accounting bridge**: gross fuel-cost change → hedging effect → fare recovery →
  operating profit change.

## 5. Order of work

1. This plan.
2. Units, decimal maths, definitions, registry, the airline model.
3. Validation, transmission engine, execution, explanations, hashes.
4. Sensitivity analysis.
5. Persistence and migration `0004`.
6. API, OpenAPI snapshot, generated types, system capability.
7. Simulation Preview UI, using the installed `frontend-design` and `dataviz` skills.
8. Tests, documentation, report, push, CI.
