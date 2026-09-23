# The Simulation preview

The page at `/simulation` (and `/simulation/runs/{id}` for a stored run) is the first
interface to the engine. It is a **preview**, not the Scenario Lab: one model at a time, one
run at a time, no saved comparisons (that is Phase 5). It collects inputs and shows what the
engine returned; **no financial figure is calculated in the browser**.

## What a reader can do

| Task | Where |
|---|---|
| Choose a model and see what it calculates, how a change travels through it, and whether the knowledge graph confirms the relationship it relies on | Before a run, the right-hand column |
| Enter inputs, grouped by kind of knowledge, with each one's unit, allowed range, default and rationale; use the stored exchange rate when one exists | The form |
| Check the inputs on the server without running, and see every problem beside its field and in a summary that links to it | "Check inputs" |
| Run, and land on the stored run's own address | "Run simulation" |
| Read the headline, baseline against scenario, and the engine's notes | The run's header |
| See how the change travelled, month by month, and how the steps add up | "Pathway and months" |
| See which change accounts for how much of each result | "Contributions" |
| See which inputs move the result most | "Sensitivity" |
| Audit every calculation step, month by month, and every equation | "Calculation" |
| See each input's value, kind and source, and the assumptions against their defaults | "Inputs and assumptions" |
| See the model version, hashes, graph build and edges, stored observations and transmission paths, and re-check reproducibility | "Provenance" |
| Reopen any stored run, with its inputs loaded into the form to vary them | "Stored runs" |

## Design

The page follows RUMIN's design system (bone white and charcoal, neutral greys, sky blue
for emphasis only, Newsreader for titles, Inter for the interface) and three installed
skills, used as follows.

- **Frontend design.** A plan before code, reviewed against the brief: an editorial,
  instrument-like page rather than a dashboard of cards. Restraint everywhere but one
  place: the **pathway**, where a new run's change travels down the chain once, layer by
  layer, as a pulse along each link. Equations are set like a textbook (the display serif,
  italic). Headings name things plainly; buttons say what happens ("Run simulation",
  "Check inputs", "Check reproducibility").
- **Data visualisation.** The form of each figure follows its job; marks, spacing, hover
  layers and table views follow the skill's specifications; the one new colour was
  validated by script, not by eye (below).
- **Financial calculator.** The headline number big and clear; the breakdown step by step;
  assumptions listed explicitly; "what moves the needle" (the sensitivity ranking); the
  statement that results are estimates of stated assumptions, not advice.

### Layout

Form on the left (25 rem), results on the right. Below 72 rem the columns stack; when a
stored run is open, its results come first and its inputs follow. The pathway switches to
a numbered list when its nodes cannot fit at a readable width (phones). Tables scroll
sideways inside their own container; the page never does.

### Kinds of knowledge

Every input and result carries a glyph and a label. Circles and squares split what is
**given** from what is **calculated**:

| Glyph | Label |
|---|---|
| Sky-blue diamond | Scenario change (the one thing the reader varies; the same glyph as a scenario input elsewhere in RUMIN) |
| Filled circle | Historical data |
| Filled square | Your figure |
| Ring | Assumption |
| Short dash | Setting |
| Open square | Derived (from the inputs alone) |
| Hatched square | Simulated (the same glyph as a simulated output elsewhere in RUMIN) |

Graph variables in the pathway keep the knowledge graph's own glyph (a diamond in ink).

### Figures

| Figure | Form | Why |
|---|---|---|
| Change in operating profit | A hero figure (large, the interface sans, proportional digits; the unit smaller beside it) | The one number the run leads with |
| Other headline results | Stat tiles with the output's plain-language description and equation ID | A handful of headline numbers |
| Baseline and scenario | A table (profit and margin: baseline, scenario, change) | Exact comparison beats a picture for two rows |
| How the change travels | A layered flow diagram, read top to bottom | Structure, not quantity: which input reaches which result, and through which relationship |
| Month by month | Two plots on one x-axis: scenario and baseline fuel cost as lines (one scale), the monthly change in operating profit as columns from zero | Change over time; never two y-scales on one plot |
| How the steps add up | A horizontal waterfall in a table | Part-to-whole with signs: each step starts where the last ended |
| Contributions | Bars from zero in a table, for a chosen result | Magnitude and sign per change |
| Sensitivity | A tornado in a table | Ranked spread per input |

**Marks.** 2 px lines with round joins; markers of radius 4 with a 2 px ring in the surface
colour; columns at most 24 px wide with a rounded data end; bars 12 px; hairline solid
gridlines; the zero line emphasised; values rounded for display with the exact figures in
tables and tooltips. The monthly chart has a crosshair and a tooltip listing every monthly
series for the month under the pointer, and works as a slider from the keyboard (arrow
keys, Home, End), announcing each month; its "Table" view lists every exact value. The bar
figures are tables whose bars are pictures of the amounts written beside them, so nothing
depends on seeing a bar.

**Colour.** One new token, `--viz-baseline`, for the baseline: grey context beside the
scenario's `--viz-series` sky blue (the "emphasis" form). The pair was checked with the
palette validator in each theme, and the grey's contrast against all four surface tokens:

| Theme | Pair | CVD separation | Normal-vision separation | Contrast, worst surface |
|---|---|---|---|---|
| Bone (light) | #5f5d57 / #3a87cc | ΔE 18.0 (target ≥ 8) | ΔE 19.0 (floor 15) | 5.5 : 1 (target 3 : 1) |
| Charcoal (dark) | #6a6e75 / #4a93d6 | ΔE 14.8 | ΔE 15.7 | 3.1 : 1 |

The validator's chroma floor flags the grey, by design: it is the grey context series of an
emphasis chart, not a categorical hue. The first greys tried (#8a867c / #7c7f86) passed
colour-blind separation but fell below the normal-vision floor (ΔE 14.5 / 12.4) and were
replaced. Waterfall steps and the sensitivity range are in the baseline grey; totals and
contributions of the scenario's changes in sky blue. Status colours appear only on status
(the "Note" badge, "Reproduced exactly"). Direction in the bars is carried by position and
the signed value beside each bar, never by red and green.

**Graph relationships** in the pathway keep the knowledge graph's evidence patterns (the
model-assumption edge is dash–dot), with arrowheads for direction and a small tag with the
coefficient and lag that links to the relationship in the graph explorer.

### Motion

One orchestrated moment: when a new run opens, nodes appear layer by layer and a sky-blue
pulse runs once along each link (about two and a half seconds in all). Stored runs opened
later do not animate. Under reduced motion (the operating system's setting or RUMIN's own
preference) nothing moves: the pulses are not rendered at all.

### Accessibility

- Every control has a visible label; help, range and default text is attached to its
  field; invalid fields are marked (`aria-invalid`) and listed in a summary whose links
  move focus to the field.
- Tabs follow the WAI-ARIA pattern (arrow keys, Home, End). Toggles are grouped with a
  legend. The monthly chart is a keyboard slider with a spoken reading; every chart has a
  table or is one; the pathway has a list view with every link and value.
- Nothing depends on colour alone: glyphs carry kinds of knowledge, line patterns carry
  evidence, circle fills carry lowered and raised points, signs carry direction.
- Contrast follows the design system's checked tokens in both themes; focus is always
  visible.

## Review

The page was reviewed in Chromium at 1440 × 900 (light and dark) and 390 × 844, with
screenshots after each change, against the brief's criteria. What the review changed:

| Found | Fixed |
|---|---|
| "−1.27 percentage points" and "−3,600,000 INR per year" wrapped inside the stat tiles | Numbers and units split: the unit set smaller beside the figure |
| The pathway said "no lag" before any run, when the lag is set by an assumption | Before a run the tag says the coefficient and lag come from the assumptions |
| "Knowledge-graph variable" was cut off inside the nodes | "Graph variable", with the graph's own glyph |
| Compact values rounded too coarsely ("−3.6 million" beside "−3,550,000") | Two decimals ("−3.55 million INR") |
| The x-axis name overlapped month 12; month labels crowded on phones | The name moved past the axis end; labels thinned to every 2nd, 3rd, 6th or 12th month by the space available |
| Label cells of the bar tables stopped being table cells, cutting their row rules short | Cells restored; their text stacks inside them |
| On phones, a new run appeared below the whole form | A stored run's results come first when the columns stack |
| Output descriptions were symbols ("ΣΔπ = ΣΔr − ΣΔb") | Plain language; the symbols stay in the equations |
| The edge tag's accessible name lost its space ("relationship,β") | Space moved outside the visually hidden text |
| Three schema names collided with existing ones and renamed contract types | Unique names, and a test that fails on any future collision |
| The dark baseline grey (#666a71) met 3 : 1 on the chart surface but not on the raised surface (2.9 : 1) | Lightened to #6a6e75 (≥ 3.08 : 1 on every surface) and validated again as a pair |
