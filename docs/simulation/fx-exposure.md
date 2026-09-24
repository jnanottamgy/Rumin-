# Foreign-currency revenue and costs (`fx_exposure` 1.0.0, preview)

What a change in the exchange rate does to one company's revenue invoiced and costs paid in
US dollars, and so to its operating profit, month by month, with hedges. Everything else
stays at its baseline: the US-dollar amounts, volumes and every other cost.

## Why this model

The Scenario Lab runs several models on one scenario, so Phase 5 added four narrow ones,
each checked by hand and anchored in relationships the knowledge graph already states
([plan, section 3](../phases/phase-5-plan.md#3-models)). This one covers the currency
channel on its own:

| | Foreign-currency revenue and costs |
|---|---|
| What it adds | Any revenue invoiced or cost paid in US dollars. The airline model converts only the fuel bill (its assumption A8); this model converts the rest |
| Graph anchor | In RUMIN's sample network, USD/INR *affects revenue of* Kovalent Digital and *affects costs of* Deltrin Refining, Aerisca Airways and Skyvara Air. All four companies are fictional, and the relationships are recorded as model assumptions on illustrative data |
| Mathematical form | An accounting identity: each month's US-dollar amounts × that month's exchange rate, with the hedged shares kept at the baseline rate |
| Checks | Exact invariants: a stronger reporting currency reverses the signs; dollar revenue and dollar costs offset, so only the net exposure moves profit; a change that lasts three months stops after three; the hedging bridge closes. Round inputs give results checkable by hand (below) |

In the Scenario Lab the graph decides whether the model applies to a company by default,
never how much. RUMIN holds **no company financial figures**, so every amount comes from
the user.

## Inputs

Each input has a category: a change you explore (`scenario_input`), a market level you
enter or take from stored data (`market_baseline`), your figures about the company
(`company_input`), a modelling assumption with a stated default (`assumption`) or how the
run is carried out (`setting`). A run labels each value with the kind of knowledge it is.
Ranges are enforced; a value outside them is refused, never clipped.

| Input | Category | Unit | Allowed | Default |
|---|---|---|---|---|
| Exchange-rate change (`fx_change`), on USD/INR | `scenario_input` | `percent_change` | > −100, ≤ 1,000; 4 decimals | 0 |
| Baseline exchange rate (`fx_rate`) | `market_baseline` | `currency_per_usd` | > 0, ≤ 100,000; 6 decimals (a stored value keeps its published precision) | Required |
| Company in the knowledge graph (`entity`) | `company_input` | `graph_node` | a company in the latest graph build | None |
| Reporting currency (`reporting_currency`) | `company_input` | `currency_code` | three capital letters | Required |
| Annual revenue (`annual_revenue`) | `company_input` | `currency_per_year` | > 0, ≤ 10¹⁵; 6 decimals | Required |
| Annual operating costs (`annual_operating_costs`) | `company_input` | `currency_per_year` | > 0, ≤ 10¹⁵; 6 decimals | Required |
| Annual revenue invoiced in US dollars (`annual_usd_revenue`) | `company_input` | `usd_per_year` | ≥ 0, ≤ 10¹⁵; 6 decimals | Required |
| Annual costs paid in US dollars (`annual_usd_costs`) | `company_input` | `usd_per_year` | ≥ 0, ≤ 10¹⁵; 6 decimals | Required |
| Revenue hedge ratio (`revenue_hedge_ratio`) | `assumption` | `percent` | 0–100; 2 decimals | 0 |
| Cost hedge ratio (`cost_hedge_ratio`) | `assumption` | `percent` | 0–100; 2 decimals | 0 |
| Hedge cover (`hedge_months`) | `assumption` | `months` | 0–36 | 0 |
| Horizon (`horizon_months`) | `setting` | `months` | 1–36 | 12 |
| Changes start in month (`shock_start_month`) | `setting` | `months` | 1–36, within the horizon | 1 |
| Changes last for (months) (`shock_duration_months`) | `setting` | `months` | 0–36 (0: to the end of the horizon) | 0 |

The baseline exchange rate is typed, or taken from the latest stored value of the World
Bank series `wb-ind-pa-nus-fcrf` (INR per USD, an annual average), which can be used only
when the reporting currency is INR
([stored observations](numbers-and-units.md#stored-observations)). The US-dollar amounts
are in dollars (0 if none) and are part of the annual figures: US-dollar revenue is part of
annual revenue, and costs another model in the same scenario already converts (jet fuel in
the airline model) must be left out of the US-dollar costs (A6). Every assumption's default
is neutral (no hedges unless entered), and each has a written rationale. None is an
estimate (L4).

## Equations

Months are m = 1 … H. Symbols: U_R and U_C annual revenue and costs in US dollars, X₀
baseline exchange rate, R annual revenue, O annual operating costs, x exchange-rate change
(a fraction), S the month the change takes effect, E the last month it lasts, h_R and h_C
the revenue and cost hedge ratios, M_h hedge months.

| | Equation | Scope | Rests on | Limits |
|---|---|---|---|---|
| E1 | R\$ = U_R × X₀: baseline US-dollar revenue in the reporting currency (an explicit conversion at the baseline exchange rate, an input, never assumed) | annual | A2 | — |
| E2 | C\$ = U_C × X₀: baseline US-dollar costs in the reporting currency | annual | A2, A6 | — |
| E3 | s_R = R\$ / R; s_C = C\$ / O: shares of revenue and costs in US dollars; neither may exceed 1 | annual | — | — |
| E4 | r₀ = R\$ / 12; c₀ = C\$ / 12: monthly baselines | annual | A2 | L6 |
| E5 | q(m) = exp(ln(1 + x) · 𝟙[S ≤ m ≤ E]): exchange rate relative to baseline, propagated by the transmission engine from the change to USD/INR | monthly | A4 | — |
| E6 | h_R(m) = h_R if m ≤ M_h, otherwise 0; h_C(m) likewise: hedged shares | monthly | A5 | — |
| E7 | Δr(m) = r₀ × (1 − h_R(m)) × (q(m) − 1): change in revenue | monthly | A1, A3, A5 | — |
| E8 | Δc(m) = c₀ × (1 − h_C(m)) × (q(m) − 1): change in costs | monthly | A1, A3, A5, A6 | — |
| E9 | Δπ(m) = Δr(m) − Δc(m): change in operating profit | monthly | — | L5 |
| E10 | ΣΔr = Σₘ Δr(m); ΣΔc = Σₘ Δc(m); ΣΔπ = Σₘ Δπ(m), m = 1…H: totals over the horizon | horizon | — | — |
| E11 | Π₀ = (R − O) × H / 12; Π₁ = Π₀ + ΣΔπ: operating profit over the horizon | horizon | A1, A2 | — |
| E12 | μ₀ = (R − O) / R; μ₁ = (R·H/12 + ΣΔr − O·H/12 − ΣΔc) / (R·H/12 + ΣΔr): operating margins | horizon | — | — |
| E13 | G_R = Σₘ r₀ (q(m) − 1); revenue hedging effect = ΣΔr − G_R; G_C = Σₘ c₀ (q(m) − 1); cost hedging effect = ΣΔc − G_C: hedging effects | horizon | A5 | — |
| E14 | N = U_R − U_C; ΔΠ* = N × X₀ × x: net exposure and the run rate (the annual change in operating profit while the change lasts, unhedged) | steady state | A3 | — |

**The timing.** The change enters the engine as a log-change, ln(1 + x), on USD/INR. The
engine applies it at that node from month S to month E and carries it along no
relationship, so q(m) = 1 + x while the change lasts and 1 before and after it. S is
`shock_start_month`; E is S + D − 1 for a duration D (`shock_duration_months`) of at least
one month, and the horizon's last month when D = 0. The run rate (E14) is the effect while
the change lasts, whatever its duration.

**The bridge.** The operating-profit change splits exactly into four outputs of the run:

  ΣΔπ = G_R + (revenue hedging effect) − G_C − (cost hedging effect)

that is, the revenue change without hedges, what the revenue hedges changed, the cost
change without hedges and what the cost hedges changed. The engine checks the identity
before storing a run (the residual must be below 10⁻¹²); a run whose bridge does not close
fails instead of being stored.

## Outputs

Every output is rounded half to even to 10 decimal places
([numbers](numbers-and-units.md)): `derived` from the inputs alone, or `simulated` under
the scenario. A run labels the currency units with the reporting currency (INR per year,
for example). Outputs marked *yes* are attributed to the scenario's changes by Shapley
values ([contributions](provenance.md#contributions-shapley-values)).

| Output | Unit | Kind | Equation | Attributed |
|---|---|---|---|---|
| Baseline US-dollar revenue (`baseline_usd_revenue`) | `currency_per_year` | derived | E1 | — |
| Baseline US-dollar costs (`baseline_usd_costs`) | `currency_per_year` | derived | E2 | — |
| Share of revenue in US dollars (`usd_revenue_share`) | `ratio` | derived | E3 | — |
| Share of costs in US dollars (`usd_cost_share`) | `ratio` | derived | E3 | — |
| Net US-dollar exposure (`net_usd_exposure`) | `usd_per_year` | derived | E14 | — |
| Baseline operating profit (horizon) (`baseline_operating_profit`) | `currency` | derived | E11 | — |
| Baseline operating margin (`baseline_operating_margin`) | `ratio` | derived | E12 | — |
| Change in revenue (horizon) (`revenue_change`) | `currency` | simulated | E10 | yes |
| Change in US-dollar costs (horizon) (`cost_change`) | `currency` | simulated | E10 | yes |
| Change in operating profit (horizon) (`operating_profit_change`) | `currency` | simulated | E10 | yes |
| Change in revenue without hedges (horizon) (`gross_revenue_change`) | `currency` | simulated | E13 | yes |
| Revenue hedging effect (horizon) (`revenue_hedging_effect`) | `currency` | simulated | E13 | yes |
| Change in US-dollar costs without hedges (horizon) (`gross_cost_change`) | `currency` | simulated | E13 | yes |
| Cost hedging effect (horizon) (`cost_hedging_effect`) | `currency` | simulated | E13 | yes |
| Scenario operating profit (horizon) (`scenario_operating_profit`) | `currency` | simulated | E11 | — |
| Scenario operating margin (`scenario_operating_margin`) | `ratio` | simulated | E12 | — |
| Change in operating margin (`operating_margin_change`) | `ratio_points` | simulated | E12 | yes |
| Run-rate annual operating-profit change (`run_rate_operating_profit_change`) | `currency_per_year` | simulated | E14 | yes |

The monthly series:

| Series | Unit | Kind | Equation |
|---|---|---|---|
| Exchange rate relative to baseline (`fx_relative`) | `price_relative` | simulated | E5 |
| Change in revenue (`revenue_change`) | `currency_per_month` | simulated | E7 |
| Change in US-dollar costs (`cost_change`) | `currency_per_month` | simulated | E8 |
| Change in operating profit (`operating_profit_change`) | `currency_per_month` | simulated | E9 |

## Graph relationships

The model declares **no transmission rule**. The exchange-rate change acts directly on
USD/INR, so a run needs no built graph unless a company is chosen
([graph integration](graph-integration.md)). The model cites two supporting relationships,
which are never followed:

| Rule | Relationship | Role |
|---|---|---|
| S1 | USD/INR → *affects revenue of* → the chosen company | The exchange rate affects the company's revenue (E1, E7) |
| S2 | USD/INR → *affects costs of* → the chosen company | The exchange rate affects the company's costs (E2, E8) |

Neither is required: a company the graph does not link to USD/INR can still be simulated,
and the result then rests on the entered figures alone.

## Assumptions

- **A1** Everything the model does not include stays at its baseline: the US-dollar amounts, volumes, prices in every currency, other costs and financing.
- **A2** US-dollar revenue and costs accrue evenly through the year: each month carries one twelfth.
- **A3** Dollar amounts are converted at the month's exchange rate. Dollar prices, volumes and demand do not respond to the exchange rate.
- **A4** Scenario changes are step changes: they take effect in the start month and last for the stated duration (to the end of the horizon unless one is set), after which the changed variables return to their baselines. Every change in a run shares this timing.
- **A5** Hedges fix the baseline exchange rate for the hedged share during the first months of cover, then expire; they are not rolled over. Revenue and cost hedges are separate.
- **A6** Only amounts invoiced or paid in US dollars are exposed. Costs another model in the same scenario already converts must be left out of the US-dollar costs.

## Limitations

- **L1** The model shows the arithmetic consequence of the inputs and assumptions. It is not a forecast of what will happen, and not investment advice.
- **L2** Transaction exposure only: revaluing dollar debt or other balance-sheet items (translation exposure) and the effect on competitiveness or demand (economic exposure) are not modelled.
- **L3** One foreign currency, the US dollar.
- **L4** The hedge ratios and cover are the user's figures or neutral defaults. None is estimated in RUMIN.
- **L5** Operating profit only: no interest, tax, hedge accounting, working capital or cash-flow timing.
- **L6** Monthly steps: timing within a month is ignored, and seasonality is not modelled.

## Validation rules

| Rule | Severity | What it checks |
|---|---|---|
| `input_range` | error | Every number is within its range and has at most the allowed decimal places; required inputs are present |
| `percent_change_limits` | error | Scenario changes are greater than −100 % and at most +1,000 %, with at most 4 decimals — the limits Phase 1 publishes for scenario inputs |
| `not_usd_reporter` | error | A company that reports in US dollars has no US-dollar exposure in this model |
| `observation_matches` | error | A stored observation may supply the exchange rate only when its currency pair and unit match the reporting currency |
| `usd_revenue_within_revenue` | error | US-dollar revenue, converted, cannot exceed annual revenue |
| `usd_costs_within_costs` | error | US-dollar costs, converted, cannot exceed annual operating costs |
| `has_exposure` | error | At least one of US-dollar revenue and US-dollar costs must be above zero |
| `start_within_horizon` | error | The changes must take effect within the horizon |
| `timing_within_horizon` | warning | Hedges that have no effect or outlast the horizon are flagged |
| `no_shock` | warning | A run in which every scenario change is zero is flagged: it equals the baseline |

The change limits are the change's own range, so a change outside them is reported as
`input_range`. A chosen company must be a company node of the latest graph build; the
engine refuses one that is not, or any company while no graph is built, with the code
`entity_is_airline`, which it uses for this check in every model. The engine adds notes to
a run: a stored historical baseline (`historical_baseline`, with its period and caveat), a
fictional company (`fictional_entity`) and a graph older than its sources (`graph_stale`).

## Headline outputs and sensitivity defaults

A summary of a run shows first the change in revenue (`revenue_change`), the change in
US-dollar costs (`cost_change`), the change in operating profit
(`operating_profit_change`) and the change in operating margin (`operating_margin_change`).

A [sensitivity analysis](sensitivity.md) with an empty request varies these inputs by
their default variation and ranks them by the change in operating profit
(`operating_profit_change`):

| Input | Default variation |
|---|---|
| `fx_change` | ±5 points |
| `fx_rate` | ±5 % |
| `annual_usd_revenue` | ±10 % |
| `annual_usd_costs` | ±10 % |
| `revenue_hedge_ratio` | ±25 points |
| `cost_hedge_ratio` | ±25 points |

A point outside an input's range (a hedge ratio below 0 %) is skipped and listed, never
clipped.

## In the Scenario Lab

The model's scenario profile (`backend/app/scenario_lab/profiles.py`;
[how profiles work](registry.md#scenario-lab-profiles)):

| | |
|---|---|
| Responds to | USD/INR, as a percent change → `fx_change` |
| Lines | Revenue: item `usd_revenue` (revenue invoiced in US dollars) from `revenue_change`. Operating costs: item `usd_costs` (costs paid in US dollars, other than those another model covers) from `cost_change` |
| Applies by default | when a company is chosen and the graph states that USD/INR *affects costs of* or *affects revenue of* the company or its industry |
| Without that statement | available: it can be included by hand, and the result rests on the entered figures (`exposure_required` is false) |
| Cautions | With the airline model: leave jet fuel out of the US-dollar costs, since the airline model already converts the fuel bill at the new exchange rate. With the crude- or gas-linked model: if some of those inputs are paid in US dollars, the combined result leaves out the small cross effect (commodity change × currency change) |
| Templates | *Rupee depreciation*, *Oil, rupee and rates together* |

The company, its reporting currency, revenue and operating costs, the exchange rate, the
horizon and the timing come from the scenario, shared with every model; the US-dollar
amounts and the hedge assumptions are this model's own. In the Lab's reference case
(`backend/tests/scenario_support.py`), 500,000 USD of revenue and 200,000 USD of costs a
year at 80, with USD/INR +5 % (a weaker rupee) for 12 months, give revenue +2,000,000 INR
and costs +800,000 INR.

## Worked example (checked by hand)

The tests' example (`backend/tests/test_simulation_models.py`). Every company figure is
**hypothetical**: round numbers chosen so the results can be checked on paper, not market
data or any company's figures.

**Inputs.** Reporting currency INR; revenue 500,000,000 INR and operating costs
400,000,000 INR a year; 80 INR per USD; 2,000,000 USD of revenue and 500,000 USD of costs a
year in US dollars; the dollar +5 % from month 1 to the end of the horizon; half the
US-dollar revenue hedged for six months, costs unhedged; 12 months.

| Step | By hand | The engine |
|---|---|---|
| E1–E2 | 2,000,000 USD × 80 = 160,000,000 INR a year; 500,000 USD × 80 = 40,000,000 INR | 160,000,000; 40,000,000 |
| E3 | 160,000,000 / 500,000,000 = 0.32; 40,000,000 / 400,000,000 = 0.1 | 0.32; 0.1 |
| E4 | r₀ = 160,000,000 / 12 = 13,333,333.33; c₀ = 40,000,000 / 12 = 3,333,333.33 a month | recorded as steps |
| E5 | q = 1.05 in every month | 1.05 |
| E7, months 1–6 | 13,333,333.33 × (1 − 0.5) × 0.05 = 333,333.33 | 333,333.3333333333 |
| E7, months 7–12 | 13,333,333.33 × 0.05 = 666,666.67 | 666,666.6666666667 |
| E8 | 3,333,333.33 × 0.05 = 166,666.67 in every month | 166,666.6666666667 |
| E10 | ΣΔr = 6 × 333,333.33 + 6 × 666,666.67 = 6,000,000; ΣΔc = 12 × 166,666.67 = 2,000,000; ΣΔπ = 4,000,000 | same |
| E11 | Π₀ = 100,000,000; Π₁ = 104,000,000 | same |
| E12 | μ₀ = 100 / 500 = 20 %; μ₁ = 104 / 506 = 20.55 %; change +0.55 percentage points | 0.2; 0.2055335968; 0.0055335968 |
| E13 | G_R = 12 × 666,666.67 = 8,000,000; revenue hedging effect = 6,000,000 − 8,000,000 = −2,000,000; G_C = 2,000,000; cost hedging effect 0 | same |
| E14 | N = 2,000,000 − 500,000 = 1,500,000 USD a year; ΔΠ* = 1,500,000 × 80 × 0.05 = 6,000,000 a year | same |
| Bridge | 8,000,000 − 2,000,000 − 2,000,000 − 0 = 4,000,000 | closes |

These numbers are asserted by `test_currency_exposure_matches_the_hand_calculation`,
together with invariants: with no hedges, the dollar −5 % gives revenue −8,000,000 and
operating profit −6,000,000; a company with 1,000,000 USD of costs and no dollar revenue
loses 8,000,000 when the dollar rises 10 %; a change that lasts three months moves
operating profit by 500,000 in each of months 1–3 (1,500,000 USD × 80 ÷ 12 × 5 %) and not
at all afterwards; and a USD reporting currency, no dollar amounts, dollar revenue or costs
above the company's totals and a start after the horizon are each refused.
