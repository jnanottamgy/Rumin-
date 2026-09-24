# Architecture

The engine is a backend package, `app/simulation/`, with one responsibility per module.
Definitions, validation, execution, sensitivity, explanation, persistence and the API are
separate, so each can be tested alone and a new model reuses all of them.

## Modules

| Module | Responsibility | Touches the database? |
|---|---|---|
| `decimal_math.py` | One exact-decimal context (34 significant digits, half-even rounding, traps on invalid operations, division by zero and overflow), correctly rounded `ln` and `exp`, output rounding and magnitude limits | No |
| `units.py` | Volume units with exact litre factors, price units (USD per volume), currency-code format, unit labels | No |
| `definitions.py` | Frozen, typed model definitions: inputs, equations with terms, outputs, transmission rules, supporting relationships, assumptions, limitations, validation rules, references, pathway, bridge. Consistency checks at construction; canonical JSON and the SHA-256 definition hash | No |
| `registry.py` | The versioned registry: (model, version) → definition, cross-field check function, compute function. Engine version | No |
| `models/` | One module per model version, each with its definition, its checks and its compute function: `airline_fuel_cost.py` (1.0.0, E1–E19) and `airline_fuel_cost_1_1.py` (1.1.0), `fx_exposure.py`, `floating_rate_interest.py`, and `commodity_linked_costs.py`, which builds the crude- and gas-linked models from one template. `common.py` holds the inputs and statements several models share ([the registry](registry.md#registered-models)) | No |
| `runtime.py` | What models are given and return: resolved values, the step recorder, issues, the compute context and result | No |
| `validation.py` | Generic input validation against a definition: kinds, units, currencies, ranges, decimal places, required inputs, stored-observation resolution; each input labelled with the kind of knowledge it is | Through a lookup function only |
| `data_sources.py` | The latest current, reported value of a series a definition names, with its provenance | Yes (read) |
| `graph_context.py` | Confirms a model's transmission rules and supporting relationships in the latest graph build, checks the chosen entity, and snapshots what it found | Yes (read) |
| `transmission.py` | The propagation engine: shocks along links, with coefficients, lags, maximum depth, simple paths only and a path budget | No |
| `engine.py` | `prepare` (validation, stored data, graph) and `execute` (propagation, compute, Shapley contributions, bridge check, hashes). `execute` is pure | `prepare` reads; `execute` does not |
| `sensitivity.py` | One-at-a-time analysis under limits | No |
| `explain.py` | Structured explanations of a stored run: equations used, steps, pathway, contributions, parameters, assumptions, limitations, warnings | No (reads the stored run) |
| `persistence.py` | Model-version storage and the definition-hash check; append-only storage of runs, steps and analyses; rebuilding a run's preparation from its snapshot | Yes |

Around the package, following the existing layers:

- `app/schemas/simulation.py`: request and response schemas (Pydantic), with bounded
  request sizes and strict number types;
- `app/services/simulation.py`: the API logic (models, validate, run, read, explain,
  provenance, verify, sensitivity), mapping engine errors to the standard error envelope;
- `app/api/v1/simulations.py`: the routes;
- `app/models/simulation.py`: the four tables (migration `0004`).

## The flow of a run

1. **Request.** `POST /api/v1/simulations` with a model ID, an optional version and the
   inputs as exact decimal strings (or JSON numbers, read through their shortest form).
2. **Model.** The registry resolves the version (the latest runnable one by default). A
   deprecated version is refused; an unknown one is a 422.
3. **Validation** (`validation.py`). Unknown inputs, missing required inputs, values that
   are not plain numbers, out-of-range values, too many decimal places, units not offered
   and wrong currency codes are each reported with the field they concern. An input may
   ask for a stored observation instead of a value; it is used only if the series is one
   the definition names, a value is stored, and its unit and currency pair match.
4. **Graph context** (`graph_context.py`). The latest graph build is read: is each
   transmission rule present as a current, validated edge (only the airline model declares
   one: crude oil → jet fuel)? Is the chosen entity (if any) a company of the build, linked
   as the model requires (the airline model: a company in air transport)? Is the graph older
   than its sources? The snapshot of what was found is kept with the run.
5. **Checks.** The model's own cross-field rules (for the airline model: a USD reporting
   currency needs a rate of exactly 1; the fuel bill cannot exceed operating costs; timing
   notes) and the channel check: a change that needs a relationship the graph does not
   confirm is refused.
6. **Execution** (`engine.py`, pure). Percent changes become log-changes and the
   transmission engine carries them along the confirmed links; a change in percentage points
   stays a level change at its own node; each change applies from its start month for its
   duration ([timing and rate changes](README.md#timing-and-rate-changes-phase-5)); the
   model computes every month and every total, recording each step with its inputs;
   contributions are attributed by Shapley values; the accounting bridge is checked (the
   run fails if it does not close); outputs are rounded; the inputs hash and the result hash
   are computed.
7. **Storage** (`persistence.py`). The model version's definition is stored the first time
   it is used, and compared on every later use. The run and its steps are inserted, never
   updated.
8. **Reading.** The run, its explanation and its provenance are read from what was stored,
   never recomputed from current code or data.

Validation (`POST /simulations/validate`) runs steps 1–5 and stores nothing. Verification
(`POST /simulations/{id}/verify`) rebuilds step 6's input from the stored snapshot and
compares the hashes. Sensitivity analysis re-evaluates the model around a stored run's
inputs.

## Safeguards

| Limit | Value | Where |
|---|---|---|
| Request body | 64 KiB (the existing API limit) | Middleware |
| Inputs per request | 40 | Schema |
| Length of a value sent as text | 128 characters | Schema |
| Numbers | Plain decimal notation only: no exponents, separators, symbols, `NaN` or infinities; booleans refused; at most 30 digits either side of the point | Schema and `validation.py` |
| Each input | Its own range, decimal places, unit choices and kind | Definition |
| Horizon | 1–36 months | Definition |
| Propagation depth | 4 links (every registered model); 6 at most for any model | Definition, `transmission.py` |
| Transmission paths | 500 per run (5,000 at most for any use) | `engine.py`, `transmission.py` |
| Changes attributed by Shapley values | 6 at once (2⁶ = 64 evaluations) | `engine.py` |
| Sensitivity | 8 inputs, 7 points each, 60 evaluations, 10 seconds | `sensitivity.py` |
| Numbers during a calculation | 34 significant digits; overflow, invalid operations and division by zero raise | `decimal_math.py` |
| Any output | Below 10²⁰ in its unit (so it fits `NUMERIC(38, 18)`) | `decimal_math.py` |
| Code execution | None: equations are Python functions in the code base; no formula is ever evaluated from text (a test fails if the package calls `eval`, `exec` or `compile`) | Tests |

A limit is reported, never worked around: an analysis that would exceed its budget is
refused with the reason; a calculation that overflows is a 422 with the message; a point of
a sensitivity analysis that falls outside an input's range is skipped and listed, never
clipped to the nearest allowed value.

## Performance

Measured on the build machine (SQLite, Python 3.11), with the page's example inputs:

| Operation | Median |
|---|---|
| Execute, one change, 12 months (99 steps) | 2.4 ms |
| Execute, three changes (Shapley: 8 evaluations), 12 months | 4.4 ms |
| Execute, three changes, 36 months (267 steps) | 9.0 ms |
| Sensitivity, the 7 default inputs (15 evaluations) | 6.2 ms |
| Sensitivity, 7 inputs × 7 values (50 evaluations), 36 months | 36.7 ms |
| `POST /api/v1/simulations`, end to end (validation, graph, execution, storage) | 30–35 ms |
| `GET` the run / explanation / provenance | 5 / 7.5 / 3.7 ms (16 / 54 / 11 kB) |
| `POST …/verify` | 6.6 ms |

The first request after the graph's sources change can take longer: the graph's
freshness check reads every source record (see [graph performance](../graph/performance.md)),
and its answer is cached for 30 seconds.
