# The interface

Financial Intelligence is the ninth module of the web app, after the Scenario Lab in the
navigation. It is built as an analytical research instrument: a ledger of findings, each of
which opens into the evidence it rests on. Every number arrives from the API as an exact
decimal string. The browser rounds for display, groups digits and chooses words, and
calculates nothing. The code is in `frontend/src/pages/IntelligencePage.tsx` and
`frontend/src/features/intelligence/`.

## Layout

A left rail of **subjects**: the workspace, then each company and industry with its stated
channels and its latest simulated headline. The main column holds the analysis. Three views
share this layout:

| View | Route | Contents |
|---|---|---|
| **Workspace** | `/intelligence` | the coverage line (companies, paths, variables, series with data, executions, and *X of the first 200 (N in the graph)* when truncated); **Findings**; **Exposure map**; **Observed series**; **Simulated impacts**; **Relationship changes**; **Stored analyses** |
| **Dossier** | `/intelligence/{entity}` | a summary line, then tabs: **Findings (N)**, **Exposure** (paths, then counterparties and context, with *Only relationships backed by a cited source*), **Drivers**, **Signals**, **History**, **Sources**, **Brief** |
| **Stored analysis** | `/intelligence/analyses/{id}` | *"…, as stored"*, its freshness (*Current* or *Stale*, with the reason), the findings as stored, the fingerprint and hashes, and a link to *The analysis now* |

The tab, the evidence filter and every threshold override live in the URL, so any view can
be linked exactly. The page header shows the graph build and its freshness, and each view has
a *Store this analysis* button. Cached data appears at once and is refreshed on arrival,
dimmed while refreshing, because intelligence follows the store.

The Overview dashboard gains a **Latest findings** panel: the first four rows of the
workspace ledger, each with its grade, and a link to all of them with their evidence.

## The ledger

Every finding is a **ruled row**: its kind, headline, evidence grade and period. Rows are
grouped by the kind of knowledge they report: *Observed data*, *Simulations*, *Relationships
and exposure*, *Coverage*. Each group is a list named for assistive technology
(*"Findings: Simulations"*). Two filters sit above the ledger: a group selector (a group with
no findings is disabled) and *Evidence at least*, which hides findings below a grade. Nothing
is ranked, scored or sorted by size.

A row opens (a button with `aria-expanded`) into:

- **the evidence chain**, the signature element of the module. It is an ordered list
  (*"Evidence chain"*) of every step: its basis (Observation, Calculation, Relationship with
  its evidence status, Record, Simulation, Assumption, Threshold), its sentence, its value,
  and the records it cites. Records are linked where RUMIN has a page for them: a company or
  industry opens its dossier, another node the Graph Explorer, a series or instrument the
  Data Explorer, an execution its scenario in the Lab. Relationships are named with their
  evidence status. The step that sets the grade is marked **Sets the grade** and outlined in
  the accent colour. Below the chain is the grade's statement, with
  *"Its figures are simulated…"* where it applies.
- the values (facts), assumptions, limitations, **What to investigate next** (next steps,
  linked the same way; a template opens the Scenario Lab's builder with it), and the
  sources.

## Evidence grades, never by colour alone

A grade is drawn as a short line sample with its word beside it. The samples reuse the
knowledge graph's own patterns for relationship evidence (decision 25): a heavy solid line
for observed, a thin solid line for documented, dashes for curated, short dashes for
simulated, dash-dot for assumed, dots for unverified. The same marks appear on every
relationship hop in the exposure paths. A reader without colour vision, or with a print,
loses nothing.

## The exposure map

A table of **companies × variables**, grouped by category. A cell names the channels (C
costs, R revenue, F financing costs). Its border says how the variable reaches the company:
solid for directly, dashed for through its industry, dotted for only upstream. Every cell
has a full sentence for screen readers, for example *"Brent crude oil price reaches the costs
of Aerisca Airways: upstream; 1 path; weakest evidence model assumption; simulatable by
airline_fuel_cost."* It is a table, not a picture, so it reads as text and scrolls inside its
own frame on narrow screens.

In a dossier, each **path** is drawn as a line of hops (origin → … → the entity), each hop
with its relationship's evidence pattern and label, the directness, the channel and the
models able to simulate it.

## Drivers, signals, history, sources, brief

- **Drivers**: for each line, a table whose bars grow from zero (right for an increase, left
  for a decrease) in **one hue** for every change. The row label says which change it is, and
  the amount, the share of the change and the effect per unit are always printed. Everything
  is labelled *simulated, not a forecast*, with the unattributed amount, the models, the
  entered figures and what is not modelled. This follows the installed `dataviz` skill: no
  second axis, values printed, a table rather than colour identity.
- **Signals**: each signal with its answer and how it was reached: definition, method,
  inputs, period, the thresholds used, evidence and limitations. *Not enough data* and
  *Undefined* are shown as answers, not hidden.
- **History**: first the **observed data**: each related series drawn with the Data
  Explorer's time-series chart, with tables of the changes that met their threshold (flagged
  values marked) and the provider's revisions. Then, apart and
  labelled, the **model interpretation** (*Model interpretation, computed on request. Not
  stored, not an observation, not a forecast*). Then the executions stored for the entity.
- **Sources**: everything the dossier read. That is the graph build; the datasets with
  licence and attribution; every relationship with its evidence status and stated rationale;
  the executions and model runs with their hashes.
- **Brief**: the [entity brief](brief.md) as data, with its narration rules and a
  *Download the brief (JSON)* button.

## Thresholds

The *Thresholds* panel is built from the API's own specification: each threshold's label,
unit, range, default and the reason for the default. Applying overrides writes them into the
URL, and the backend validates them. A refused value opens the panel and shows the message
beside its field (*"Change in a level or exchange rate must be between 0.1 and 100
(percent)."*), next to an error state for the view.

## Design choices

The identity is fixed by the brief and the existing design system, so no new colour was
invented. The palette is bone surfaces, charcoal ink and stone greys for context. The sky-blue
accent appears in exactly three places: the subject in focus in the rail, the chain step that
sets the grade, and the entity at the end of an exposure path. Status colours appear only
where they mean status: an invalid threshold field, a notice, and the freshness of a stored
analysis (good for current, warning for stale). Titles are set in Newsreader, text in Inter,
and figures in tabular numerals.

Rejected, after review against the brief:

- **A dashboard of gauges and scores.** It is the generic answer, and it would present
  numbers that nothing defines. There is no composite score anywhere.
- **Cards of equal weight for every finding.** They flatten the difference between an
  observation and an assumption. The ledger keeps rows quiet and puts the difference in the
  grade and the chain.
- **A network drawing of exposure.** The Graph Explorer already draws the graph. Here the
  question is which variables reach which companies, and a table answers it and reads as
  text.

The frontend-design guidance was followed for the process: a token plan reviewed against the
brief, one signature element, restraint and screenshot critique. It was also followed for
details. This module has no all-caps eyebrows and no dotted metadata strings.

## Accessibility and responsiveness

- Every group, chain, table and tab list is named. Findings are buttons with
  `aria-expanded`. The thresholds panel's errors are tied to their fields. Stored-analysis
  freshness is a `status` region.
- Tables stay tables at every width. The matrix and wide tables scroll inside their own frame,
  and the page never scrolls sideways. A regression found in review, visually hidden text in
  scroll frames widening the page on phones, was fixed by positioning the frames.
- The header navigation was re-fitted for nine modules. The item spacing and breakpoints
  changed so that the navigation stays inside the header above 72rem, and collapses into
  the menu below.
- Motion is limited to short transitions and respects `prefers-reduced-motion`.

The module was reviewed from screenshots in Chromium. The set covered the workspace (light
and dark, with a finding opened), a dossier on each of its seven tabs (the drivers also in
dark), the thresholds refusal, a stale stored analysis (dark, and at phone width), the list
of stored analyses, the dashboard panel, and tablet and phone widths. Each screenshot run
also checked for console errors and sideways page scrolling. The review found that on a
phone the subject picker read *Workspace* while a stored analysis was open. It now reads
*A stored analysis*.
