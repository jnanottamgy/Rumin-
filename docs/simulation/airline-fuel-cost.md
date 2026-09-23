# The airline fuel-cost model (`airline_fuel_cost` 1.0.0, preview)

What a change in crude oil, the jet fuel price and the exchange rate does to one airline's
fuel bill and operating profit, month by month, with hedging and a lagged pass-through to
fares. Everything else stays at its baseline.

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
attributed exactly.
