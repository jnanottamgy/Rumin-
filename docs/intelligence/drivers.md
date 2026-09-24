# Drivers

*What drives a simulated result, and what does it rest on?* Everything on this page is read
from stored results and never recomputed: completed Scenario Lab executions (Phase 5) and
their Phase 4 model runs. The code is in `backend/app/intelligence/drivers.py`, and the
dossier's Drivers tab and `GET /intelligence/entities/{key}/drivers` show it.

## Contributions

Each model run stores **Shapley contributions**, the credit of each change to each output.
The Lab combines them into each line's `by_change` credits, which add up to the line's change
within 10⁻⁹. For each line of the latest completed execution for the entity (revenue,
operating costs, operating profit, interest expense, profit before tax, as far as the
included models reach), each change's contribution is shown three ways:

| Form | Calculation |
|---|---|
| **Amount** | the stored contribution, in the line's currency |
| **Share of the change** | contribution ÷ the line's change × 100 |
| **Points of the baseline** | contribution ÷ the line's baseline × 100 |

The sum is checked against the line's change, and the difference is reported as
**unattributed** (`residual`), never hidden. **Ratios** (operating margin, interest
coverage) are shown with their baseline and scenario values but are **not attributed**:
a ratio's change has no additive split, and the result says so. **Shapley credits** split
an interaction between two changes evenly between them, and every contribution finding says
this.

The reference execution (hypothetical figures, "oil, rupee and rates" on the fictional
Aerisca Airways):

| Line | Baseline (INR) | Change | Brent +20 % | USD/INR +5 % | Repo +0.5 pp | Unattributed |
|---|---|---|---|---|---|---|
| Revenue | 300,000,000 | +6,925,000 | +3,587,500 (51.81 %) | +3,337,500 (48.19 %) | | 0 |
| Operating costs | 250,000,000 | +13,250,000 | +9,225,000 (69.62 %) | +4,025,000 (30.38 %) | | 0 |
| Operating profit | 50,000,000 | −6,325,000 | −5,637,500 (89.13 %) | −687,500 (10.87 %) | | 0 |
| Interest expense | 12,000,000 | +375,000 | | | +375,000 (100 %) | 0 |
| Profit before tax | 38,000,000 | **−6,700,000** | −5,637,500 (84.14 %) | −687,500 (10.26 %) | −375,000 (5.60 %) | 0 |

The **headline line** of an execution is the first of profit before tax, operating profit,
operating costs and revenue that it reports. S01 states it, and S03 and the scenario
sensitivity signal are measured on it.

## Effects per unit

The **effect per unit** of a change is its contribution to the headline divided by the
change's size: per 1 % for prices and exchange rates, per percentage point for rates. For
the reference execution, profit before tax moves by −281,875 INR per 1 % of Brent,
−137,500 INR per 1 % of USD/INR and −750,000 INR per percentage point of the repo rate
(S03).

This is an **average over the scenario's change, not a slope**. The models are not linear
(hedges, lags, compounding), so doubling a change does not double its effect, and the
per-unit effect of a +20 % change is not that of a +5 % change. Every S03 finding says so.

## Stored sensitivity

When a one-at-a-time sensitivity analysis is stored for the latest execution (Phase 5), the
drivers include the ranking of the most recent one. For each quantity varied, the spread is
the difference between the highest and lowest value of the analysis's metric (the line or
ratio it was run on) over the points evaluated, base value included. **S04** reports the
quantity with the largest spread.
When none is stored, S01 and C01 suggest running one (`run_sensitivity`), and nothing is
estimated in its place.

## What a simulated result rests on

Every simulated finding carries what the execution rests on:

- **The figures the user entered** (baseline prices, annual revenue and costs, debt, dollar
  revenue and costs, …), as an *assumption* step of the chain. Identity inputs such as the
  entity and the reporting currency are left out.
- **The runs' stated assumptions** (for example hedge ratios, pass-through, lags), up to 12
  per finding, then *"… and N more stated with the model runs"*. The reference execution
  states 32.
- **The models**, with versions, run ids and definition hashes, so each run can be opened and
  verified on its own (Phase 4).
- **What is not modelled**: lines no included model reaches, such as cash flow.
- **Unstated exposures**: a model included although the graph states no exposure of the
  company to its variable. In the reference execution, floating-rate interest runs for the
  RBI repo rate, which the graph does not state as an exposure of Aerisca Airways: *"the
  result rests on your figures alone."* C01 repeats this for the whole dossier.

Each is labelled **simulated under the scenario's changes, figures and assumptions: not a
forecast.**

## Comparing executions

When the company has an earlier completed execution of the same scenario, the dossier
reads its drivers too. **S05** reports how the headline moved between the two
([changes](changes.md#execution-changes)).
