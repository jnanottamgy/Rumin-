# The verification register

Phase 9 makes what has been checked about each model **visible in the product**. Until then
the hand calculations lived in the model pages and the tests only; every model was, and
remains, *preview*. The register runs every registered model version through the real engine
now — `validate_inputs` → the model's `check` → `execute`, without a database — and reports
each check with its detail, beside a list of what is **not** verified.

> Passing every check shows that the arithmetic reproduces hand calculations and that the
> properties the model states hold. It does **not** validate the model: no parameter has been
> estimated from data and no result has been compared with what happened. RUMIN never calls a
> model "validated".

## The checks

| Kind | Check | What it establishes |
|---|---|---|
| Reference | Worked example | The model page's worked example — HYPOTHETICAL round figures, calculated by hand — is reproduced exactly: every output equals the hand calculation to the output quantum (10⁻¹⁰) |
| Property | No change, no effect | With every change at zero, every output attributed to the changes is zero |
| Property | The accounting bridge closes | The model's own bridge (e.g. −gross fuel cost change − hedging effect + fare recovery = operating profit change) holds exactly |
| Property | Months add up to the horizon | The monthly values of each flow add up to its horizon total |
| Property | Contributions add up | With two changes at once, each attributed output equals the sum of its Shapley contributions (models with two or more changes) |
| Property | Linear where the equations are linear | Doubling a cause doubles its effect (e.g. crude +10 → +20 doubles the fuel cost change) |
| Property | The effect moves one way | An effect rises (or falls) at every step as its cause goes from −20 to +40 |
| Property | Units do not change the result | The same fuel volume and price stated in barrels, gallons or a mix give identical results (the airline model, which accepts several units) |
| Range | Documented limits | Every scenario input's and assumption's documented minimum and maximum is accepted, and a value one step beyond is refused. A limit that the model's own rule stops, with the worked example's other figures, is reported rather than failed — e.g. a repo-rate change of −25 points would take interest to zero or below |
| Reproducibility | Reproducible | The same inputs twice give identical inputs and result hashes |

Each model has the checks its definition supports:

| Model version | Checks | Reference |
|---|---|---|
| `airline_fuel_cost` 1.1.0 and 1.0.0 | 10 | [the model page's worked example](airline-fuel-cost.md) |
| `floating_rate_interest` 1.0.0 | 9 | [worked example](floating-rate-interest.md) |
| `fx_exposure` 1.0.0 | 8 | [worked example](fx-exposure.md) |
| `crude_linked_costs` 1.0.0 | 8 | [worked example](crude-linked-costs.md) |
| `gas_linked_costs` 1.0.0 | 8 | [worked example](gas-linked-costs.md) |

All six versions pass every check (register version 1.0.0).

## What is not verified

Every register lists, per model:

- **Parameters** — elasticities, delays, pass-through and hedge terms are assumptions with
  stated defaults; none has been estimated from data.
- **Back-testing** — no result has been compared with what happened: RUMIN stores no observed
  company or market outcomes to test against.
- **The graph** (models that propagate along it) — the relationship is recorded in the sample
  network as a model assumption on illustrative data, not an empirical finding.
- **Sample data** — the companies are fictional and the checks use hypothetical round figures.

Estimation and back-testing were not attempted in Phase 9: no observation is stored in this
environment (the World Bank retrieval is blocked by the network) and the sample companies are
fictional, so there is nothing honest to estimate from or test against.

## How the checks are built

- **A check's graph states the model's relationships as present.** The checks test arithmetic
  and stated properties; whether a real knowledge graph holds a relationship is checked when a
  run is prepared (see [graph integration](graph-integration.md)).
- **Failures are reported, not raised.** A check that finds a wrong value, a bridge that does
  not close or an effect without a cause fails with its expected and actual values; an
  unexpected error fails the check that met it. Tests break a model on purpose — a wrong total,
  an effect without a cause, a bridge that does not close — and assert the right checks fail.
- **Timing.** The register takes 45–110 ms per model version; it is recomputed on every
  request, never stored.

## Where to see it

| Where | What |
|---|---|
| Simulation page | The model's full register: each check, its kind and detail; what is not verified; the version, definition hash, engine version and duration |
| Scenario Lab, Plan tab | For each included model: *N of N checks passed*, *Not verified: parameters are assumptions; no back-testing*, and the checks a click away |
| API | `GET /api/v1/simulation-models/{model_id}/verification?version=` (the model's default version when omitted) |
| Command line | `make verify-models` (`python -m app.simulation.verification`): every registered version; exits 1 on a failure |

## Where it lives

`backend/app/simulation/verification.py` (the checks, per-model reference values and the
register), `backend/app/services/simulation.py` (`model_verification`),
`backend/app/api/v1/simulations.py`, `frontend/src/features/simulation/VerificationPanel.tsx`;
tests in `backend/tests/test_simulation_verification.py` and
`frontend/tests/integration/analyses.integration.test.ts`.

Adding a model version: add its reference values and the checks it supports to `CHECKS` in
`verification.py`; `test_every_registered_model_has_checks` fails until you do (see
[the registry](registry.md#adding-a-model)).
