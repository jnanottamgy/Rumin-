# Crude-oil-linked costs (`crude_linked_costs` 1.0.0, preview)

What a change in the Brent crude oil price does to one company's operating costs priced off
crude oil (feedstock crude, diesel and other fuels) and so to its operating profit, month
by month, with hedging and a partial recovery through selling prices. Everything else stays
at its baseline.

This model and [natural-gas-linked costs](gas-linked-costs.md) are built from one template
(`backend/app/simulation/models/commodity_linked_costs.py`): the same inputs, equations,
outputs, assumptions and rules, with the commodity, its benchmark and the relationships it
cites changed. They are separate models with separate definition hashes.

## Why this model

The Scenario Lab runs several models on one scenario, so Phase 5 added four narrow ones,
each checked by hand and anchored in relationships the knowledge graph already states
([plan, section 3](../phases/phase-5-plan.md#3-models)). This one covers costs priced off
crude oil:

| | Crude-oil-linked costs |
|---|---|
| What it adds | Costs priced off crude oil other than jet fuel, for refiners and road freight: the extension the [airline model's reasoning](airline-fuel-cost.md#why-this-domain) names. Jet fuel stays with the airline model |
| Graph anchor | Brent crude *affects costs of* petroleum refining and land transport (supporting relationships S2 and S3). In RUMIN's sample network the companies in those industries are Deltrin Refining, Solvane Refining and Trakvel Logistics. They are fictional, and the relationships are recorded as model assumptions on illustrative data |
| Mathematical form | The airline fuel bill's structure without the currency: a monthly cost × the input's price relative to its baseline, with a hedged share at the baseline price and a lagged recovery through selling prices |
| No graph rule | The company's input price is not a node of the knowledge graph, so the elasticity β and the price delay L are assumptions inside the model (E4), not a transmission rule |
| Checks | Exact invariants: β scales the log-change (β = 0.5 turns +20 % into √1.2); the delay postpones the effect; the hedging bridge closes; linked costs above operating costs are refused. Round inputs give results checkable by hand (below) |

In the Scenario Lab the graph decides whether the model applies to a company by default,
never how much. RUMIN holds **no company financial figures**, so every amount comes from
the user.

## Inputs

Each input has a category: a change you explore (`scenario_input`), your figures about the
company (`company_input`), a modelling assumption with a stated default (`assumption`) or
how the run is carried out (`setting`). A run labels each value with the kind of knowledge
it is. Ranges are enforced; a value outside them is refused, never clipped.

| Input | Category | Unit | Allowed | Default |
|---|---|---|---|---|
| Crude oil price change (`crude_oil_change`), on Brent crude | `scenario_input` | `percent_change` | > −100, ≤ 1,000; 4 decimals | 0 |
| Company in the knowledge graph (`entity`) | `company_input` | `graph_node` | a company in the latest graph build | None |
| Reporting currency (`reporting_currency`) | `company_input` | `currency_code` | three capital letters | Required |
| Annual revenue (`annual_revenue`) | `company_input` | `currency_per_year` | > 0, ≤ 10¹⁵; 6 decimals | Required |
| Annual operating costs (`annual_operating_costs`) | `company_input` | `currency_per_year` | > 0, ≤ 10¹⁵; 6 decimals | Required |
| Annual costs priced off crude oil (`linked_annual_cost`) | `company_input` | `currency_per_year` | > 0, ≤ 10¹⁵; 6 decimals | Required |
| Elasticity to crude oil (`cost_pass_through`) | `assumption` | `elasticity` | 0–3; 4 decimals | 1 |
| Price delay (`cost_pass_through_lag`) | `assumption` | `months` | 0–12 | 0 |
| Hedge ratio (`hedge_ratio`) | `assumption` | `percent` | 0–100; 2 decimals | 0 |
| Hedge cover (`hedge_months`) | `assumption` | `months` | 0–36 | 0 |
| Price recovery (`price_recovery`) | `assumption` | `percent` | 0–100; 2 decimals | 0 |
| Price recovery delay (`price_recovery_lag`) | `assumption` | `months` | 0–12 | 0 |
| Horizon (`horizon_months`) | `setting` | `months` | 1–36 | 12 |
| Changes start in month (`shock_start_month`) | `setting` | `months` | 1–36, within the horizon | 1 |
| Changes last for (months) (`shock_duration_months`) | `setting` | `months` | 0–36 (0: to the end of the horizon) | 0 |

The linked costs are operating costs whose price follows crude oil, in the reporting
currency; leave out jet fuel if the airline model is also used, since it covers fuel
itself. Every assumption's default is neutral (β = 1 moves the input's price in proportion
to the benchmark; no delay, hedging or recovery unless entered), and each has a written
rationale. None is an estimate (L4).

## Equations

Months are m = 1 … H. Symbols: K annual costs priced off crude oil, O annual operating
costs, R annual revenue, c crude oil price change (a fraction), S the month the change
takes effect, E the last month it lasts, β elasticity to crude oil, L price delay, h hedge
ratio, M_h hedge months, φ price recovery, L_p price recovery delay.

| | Equation | Scope | Rests on | Limits |
|---|---|---|---|---|
| E1 | f = K / O: linked share of operating costs; must not exceed 1 | annual | — | — |
| E2 | k₀ = K / 12: monthly baseline linked cost | annual | A2 | L6 |
| E3 | ℓ_B(m) = ln(1 + c) · 𝟙[S ≤ m ≤ E]: Brent crude log-change in effect, propagated by the transmission engine | monthly | A4 | — |
| E4 | r(m) = exp(β · ℓ_B(m − L)): input price relative to baseline (1 before the delay has passed) | monthly | A3 | L3, L4 |
| E5 | h(m) = h if m ≤ M_h, otherwise 0: hedged share | monthly | A5 | — |
| E6 | k₁(m) = k₀ × [h(m) + (1 − h(m)) × r(m)]: scenario monthly linked cost | monthly | A1, A3, A5 | — |
| E7 | Δk(m) = k₁(m) − k₀: change in linked cost | monthly | — | — |
| E8 | Δp(m) = φ × Δk(m − L_p) if m > L_p, otherwise 0: price recovery | monthly | A6 | L2 |
| E9 | Δπ(m) = Δp(m) − Δk(m): change in operating profit | monthly | A1 | L5 |
| E10 | ΣΔk = Σₘ Δk(m); ΣΔp = Σₘ Δp(m); ΣΔπ = Σₘ Δπ(m), m = 1…H: totals over the horizon | horizon | — | — |
| E11 | Π₀ = (R − O) × H / 12; Π₁ = Π₀ + ΣΔπ: operating profit over the horizon | horizon | A1, A2 | — |
| E12 | μ₀ = (R − O) / R; μ₁ = (R·H/12 + ΣΔp − O·H/12 − ΣΔk) / (R·H/12 + ΣΔp): operating margins | horizon | — | — |
| E13 | ΔK* = K × (exp(β · ln(1 + c)) − 1); ΔΠ* = (φ − 1) × ΔK*: run-rate annual effect, while the change lasts, once every lag has passed and every hedge has expired | steady state | A3, A6 | — |
| E14 | G = Σₘ k₀ × (r(m) − 1); hedging effect = ΣΔk − G: the change with no hedges, and what the hedges changed | horizon | A5 | — |

**Why log-changes.** A crude change reaches the input's price as β·ln(1 + c): with β = 1 a
20 % rise in crude is a 20 % rise in the input's price, and with β = 0.5 it is
exp(0.5 · ln 1.2) = √1.2, a rise of about 9.54 %.

**The timing.** The change enters the engine as a log-change, ln(1 + c), on Brent crude.
The engine applies it at that node from month S to month E and carries it along no
relationship (E3); the model reads it L months later (E4), so the input's price moves from
month S + L to month E + L, within the horizon. S is `shock_start_month`; E is S + D − 1 for
a duration D (`shock_duration_months`) of at least one month, and the horizon's last month
when D = 0. The run rate (E13) is the yearly effect while the change lasts.

**The bridge.** The operating-profit change splits exactly into three outputs of the run:

  ΣΔπ = −G − (hedging effect) + ΣΔp

that is, the linked-cost change without hedges, what the hedges changed, and price
recovery. The engine checks the identity before storing a run (the residual must be below
10⁻¹²); a run whose bridge does not close fails instead of being stored.

## Outputs

Every output is rounded half to even to 10 decimal places
([numbers](numbers-and-units.md)): `derived` from the inputs alone, or `simulated` under
the scenario. A run labels the currency units with the reporting currency. Outputs marked
*yes* are attributed to the scenario's changes by Shapley values
([contributions](provenance.md#contributions-shapley-values)).

| Output | Unit | Kind | Equation | Attributed |
|---|---|---|---|---|
| Linked share of operating costs (`linked_cost_share`) | `ratio` | derived | E1 | — |
| Monthly baseline linked cost (`monthly_baseline_linked_cost`) | `currency_per_month` | derived | E2 | — |
| Baseline operating profit (horizon) (`baseline_operating_profit`) | `currency` | derived | E11 | — |
| Baseline operating margin (`baseline_operating_margin`) | `ratio` | derived | E12 | — |
| Input price change (run rate) (`input_price_change`) | `ratio` | simulated | E13 | yes |
| Change in linked costs (horizon) (`linked_cost_change`) | `currency` | simulated | E10 | yes |
| Change in linked costs without hedges (horizon) (`gross_linked_cost_change`) | `currency` | simulated | E14 | yes |
| Hedging effect (horizon) (`hedging_effect`) | `currency` | simulated | E14 | yes |
| Price recovery (horizon) (`price_recovery`) | `currency` | simulated | E10 | yes |
| Change in operating profit (horizon) (`operating_profit_change`) | `currency` | simulated | E10 | yes |
| Scenario operating profit (horizon) (`scenario_operating_profit`) | `currency` | simulated | E11 | — |
| Scenario operating margin (`scenario_operating_margin`) | `ratio` | simulated | E12 | — |
| Change in operating margin (`operating_margin_change`) | `ratio_points` | simulated | E12 | yes |
| Run-rate annual linked-cost change (`run_rate_cost_change`) | `currency_per_year` | simulated | E13 | yes |
| Run-rate annual operating-profit change (`run_rate_operating_profit_change`) | `currency_per_year` | simulated | E13 | yes |

The monthly series:

| Series | Unit | Kind | Equation |
|---|---|---|---|
| Brent crude relative to baseline (`benchmark_relative`) | `price_relative` | simulated | E3 |
| Input price relative to baseline (`input_price_relative`) | `price_relative` | simulated | E4 |
| Hedged share (`hedged_share`) | `ratio` | derived | E5 |
| Change in linked costs (`linked_cost_change`) | `currency_per_month` | simulated | E7 |
| Price recovery (`price_recovery`) | `currency_per_month` | simulated | E8 |
| Change in operating profit (`operating_profit_change`) | `currency_per_month` | simulated | E9 |

## Graph relationships

The model declares **no transmission rule**: the crude change acts directly on Brent crude,
and β and L act inside the model. A run therefore needs no built graph unless a company is
chosen ([graph integration](graph-integration.md)). The model cites three supporting
relationships, which are never followed:

| Rule | Relationship | Role |
|---|---|---|
| S1 | Brent crude → *affects costs of* → the chosen company | Crude oil affects the company's costs |
| S2 | Brent crude → *affects costs of* → petroleum refining (`industry:ind_petroleum_refining`) | Crude oil is a cost of refining (feedstock) |
| S3 | Brent crude → *affects costs of* → land transport (`industry:ind_land_transport`) | Crude oil is a cost of land transport (diesel) |

None is required: a company the graph does not link to crude oil can still be simulated,
and the result then rests on the entered figures alone.

## Assumptions

- **A1** Everything the model does not include stays at its baseline: volumes, other costs, demand, selling prices (apart from the stated recovery) and financing.
- **A2** Linked costs, revenue and operating costs accrue evenly through the year: each month carries one twelfth.
- **A3** The company's input price, in the reporting currency, follows crude oil with a constant elasticity β after a delay L: ln(input price) changes by β × ln(1 + crude oil change). Exchange-rate effects on the input are not part of this model.
- **A4** Scenario changes are step changes: they take effect in the start month and last for the stated duration (to the end of the horizon unless one is set), after which the changed variables return to their baselines. Every change in a run shares this timing.
- **A5** Hedged inputs keep their baseline price until the hedges expire; hedges are not rolled over.
- **A6** Selling prices recover a fixed share of the change in linked costs after a delay, for rises and falls alike, and demand does not respond.

## Limitations

- **L1** The model shows the arithmetic consequence of the inputs and assumptions. It is not a forecast of what will happen, and not investment advice.
- **L2** Demand, volumes and market share do not respond to selling prices.
- **L3** For inputs paid in US dollars, a simultaneous exchange-rate change also moves their cost. Model that with the currency model; the combination leaves out the small cross effect (commodity change × currency change).
- **L4** The elasticity, delays, hedge terms and recovery are assumptions with neutral defaults. None is estimated in RUMIN.
- **L5** Operating profit only: no interest, tax, hedge accounting, working capital or cash-flow timing.
- **L6** Monthly steps: timing within a month is ignored, and seasonality is not modelled.

## Validation rules

| Rule | Severity | What it checks |
|---|---|---|
| `input_range` | error | Every number is within its range and has at most the allowed decimal places; required inputs are present |
| `percent_change_limits` | error | Scenario changes are greater than −100 % and at most +1,000 %, with at most 4 decimals — the limits Phase 1 publishes for scenario inputs |
| `linked_cost_within_costs` | error | The linked costs cannot exceed annual operating costs |
| `start_within_horizon` | error | The changes must take effect within the horizon |
| `timing_within_horizon` | warning | Delays, hedges and price responses that fall outside the horizon are flagged |
| `no_shock` | warning | A run in which every scenario change is zero is flagged: it equals the baseline |

The change limits are the change's own range, so a change outside them is reported as
`input_range`. A run is refused when revenue over the horizon would fall to zero or below,
since the operating margin would be undefined. A chosen company must be a company node of
the latest graph build; the engine refuses one that is not, or any company while no graph
is built, with the code `entity_is_airline`, which it uses for this check in every model.
The engine adds notes to a run: a fictional company (`fictional_entity`) and a graph older
than its sources (`graph_stale`).

## Headline outputs and sensitivity defaults

A summary of a run shows first the change in linked costs (`linked_cost_change`), the
change in operating profit (`operating_profit_change`), the change in operating margin
(`operating_margin_change`) and the run-rate annual operating-profit change
(`run_rate_operating_profit_change`).

A [sensitivity analysis](sensitivity.md) with an empty request varies these inputs by
their default variation and ranks them by the change in operating profit
(`operating_profit_change`):

| Input | Default variation |
|---|---|
| `crude_oil_change` | ±10 points |
| `cost_pass_through` | ±0.2 |
| `hedge_ratio` | ±25 points |
| `price_recovery` | ±25 points |
| `linked_annual_cost` | ±10 % |

A point outside an input's range (a hedge ratio below 0 %) is skipped and listed, never
clipped.

## In the Scenario Lab

The model's scenario profile (`backend/app/scenario_lab/profiles.py`;
[how profiles work](registry.md#scenario-lab-profiles)):

| | |
|---|---|
| Responds to | Brent crude, as a percent change → `crude_oil_change` |
| Lines | Operating costs: item `crude_linked_inputs` (inputs priced off crude oil, other than jet fuel) from `linked_cost_change`. Revenue: item `crude_cost_recovery` (price recovery of crude-linked costs) from `price_recovery` |
| Applies by default | when a company is chosen and the graph states that Brent crude *affects costs of* the company or its industry |
| Without that statement | available: it can be included by hand, and the result rests on the entered figures (`exposure_required` is false) |
| Cautions | With the airline model: both respond to crude oil, so leave jet fuel out of the crude-linked costs. With the currency model: if some crude-linked inputs are paid in US dollars, the combined result leaves out the small cross effect (crude change × currency change) |
| Templates | *Crude oil shock on crude-linked costs* |

The company, its reporting currency, revenue and operating costs, the horizon and the
timing come from the scenario, shared with every model; the linked costs and the
assumptions are this model's own.

## Worked example (checked by hand)

The tests' example (`backend/tests/test_simulation_models.py`). Every company figure is
**hypothetical**: round numbers chosen so the results can be checked on paper, not market
data or any company's figures.

**Inputs.** Reporting currency INR; revenue 500,000,000 INR and operating costs
400,000,000 INR a year, of which 120,000,000 INR are priced off crude oil; crude oil +20 %
from month 1 to the end of the horizon; β = 1 and no price delay (defaults); a quarter of
the linked costs hedged for six months; half of the change recovered through selling prices
a month later; 12 months.

| Step | By hand | The engine |
|---|---|---|
| E1 | 120,000,000 / 400,000,000 = 0.3 | 0.3 |
| E2 | 120,000,000 / 12 = 10,000,000 a month | 10,000,000 |
| E3–E4 | ℓ_B = ln 1.2 from month 1; r = exp(ln 1.2) = 1.2 | 1.2 |
| E5–E7, months 1–6 | 10,000,000 × (0.25 + 0.75 × 1.2) − 10,000,000 = 1,500,000 | 1,500,000 |
| E5–E7, months 7–12 | 10,000,000 × 1.2 − 10,000,000 = 2,000,000 | 2,000,000 |
| E8 | months 2–7: 0.5 × 1,500,000 = 750,000; months 8–12: 0.5 × 2,000,000 = 1,000,000 | same |
| E10 | ΣΔk = 6 × 1,500,000 + 6 × 2,000,000 = 21,000,000; ΣΔp = 6 × 750,000 + 5 × 1,000,000 = 9,500,000; ΣΔπ = −11,500,000 | same |
| E11 | Π₀ = 100,000,000; Π₁ = 88,500,000 | same |
| E12 | μ₀ = 100 / 500 = 20 %; μ₁ = 88.5 / 509.5 = 17.37 %; change −2.63 percentage points | 0.2; 0.1736997056; −0.0263002944 |
| E13 | ΔK* = 120,000,000 × (1.2 − 1) = 24,000,000 a year; ΔΠ* = (0.5 − 1) × 24,000,000 = −12,000,000 a year | same |
| E14 | G = 12 × 2,000,000 = 24,000,000; hedging effect = 21,000,000 − 24,000,000 = −3,000,000 | same |
| Bridge | −24,000,000 + 3,000,000 + 9,500,000 = −11,500,000 | closes |

These numbers are asserted by `test_crude_linked_costs_match_the_hand_calculation`,
together with invariants: with β = 0.5 and a two-month price delay, the input's price stays
at its baseline in months 1–2 and is √1.2 = 1.095445115 times it from month 3
(`input_price_change` 0.095445115); and linked costs above operating costs are refused
(`linked_cost_within_costs`).
