# Limitations

What the simulation engine and its first model cannot do, stated plainly. The model's own
assumptions (A1–A8) and limitations (L1–L7) are in [the model page](airline-fuel-cost.md);
this page covers the engine and the phase.

## What the results are

- **Not forecasts.** A run is the arithmetic consequence of stated inputs and assumptions
  with everything else held constant. Nothing in RUMIN says how likely a scenario is.
- **Not advice.** Results are not investment, lending, pricing or hedging advice. The
  "offsetting revenue change" (E18) is arithmetic, not a recommendation to raise fares.
- **Not validated against outcomes.** No parameter has been estimated from data and no
  result has been back-tested: β, the lags, the hedge terms and the pass-through are
  assumptions with neutral defaults. Estimation and back-testing are Phase 9.
- **Illustrative graph.** The relationship the model relies on (Brent crude influences jet
  fuel) is recorded in RUMIN's sample network as a model assumption on illustrative data;
  the sample airlines are fictional. The page and the API say so on every run.

## The engine

| Limitation | Consequence | Where it goes next |
|---|---|---|
| One model, one domain | Other questions (financing costs, other commodities) need their own models | New models in the same registry ([how](registry.md#adding-a-model)) |
| Deterministic only | Uncertainty is shown by one-at-a-time sensitivity, never by distributions | Monte Carlo, with the stored `random_seed` (Phase 9) |
| One-at-a-time sensitivity | No interactions between inputs; low and high are not a confidence interval | Two-way grids and probabilistic analysis |
| Monthly time step, step shocks | No intra-month timing, no seasonality, no phased shocks; since Phase 5 a change can start later and last a number of months (airline 1.1.0 and the Phase 5 models), at a constant size | Paths (gradual or decaying changes) in a later version |
| One graph rule (T1) | Only crude → jet fuel travels through the graph; the currency and the jet fuel margin act directly | More rules as models need them; parameters never read from edges |
| Coefficients are inputs | The engine never infers an elasticity or a lag from the graph or from data | Estimation from Phase 2 series, with its own provenance (Phase 9) |
| Stored-observation inputs | Only the exchange rate can come from stored data, and only as the latest annual average; nothing is stored in this environment because the World Bank retrieval was blocked | More series (MoSPI, prices) as data sources arrive |
| One model per run on the Simulation page | The Simulation page runs one model on its own inputs; composing models, versioned scenarios and comparisons are the Scenario Lab | Done in Phase 5: [the Scenario Lab](../scenario-lab/README.md) |

## Operations and security

- **No authentication.** Anyone who can reach the API can create runs and analyses. They
  are append-only, so a run cannot be altered or deleted through the API, but nothing
  limits how many are stored. Run RUMIN locally only (as for every phase so far).
- **No rate limiting.** Each request is bounded (inputs, horizon, depth, paths,
  sensitivity evaluations, time), but requests are not counted. Rate limits come with
  authentication (Phase 10).
- **Growth.** A 12-month run stores 99 steps (267 for 36 months) and about 16–17 kB of run
  JSON; there is no retention policy yet.
- **Freshness check cost.** Validating and running read the graph's freshness, which is
  cached for 30 seconds but costs a full read of the graph's sources when it expires
  ([graph performance](../graph/performance.md)).

## Technical debt

- `run_sensitivity` re-evaluates the whole model for every point; fine at ≤ 60 evaluations
  of a few milliseconds, but a larger model would want partial re-evaluation.
- The page's presentation helpers find the baseline-and-scenario pairs and the monthly
  chart's series by naming convention (`baseline_x` / `scenario_x`); a future model with
  other conventions should declare its presentation in its definition instead.
- The pathway layout is a simple layered layout (longest path to the result, placeholders,
  a few ordering sweeps); a large pathway would want a proper crossing-minimisation pass.
- The explanation endpoint returns every step at once (about 54 kB for 12 months and
  101 kB for 36); pagination by month would help larger models.
