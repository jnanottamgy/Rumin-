# Advanced analysis

Phase 9 adds three analyses to a **stored, completed execution** of the Scenario Lab: a
chosen one-at-a-time sensitivity analysis, a **two-quantity grid** with its interaction term,
and a **Monte Carlo** analysis under distributions the user states. None is a second engine:
each re-evaluates the execution's stored model runs through the Phase 4 engine
(`evaluate_result`), the same model rules, the same graph channel check and the same
aggregation (AG0–AG7) as the execution itself. The plan is in
[phase-9-plan.md](../phases/phase-9-plan.md); the model checks that sit beside these analyses
are in [the verification register](../simulation/verification.md).

> Every figure in these analyses is conditional: *if* the quantities took these values (or
> varied as you stated), the models give this. The distributions are the user's assumptions,
> not estimates from data. Nothing here is a forecast or the probability of an outcome.

## The four kinds of analysis

The Lab states which kind each tab runs; the words are used strictly.

| Kind | Question | Where | What it varies |
|---|---|---|---|
| **Scenario** | What do these changes do? | Execute; Pathway, Plan, Months, Explain | Nothing: one deterministic path |
| **Stress** | What if the changes were larger or smaller? | Stress tab | The magnitude of every change at once (up to five cases) |
| **Sensitivity** | How much does the result depend on each quantity, alone or with one other? | Sensitivity tab: *One at a time*, *Two together* | One quantity (or two) over chosen points, everything else as executed |
| **Stochastic** | How spread out is the result if the quantities vary as I state? | Uncertainty tab | Up to eight quantities drawn from stated distributions |

## What an execution can vary

`GET /api/v1/scenario-executions/{id}/analysis-targets` lists every quantity an analysis may
vary, read from the execution's own specification and stored runs:

- **changes** — each change of the scenario (`change:var_brent_crude`), in its own unit;
- **shared figures** — annual revenue, annual operating costs, the exchange rate
  (`shared:annual_revenue`), which every model that uses them receives;
- **model inputs** — each included model's market, company and assumption inputs
  (`model:airline_fuel_cost:hedge_ratio`).

Each comes with its label, kind, unit, the models that use it, the execution's value, its
valid range (inclusive or exclusive ends), decimals, whether it is a whole number of months,
and its default variation (±10 % of a level, ±5 points of a percentage, and so on — the
model's own declaration). The listing also gives the lines and metrics an analysis can report
— revenue, operating costs, operating profit, interest expense and profit before tax as a
**change over the horizon**, operating margin and interest coverage as **the scenario's value**
— and every limit below.

## One quantity at a time

Unchanged in method since Phase 5 except for one correction; the interface now chooses the
quantities (up to eight), their values (up to seven each, or the model's default variation)
and the line or metric. The tornado ranks quantities by the spread they cause.

**Correction (method 1.1.0).** Until Phase 9 the Lab's aggregation step combined the lines
from the *executed* revenue, operating costs and interest expense even when the analysis
varied them, so the models moved but operating margin and interest coverage did not. The
shared evaluator now passes the varied figures to the aggregation; a regression test pins
operating margin at revenue 270,000,000 to 13.675 / 276.925 and interest coverage to
13.675 / 12.375. Stored analyses record `method_version`; those made before the correction
(`1.0.0`, set by migration 0008) carry a caveat when they ranked a margin or coverage by one
of those figures. Nothing stored was rewritten.

## Two quantities together

`POST …/analyses` with `kind: "joint_sensitivity"`: two different quantities *A* and *B*,
each with its default variation or up to six values, plus its executed value — at most
7 × 7 cells. For every cell the grid gives the line or metric *f(a, b)*, its change from the
execution *f(a, b) − f(a₀, b₀)*, and the **interaction**

  *I(a, b) = f(a, b) − f(a, b₀) − f(a₀, b) + f(a₀, b₀)*,

which is zero when the two effects simply add and non-zero when one changes the other's
effect. Along the executed row and column it is zero by construction.

*Worked example* (hypothetical figures of the reference execution): fuel costs 5,000,000 a
month; crude acts from month 2 and 40 % is hedged for six months, so 9 month-equivalents
carry both a crude and a dollar change. Crude ±10 points and the dollar ±5 points interact by
5,000,000 × 9 × 0.10 × 0.05 = 225,000 on costs; half of the cost change reaches fares two
months later (7 month-equivalents), 87,500 back in revenue: **∓137,500 on operating profit**
at the grid's corners. The test `test_the_crude_and_rupee_interaction_matches_a_hand_calculation`
asserts exactly these cells. Crude and the repo rate act on different lines, so their grid is
additive: every interaction is zero, and the summary says so (`additive`, within a tolerance
of 0.000001).

A cell outside an input's range or breaking a model's rule is **skipped with its reason**;
interactions that need it are not computed. The summary names the largest interaction and
the largest change. There is no probability in a grid.

## Monte Carlo

`POST …/analyses` with `kind: "monte_carlo"`.

### What is drawn

- **1–8 quantities**, each with one distribution: **uniform** *U(a, b)* with *a < b*;
  **triangular** *T(a, c, b)* with *a ≤ c ≤ b* and *a < b*; **discrete**, 2–12 values with
  positive weights (equal when omitted). A whole-month input (a lag, a hedge's cover) takes
  only a discrete distribution.
- **The whole support must be valid.** Every endpoint and every discrete value must pass the
  input's own range rule and decimal limit, so no draw is ever clipped. Draws are rounded
  half to even to the input's decimals.
- **Independent draws.** Quantities are drawn independently of each other; a relationship
  between them (a weaker rupee when crude rises) is not modelled, and every analysis with
  more than one quantity says so.
- **Random numbers.** `random.Random(seed).random()` — the Mersenne Twister, 53 bits a draw,
  whose sequence for a given seed Python guarantees across versions — consumed draw by draw,
  quantity by quantity, in request order; every draw consumes one number per quantity even
  when it is rejected. The inverse transform runs in exact decimal arithmetic: for the
  triangular, with *F = (c − a)/(b − a)*, *x = a + √(u(b − a)(c − a))* when *u < F*, else
  *x = b − √((1 − u)(b − a)(b − c))*; for the discrete, the first value whose cumulative
  weight exceeds *u · Σw*. The **seed** is recorded; when none is given the server chooses
  one (`secrets.randbits(53)`). Seeds are at most 2⁵³ − 1 so that a browser reads them
  exactly.
- **Draws**: 100–2,000 (default 500).

### Rejected draws

A draw that breaks a model's rule (a fuel bill above operating costs, say) or needs a graph
relationship the execution's stored snapshot does not state is **rejected, counted by rule
and never adjusted**; the result lists each rule with its count and one example. The
summaries then describe the accepted draws — the stated distributions cut where the models
do not apply — and a note says so. **Fewer than 100 accepted draws: no summary** — the request
is refused with the reasons and nothing is stored.

### What is reported

For the chosen line or metric, over the *n* accepted draws:

| Figure | Definition |
|---|---|
| Mean, standard deviation | Sample mean; sample standard deviation (*n − 1*) |
| Standard error (MCSE) | *s/√n*, and relative to the mean — how precisely the mean is estimated, not how uncertain the result is |
| Percentiles P5, P10, P25, P50, P75, P90, P95 | Linear interpolation between order statistics (Hyndman–Fan type 7, as Excel's `PERCENTILE.INC`) |
| Intervals for P5, P50, P95 | Between two order statistics, with their **exact binomial coverage** (about 95 %) — so a percentile is never shown more precisely than the draws support |
| Shares | Of draws below zero (for a change) and, when a threshold is given (a covenant level, say), at or below it — shares of draws under the stated distributions, never probabilities |
| Minimum, maximum; histogram | 20 equal-width bins; the counts add up to *n* |
| Rank correlations | Spearman's (average ranks for ties) of each quantity with the result: monotonic association within the sample — not causation, not a share of the variance |
| Every line and metric | Mean, P5, P50 and P95 beside the executed value |

**Diagnostics**: the running mean with ±2 MCSE at 20 checkpoints; the two halves' means and
their difference in standard errors, flagged (with a note) above 3; the relative MCSE; the
rejected draws.

*Known answer*: interest on 100,000,000 of repo-linked debt repriced after 3 of 12 months
costs 750,000 per point, so a repo-rate change uniform on [0, 1] gives a mean of 375,000 and
a standard deviation of 750,000/√12 = 216,506.35. A test checks 2,000 draws land within four
standard errors of the mean and 5 % of the standard deviation, with a rank correlation of
exactly 1.

## Reproducibility and storage

Every analysis is stored, append-only, in `scenario_analyses` (migration 0008): the kind, the
metric, the normalised request, a **configuration** — the execution's result hash; for each
run its model, version, definition hash, run id, inputs hash, graph build and fingerprint; the
analysis, Lab and engine versions; the generator, sampler version, seed and draws — the
results, the evaluations, the duration, an **inputs hash** (over the configuration and the
request) and a **result hash** (over the results, without timings). There is no update or
delete route.

`POST …/analyses/{analysis_id}/verify` recomputes the analysis from the stored runs and the
stored request and compares both hashes; it stores nothing. A grid, and a Monte Carlo analysis
with its seed, reproduce exactly. A stored request that was changed is reported as not
reproduced. An execution that has not completed, or whose model version is no longer
registered with the same definition, cannot be analysed or re-run (409).

## The graph

The analyses use the graph snapshot stored with each run. They add no relationship and read
no coefficient from the graph; a varied change that needs a relationship the snapshot does
not state is skipped (a grid cell) or rejected (a draw) with the reason. The configuration
records every run's graph build and fingerprint.

## Limits and safety

| Limit | Value |
|---|---|
| Monte Carlo | 100–2,000 draws; ≤ 8 quantities; ≤ 12 discrete values; ≥ 100 accepted draws; 20 s |
| Grid | ≤ 7 points per axis (the executed value included); 10 s |
| One at a time | ≤ 8 quantities; ≤ 7 points each; ≤ 60 evaluations |
| Concurrency | At most two analyses compute at once in an API process; a third is refused with 429 (`rate_limited`) and nothing is stored |

An analysis that passes its deadline stops, stores nothing and says how far it got. Bodies
are strict (unknown fields are refused); numbers travel as decimal strings; distributions
come from a closed set and are data — nothing is evaluated.

## API

| Method and path | What it does |
|---|---|
| `GET /api/v1/scenario-executions/{id}/analysis-targets` | What the execution can vary, its lines and metrics, and the limits |
| `POST /api/v1/scenario-executions/{id}/analyses` | Runs and stores a `monte_carlo` or `joint_sensitivity` analysis (201, `Location`) |
| `GET /api/v1/scenario-executions/{id}/analyses` | The execution's analyses, newest first (a summary each) |
| `GET /api/v1/scenario-executions/{id}/analyses/{analysis_id}` | One analysis with its configuration and results |
| `POST /api/v1/scenario-executions/{id}/analyses/{analysis_id}/verify` | Recomputes and compares the hashes; stores nothing |
| `POST /api/v1/scenario-executions/{id}/sensitivity` | One-at-a-time sensitivity (Phase 5; method 1.1.0 since Phase 9) |

## The interface

- **Sensitivity** tab: *One at a time* — choose the quantities (each shows its executed value
  and default variation), their values and the line or metric; the tornado and its table.
  *Two together* — two quantities and their values; the grid by change or by interaction,
  the executed cell marked, skipped cells with their reason.
- **Uncertainty** tab: the line or metric, draws, seed and an optional threshold; each
  quantity's distribution (a starting point from the model's default variation is offered
  and labelled as the user's assumption); the result — mean, P5, P50, P95 with the interval
  the draws support, the shares, the histogram (P5, P50, P95 and the executed value as
  rules, the threshold dashed), the percentile table, the quantities drawn with their rank
  correlations, every line and metric, *How reliable is this estimate?* (the convergence
  chart and the rejected draws) and *Configuration and reproducibility* with *Run again and
  compare*; the stored analyses of the execution.
- **Plan** tab: each included model's verification summary, with the checks a click away.

Charts follow the [design system](../design-system.md#analysis-charts-phase-9): one sky-blue
series, grey for context, thin marks, a table twin, and operable from the keyboard (arrow
keys move through bins or checkpoints; the value is announced). The browser computes no
figure: every number shown is the backend's, formatted.

## Performance

Measured through the API on this machine (SQLite; the work is in memory, so PostgreSQL does
not change it), the reference scenario's three models:

| Analysis | 12 months | 36 months |
|---|---|---|
| Monte Carlo, 500 draws × 3 quantities | 0.59 s | 1.58 s |
| Monte Carlo, 2,000 draws × 8 quantities (the maximum) | 2.87 s | 5.75 s |
| *Run again and compare* for the same | 3.08 s | 5.82 s |
| Grid, 7 × 7 | 64 ms | 104 ms |
| One at a time, 8 quantities, default points (17 evaluations) | 14 ms | 22 ms |

Results are 9.6–12.6 kB of JSON for a Monte Carlo analysis and about 6.9 kB for a 7 × 7 grid.
The worst case sits well inside the 20-second deadline; it holds one of the two analysis slots
for its duration. In Chromium, five quantities took 1.6 s (1,000 draws) and 3.2 s (2,000) from
the click to the drawn result. Details in [performance](performance.md#advanced-analyses-phase-9).

## Where it lives

| Layer | Location |
|---|---|
| Evaluation | `backend/app/scenario_lab/evaluation.py` (the shared evaluator), `sensitivity.py`, `joint.py`, `montecarlo.py` |
| Statistics | `backend/app/scenario_lab/sampling.py` (distributions, generator), `summaries.py` (percentiles, intervals, ranks, histogram, diagnostics) |
| Storage and API | `backend/app/models/scenario.py` (`ScenarioAnalysis`), migration `0008_advanced_analyses`, `backend/app/services/scenario_analyses.py`, `backend/app/api/v1/scenario_lab.py`, `backend/app/schemas/analysis.py` |
| Interface | `frontend/src/features/scenarioLab/`: `SensitivityViews.tsx`, `UncertaintyView.tsx`, `DistributionChart.tsx`, `ConvergenceChart.tsx`, `AnalysisTypes.tsx`, `analysisForm.ts` |
| Tests | `backend/tests/test_scenario_lab_statistics.py`, `test_scenario_lab_analyses.py`, `test_scenario_analyses_api.py`; `frontend/tests/scenarioLab/analysisForm.test.ts`, `tests/pages/scenarioLab.test.tsx`, `tests/integration/analyses.integration.test.ts` |

What these analyses do not do is in [limitations](limitations.md#analyses).
