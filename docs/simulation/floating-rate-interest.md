# Floating-rate interest costs (`floating_rate_interest` 1.0.0, preview)

What a change in the RBI policy repo rate or in US short-term rates does to the interest one
company pays on its floating-rate debt, and so to its profit before tax and its interest
coverage, month by month. A rate change is given in percentage points; it reaches each
loan's rate by a stated share after a stated repricing delay. Everything else stays at its
baseline: the amount of debt, fixed-rate debt and operating profit.

## Why this model

The Scenario Lab runs several models on one scenario, so Phase 5 added four narrow ones,
each checked by hand and anchored in relationships the knowledge graph already states
([plan, section 3](../phases/phase-5-plan.md#3-models)). This one covers financing costs:

| | Floating-rate interest costs |
|---|---|
| What it adds | Interest expense, a line no other model touches, and with it profit before tax and interest coverage. Operating profit does not change in this model |
| Graph anchor | In RUMIN's sample network, the RBI repo rate *affects financing costs of* Gridwell Power and Trakvel Logistics, and the US effective federal funds rate *affects financing costs of* Lumeric Chemicals. The companies are fictional, and the relationships are recorded as model assumptions on illustrative data |
| Mathematical form | Debt × the change in its rate ÷ 12 each month; percent × percentage points ÷ 10,000 is the change in the rate as a fraction |
| Rates in percentage points | A rate is changed in percentage points, never in percent of the rate: +10 % of a 6.5 % rate would be ambiguous (the Phase 1 rule, reference R1). The engine applies such a change as a level shock ([timing and rate changes](README.md#timing-and-rate-changes-phase-5)) |
| Checks | Exact invariants: the repricing delay postpones the effect; the pass-through scales it; the two benchmarks add up; a rate change is recorded in percentage points at its own node; the bridge closes. Round inputs give results checkable by hand (below) |

In the Scenario Lab the graph decides whether the model applies to a company by default,
never how much. RUMIN holds **no company financial figures**, so every amount comes from
the user. RUMIN does not predict policy rates: the change is taken as given (A3).

## Inputs

Each input has a category: a change you explore (`scenario_input`), your figures about the
company (`company_input`), a modelling assumption with a stated default (`assumption`) or
how the run is carried out (`setting`). A run labels each value with the kind of knowledge
it is. Ranges are enforced; a value outside them is refused, never clipped.

| Input | Category | Unit | Allowed | Default |
|---|---|---|---|---|
| RBI repo rate change (`repo_rate_change`), on the RBI policy repo rate | `scenario_input` | `percentage_points` | ≥ −25, ≤ 25; 4 decimals | 0 |
| US short-term rate change (`us_rate_change`), on the US effective federal funds rate | `scenario_input` | `percentage_points` | ≥ −25, ≤ 25; 4 decimals | 0 |
| Company in the knowledge graph (`entity`) | `company_input` | `graph_node` | a company in the latest graph build | None |
| Reporting currency (`reporting_currency`) | `company_input` | `currency_code` | three capital letters | Required |
| Annual revenue (`annual_revenue`) | `company_input` | `currency_per_year` | > 0, ≤ 10¹⁵; 6 decimals | Required |
| Annual operating costs (`annual_operating_costs`) | `company_input` | `currency_per_year` | > 0, ≤ 10¹⁵; 6 decimals | Required |
| Annual interest expense (`annual_interest_expense`) | `company_input` | `currency_per_year` | ≥ 0, ≤ 10¹⁵; 6 decimals | Required |
| Debt linked to the repo rate (`repo_linked_debt`) | `company_input` | `currency` | ≥ 0, ≤ 10¹⁵; 6 decimals | Required |
| Debt linked to US short-term rates (`us_rate_linked_debt`) | `company_input` | `currency` | ≥ 0, ≤ 10¹⁵; 6 decimals | Required |
| Repo pass-through (`repo_pass_through`) | `assumption` | `percent` | 0–200; 2 decimals | 100 |
| Repo repricing delay (`repo_repricing_lag`) | `assumption` | `months` | 0–12 | 0 |
| US-rate pass-through (`us_pass_through`) | `assumption` | `percent` | 0–200; 2 decimals | 100 |
| US-rate repricing delay (`us_repricing_lag`) | `assumption` | `months` | 0–12 | 0 |
| Horizon (`horizon_months`) | `setting` | `months` | 1–36 | 12 |
| Changes start in month (`shock_start_month`) | `setting` | `months` | 1–36, within the horizon | 1 |
| Changes last for (months) (`shock_duration_months`) | `setting` | `months` | 0–36 (0: to the end of the horizon) | 0 |

The interest expense is on all debt, fixed and floating, per year at today's rates. Each
floating-rate amount is the debt outstanding (0 if none); debt linked to US rates is stated
in the reporting currency at today's exchange rate (A5). The defaults pass a benchmark
change on in full (100 %) with no repricing delay, and each has a written rationale. None is
an estimate (L4).

## Equations

Months are m = 1 … H. Symbols: Δk_r and Δk_u the changes in the repo rate and in US
short-term rates (percentage points), S the month the changes take effect, E the last month
they last, D_r and D_u the debt linked to each benchmark, p_r and p_u the pass-through
(percent), L_r and L_u the repricing delays, R annual revenue, O annual operating costs, I
annual interest expense.

| | Equation | Scope | Rests on | Limits |
|---|---|---|---|---|
| E1 | Δk(m) = Δk · 𝟙[S ≤ m ≤ E]: benchmark change in effect, for each benchmark, applied by the transmission engine at the benchmark's own node | monthly | A4 | — |
| E2 | ΔI_r(m) = D_r × p_r × Δk_r(m − L_r) / 10 000 / 12: change in interest on repo-linked debt | monthly | A1, A2, A3 | L4 |
| E3 | ΔI_u(m) = D_u × p_u × Δk_u(m − L_u) / 10 000 / 12: change in interest on US-rate-linked debt | monthly | A1, A2, A3, A5 | L4 |
| E4 | ΔI(m) = ΔI_r(m) + ΔI_u(m); ΣΔI = Σₘ ΔI(m), m = 1…H: change in interest expense | horizon | — | — |
| E5 | P₀ = (R − O − I) × H / 12; ΔP = −ΣΔI; P₁ = P₀ + ΔP: profit before tax over the horizon; operating profit itself does not change | horizon | A1, A2 | L3 |
| E6 | κ₀ = (R − O) / I; κ₁ = (R − O) × H / 12 / (I × H / 12 + ΣΔI): interest coverage | horizon | — | — |
| E7 | ΔI* = (D_r × p_r × Δk_r + D_u × p_u × Δk_u) / 10 000: run-rate annual interest change, once every loan has repriced | steady state | A2 | — |

**Units.** The pass-through is in percent and the change in percentage points, so their
product divided by 10,000 is the change in the loan's rate as a fraction
(100 × 0.5 / 10,000 = 0.005, half a percentage point); dividing by 12 gives one month's
interest.

**The timing.** A rate change is a *level* shock: the engine applies it, in percentage
points, at the benchmark's own node from month S to month E, and never carries it along a
relationship (E1). S is `shock_start_month`; E is S + D − 1 for a duration D
(`shock_duration_months`) of at least one month, and the horizon's last month when D = 0.
A loan reads the change L months later, so it pays the changed rate from month S + L to
month E + L, within the horizon. The run rate (E7) is the yearly change while the changes
last, once every loan has repriced.

**The bridge.** The change in profit before tax splits exactly into the two debts:

  ΔP = −ΣΔI_r − ΣΔI_u

The engine checks the identity before storing a run (the residual must be below 10⁻¹²); a
run whose bridge does not close fails instead of being stored.

## Outputs

Every output is rounded half to even to 10 decimal places
([numbers](numbers-and-units.md)): `derived` from the inputs alone, or `simulated` under
the scenario. A run labels the currency units with the reporting currency. Outputs marked
*yes* are attributed to the scenario's changes by Shapley values
([contributions](provenance.md#contributions-shapley-values)).

| Output | Unit | Kind | Equation | Attributed |
|---|---|---|---|---|
| Floating-rate debt (`floating_rate_debt`) | `currency` | derived | E4 | — |
| Baseline interest expense (horizon) (`baseline_interest_expense`) | `currency` | derived | E5 | — |
| Baseline profit before tax (horizon) (`baseline_profit_before_tax`) | `currency` | derived | E5 | — |
| Baseline interest coverage (`baseline_interest_coverage`) | `times` | derived | E6 | — |
| Change in interest on repo-linked debt (horizon) (`repo_interest_change`) | `currency` | simulated | E4 | yes |
| Change in interest on US-rate-linked debt (horizon) (`us_interest_change`) | `currency` | simulated | E4 | yes |
| Change in interest expense (horizon) (`interest_expense_change`) | `currency` | simulated | E4 | yes |
| Change in profit before tax (horizon) (`profit_before_tax_change`) | `currency` | simulated | E5 | yes |
| Scenario profit before tax (horizon) (`scenario_profit_before_tax`) | `currency` | simulated | E5 | — |
| Scenario interest coverage (`scenario_interest_coverage`) | `times` | simulated | E6 | — |
| Change in interest coverage (`interest_coverage_change`) | `times` | simulated | E6 | yes |
| Run-rate annual interest change (`run_rate_interest_change`) | `currency_per_year` | simulated | E7 | yes |

The monthly series:

| Series | Unit | Kind | Equation |
|---|---|---|---|
| Repo-rate change in effect (`repo_rate_change_in_effect`) | `percentage_points` | simulated | E1 |
| US-rate change in effect (`us_rate_change_in_effect`) | `percentage_points` | simulated | E1 |
| Change in interest on repo-linked debt (`repo_interest_change`) | `currency_per_month` | simulated | E2 |
| Change in interest on US-rate-linked debt (`us_interest_change`) | `currency_per_month` | simulated | E3 |
| Change in interest expense (`interest_expense_change`) | `currency_per_month` | simulated | E4 |
| Change in profit before tax (`profit_before_tax_change`) | `currency_per_month` | simulated | E5 |

## Graph relationships

The model declares **no transmission rule**. A change in percentage points is applied at
its own node and could not travel along a log-linear rule in any case: a definition with a
rule that touches a node shocked in percentage points cannot be built. A run therefore
needs no built graph unless a company is chosen ([graph integration](graph-integration.md)).
The model cites two supporting relationships, which are never followed:

| Rule | Relationship | Role |
|---|---|---|
| S1 | RBI repo rate → *affects financing costs of* → the chosen company | The repo rate affects the company's financing costs (E2) |
| S2 | US effective federal funds rate → *affects financing costs of* → the chosen company | US short-term rates affect the company's financing costs (E3) |

Neither is required: a company the graph does not link to either rate can still be
simulated, and the result then rests on the entered figures alone.

## Assumptions

- **A1** Everything the model does not include stays at its baseline: the amount of debt (no repayments or new borrowing), fixed-rate debt, operating profit and other income.
- **A2** Floating-rate loans reprice by the stated share of the benchmark change after the stated delay, then keep that rate while the change lasts. Interest accrues evenly: each month carries one twelfth of the annual rate.
- **A3** The benchmark change is taken as given. RUMIN does not predict policy rates.
- **A4** Scenario changes are step changes: they take effect in the start month and last for the stated duration (to the end of the horizon unless one is set), after which the changed variables return to their baselines. Every change in a run shares this timing.
- **A5** Debt linked to US rates is stated in the reporting currency at today's exchange rate; exchange-rate movements on it are not modelled here.

## Limitations

- **L1** The model shows the arithmetic consequence of the inputs and assumptions. It is not a forecast of what will happen, and not investment advice.
- **L2** No refinancing, repayment, covenant, credit-spread or rating effects, and no change in deposits or interest income.
- **L3** Before tax: the tax deductibility of interest is not modelled.
- **L4** The pass-through shares and repricing delays are assumptions with neutral defaults. None is estimated in RUMIN.
- **L5** Two benchmarks only: the RBI repo rate and US short-term rates.
- **L6** Monthly steps: timing within a month is ignored, and seasonality is not modelled.

## Validation rules

| Rule | Severity | What it checks |
|---|---|---|
| `input_range` | error | Every number is within its range and has at most the allowed decimal places; required inputs are present |
| `rate_change_limits` | error | Rate changes are in percentage points, between −25 and +25, with at most 4 decimals — the limits Phase 1 publishes for rates |
| `has_floating_debt` | error | At least one of the floating-rate debt amounts must be above zero |
| `interest_positive` | error | Interest expense must be above zero when floating-rate debt is stated |
| `operating_profit_positive` | warning | Interest coverage is only meaningful with a positive operating profit; a loss is flagged |
| `start_within_horizon` | error | The changes must take effect within the horizon |
| `timing_within_horizon` | warning | Repricing that happens only after the horizon is flagged |
| `no_shock` | warning | A run in which every scenario change is zero is flagged: it equals the baseline |

The rate limits are the change's own range, so a change outside them, or with more than
four decimals, is reported as `input_range`. A run is also refused, with the code
`interest_positive`, when interest over the horizon would fall to zero or below (coverage
would be undefined). A chosen company must be a company node of the latest graph build;
the engine refuses one that is not, or any company while no graph is built, with the code
`entity_is_airline`, which it uses for this check in every model. The engine adds notes to
a run: a fictional company (`fictional_entity`) and a graph older than its sources
(`graph_stale`).

## Headline outputs and sensitivity defaults

A summary of a run shows first the change in interest expense (`interest_expense_change`),
the change in profit before tax (`profit_before_tax_change`), the change in interest
coverage (`interest_coverage_change`) and the run-rate annual interest change
(`run_rate_interest_change`).

A [sensitivity analysis](sensitivity.md) with an empty request varies these inputs by
their default variation and ranks them by the change in profit before tax
(`profit_before_tax_change`):

| Input | Default variation |
|---|---|
| `repo_rate_change` | ±0.25 percentage points |
| `us_rate_change` | ±0.25 percentage points |
| `repo_pass_through` | ±25 points |
| `repo_repricing_lag` | ±2 months |
| `repo_linked_debt` | ±10 % |
| `us_rate_linked_debt` | ±10 % |

A point outside an input's range (a repricing delay below 0) is skipped and listed, never
clipped.

## In the Scenario Lab

The model's scenario profile (`backend/app/scenario_lab/profiles.py`;
[how profiles work](registry.md#scenario-lab-profiles)):

| | |
|---|---|
| Responds to | The RBI repo rate → `repo_rate_change` and the US effective federal funds rate → `us_rate_change`, each as a change in percentage points (`absolute_change` in a scenario) |
| Lines | Interest expense: item `repo_linked_interest` from `repo_interest_change`, and item `us_rate_linked_interest` from `us_interest_change` |
| Applies by default | when a company is chosen and the graph states that the repo rate or the US federal funds rate *affects financing costs of* the company or its industry |
| Without that statement | available: it can be included by hand, and the result rests on the entered figures (`exposure_required` is false) |
| Operating profit | Not changed: the profile names no operating-profit output. With this model alone, the Lab shows interest expense and profit before tax, with operating profit held at its baseline |
| Templates | *Policy-rate rise*, *Oil, rupee and rates together* |

The company, its reporting currency, revenue and operating costs, the horizon and the
timing come from the scenario, shared with every model; the interest expense, the debt
amounts and the pass-through and delay assumptions are this model's own. In the Lab's
reference case (`backend/tests/scenario_support.py`), 100,000,000 INR of repo-linked debt
and the repo rate +0.5 percentage points after a 3-month delay give 9 × 41,666.67 =
375,000 INR of extra interest.

## Worked example (checked by hand)

The tests' example (`backend/tests/test_simulation_models.py`). Every company figure is
**hypothetical**: round numbers chosen so the results can be checked on paper, not market
data or any company's figures.

**Inputs.** Reporting currency INR; revenue 500,000,000 INR, operating costs 400,000,000 INR
and interest expense 80,000,000 INR a year; 1,000,000,000 INR of debt linked to the repo
rate, none to US rates; the repo rate +0.5 percentage points from month 1 to the end of the
horizon, passed on in full (the default 100 %) after a 3-month repricing delay; 12 months.

| Step | By hand | The engine |
|---|---|---|
| E1 | Δk_r(m) = 0.5 percentage points in every month | 0.5 |
| E2, months 1–3 | Δk_r(m − 3) = 0 until the loans reprice | 0 |
| E2, months 4–12 | 1,000,000,000 × 100 × 0.5 / 10,000 / 12 = 416,666.67 | 416,666.6666666667 |
| E4 | ΣΔI = 9 × 416,666.67 = 3,750,000 | 3,750,000 |
| E5 | P₀ = (500,000,000 − 400,000,000 − 80,000,000) × 12 / 12 = 20,000,000; ΔP = −3,750,000; P₁ = 16,250,000 | same |
| E6 | κ₀ = 100 / 80 = 1.25; κ₁ = 100,000,000 / 83,750,000 = 1.194 | 1.25; 1.1940298507 |
| E7 | ΔI* = 1,000,000,000 × 100 × 0.5 / 10,000 = 5,000,000 a year | 5,000,000 |
| Bridge | −3,750,000 − 0 = −3,750,000 | closes |

These numbers are asserted by `test_interest_matches_the_hand_calculation`, together with
invariants: the pass-through and both benchmarks add up (the repo rate +1 point at 50 % on
600,000,000 is 3,000,000 a year, US rates −0.5 point on 240,000,000 are −1,200,000, and
together 1,800,000 over 12 months and as the run rate); a repo change of 0.25 is recorded
as one transmission path of kind `level`, 0.25 percentage points at the repo-rate node only,
and is in force in every month; a 12-month repricing delay on a 12-month horizon is flagged
(`timing_within_horizon`); and a change of 25.5 points or with five decimals, no
floating-rate debt and a zero interest expense are each refused.
