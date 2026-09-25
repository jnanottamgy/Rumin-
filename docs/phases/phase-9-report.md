# Phase 9 report — Advanced simulation and validation

Phase 9 adds three analyses to the Scenario Lab's stored executions — sensitivity to chosen
quantities **one at a time** or **two together** (with the interaction between them), and
**Monte Carlo** under distributions the user states — and a **verification register** that
shows, for every model version, what has been checked and what has not. Every analysis
re-evaluates the execution's stored model runs through the Phase 4 engine; there is no second
engine. The plan is in [phase-9-plan.md](phase-9-plan.md); the guides are
[advanced analysis](../scenario-lab/advanced-analysis.md) and
[the verification register](../simulation/verification.md).

## At a glance

| | |
|---|---|
| **Capabilities** | Monte Carlo on a stored execution (uniform, triangular or discrete distributions for up to 8 quantities, 100–2,000 draws, a recorded seed); a two-quantity grid with the interaction term (up to 7 × 7); one-at-a-time sensitivity with chosen quantities, values and line or metric; a verification register for all six model versions |
| **What a result says** | Conditional figures only: *if* the quantities varied as stated. Percentiles carry an interval with exact coverage; shares are shares of draws, never probabilities; nothing is called validated |
| **Reproducibility** | Every grid and Monte Carlo analysis is stored append-only with its configuration (runs, versions, graph builds, generator, seed) and hashes; *Run again and compare* reproduces it exactly |
| **A defect corrected** | The Lab's one-at-a-time analysis (Phase 5) held margins and coverage at their executed values when revenue, costs or interest were varied; fixed as method 1.1.0, older stored analyses flagged, none rewritten |
| **Performance** | Worst case (2,000 draws × 8 quantities over 36 months) 5.7 s of a 20 s deadline; a 7 × 7 grid 64–104 ms; a register 45–111 ms |
| **Accessibility** | `axe-core` clean on the Sensitivity, Uncertainty and Plan views and the Simulation page in both themes after fixing three causes of violation; keyboard sliders and table twins for the charts; no sideways scrolling at 390 px |
| **Tests** | Backend 1,149 passed + 1 skipped (+91), frontend 404 (+24), integration 66 (+6) — [quality gates](#quality-gates) |
| **Not done, and why** | Estimation, calibration and back-testing (no observations are stored here; the companies are fictional); model chaining (no documented input contract between models) |

## 1. Re-audit (9.1)

Recorded in the [plan](phase-9-plan.md#1-re-audit-91). In short: the engine was already
monthly over 1–36 months with timed changes, integrated with the graph through one
confirmed transmission rule, with Shapley attribution, hashes and re-execution; the Lab
already composed five models, ran stress cases and a one-at-a-time analysis that the page
could not configure. The gaps: deterministic only, no interactions, no way to choose what to
vary, and a validation status that lived only in tests and model pages. One full
re-evaluation of the reference execution took 1.1 ms, which made a bounded, synchronous Monte
Carlo feasible. Phase 8's gate had passed and its suites were green (backend 1,058 + 1
skipped, frontend 380, integration 60).

## 2. What was built

- **Shared evaluator** (`scenario_lab/evaluation.py`): re-evaluates a stored execution with
  some quantities changed — the engine, each model's rules, the graph channel check against
  the run's stored snapshot, the Lab's aggregation — used by all three analyses.
- **Statistics** (`sampling.py`, `summaries.py`): bounded distributions with exact moments,
  CDFs and quantiles; the seeded stream; percentiles, order-statistic intervals with exact
  binomial coverage (fractions), ranks and Spearman, histogram, running mean, halves, shares.
- **Grids** (`joint.py`) and **Monte Carlo** (`montecarlo.py`), with their limits,
  rejections, notes and diagnostics.
- **Storage and API**: migration `0008` (`scenario_analyses`,
  `scenario_sensitivity_analyses.method_version`); `GET …/analysis-targets`, `POST/GET
  …/analyses`, `GET …/analyses/{id}`, `POST …/analyses/{id}/verify`; the 429 guard; OpenAPI
  and generated types.
- **The verification register** (`simulation/verification.py`): ten kinds of check, reference
  values for every model, `GET /simulation-models/{id}/verification`, `make verify-models`.
- **Interface**: the Sensitivity tab's *One at a time* (choose quantities, values, the line or
  metric) and *Two together* (the grid by change or interaction); a new **Uncertainty** tab
  (the distribution editor, the result with histogram, percentile table, quantities and rank
  correlations, every line, *How reliable is this estimate?*, configuration and *Run again
  and compare*, the stored analyses); the four kinds of analysis stated on the Stress,
  Sensitivity and Uncertainty tabs; each included model's verification in the Plan tab and
  the full register on the Simulation page.
- About 3,300 lines of backend code and 3,000 of frontend code, with ten commits on the
  branch (all pushed; the last code commit is `836bdf7`).

## 3. Capabilities chosen, and why (9.2)

| Capability | Why it was chosen |
|---|---|
| **Stochastic analysis (Monte Carlo)** | The brief's central request, and feasible honestly: the models have explicit inputs with ranges, the engine is exact and fast, and every distribution can be made the user's stated assumption rather than a pretended observation |
| **Two quantities together** | One-at-a-time analysis cannot show interactions (a weaker rupee makes a crude rise costlier); a grid with the interaction term is exact, checkable by hand and cheap |
| **A verification register** | The brief asks for validation; without observations, the honest version is to show what has been checked (hand calculations, properties, limits, reproducibility) beside what has not |
| **Sensitivity controls** | The API accepted chosen quantities since Phase 5, but the page did not; multiple quantities, values and a line or metric are now chosen in the interface |

**Not chosen** (details in the plan): **model chaining** — no model's output is a documented
input of another, and chaining the fuel-cost change into another model's costs would count it
twice; **estimation and back-testing** — no observation is stored (the World Bank retrieval is
blocked by the network) and the companies are fictional, so any estimate would be fabricated;
**further temporal behaviour** — the engine was already multi-period; **correlated draws, Latin
hypercube sampling, Sobol indices, reverse stress tests** — sound, but each would widen the
phase; recorded as next steps.

## 4. Models and workflows affected

- **All five models, six versions** — through the Lab's analyses (every model that uses a
  varied quantity is re-evaluated) and the verification register (each version checked).
  No model definition changed; no definition hash changed.
- **Scenario Lab**: the Sensitivity tab (new controls and the grid), the new Uncertainty tab,
  the Plan tab (verification), the Stress tab (the four kinds of analysis stated).
- **One-at-a-time sensitivity** (Phase 5): method corrected (1.1.0); the page now configures it.
- **Simulation page**: the model's full register.
- **Unchanged**: the engine, executions, results, pathways, explanations, comparisons, the
  graph, Financial Intelligence, the Analyst and the 3D universe.

## 5. Mathematics, assumptions and validation approach (9.3, 9.4)

The full statement is in [advanced analysis](../scenario-lab/advanced-analysis.md). In short:

- **Distributions**: uniform *U(a, b)*, triangular *T(a, c, b)*, discrete (2–12 values,
  positive weights); the whole support must lie inside the input's valid range and decimals,
  so nothing is clipped; draws are rounded half to even to the input's decimals; whole-month
  inputs are discrete only. Quantities are **independent** — stated on every analysis.
- **Random numbers**: `random.Random(seed).random()` (Mersenne Twister, 53 bits, guaranteed
  across Python versions), inverse transform in 34-digit decimal arithmetic; seed recorded,
  at most 2⁵³ − 1.
- **Rejected draws**: counted by rule with an example, never adjusted; summaries describe the
  accepted draws and say the distribution was cut; fewer than 100 accepted: refused.
- **Summaries**: mean, sample SD, MCSE; type-7 percentiles; intervals for P5, P50, P95 between
  order statistics with exact binomial coverage; shares of draws; a 20-bin histogram;
  Spearman rank correlations; every line and metric. **Diagnostics**: running mean ± 2 MCSE,
  halves compared in standard errors (flagged above 3), relative MCSE.
- **Grid**: value, change and interaction *f(a, b) − f(a, b₀) − f(a₀, b) + f(a₀, b₀)* per
  cell; skipped cells with reasons; an additivity flag within 10⁻⁶.
- **The four kinds of analysis** (scenario, stress, sensitivity, stochastic) are defined in the
  guide and stated in the interface where each runs.

**Validation approach.** Known answers where they exist: the Monte Carlo mean and SD of a
linear line (repo-rate change uniform on [0, 1] → mean 375,000, SD 216,506.35: within 4 MCSE
and 5 %); the crude × rupee interaction (∓137,500, from a hand calculation to the rupee);
percentiles against Excel's `PERCENTILE.INC`; a percentile interval's coverage by exact
arithmetic and by repeated sampling. Statistical checks with fixed seeds (so they are
deterministic): moments within 4 standard errors, Kolmogorov–Smirnov against the exact CDF
(and a deliberately biased sampler failing it), χ² on discrete frequencies. Reproducibility by
hash. The **verification register** runs every model version against its worked example and
stated properties; tests break a model on purpose and see the right checks fail. What is
**not** verified is listed with every register: parameters are not estimated, nothing is
back-tested, graph relationships are illustrative assumptions, the companies are fictional.

## 6. Graph integration (9.5)

The analyses use each run's stored graph snapshot and the existing channel rule; they add no
relationship and read no coefficient from the graph. A varied change that needs a relationship
the snapshot does not state is skipped (a cell) or rejected (a draw) with the reason. Each
analysis records every run's graph build and fingerprint. The register checks models with a
graph that states their own transmission relationships, and lists the relationship's
illustrative status as not verified.

## 7. Reproducibility and audit (9.6)

Stored for every analysis: id and time, kind, metric, the normalised request (with the seed
actually used), the configuration (the execution's result hash; each run's model, version,
definition hash, run id, inputs hash, graph build and fingerprint; the analysis, Lab, engine
and sampler versions; the generator and draws), the results, evaluations, duration, an inputs
hash and a result hash. **Nothing can be updated or deleted** through the API. `verify`
recomputes from the stored runs and request and compares both hashes; every Monte Carlo
analysis tried in the review and the tests reproduced exactly, including the maximum at 36
months. Individual draws are not stored — the seed reproduces them — which keeps a result at
10–13 kB. What changed between two analyses is readable from their stored settings in the
list; there is no side-by-side comparison of two analyses yet.

## 8. Installed skills inspected and used

Inspected from the installed list at the start of the phase and again for this report:

| Skill | Inspected | Used | Contribution |
|---|---|---|---|
| `dataviz` (bundled) | Yes: the procedure, choosing a form, colour jobs, marks and anatomy, interaction, components, anti-patterns | **Yes** | The histogram's form (equal bins from a zero baseline, 2 px gaps, 4 px rounded data ends, rules for percentiles, the executed value in the baseline grey, the threshold as the only dashed mark), the convergence chart (one line with a wash, not two series), rank correlations as bars from a centre with values printed, the grid as a table rather than a heat map, one accent for one series, tooltips that never gate a value, keyboard sliders and table twins, text in text tokens. It led to removing a browser-computed share from the histogram (counts are the backend's). No new colour was introduced, so the palette validator was not re-run; the pair validated in Phase 4 is reused |
| `kapture-browser-automation` | Yes | No | It drives Chrome through the Kapture extension, which is not connected in this environment; the review used Playwright with the pre-installed Chromium instead |
| `docs`, `docx`, `pptx`, `xlsx`, `pdf`, `morning`, `import-memory`, `skill-creator` | Yes (descriptions and triggers) | No | Documents, files, briefs and skill authoring — not relevant to this interface |
| `claude-api` (bundled) | Yes | No | No model integration changed in Phase 9 |

No installed skill covers frontend design or accessibility in general. The accessibility work
followed WCAG 2.2 and the project's conventions, checked with `axe-core` (a scratch
dependency of the review, not of the project).

## 9. Tests run and results (9.9)

| Suite | Result | Phase 9 additions |
|---|---|---|
| Backend (pytest), SQLite and PostgreSQL 16 | **1,149 passed, 1 skipped** (the skipped test needs a model key) | `test_scenario_lab_statistics.py` (39), `test_scenario_lab_analyses.py` (21), `test_scenario_analyses_api.py` (16), `test_simulation_verification.py` (12), the sensitivity regression in `test_scenario_lab.py`, migration `0008` up and down, unique operation IDs |
| Frontend (Vitest, jsdom) | **404 passed** (35 files) | `scenarioLab/analysisForm` (9); five new Lab page tests (the grid, Monte Carlo with only stated distributions, browser-side checks, the server's refusal shown, verification in the plan) and the one-at-a-time test rewritten to choose quantities and values; the register on the Simulation page; exact decimal helpers; eight contract checks on captured fixtures |
| Integration (live API) | **66 passed** | `analyses.integration.test.ts` (6): targets, Monte Carlo stored/listed/reproduced, refusals on their fields, the grid, the corrected sensitivity, every executed model's register |
| `make smoke` | Passed | Fresh database → live API → the integration suite |
| Register | All six versions pass: airline 1.1.0 and 1.0.0 10/10, floating-rate interest 9/9, foreign-currency 8/8, crude-linked 8/8, gas-linked 8/8 | `make verify-models` |

Everything is described in [testing](../testing.md). No test uses real financial data: the
figures are the tests' hypothetical round numbers and the fictional sample network, labelled
as such.

## 10. Browser review, accessibility and performance

**Review.** A scripted Chromium walk-through of a production build: one-at-a-time sensitivity,
the grid by change and by interaction, a Monte Carlo analysis (five quantities, 1,000 draws, a
threshold), its diagnostics and configuration, *Run again and compare* (identical), the Plan's
verification and the Simulation page's register, in both themes at 1440 px with `axe-core` on
five views each; the histogram from the keyboard (Home, arrows; the bin announced; a 2 px
focus ring); the console watched; the views at 390 px checked for sideways scrolling. The
findings are in [§ 11](#11-defects-found-and-fixed-during-the-phase); after the fixes, no axe
violation, no overflow and no console message.

**Performance** (server duration; the work is in memory, so SQLite and PostgreSQL do not
differ):

| Analysis | 12 months | 36 months |
|---|---|---|
| Monte Carlo, 500 draws × 3 quantities | 593 ms | 1,578 ms |
| Monte Carlo, 2,000 draws × 8 quantities (the maximum) | 2,867 ms | 5,749 ms |
| Grid, 7 × 7 | 64 ms | 104 ms |
| One at a time, 8 quantities, default points | 14 ms | 22 ms |
| Verification register, one version | 45–111 ms | — |

In Chromium, five quantities took 1.6 s (1,000 draws) and 3.2 s (2,000) from the click to the
drawn result. Results are 9.6–12.6 kB (Monte Carlo) and about 6.9 kB (a 7 × 7 grid).

## 11. Defects found and fixed during the phase

| Found by | Defect | Fix |
|---|---|---|
| Building the shared evaluator | **The Lab's one-at-a-time analysis (Phase 5) held operating margin and interest coverage at their executed values** when it varied revenue, operating costs or interest expense: the models moved, the aggregation did not | The evaluator passes the varied figures to the aggregation (method 1.1.0); a regression test (margin 13.675 / 276.925 at revenue 270,000,000); migration `0008` marks older analyses `1.0.0` and the API adds a caveat where it applies. No stored result rewritten ([decision 85](../decisions.md#85-a-methods-defect-is-fixed-by-versioning-the-method-not-by-rewriting-results)) |
| Generating the TypeScript types | Three new route functions shared operation IDs with Financial Intelligence routes, which silently renamed generated types | Routes renamed; a test that operation IDs are unique |
| Interface work | Server-chosen seeds up to 2⁶³ could not be read exactly by a browser, so a shown or re-sent seed could differ | Seeds are at most 2⁵³ − 1, chosen with `secrets.randbits(53)`; larger ones refused (a test) |
| Self-review against `dataviz` | The histogram computed percentage shares in the browser | Counts from the backend ("12 of 1,000 draws") |
| The register | The limits check failed the floating-rate model at a repo-rate change of −25, which the model's own rule stops (interest would fall to zero or below) | A limit stopped by a stated rule is reported, not failed |
| Review of rejections | Rejection reasons carried amounts, so identical causes never grouped | Grouped by rule, with one example each |
| CI #29–#32 | A line too long after a rename (ruff E501); `sum()` in a test typed as `Decimal | int` (mypy on `app tests`) | Fixed; the full `make check` is now run before every push |
| Chromium review | **Contrast below 4.5:1 on not-applicable model rows**, from a Phase 5 `opacity: 0.72`, in every Lab view and both themes | A recessed background instead, text at full contrast |
| Chromium review | Muted notes on the dark theme's accent wash measured 3.9:1 (emphasised table rows, the selected stored analysis) | Secondary ink there |
| Chromium review | A heading-order skip: the builder's h3 followed the page's h1 | Hidden h2 headings for the three regions; the Uncertainty view's titles at h3 |
| Chromium review | **166 px of sideways scrolling at 390 px**: the quantity picker's longest option sized the whole form column | The picker is capped at the form's width; the configuration table wraps hashes |
| Chromium review | Each one-at-a-time checkbox's name included its whole note | Named by the quantity; the executed value and variation describe it (`aria-describedby`) |

## 12. Deviations from the plan

- **Seeds are capped at 2⁵³ − 1** (the plan said only "recorded").
- **A limit that a model's own rule stops is reported**, not failed, in the register.
- **The one-at-a-time correction** was not planned; it was found and fixed.
- **No side-by-side comparison of two analyses**: the stored list shows each one's settings.
- The planned *Reproduce* is *Run again and compare*; the Plan tab shows a summary per model
  with the checks a click away, and the Simulation page the full register.

## 13. Security and privacy (9.8)

Strict bodies (unknown fields refused); distributions are data from a closed set, checked
against each input's range and decimals before any draw; nothing is evaluated. Work is bounded
(draws, quantities, discrete values, grid size, deadlines) and at most two analyses compute at
once per process (429 beyond, before any work). Analyses are append-only; *verify* stores
nothing and detects a changed stored request. The seed generator is not cryptographic and is
not used for anything secret. No dependency and no secret was added; no route lets a client
change a stored result ([security](../security.md#advanced-analysis-phase-9)). Authorisation
remains absent, as in every phase so far (Phase 10).

## 14. Completion gate (9.10)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Advanced capabilities integrated with the engine and the Scenario Lab | **Met** | One evaluator over stored executions, used by all three analyses; the Lab's tabs; the Simulation page |
| 2 | Workflows work end to end with real supported data | **Met, with stated limits** | The real registered models, engine, API, database and sample graph, end to end in the integration suite and the browser; the figures are hypothetical because RUMIN holds no company accounts and no observations are stored here |
| 3 | Assumptions, validation status, uncertainty and limitations visible | **Met** | Notes on every result (conditional, independent draws, cut distributions), intervals and diagnostics, the register with what is not verified, caveats on older analyses, the four kinds of analysis stated |
| 4 | Results traceable and reproducible | **Met** | Configuration and hashes stored; *verify* reproduces exactly (tests, integration, review) |
| 5 | Graph integration only through documented, model-compatible relationships | **Met** | Stored snapshots and the existing channel rule; no relationship added or read as a coefficient |
| 6 | Tests pass, or failures documented | **Met** | [Quality gates](#quality-gates) |
| 7 | UI polished, accessible, responsive, consistent | **Met, with stated limits** | Both themes, 1440 and 390 px; `axe-core` clean on the reviewed views; keyboard sliders; table twins. Not automated; Chromium only; no screen-reader session with a user |
| 8 | Phases 1–8 remain functional | **Met** | Every earlier suite passes; the Phase 5 contrast defect and the sensitivity method were corrected, not regressed |
| 9 | Documentation updated | **Met** | [Advanced analysis](../scenario-lab/advanced-analysis.md), [the verification register](../simulation/verification.md), decisions 79–87, API, data model and dictionary, testing, design system, security, architecture, Lab and simulation guides, limitations, roadmap, README |
| 10 | Report written, with the installed UI/UX skills used | **Met** | This report, [§ 8](#8-installed-skills-inspected-and-used) |

**The gate is passed**, with the limits stated in criteria 2 and 7.

## 15. Known gaps and limitations

- **No estimation, calibration or back-testing** — the register says so for every model.
- **Distributions are assumptions**; quantities are independent; three distribution shapes;
  plain random sampling; rank correlations, not variance-based indices.
- **Bounded and in-process**: two analyses at once per process, synchronous, no queue.
- **Stored executions only**: no Monte Carlo on single Simulation-page runs.
- **No comparison view of two analyses**; no reverse stress test.
- **Review not automated**: Chromium only, no screen-reader session.

The full lists: [Lab limitations](../scenario-lab/limitations.md#analyses),
[simulation limitations](../simulation/limitations.md),
[known limitations](../known-limitations.md#advanced-analysis-phase-9).

## 16. How to run and verify

```bash
make install && make migrate seed catalog graph
make backend                       # API on http://127.0.0.1:8000
make frontend                      # http://127.0.0.1:5173/scenarios
make verify-models                 # every model version's register; exit 1 on a failure
cd backend && uv run pytest tests/test_scenario_lab_statistics.py \
  tests/test_scenario_lab_analyses.py tests/test_scenario_analyses_api.py \
  tests/test_simulation_verification.py
make smoke                         # fresh database, live API, the integration suite
```

In the Lab, start from the *oil, rupee and rates* template, enter figures, save and execute;
then open **Sensitivity** (*One at a time*, *Two together*) or **Uncertainty**: *Add the
scenario's changes*, adjust the distributions, set a seed and run; *Configuration and
reproducibility* → *Run again and compare* checks it. The Plan tab and the Simulation page show
each model's register.

## 17. Recommendations for Phase 10

- **Authentication and ownership** before anything else: analyses, executions and runs are
  append-only but unowned and unlimited; add per-user limits and retention with it.
- **A shared job queue** (PostgreSQL-backed) for executions and analyses before running
  several API processes; the per-process semaphores are not shared.
- **Automated browser checks in CI**: the Phase 9 review script (walk-through, `axe-core`,
  overflow at 390 px) is a ready starting point.
- **Observability**: record analysis durations, rejections and 429s; they are the first
  capacity signals.

## Quality gates

| Check | Result |
|---|---|
| `make check` (ruff, format, mypy on `app tests`, Biome, `tsc`, both suites, OpenAPI snapshot), backend on PostgreSQL 16 | Passed: frontend 404, backend 1,149 passed and 1 skipped, contract up to date |
| `make smoke` (fresh database, live API, integration suite) | Passed: 66 tests |
| `make verify-models` | All six versions pass every check |
| Chromium review, keyboard, `axe-core`, 390 px | No violation in five views × two themes, no overflow, no console message (after the fixes in § 11) |
| CI | Run #34 on `836bdf7`: green — backend (lint, format, types, sample dataset, OpenAPI snapshot, tests on SQLite and PostgreSQL 16), frontend (lint, types, tests, build, API types) and the end-to-end smoke test. Runs #29–#32 failed on the lint and typing issues in § 11; #33 was the first green run after them |
