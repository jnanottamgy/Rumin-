# The airline fuel-cost model (`airline_fuel_cost` 1.0.0 and 1.1.0, preview)

What a change in crude oil, the jet fuel price and the exchange rate does to one airline's
fuel bill and operating profit, month by month, with hedging and a lagged pass-through to
fares. Everything else stays at its baseline.

Two versions are registered, both `preview`:

| Version | What it is | When it runs |
|---|---|---|
| 1.0.0 | Every change is a permanent step from month 1. Registered unchanged: its definition hash is pinned, and its runs can still be verified | When a request names it (`model_version`) |
| 1.1.0 | 1.0.0 plus the timing of the changes (a start month and a duration) and a monthly exchange-rate factor | By default: it is the latest runnable version, and the version the Scenario Lab runs |

The sections below describe 1.0.0; [version 1.1.0](#version-110) lists everything 1.1.0
changes, and whatever it does not list is the same in both versions. Phase 5 also added
four models that the Scenario Lab can run beside this one
([the registry](registry.md#registered-models)).

## Why this domain

The brief asked for one narrow domain, chosen for data availability, financial relevance,
mathematical clarity, validation potential and extensibility. Five candidates were
compared ([plan, section 2](../phases/phase-4-plan.md#2-the-domain-an-airline-fuel-cost-shock)).
The airline fuel-cost shock won on every criterion that RUMIN could already support:

| Criterion | Why the airline model |
|---|---|
| Data available | The knowledge graph states the channel (Brent crude → *influences* → jet fuel → *affects costs of* → air transport) and the currency channel; the variables have defined units; the World Bank official exchange rate (INR per USD) can supply the baseline exchange rate |
| Financial relevance | Fuel is one of an airline's largest and most volatile costs, priced in US dollars, so a weaker rupee raises it too |
| Mathematical clarity | An accounting identity (volume × price × exchange rate) with three clearly separated mechanisms: hedging, a lagged fare pass-through and a crude-to-jet-fuel elasticity |
| Validation potential | Exact invariants: no change → no effect; fully hedged → no price effect while the hedges last; full pass-through → no steady-state profit effect; the bridge closes; contributions add up. Round inputs give results checkable by hand (below) |
| Extensibility | The same structure fits other cost shocks (refiners and crude oil, logistics and diesel) as new models in the same registry |

It exercises every requirement of the engine: unit conversions (litres, US gallons, US
barrels), currencies, frequency (annual figures on a monthly grid), time lags, and a
multi-step propagation through a validated graph relationship. RUMIN holds **no company
financial figures**, so the airline's figures always come from the user.

## Inputs

Each input is labelled with the kind of knowledge it is. Ranges are enforced; a value
outside them is refused, never clipped.

| Input | Kind of knowledge | Unit | Allowed | Default |
|---|---|---|---|---|
| Crude oil price change (`crude_oil_change`) | Scenario change (on Brent crude) | % change | > −100, ≤ 1,000; 4 decimals | 0 |
| Additional jet fuel price change (`jet_fuel_margin_change`) | Scenario change (on jet fuel, beyond crude) | % change | > −100, ≤ 1,000; 4 decimals | 0 |
| Exchange-rate change (`usd_change`) | Scenario change (on the reporting currency's price of a dollar) | % change | > −100, ≤ 1,000; 4 decimals | 0 |
| Baseline jet fuel price (`jet_fuel_price`) | Your figure (a market baseline you rely on) | USD per US gallon, US barrel or kilolitre | > 0, ≤ 100,000; 6 decimals | Required |
| Baseline exchange rate (`fx_rate`) | Your figure, or historical data (the stored World Bank annual average) | reporting currency per USD | > 0, ≤ 100,000; 6 decimals (a stored value keeps its published precision) | Required |
| Airline in the knowledge graph (`entity`) | Your choice | graph node | a company in air transport | None |
| Reporting currency | Your figure | ISO 4217 code | three capital letters | Required |
| Annual revenue, annual operating costs | Your figures | reporting currency per year | > 0, ≤ 10¹⁵; 6 decimals | Required |
| Annual fuel consumption | Your figure | kilolitres, US gallons or US barrels a year | > 0, ≤ 10¹²; 6 decimals | Required |
| Crude-to-jet-fuel elasticity β (`crude_pass_through`) | Assumption | dimensionless | 0–3; 4 decimals | 1 |
| Crude-to-jet-fuel lag | Assumption | months | 0–12 | 0 |
| Hedge ratio | Assumption | % | 0–100; 4 decimals | 0 |
| Hedge cover | Assumption | months | 0–36 | 0 |
| Fare pass-through | Assumption | % | 0–100; 4 decimals | 0 |
| Fare pass-through lag | Assumption | months | 0–12 | 0 |
| Horizon | Setting | months | 1–36 | 12 |

Every assumption's default is neutral (β = 1 keeps the refining margin proportional; no lag,
no hedging, no pass-through unless entered), and each has a written rationale shown beside
it. None is an estimate.

## Equations

Months are m = 1 … H. Symbols: Q annual consumption, λ(u) litres per unit u, P₀ baseline
jet fuel price, X₀ baseline exchange rate, R annual revenue, O annual operating costs,
c crude change, s additional jet fuel change, x exchange-rate change (fractions),
β elasticity, L crude lag, h hedge ratio, M_h hedge months, φ fare pass-through, L_f fare
lag.

| | Equation | Scope | Rests on | Limits |
|---|---|---|---|---|
| E1 | V = Q × λ(u_Q) / λ(u_P): consumption in the price's volume unit (exact factors, e.g. barrel → gallon = 42) | annual | — | — |
| E2 | B_USD = V × P₀: baseline benchmark fuel cost in US dollars | annual | A3 | L4 |
| E3 | B = B_USD × X₀: in the reporting currency (an explicit conversion at an entered or stored rate) | annual | A8 | — |
| E4 | f = B / O: fuel share of operating costs; must not exceed 1 | annual | — | — |
| E5 | b₀ = B / 12: monthly baseline fuel cost | annual | A2 | L6 |
| E6 | ℓ(m) = β · ln(1 + c) · 𝟙[m > L] + ln(1 + s): jet fuel log-change, propagated along rule T1 | monthly | A4, A5 | L5 |
| E7 | r(m) = exp(ℓ(m)): jet fuel price relative to baseline | monthly | — | — |
| E8 | q = 1 + x: exchange rate relative to baseline | monthly | A4, A8 | — |
| E9 | h(m) = h if m ≤ M_h, otherwise 0: hedged share | monthly | A6 | — |
| E10 | b₁(m) = b₀ × q × [h(m) + (1 − h(m)) × r(m)]: scenario monthly fuel cost | monthly | A1, A3, A6, A8 | — |
| E11 | Δb(m) = b₁(m) − b₀: change in fuel cost | monthly | — | — |
| E12 | Δr(m) = φ × Δb(m − L_f) if m > L_f, otherwise 0: fare recovery | monthly | A7 | L2, L3 |
| E13 | Δπ(m) = Δr(m) − Δb(m): change in operating profit | monthly | A1 | L7 |
| E14 | ΣΔb, ΣΔr, ΣΔπ: totals over the horizon | horizon | — | — |
| E15 | Π₀ = (R − O) × H / 12; Π₁ = Π₀ + ΣΔπ: operating profit over the horizon | horizon | A1, A2 | — |
| E16 | μ₀ = (R − O) / R; μ₁ = (R·H/12 + ΣΔr − O·H/12 − ΣΔb) / (R·H/12 + ΣΔr): operating margins | horizon | — | — |
| E17 | ΔB* = B × [q × exp(β·ln(1 + c) + ln(1 + s)) − 1]; ΔΠ* = (φ − 1) × ΔB*: steady-state annual effect (lags passed, hedges expired) | steady state | A4, A5, A7 | — |
| E18 | g = ΣΔb / (R × H / 12): the uniform revenue change that would offset the fuel-cost change (arithmetic, not a recommendation) | horizon | — | L2 |
| E19 | G = Σₘ b₀ × (q × r(m) − 1); hedging effect = ΣΔb − G | horizon | A6 | — |

**Why log-changes.** A crude change travels to jet fuel as ℓ = β·ln(1 + c): with β = 1, a
10 % rise in crude is a 10 % rise in jet fuel (the refining margin stays proportional), and
successive changes compound correctly (ln(1.1) + ln(1.1) = ln(1.21)). The transmission
engine adds log-changes along paths, which is exact for multiplicative effects.

**The bridge.** The operating-profit change splits exactly into three outputs of the run:

  ΣΔπ = −G − (hedging effect) + ΣΔr

that is, the fuel-cost change without hedges, what the hedges changed, and fare recovery.
The engine checks the identity before storing a run (the residual must be below 10⁻¹²);
a run whose bridge does not close fails instead of being stored.

## Assumptions

- **A1** Everything the model does not include stays at its baseline: fuel consumption, other costs, traffic, capacity, fares (apart from the stated pass-through) and financing.
- **A2** Fuel is consumed evenly through the year: each month uses one twelfth of the annual volume, and annual revenue and costs accrue evenly.
- **A3** The fuel bill is consumption × the benchmark jet fuel price × the exchange rate. Taxes, fees and supplier margins that do not follow the benchmark are outside the model.
- **A4** Scenario changes are permanent step changes that start in month 1 and last for the whole horizon.
- **A5** Jet fuel responds to crude oil with a constant elasticity β after a lag: ln(jet fuel) changes by β × ln(1 + crude change). With β = 1 the refining margin stays a constant proportion of the price.
- **A6** Hedged fuel pays the baseline US-dollar price until the hedges expire; the exchange rate is not hedged; hedges are not rolled over.
- **A7** Fares recover a fixed share of the change in fuel cost after a lag, for rises and falls alike, and passenger demand does not respond.
- **A8** The exchange rate affects the fuel bill only: other dollar costs and any dollar revenue are outside the model.

## Limitations

- **L1** The model shows the arithmetic consequence of the inputs and assumptions. It is not a forecast of what will happen, and not investment advice.
- **L2** Passenger demand, capacity and schedules do not respond to fares or costs.
- **L3** Competitors' responses and market share are not modelled.
- **L4** Only the benchmark-linked fuel cost is modelled. Ad-valorem taxes that scale with the price are not captured, so a real fuel bill can move more than the benchmark.
- **L5** The elasticity, lags, hedge terms and pass-through are assumptions with stated defaults. None has been estimated from data in RUMIN.
- **L6** Monthly steps: timing within a month is ignored, and seasonality is not modelled.
- **L7** Operating profit only: no interest, tax, hedge accounting, working capital or cash-flow timing.

## Validation rules

| Rule | Severity | What it checks |
|---|---|---|
| `input_range` | error | Every number is within its range and has at most the allowed decimal places; required inputs are present |
| `percent_change_limits` | error | Scenario changes are > −100 % and ≤ +1,000 %, with at most 4 decimals — the limits Phase 1 publishes for scenario inputs |
| `unit_choice` | error | Quantities use one of the listed units; no other unit is converted |
| `usd_rate_is_one` | error | A USD reporting currency needs an exchange rate of exactly 1 |
| `observation_matches` | error | A stored observation may supply the exchange rate only when its currency pair and unit match the reporting currency |
| `fuel_share_exceeds_costs` | error | The benchmark fuel cost of the stated consumption cannot exceed operating costs |
| `fuel_share_low` | warning | A fuel cost below 1 % of operating costs usually means a wrong unit |
| `channel_confirmed` | error | A crude oil change reaches jet fuel only if the knowledge graph states that Brent crude influences jet fuel |
| `entity_is_airline` | error | A chosen entity must be a company that operates in air transport in the graph |
| `timing_within_horizon` | warning | Hedges, lags and fare responses that fall outside the horizon are flagged |
| `no_shock` | warning | A run where every change is zero equals the baseline |

The engine adds further notes to a run: a relationship recorded as a model assumption
(`assumption_based_channel`), a stored historical baseline (`historical_baseline`, with its
period and caveat), a fictional company (`fictional_entity`) and a graph older than its
sources (`graph_stale`).

## Worked example (checked by hand)

The Simulation page's example. Every figure is **hypothetical**: round numbers chosen so
the results can be checked on paper, not market data or any airline's figures.

**Inputs.** Crude oil +10 %; jet fuel 750 USD per kilolitre; 80 INR per USD; revenue
300,000,000 INR and operating costs 250,000,000 INR a year; 1,000 kL of fuel a year; half
the fuel hedged for three months; 40 % of fuel-cost changes passed on to fares after two
months; β = 1 and no crude lag (defaults); 12 months.

| Step | By hand | The engine |
|---|---|---|
| E1–E3 | 1,000 kL × 750 USD = 750,000 USD × 80 = 60,000,000 INR a year | 750,000; 60,000,000 |
| E4 | 60,000,000 / 250,000,000 = 0.24 | 0.24 |
| E5 | 60,000,000 / 12 = 5,000,000 INR a month | 5,000,000 |
| E6–E7 | ℓ = ln 1.1, r = 1.1 from month 1 | r = 1.1 |
| E10–E11, months 1–3 | 5,000,000 × (0.5 + 0.5 × 1.1) − 5,000,000 = 250,000 | 250,000 |
| E10–E11, months 4–12 | 5,000,000 × 1.1 − 5,000,000 = 500,000 | 500,000 |
| E12 | months 3–5: 0.4 × 250,000 = 100,000; months 6–12: 0.4 × 500,000 = 200,000 | same |
| E14 | ΣΔb = 3 × 250,000 + 9 × 500,000 = 5,250,000; ΣΔr = 3 × 100,000 + 7 × 200,000 = 1,700,000; ΣΔπ = −3,550,000 | same |
| E15 | Π₀ = 50,000,000; Π₁ = 46,450,000 | same |
| E16 | μ₀ = 50 / 300 = 16.67 %; μ₁ = 46,450,000 / 301,700,000 = 15.40 %; change −1.27 percentage points | 0.1666666667; 0.1539608883; −0.0127057784 |
| E17 | ΔB* = 60,000,000 × 0.1 = 6,000,000 a year; ΔΠ* = (0.4 − 1) × 6,000,000 = −3,600,000 a year | same |
| E18 | 5,250,000 / 300,000,000 = 1.75 % | 0.0175 |
| E19 | G = 12 × 500,000 = 6,000,000; hedging effect = 5,250,000 − 6,000,000 = −750,000 | same |
| Bridge | −6,000,000 + 750,000 + 1,700,000 = −3,550,000 | closes |

Sensitivity around this run (the model's default set) ranks crude oil first: at 0 % the
change is nil, at 20 % the operating-profit change is −7,100,000 INR (by hand: ΣΔb =
3 × 500,000 + 9 × 1,000,000 = 10,500,000; ΣΔr = 0.4 × 8,500,000 = 3,400,000).

These numbers are asserted by the tests (`backend/tests/test_simulation_model.py`,
`frontend/tests/integration/simulation.integration.test.ts`), together with invariants:
hedges do not cover the exchange rate; the crude lag delays the effect but not the steady
state; the elasticity scales the log-change (β = 0.5 gives √1.1); the margin change is
refused when revenue over the horizon would fall to zero; and three simultaneous changes are
attributed exactly. Both suites run the default version, 1.1.0, with its default timing
(from month 1 to the end of the horizon);
`test_version_1_1_0_gives_1_0_0_s_results_when_changes_are_permanent`
(`backend/tests/test_simulation_timing.py`) runs the same inputs on 1.0.0 and checks that
the outputs are identical.

## Version 1.1.0

**What changed, and why.** A Scenario Lab scenario gives every model one timing: the month
its changes take effect and how long they last. Version 1.0.0 cannot take it: its changes
are permanent steps from month 1 (A4), and its exchange rate is one factor, q = 1 + x, for
the whole horizon (E8). A released version never changes ([versions](registry.md#versions)),
so the timing is a new version. In 1.1.0 every change, the exchange rate included, is
carried by the transmission engine inside the run's window, so the exchange rate becomes a
monthly factor q(m) that returns to 1 when the changes end. Everything else (the other
equations, the defaults, the ranges, the output ids) is 1.0.0's:
`backend/app/simulation/models/airline_fuel_cost_1_1.py` builds 1.1.0 from 1.0.0's
definition and replaces only what this section lists.

**1.0.0 stays registered unchanged**, with its own code, so its runs remain verifiable:
`POST /api/v1/simulations/{id}/verify` re-executes a stored run with the version it names,
and a test pins the definition hash of both versions (`RELEASED` in
`backend/tests/test_simulation_model.py`). A request without `model_version` runs 1.1.0;
one that names 1.0.0 runs 1.0.0. `ENGINE_VERSION` is unchanged (1.0.0).

**New inputs.** Two settings, shared by every model the Scenario Lab runs:

| Input | Kind of knowledge | Unit | Allowed | Default |
|---|---|---|---|---|
| Changes start in month (`shock_start_month`) | Setting | months | 1–36, within the horizon | 1 |
| Changes last for (months) (`shock_duration_months`) | Setting | months | 0–36; 0 means to the end of the horizon | 0 |

The definition names them as its timing inputs (`shock_start_input`,
`shock_duration_input`). The descriptions of the three changes (`crude_oil_change`,
`jet_fuel_margin_change`, `usd_change`) now say that each takes effect in the start month
and lasts for the stated duration, instead of "a permanent step change from month 1"; their
units, ranges and defaults are unchanged.

**Changed equations.** S is the month the changes take effect and E the last month they
last: S + D − 1 for a duration D of at least one month, the horizon's last month when D = 0.

| | Equation in 1.1.0 | Scope | Rests on | Limits |
|---|---|---|---|---|
| E6 | ℓ(m) = β · ln(1 + c) · 𝟙[S + L ≤ m ≤ E + L] + ln(1 + s) · 𝟙[S ≤ m ≤ E]: jet fuel log-change; each change lasts from S to E, and the crude-driven part arrives L months later and ends L months later | monthly | A4, A5 | L5 |
| E8 | q(m) = exp(ln(1 + x) · 𝟙[S ≤ m ≤ E]): exchange rate in month m relative to baseline, propagated by the transmission engine like every change | monthly | A4, A8 | — |
| E10 | b₁(m) = b₀ × q(m) × [h(m) + (1 − h(m)) × r(m)]: scenario monthly fuel cost, at the month's exchange rate | monthly | A1, A3, A6, A8 | — |
| E17 | ΔB* = B × [(1 + x) × exp(β·ln(1 + c) + ln(1 + s)) − 1]; ΔΠ* = (φ − 1) × ΔB*: run-rate annual effect, while the changes last, after every lag has passed and every hedge has expired; for changes that last the whole horizon it is the steady state | steady state | A4, A5, A7 | — |
| E19 | G = Σₘ b₀ × (q(m) × r(m) − 1); hedging effect = ΣΔb − G | horizon | A6 | — |

The bridge (ΣΔπ = −G − hedging effect + ΣΔr) is unchanged and is still checked before a
run is stored.

**Outputs.** The ids are unchanged. Three outputs are relabelled because they describe the
run rate while the changes last, not a permanent steady state: `jet_fuel_price_change` is
now *Jet fuel price change (run rate)*, `steady_state_fuel_cost_change` is *Run-rate annual
fuel-cost change* and `steady_state_operating_profit_change` is *Run-rate annual
operating-profit change*. One monthly series is added: `fx_relative`, the exchange rate
relative to baseline (`price_relative`, simulated, E8).

**Assumption A4** becomes: *Scenario changes are step changes: they take effect in the
start month and last for the stated duration (to the end of the horizon unless one is set),
after which the changed variables return to their baselines. Every change in a run shares
this timing.* The other assumptions and every limitation are unchanged.

**Validation.** One rule is added, and the timing warnings count from the start month:

| Rule | Severity | What it checks |
|---|---|---|
| `start_within_horizon` | error | The changes must take effect within the horizon |
| `timing_within_horizon` | warning | As in 1.0.0, with the fare and crude lags counted from the start month (flagged when S + L > H); hedges that end before the changes start (0 < M_h < S) are also flagged |

**Timing checked by hand** (`backend/tests/test_simulation_timing.py`). The worked
example's **hypothetical** inputs (crude oil +10 %, half the fuel hedged for three months,
40 % of the change passed on to fares after two months, a fuel bill of 5,000,000 INR a
month) with a timing:

| Timing | By hand | The engine |
|---|---|---|
| From month 1 to the end of the horizon (the defaults) | The worked example above: ΣΔb = 5,250,000, ΣΔπ = −3,550,000 | 1.0.0's outputs, exactly |
| Six months (`shock_duration_months` = 6) | Months 1–3: +250,000 (half hedged); months 4–6: +500,000; months 7–12: 0. ΣΔb = 2,250,000; fares 3 × 100,000 + 3 × 200,000 = 900,000; ΣΔπ = −1,350,000 | same |
| From month 4 (`shock_start_month` = 4) | The hedges end in month 3, before the change: 9 × 500,000 = 4,500,000; fares in months 6–12: 7 × 200,000 = 1,400,000; ΣΔπ = −3,100,000; a `timing_within_horizon` warning | same |
| The dollar +10 % for two months, no crude change, no hedges | q(m) = 1.1, 1.1, then 1: ΣΔb = 2 × 500,000 = 1,000,000; the run-rate fuel-cost change is 60,000,000 × 10 % = 6,000,000 a year | same |
| From month 2, for three months | The crude path is in effect from month 2 to month 4 (`first_month` 2, `last_month` 4, kind `log`) | same |
| From month 13 of a 12-month horizon | Refused (`start_within_horizon`) | refused |

## In the Scenario Lab

The Lab runs the latest runnable version, 1.1.0. Its scenario profile
(`backend/app/scenario_lab/profiles.py`; [how profiles work](registry.md#scenario-lab-profiles)):

| | |
|---|---|
| Responds to | Brent crude → `crude_oil_change`, jet fuel → `jet_fuel_margin_change` and USD/INR → `usd_change`, each as a percent change |
| Lines | Operating costs: item `jet_fuel` from `fuel_cost_change`. Revenue: item `fuel_cost_recovery` (fare recovery of fuel costs) from `fare_recovery` |
| Applies by default | when a company is chosen and the graph states that jet fuel *affects costs of* the company or its industry (in the sample network: air transport, the industry of Aerisca Airways and Skyvara Air) |
| Without that statement | not applicable to that company, and including it by hand blocks the plan: `exposure_required` is true, since the model itself accepts only a company in air transport (S2) |
| Cautions | With the currency model: leave jet fuel out of the US-dollar costs. With the crude-linked model: both respond to crude oil, so leave jet fuel out of the crude-linked costs |
| Templates | *Crude oil shock on an airline*, *Jet fuel price shock*, *Oil, rupee and rates together* |
