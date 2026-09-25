# Scenario overlays

An overlay lays one **stored, completed execution** of the Scenario Lab over the knowledge
graph: what the scenario changed, which company the models simulated, which relationships a
model carried the change along, which ones only decided which models apply, and which ones
the graph states but no included model simulates — with the execution's stored results.

It is read-only (`GET /scenario-executions/{id}`, then `/pathways` and `/results`) and it
infers nothing from the graph. A relationship in the graph is never treated as an impact.

## Opening one

- *See it in the 3D universe* on a completed execution in the Scenario Lab;
- *Scenario overlay* above the canvas: every scenario whose latest execution completed;
- a link with `?execution=<id>`.

An execution that has not completed is **not laid over**, and its pathway and results are not
requested. While it is still running (queued, validating, simulating, propagating or
aggregating), the panel says *No overlay yet*, names its status, reads it again at the
interval the server suggests (between 0.25 and 5 seconds) and offers *Check now*; the overlay
appears when it completes. A failed or cancelled execution is never read again: the panel says
it has no results to lay over, and the Scenario Lab says why. An execution that cannot be read
shows an error with *Try again*.

## What each part shows, and where it comes from

| Part | Source | On the canvas | In the panel |
|---|---|---|---|
| **Changed** variables | the execution's plan (`changes`) | *Changed in the scenario*: emphasised, named first | the stated change, as entered: *Brent crude oil price +20 %* — a **hypothetical input** |
| **Simulated entity** | the plan (`entity`) | *Simulated entity* | its name, and *Fictional company* when it is |
| A model's **variables** | the pathway's variable nodes, mapped to graph keys | *A model's variable* | — |
| **Context** records | the pathway's context nodes | *Context for the models* | — |
| **Propagated** relationships | the pathway's `transmission` links that carry a graph edge key | sky blue, solid, heavier | the rule, coefficient, lag and model (for the reference execution: *Rule T1 · coefficient 1 · lag 1 month · Airline fuel cost 1.1.0*) |
| **Cited** relationships | the pathway's `cited` links | sky blue, dashed | *decided which models apply; carries no values* |
| **Not simulated** relationships | the pathway's `unmodelled` list (graph edges around the changed variables) | the edge's own pattern, dimmed | *stated in the graph; no included model simulates it*, with the reason |
| **Results** | the stored results (`lines`) | none | each line's baseline, change and change %, in the reporting currency, over the horizon — *simulated, not observations and not a forecast* |
| **Models** | the plan's included models | none | title and version |

Everything else in the view is dimmed. Figures appear **only in the panel**, read from the
stored strings: nothing is recomputed or added up; money is shown to whole units of the
reporting currency and percentage changes to two decimal places. Values are never drawn as
sizes, heights or colours on the canvas.

## Honesty rules

- **Build mismatch.** An execution records the graph build it was planned on. When the
  universe shows a different build, the panel says so: relationships may have changed since.
- **Missing records.** When the current view does not hold some of the overlay's records
  (for example, a neighbourhood that does not reach them), the panel says how many are not in
  view and offers *Show the whole universe* when the whole build fits the budget.
- **No causality.** Propagated means *a model rule declared this relationship and carried
  the change along it*; it is not a measured effect. Cited relationships carry no values.
  *Not simulated* is not the same as *unaffected*.
- **Simulated, not forecast.** Every overlay carries the badges *Simulated* and *Not a
  forecast*, and links to the execution in the Scenario Lab, where its plan, runs, hashes and
  reproducibility check are.

## Mapping pathway nodes to graph records

The pathway's node identifiers are the Scenario Lab's, not the graph's. `buildOverlay` maps
them: `change:var_x` → `variable:var_x`; `model:variable:var_x` → `variable:var_x`; graph keys
(`company:…`, `industry:…`) stay as they are; model outputs and result lines map to no graph
record and are not drawn. When a record has several roles, the strongest is kept (changed >
entity > a model's variable > context; propagated > cited > not simulated).

## Extension point

Overlays show one execution at a time, and only its **modelled pathway** and **line
results**. Comparing two executions, stress cases, sensitivity and month-by-month values stay
in the Scenario Lab; the overlay model (`overlay.ts`) is where a comparison would be added.
