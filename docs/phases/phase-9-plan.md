# Phase 9 plan — Advanced simulation and validation

Phase 9 builds on the Phase 4 engine and the Phase 5 Scenario Lab. It adds no second engine:
every new analysis re-evaluates the models of a stored execution through the same
`evaluate_result`, the same rules (`check`), the same graph channels (`channel_issues`) and
the same aggregation (AG0–AG7) that the one-at-a-time sensitivity analysis uses.

## 1. Re-audit (9.1)

Starting point: commit `7821751`, CI run #27 green on `ac25c0d` (the Phase 8 code; the next
commit only records CI in the report). The Phase 8 report is written and its gate passed.

**What the engine already does** (Phase 4, `app/simulation/`):

- Six registered model versions (five models): `airline_fuel_cost` 1.0.0 (deprecated for new
  runs, kept re-executable) and 1.1.0, `fx_exposure`, `floating_rate_interest`,
  `crude_linked_costs`, `gas_linked_costs`, all *preview*.
- Typed, hashed definitions: inputs with category, kind, unit, range, decimals, default,
  rationale and a default sensitivity variation; equations with terms, units, assumptions and
  limitations; outputs; transmission rules; assumptions, limitations and validation rules.
- **Multi-period already**: a monthly time step over a 1–36 month horizon; changes can start
  later and last a number of months (the timing inputs); every run returns monthly series.
- **Graph integration already**: one log-linear transmission rule (T1, Brent crude → jet
  fuel), its coefficient and lag are model inputs, never read from the graph; a shock needing
  a relationship the graph does not state is refused; the run stores the graph snapshot.
- Shapley attribution of every attributable output, an accounting bridge that must close,
  inputs and result hashes, re-execution (`verify`) of stored runs.

**What the Lab already does** (Phase 5, `app/scenario_lab/`): composes the applicable models
over shared figures (revenue, operating costs, the exchange rate) into five lines and two
metrics; stress cases (other magnitudes of the same changes); one-at-a-time sensitivity
across the scenario (≤ 8 quantities, ≤ 7 points, ≤ 60 evaluations, stored); comparisons of
2–6 executions; re-execution of an execution from its stored runs.

**Measured**: one full re-evaluation of the reference execution (three models, 12 months,
aggregation included) takes **1.1 ms** on this machine, so a Monte Carlo analysis of a few
thousand draws fits in a bounded request.

**Gaps found**

| Gap | Where it shows |
|---|---|
| Deterministic only; "Monte Carlo, with the stored `random_seed`" and "two-way grids" are the documented next steps | `docs/simulation/limitations.md` |
| One-at-a-time only: no interaction between two quantities | Lab and Phase 4 sensitivity |
| The Lab's Sensitivity tab always runs the default quantities on the default line; the API accepts chosen quantities, points and a metric, but the interface offers none of it, and nothing lists what can be varied | `AnalysisViews.tsx`, the API |
| Validation status is not visible in the product: every model is "preview", the hand calculations live in tests and in the model pages only | Simulation page, Lab plan |
| "Not validated against outcomes … estimation and back-testing are Phase 9" | limitations |

**Skills inspected again** (the installed list, not memory): `dataviz` (bundled) — its form
heuristic, colour jobs, mark specs, interaction rules, components and anti-patterns were
re-read for the histogram, the convergence chart and the grid; `kapture-browser-automation`
— needs the Kapture Chrome extension, which is not connected in this environment, so the
browser review uses Playwright with the pre-installed Chromium as in Phases 5–8; `docx`,
`pptx`, `xlsx`, `pdf`, `docs`, `morning`, `import-memory`, `skill-creator`,
`session-start-hook` and `claude-api` — inspected, not relevant to this interface. No
installed skill covers frontend design or accessibility in general; the accessibility work
follows WCAG 2.2 and the project's own conventions, checked with `axe-core`.

## 2. Capabilities chosen (9.2)

1. **Stochastic analysis (Monte Carlo)** on a stored execution, with explicit, bounded
   distributions chosen by the user, a recorded seed, honest summaries and diagnostics.
2. **Joint sensitivity (two quantities together)**: a grid over two quantities with the
   interaction term, which one-at-a-time analysis cannot show.
3. **A model verification register**: executable checks for every registered model version —
   hand-calculated reference cases, stated properties, range limits, reproducibility — run
   live through the engine and shown in the product, with what is *not* verified.
4. **Sensitivity controls** in the Lab (quantities, points, the line or metric) and a listing
   of what an execution can vary; a plain statement of the four kinds of analysis.

**Not chosen, and why**

- **Model chaining.** No model's output is a documented input of another. The Lab already
  combines models through an accounting aggregation with explicit line contracts; feeding,
  say, the fuel-cost change into another model's operating costs would count it twice. The
  brief forbids chaining without a documented contract, so none is added.
- **Estimation and back-testing.** No observation is stored in this environment (the World
  Bank retrieval is blocked by the network, 403) and the sample companies are fictional:
  there is nothing honest to estimate from or test against. Stated, not simulated.
- **More temporal behaviour.** The engine is already monthly with timed changes; gradual or
  decaying paths remain a documented limitation.
- **Correlated draws, Latin hypercube sampling, variance-based (Sobol) indices, Monte Carlo on
  single Simulation-page runs, reverse stress testing.** Each is sound but would widen the
  phase; they are recorded as next steps. `simulation_runs.random_seed` stays unused: an
  analysis stores its own seed.

## 3. Mathematics (9.3, 9.4)

Notation: *E* is a completed execution; *m* is a line's change over the horizon or a metric's
scenario value; *f(·)* is *m* after re-evaluating every model that uses the varied quantities,
everything else at *E*'s values.

### Monte Carlo

- **Quantities**: 1–8 of the execution's variable quantities (a change, a shared figure, a
  model's company, market or assumption input), each with one distribution:
  - uniform *U(a, b)*, *a < b*;
  - triangular *T(a, c, b)*, *a ≤ c ≤ b*, *a < b*;
  - discrete: 2–12 values with positive weights (default equal) — the only kind allowed for
    whole-month inputs.
- **Support inside the range**: every endpoint (every discrete value) must pass the input's own
  range rule and precision, so no draw is ever clipped. Draws are rounded half to even to the
  input's decimals (e.g. 0.01 for a percentage).
- **Independence**: quantities are drawn independently. Correlation between them (crude and
  the currency, say) is not modelled — stated on every analysis.
- **Random numbers**: `random.Random(seed).random()` (Mersenne Twister, 53-bit), whose sequence
  for a given seed Python guarantees across versions; inverse transform in exact decimal
  arithmetic; consumed draw by draw, quantity by quantity, in request order. The seed is
  recorded (chosen by the server when not given).
  - Triangular: with *F_c = (c − a)/(b − a)*, *x = a + √(u(b − a)(c − a))* if *u < F_c*,
    otherwise *x = b − √((1 − u)(b − a)(b − c))*.
  - Discrete: the first value whose cumulative weight exceeds *u · Σw*.
- **Rejected draws**: a draw that breaks a model's rule (e.g. the fuel bill above operating
  costs) or needs a graph relationship the stored snapshot does not state is rejected, counted
  and its reason recorded. Summaries describe the accepted draws; a warning says the
  distribution was cut by the models' rules. Fewer than 100 accepted draws: no summary.
- **Summaries** of the *n* accepted values:
  - mean, sample standard deviation (*n − 1*), Monte Carlo standard error *s/√n*;
  - percentiles P5, P10, P25, P50, P75, P90, P95 by linear interpolation between order
    statistics (Hyndman–Fan type 7, as Excel's `PERCENTILE.INC`);
  - for P5, P50 and P95 a distribution-free interval between two order statistics, with its
    exact binomial coverage (about 95 %) — so a percentile is never shown with more precision
    than the draws support;
  - the share of draws below zero and, when a threshold is given (an interest-coverage
    covenant, say), the share at or below it — always "share of draws under the chosen
    distributions", never a probability of the future;
  - a 20-bin histogram; the minimum and maximum;
  - every line and metric: mean, P5, P50, P95;
  - Spearman rank correlation of each quantity with *m* (average ranks for ties): monotonic
    association within the sample, not a share of variance and not causation.
- **Diagnostics**: the running mean with ±2 MCSE at 20 checkpoints; the two halves' means and
  their difference in standard errors (flagged above 3); the relative MCSE; rejected draws.

### Joint sensitivity

- Two different quantities *A* and *B*, each with points (the default variation, or up to six
  values) plus its execution value *a₀*, *b₀*: at most 7 × 7 cells.
- Each cell: *f(a, b)*, its change from the execution *f(a, b) − f(a₀, b₀)*, and the
  **interaction** *I(a, b) = f(a, b) − f(a, b₀) − f(a₀, b) + f(a₀, b₀)*: zero when the two
  effects simply add, non-zero when one changes the other's effect (a weaker rupee makes a
  crude rise costlier).
- A cell outside a range or breaking a rule is skipped with its reason; interactions that
  need it are not computed.

### Verification register

For every registered model version, checks run through the real engine (pure; no database):

| Kind | What it establishes |
|---|---|
| Reference case | The engine reproduces a hand calculation (the worked examples of the model pages; HYPOTHETICAL round figures) exactly, to the output quantum |
| Property | A stated property holds: no change → no effect; the same volume in kilolitres, gallons or barrels gives the same bill; linearity where the equations are linear; the direction of an effect; monthly values add up to the horizon totals; contributions add up to the total |
| Range limit | Each assumption's documented minimum and maximum run without a numerical error; a value beyond is refused |
| Reproducibility | The same inputs twice give the same inputs and result hashes |

Plus, per model, what is **not verified**: parameters are not estimated from data; results are
not back-tested; graph relationships are illustrative model assumptions; sample companies are
fictional. A model is never called "validated" because its checks pass.

## 4. Graph (9.5)

The new analyses use the graph snapshot stored with each run of the execution. They add no
relationship, read no coefficient from the graph, and apply the same channel rule: a varied
change that needs a relationship the snapshot does not state is skipped or rejected with the
reason. Each analysis records every run's graph build and fingerprint.

## 5. Reproducibility and audit (9.6)

A new append-only table, `scenario_analyses` (migration 0008): kind, execution, metric, the
normalised request, a `config` (the execution's result hash; for each run its model, version,
definition hash, inputs hash, run id and graph build; the Lab, engine and sampler versions;
the random-number generator, seed and draws), the results, evaluations, rejected draws,
duration, `inputs_hash` (over config and request) and `result_hash`. No update or delete route.
`POST …/analyses/{id}/verify` recomputes from the stored runs and configuration and compares
the hashes, storing nothing. Deterministic analyses and Monte Carlo with its seed reproduce
exactly.

## 6. Interface (9.7)

- **Sensitivity** tab: *One at a time* (now with the quantities, points and line or metric
  chosen) and *Two together* (the grid and its interactions).
- **Uncertainty** tab (new): the distribution editor (each quantity's range and base shown;
  the default variation offered as a starting point, marked as the user's assumption), draws,
  seed, optional threshold; the histogram with P5, P50, P95 and the execution's value, the
  percentile table with intervals, the shares, diagnostics, rank correlations, every line;
  the analysis history with settings; *Reproduce*.
- **Four kinds of analysis** — sensitivity, scenario, stress, stochastic — stated at the top of
  the Stress, Sensitivity and Uncertainty tabs, each marking which one it is.
- **Verification** in the Plan tab (per included model) and on the Simulation page.
- `dataviz` rules: one accent (sky blue) for the one series, grey for context, amber only for
  flags; thin marks; every chart with its table twin; values in text tokens; no dual axes.

## 7. API, persistence and safety (9.8)

- `GET /scenario-executions/{id}/analysis-targets` — what an execution can vary, with ranges,
  units, base values and default variations; the lines and metrics.
- `POST /scenario-executions/{id}/analyses` (kind `monte_carlo` or `joint_sensitivity`),
  `GET …/analyses`, `GET …/analyses/{analysis_id}`, `POST …/analyses/{analysis_id}/verify`.
- `GET /simulation-models/{model_id}/verification?version=`.
- Limits: 100–2,000 draws; ≤ 8 quantities; ≤ 12 discrete values; ≤ 7 points per axis;
  deadlines (Monte Carlo 20 s, grid 10 s) after which nothing is stored; at most two analyses
  computing at once (429 otherwise). Bodies are strict (unknown fields refused); numbers are
  decimal strings; distributions are data from a closed set — nothing is evaluated.

## 8. Testing (9.9)

- Sampler: moments within 4 standard errors, Kolmogorov–Smirnov against the exact CDF (fixed
  seeds, so deterministic), discrete frequencies (χ²), seed reproducibility, edge cases.
- Statistics: type-7 percentiles, intervals and coverage, ranks with ties, known answers.
- Monte Carlo known answer: floating-rate interest is linear in the repo-rate change, so its
  mean and standard deviation under a uniform change are known exactly; the estimate must lie
  within 4 MCSE.
- Joint grid: additive quantities give zero interaction; the crude × currency interaction
  matches a hand calculation.
- Register: every model passes; a deliberately broken model fails the right checks.
- Persistence, append-only, verification (and a tampered result detected), API contracts,
  limits, the 429 guard, migration 0008 up and down; frontend unit, page and live-API
  integration tests; Chromium review, `axe-core`; Phases 1–8 suites unchanged.

## 9. Order of work

1. Statistics core and its tests.
2. The shared evaluator (from the one-at-a-time analysis), joint grids and Monte Carlo.
3. Migration 0008, storage, API, OpenAPI, generated types.
4. The verification register, its endpoint and command.
5. The Lab and Simulation interface.
6. Tests, browser review, measurements.
7. Documentation, ADRs, report, commit, push, CI.
