# The Scenario Lab interface

`frontend/src/pages/ScenarioLabPage.tsx` and `frontend/src/features/scenarioLab/`. Routes:
`/scenarios` (the library), `/scenarios/new` (optionally `?template=…`), `/scenarios/{id}`
(optionally `?execution=…` and `&compare=…`), `/scenarios/compare?execution=…`.

## Layout

```
┌──────────────┬──────────────────────────────────┬───────────────┐
│ CONTROLS     │ PATHWAY · Plan · Months · Stress  │ RESULTS       │
│ scenario     │ Sensitivity · Uncertainty ·       │ headline      │
│ changes      │ Explain · History · Compare       │ baseline vs   │
│ company      │                                   │ scenario      │
│ timing       │  changes → variables → line items │ metrics       │
│ models       │  → lines and metrics              │ not modelled  │
│ constraints  │                                   │ models used   │
│ stress cases │                                   │               │
├──────────────┴──────────────────────────────────┴───────────────┤
│ EXECUTION: Execute · stages as recorded · status                  │
│ TIMELINE: one line's change by month · replay · events            │
└───────────────────────────────────────────────────────────────────┘
```

Above 1,408 px the three columns sit side by side; up to 1,408 px the results move under
the centre, and up to 992 px everything stacks (controls, views, results, execution). The page
never scrolls sideways (checked from 360 px to 1,920 px); a wide diagram or table scrolls
inside its own frame.

## Preview or stored execution — always labelled

What the centre and the right show is labelled in the header:

- **Showing stored execution · v1 · date** — a saved version's execution: reproducible,
  with its model runs and hashes.
- **Live preview · computed, not stored** — the backend's computation of the scenario as it
  stands (`POST /scenarios/preview`), a short moment (450 ms) after the last edit. An older
  request is cancelled when a newer one starts; while it runs, the previous figures stay on
  screen, dimmed, and the tag reads **updating…**.

Editing a saved scenario marks it **Unsaved changes**; *Save new version* stores the edit as
a new version (never overwriting), *Save and execute* saves, then executes, and *Discard
changes* returns to the saved version (*Start over* returns a new scenario to its template's
starting point). Restoring an older version is in History.

## Controls

Each field shows the problem the API reports for it, at the same field path: the browser
applies no domain rule of its own (it only checks that a name, a variable and a magnitude are
there). A value a template or model still needs is shown as a neutral note ("Annual revenue
is required.") until the user tries to save or execute; it then becomes an error.

- **Changes** — variable, kind of change (percent, or in the variable's unit), rise or fall,
  magnitude with its unit and a slider, and the allowed range in rise/fall terms ("a fall of
  less than 100 % or a rise of up to 1,000 %"). Up to ten.
- **Company and figures** — a company of the knowledge graph (those whose stated exposure a
  model covers are grouped first), reporting currency, annual revenue and operating costs,
  the exchange rate typed or taken from the latest stored World Bank value.
- **Timing** — start month, duration (0 = to the end), horizon.
- **Models** — every model with its status and reasons, *Auto / Include / Exclude*, and for
  included or blocked models their own inputs (with units) and assumptions (defaults shown
  as placeholders, applied when left empty).
- **Constraints** — evidence-backed relationships only; stored market data only.
- **Stress cases** — by a multiple of every change, or by values.

## Views

| Tab | What it shows |
|---|---|
| Pathway | the [impact pathway](pathway.md), with its inspector, a list view and what is not modelled |
| Plan | whether the scenario can run and why; which model simulates each change; every model with its status and reasons; notes and cautions; the companies the graph ties to the changes, and which ties a model covers |
| Months | every line's change by simulated month, with the model events on the months they happen |
| Stress | the scenario and its stress cases: a bar per case for the chosen line (the scenario emphasised, the cases in grey) and a table of every line and metric, with each case's changes in their units; not ranked |
| Plan (Phase 9) | also shows, for each included model, its verification summary (*N of N checks passed*, what is not verified) with the checks a click away |
| Sensitivity | *One at a time*: choose the quantities (each with its executed value and default variation, as a description), their values and the line or metric; the tornado of each quantity's range, with the execution's value as a rule. *Two together*: two quantities and their values; the grid read by change or by interaction, the executed cell marked, skipped cells with their reason. Both state that they are sensitivity, not stochastic, analysis |
| Uncertainty (Phase 9) | a Monte Carlo analysis under distributions the user states: the form (line or metric, draws, seed, threshold, each quantity's distribution), the result (mean, percentiles with the interval the draws support, shares, histogram, rank correlations, every line, convergence, rejected draws, configuration, *Run again and compare*) and the execution's stored analyses — see [advanced analysis](advanced-analysis.md#the-interface) |
| Explain | *what caused this?* for any line or metric: the chain, the Lab's equation and terms, each change's contribution, then each model's inputs, equations, worked steps, graph relationships and outputs |
| History | every execution (open it, verify it reproduces, tick it for comparison) and every version (restore one as a new version) |
| Compare | the ticked executions side by side, differenced against a reference only when currency and horizon match |

The **results** panel shows the headline (profit before tax when an interest model is
included, else operating profit), baseline against scenario for every modelled line — change,
percentage and whether it raises or reduces profit, each line expandable into its items and
its change by variable — the metrics, what is not modelled and why (cash flow is always
listed), and every model used with its key outputs and a link to its stored run.

The **execution strip** shows the stages exactly as the server recorded them, with their real
durations; nothing on it advances by itself. The **timeline** draws one line's change by
simulated month as columns from zero, the months the changes last as a rule under the axis,
and the model events; hovering a month reads its value out in the header, and the scrubber,
play button and event chips replay the months in the pathway.

## Charts

The charts follow RUMIN's chart rules (the `dataviz` method): one emphasised series in the
validated series colour with the rest as grey context, thin marks, hairline axes, no dual
axes, direct labels in text colours, and a table with the exact values beside every chart
(Months for the timeline, the stress table for the stress bars, the tornado's own figures).
The Phase 9 charts — the Monte Carlo histogram and the convergence chart — follow the same
rules and are described in the [design system](../design-system.md#analysis-charts-phase-9).

## Accessibility

The three regions (controls, impact, results) are labelled by (visually hidden) level-2
headings under the scenario's title, so the page's headings nest in order. Every control is
a native element with a label; tabs follow the WAI-ARIA pattern; pathway
steps are buttons and every link is reachable from a step's details, so the pathway can be
walked from the keyboard; choosing a link from the details moves focus to the details, and
Escape closes them. The replay's readout is a live region. Status and chart colours never
carry meaning alone. Motion follows state only and respects reduced motion. The histogram
and the convergence chart are sliders from the keyboard (arrow keys, Home, End; the bin or
checkpoint is announced) with a table twin; a one-at-a-time checkbox is named by its quantity
and described by its executed value and variation. `axe-core` finds no violation on the
Sensitivity, Uncertainty and Plan views or the Simulation page, in either theme (Phase 9
review).

## Design choices

An instrument, not a dashboard: bone and charcoal surfaces, hairline rules, the display serif
for titles, monospaced figures in the pathway. Sky blue is reserved for the scenario's
changes, the relationships the engine propagated along, and the one emphasised series in a
chart. No gradients, glows, glass or 3D. Disclosure uses chevrons, never "+" and "−", which
read as signs in a financial table.

No animation pretends that work is happening: the stage strip moves when the server records
a stage, the preview dims while the backend is computing, and the replay steps through values
already computed. The current stage's marker pulses only while the server reports that stage
as running.
