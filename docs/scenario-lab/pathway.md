# The impact pathway

The pathway shows how each change travelled to each line **as the engine computed it**. It
is assembled by `backend/app/scenario_lab/pathways.py` from each included model's declared
pathway (its definition) and its run (the transmission paths, outputs and monthly series),
joined by the Lab's own equations:

```
change ─applies→ variable ─transmission (graph edge, β, lag)→ variable
       ─equation→ line item (a model output) ─aggregation (AG1–AG7)→ line → metric
```

Only links that carried the scenario's changes are included. **A connection in the graph is
not evidence of causation, and nothing is drawn that the engine did not compute.**

## Nodes

| Kind | What it is | Value shown |
|---|---|---|
| `change` | a change of the scenario — what you set (scenario input) | its size, e.g. +20 % |
| `variable` | a knowledge-graph variable a model moved: the change as the model applied it, or a variable it reached along a relationship | its change while the scenario lasts, once every lag has elapsed |
| `driver` | a line item: a model output that feeds a line (the fuel bill, fare recovery, US-dollar revenue, repo-linked interest…) | its change over the horizon (simulated) |
| `line` | a line of the Lab's result: revenue, operating costs, operating profit, interest expense, profit before tax | its change over the horizon (simulated) |
| `metric` | operating margin, interest coverage | its change from the baseline (simulated) |
| `context` | a graph entity a model cites (an industry, the company) | none — it carries no value |

Every node that carries a value also carries its monthly series (except metrics, which are
computed over the horizon) and the first month it moves.

## Links

| Kind | `simulation` | Meaning | Drawn as |
|---|---|---|---|
| `applies` | `applied` | a change enters a model as the variable it accepts | ink line |
| `transmission` | `propagated` | the engine carried the change along a **knowledge-graph relationship** the model declares and the graph confirms, with its coefficient (β), lag and months in effect | sky-blue line; β and lag shown on the variable it reaches |
| `equation` | `computed` | a model's equations turned variables into a line item | ink line |
| `aggregation` | `aggregated` | the Lab added line items into lines (AG1–AG5) and lines into metrics (AG6–AG7); `sign` −1 where a line is subtracted | hairline, "−" where subtracted |
| `cited` | `context_only` | a relationship the graph **states** and the Lab only cites: it decided that a model applies, and no value travels along it | not drawn as a step: listed in the model's lane header ("Why it applies") and in the inspector |

Each link carries what supports it: the graph edge (relationship, evidence status —
evidence-backed, analyst-created, model assumption or unverified — source record key,
whether it is illustrative), the equations with their formulas, the parameters and
assumptions used (and whether each is a default), and the stated assumptions (A1…).

## Not modelled

The graph's other relationships from the changed variables — in the reference example,
eleven of them, such as *Brent crude oil price influences India CPI inflation* and *RBI
policy repo rate affects revenue of Anvaya Bank* — are listed **apart**, under "Stated in
the graph, not modelled", with their evidence status (all eleven are model assumptions). No included model simulates
them, so nothing is computed along them. The page never draws them into the pathway.

## How the page draws it

`frontend/src/features/scenarioLab/pathwayLayout.ts` is pure geometry (unit-tested without
rendering):

- **Four columns**: changes → variables moved → line items → lines, with the metrics under
  the lines.
- **One lane per model**, holding its variables and line items, so a model's part reads as
  one band; a lane can be collapsed to a single step (its links are re-routed to it, and the
  links inside it disappear). The lane header names the model and version and lists the
  graph context it cites.
- Changes, lines and metrics are placed as close as possible to the average height of what
  they connect to, without overlapping; lines keep their accounting order.
- Links between steps of one column (jet fuel reached from Brent; operating profit from
  revenue and costs) are drawn as arcs outside the column's right edge, nesting by distance.

Selecting a step or a link highlights its chain — everything upstream and downstream — and
opens the inspector: for a step, what it is, its value, its monthly series, and the links it
comes from and leads to (each a button, so the whole pathway can be walked from the
keyboard); for a link, its type, how it was used, the graph relationship and evidence, β,
lag, equations and assumptions. Escape closes it. A **List** view shows every link as a
table.

## The month replay

The simulated months can be replayed with the timeline's scrubber, play button or event
chips (a lag elapsing, fares starting to recover, hedges expiring, loans repricing). During a
replay every step shows its **simulated value in that month**, a step stays dim until the
month its change first reaches it, and metrics — computed over the horizon — show "Horizon
only". The replay moves only through values the backend already computed; nothing is
interpolated and nothing moves by itself.
