# Sensitivity analysis

First-level, one-at-a-time sensitivity around a stored run: each chosen input moves on its
own while every other input keeps the run's value, and the model is evaluated at each
point. The spread of a result shows how much it depends on that input — **not how likely
any value is**. No probabilities are estimated.

## Requesting an analysis

`POST /api/v1/simulations/{run_id}/sensitivity`

```json
{
  "metric": "operating_profit_change",
  "inputs": [
    { "input": "crude_oil_change" },
    { "input": "jet_fuel_price", "mode": "relative", "step": "10" },
    { "input": "hedge_ratio", "mode": "values", "values": ["25", "75", "100"] },
    { "input": "crude_pass_through_lag", "mode": "absolute", "step": "2" }
  ]
}
```

An empty body uses the model's defaults: the airline model varies crude oil, the exchange
rate, β, the hedge ratio, fare pass-through, the jet fuel price and consumption, ranked by
the change in operating profit.

| Mode | Points |
|---|---|
| `default` | The input's own variation from the model definition (e.g. crude oil ±10 points, β ±0.2, the jet fuel price ±10 %) |
| `absolute` | Low = run value − step, high = run value + step, in the input's unit |
| `relative` | Low = run value × (1 − step %), high = run value × (1 + step %); step below 100 %; not for whole-month inputs |
| `values` | The listed values (1–7) |

Every point is evaluated with the model's cross-field checks and the graph-channel check,
exactly as a run would be.

## What is returned

For each input: its label, category, unit, the run's value, the mode and step, and each
point with its value, **every** output at that point, the difference from the run for each
output, or the reason the point was skipped. For the chosen metric: the lowest and highest
results reached (including the run's own) and their spread. A **ranking** orders the
inputs by spread, largest first (ties by input ID). The analysis also reports the number
of evaluations and the time taken, and is stored (append-only) with a result hash over
everything except the timing.

## Honest limits

- **Skipped, not clipped.** A point outside an input's range (a hedge ratio of −20 %, a
  price of zero) is skipped and listed with the reason; it is never moved to the nearest
  allowed value. So is a point the model refuses (the fuel bill exceeding operating costs)
  or one that needs a relationship the graph does not confirm.
- **Generated points** are rounded to the input's allowed decimal places (half to even);
  typed values must already fit.
- **Limits**: at most 8 inputs, 7 points each, 60 evaluations and 10 seconds; each input at
  most once; settings (the horizon) and non-numeric inputs cannot be varied. A request over
  a limit is refused (422) with the reason; the analysis never runs part of the request.

## What it is not

It varies one input at a time, so it shows no interactions between inputs, and a low and
high point are not a confidence interval. Two inputs that enter the model the same way
show the same spread (the jet fuel price and the consumption both scale the fuel bill). A
probabilistic analysis (Monte Carlo over distributions of the inputs) is a later phase:
each run already records a `random_seed` field (`null` for deterministic runs) so that such
runs can be reproduced when they exist.

## Reading it on the page

The Simulation page draws the analysis as a **tornado**: one row per input in rank order;
a bar from the lowest to the highest result; a vertical rule at the run's own result; a
hollow circle for the result with the input lowered and a filled circle with it raised
(shape, not colour); and each row's input values and result range written out beside it.
