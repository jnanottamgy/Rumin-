# Numbers, units and currencies

## Exact decimals

Every calculation runs in one `decimal` context (`app/simulation/decimal_math.py`):

| Property | Value | Why |
|---|---|---|
| Precision | 34 significant digits (as IEEE 754 decimal128) | Far beyond any input's precision, so rounding inside a run never shows in a result |
| Rounding | Half to even | No drift in either direction over many operations |
| Traps | Invalid operation, division by zero, overflow | An impossible calculation raises (and becomes a 422 with the reason) instead of producing `NaN` or `Infinity` |
| `ln`, `exp` | Python's `Decimal.ln` and `Decimal.exp`, correctly rounded | Every machine gets the same digits, which is what makes result hashes reproducible |
| Outputs | Rounded half to even to 10 decimal places, canonical (no trailing zeros), served as plain decimal strings | The Phase 2 convention: no digit is lost to floating point |
| Magnitude limit | Every output below 10²⁰ in its own unit | Rounded to 10 places it fits the database's `NUMERIC(38, 18)`; inputs are bounded more tightly by each model |

Contributions (Shapley weights such as ⅓) are computed at 34 digits and rounded like any
output, so credits add up to the total within the output rounding (1 × 10⁻¹⁰ per credit).

## Reading numbers from a request

Values are sent as exact decimal strings (`"2.35"`) or as JSON numbers. A JSON number is
read through its shortest representation (`0.1` stays `0.1`, not
`0.1000000000000000055…`). Refused, with the field and the reason: exponents (`1e6`),
separators (`1,000,000`), symbols (`₹100`, `10%`), `NaN` and infinities, booleans, strings
longer than 128 characters, and more than 30 digits either side of the point. Each input
also has a maximum number of decimal places; a value with more is refused, never rounded.
The API never coerces a string into a number type: a number must be a JSON number, text a
JSON string.

## Units

A conversion is always an explicit, recorded step with its factor (E1), never a silent
change of unit.

| Unit | Litres | Source |
|---|---|---|
| litre | 1 | SI |
| kilolitre | 1,000 | SI |
| US gallon | 3.785411784 (exact) | 231 cubic inches, by definition |
| US barrel (petroleum) | 158.987294928 (exact) | 42 US gallons |

Factors are ratios of these exact definitions: barrel → gallon is exactly 42; kilolitre →
gallon is 264.1720523581484153… (correctly rounded to 34 digits). A price is quoted in US
dollars per one of these volumes; consumption can be entered in another, and E1 converts it
to the price's unit. Quantities of different dimensions (a volume and a price, one currency
and another) are never converted into each other.

## Currencies

- The reporting currency is an ISO 4217-style code (three capital letters). RUMIN keeps no
  copy of the ISO list, so only the format is checked.
- Jet fuel is priced in US dollars. The conversion to the reporting currency uses the
  **baseline exchange rate**, which is always an input — entered, or taken from a stored
  observation — never assumed (E3).
- A USD reporting currency needs a rate of exactly 1.
- A stored exchange rate can be used only when its currency pair matches: the World Bank
  series gives INR per USD, so it is refused for a EUR reporting currency, with the
  message that RUMIN does not convert between currencies without a rate you provide.

## Percentages

Scenario changes and assumption percentages are entered in percent (`10` means 10 %) and
converted to fractions exactly (moving the decimal point). Changes must be above −100 %
(a price cannot fall by all of itself) and at most +1,000 %, with at most four decimals —
the same limits Phase 1 publishes for scenario inputs. Ratios in results are fractions
(`0.24`); the page shows them as percentages, and a change of a ratio (the margin change)
in percentage points.

## Frequency and time

Figures are entered per year and simulated on a monthly grid: the annual fuel bill, revenue
and costs are spread evenly over twelve months (E5, E15; assumption A2). Scenario changes
are permanent steps from month 1 (A4). Lags are whole months. The horizon is 1–36 months;
effects that begin after it are listed in the transmission paths and counted in the steady
state, not in the horizon totals, and the run carries a note saying so.

## Stored observations

An input whose definition names a stored series (the baseline exchange rate names the
World Bank official exchange rate, `wb-ind-pa-nus-fcrf`) may take that series' **latest
current, reported value** instead of a typed one. The run records the series, the period,
the value exactly as published, the quality status, the revision, when RUMIN last confirmed
it, the capture and job it came from, and the dataset's licence and attribution. It is
labelled *historical data*, with a note that it is an annual average and not a current
market rate. If nothing is stored, the input must be entered: nothing is interpolated or
filled in.
