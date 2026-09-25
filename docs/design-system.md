# Design system

RUMIN should feel like a precise instrument: calm surfaces, exact typography, and colour
used only where it carries meaning. Everything visual is defined once, in
[`frontend/src/styles/tokens.css`](../frontend/src/styles/tokens.css); components use
semantic tokens and never hard-code colours.

## Principles

1. **Evidence first.** Every figure shown is live application state with a stated source;
   every relationship is labelled an assumption; nothing decorative imitates data.
2. **Colour is scarce.** Neutrals do the work. Sky blue marks emphasis — selection, focus,
   the active element — and nothing else. Status colours are reserved for status.
3. **Shape and text before colour.** Entity kinds, knowledge categories and statuses are
   each told apart by a glyph and a label, so nothing depends on seeing colour.
4. **Quiet motion.** Short, purposeful transitions; all motion stops when the reader asks
   for reduced motion.

## Tokens

Two layers:

- **Primitives** — the raw palette (`--bone-*`, `--stone-*`, `--charcoal-*`, `--sky-*`),
  type families, the spacing scale, radii, durations.
- **Semantic tokens** — what components use (`--color-ink`, `--color-surface`,
  `--color-accent`, `--viz-edge-economic`, …). Each theme remaps only this layer.

Themes: **Bone** (light) and **Charcoal** (dark), chosen per viewer: *System* follows the
operating system, or pick one explicitly (header button; System page). The choice is
stored in the browser and applied before first paint, so pages never flash the wrong theme.

### Colour

| Role | Token | Bone (light) | Charcoal (dark) |
|---|---|---|---|
| Page background | `--color-bg` | `#f4f1ea` bone white | `#121316` deep charcoal |
| Panels | `--color-surface` | `#fbfaf6` | `#191b1f` |
| Raised / sunken areas | `--color-surface-raised` / `-sunken` | `#eeeae1` / `#efebe2` | `#202328` / `#0f1012` |
| Primary text | `--color-ink` | `#17181b` | `#ece8df` |
| Secondary text | `--color-ink-secondary` | `#4a4945` | `#b8b4aa` |
| Muted text | `--color-ink-muted` | `#6b6962` | `#8e8a81` |
| Dividers | `--color-line` / `--color-line-strong` | `#dad5c9` / `#b9b3a5` | `#2b2e33` / `#3c4046` |
| Text-field borders | `--color-field-border` | `#858176` | `#6d7178` |
| Emphasis (sky blue) | `--color-accent` / `--color-accent-ink` (text) | `#3a87cc` / `#1f63a3` | `#72b0e6` / `#8ec1ee` |
| Status: good / warning / critical (text) | `--color-*-ink` | `#006300` / `#8a5a00` / `#b02a2a` | `#3fc23f` / `#e3a73a` / `#ec8584` |

A **brushed-metal hairline** (`--metal-hairline`, a subtle gradient) marks two key edges
— the application header and the landing page's network figure — and is the only
"metallic" effect. Metallic finishes never appear on data.

### Contrast (checked, WCAG 2.2)

Computed for every text token against all four surface tokens, in both themes; the worst
case is shown.

| Token | Bone | Charcoal | Requirement |
|---|---|---|---|
| `--color-ink` | 14.8 : 1 | 12.9 : 1 | 4.5 : 1 |
| `--color-ink-secondary` | 7.5 : 1 | 7.6 : 1 | 4.5 : 1 |
| `--color-ink-muted` | 4.6 : 1 | 4.6 : 1 | 4.5 : 1 |
| `--color-accent-ink` | 5.2 : 1 | 8.3 : 1 | 4.5 : 1 |
| Status inks (good / warning / critical) | ≥ 4.9 : 1 | ≥ 6.2 : 1 | 4.5 : 1 |
| `--color-accent`, focus ring | 3.2 : 1 | 6.8 : 1 | 3 : 1 |
| `--viz-node` (network marks) | 11.8 : 1 | 10.7 : 1 | 3 : 1 |
| `--viz-edge-economic` | 3.0 : 1 | 3.9 : 1 | 3 : 1 |
| `--color-field-border` | 3.2 : 1 | 3.2 : 1 | 3 : 1 |
| `--viz-series`, `--viz-flag` (time-series marks) | ≥ 3 : 1 | ≥ 3 : 1 | 3 : 1 |
| `--viz-baseline` (simulation baseline marks) | 5.5 : 1 | 3.1 : 1 | 3 : 1 |

The time-series pair (`--viz-series` #3a87cc / #4a93d6 and `--viz-flag` #b07a00 / #c98500,
light / dark) was checked with a palette validator as a pair, in each theme: inside the
lightness band, above the chroma floor, colour-vision-deficiency separation ΔE ≈ 24 (target
≥ 8), normal-vision separation ≈ 25, and ≥ 3 : 1 against the chart surface.

The simulation pair (`--viz-baseline` #5f5d57 / #6a6e75 beside `--viz-series`) was checked
the same way: separation ΔE 18.0 / 14.8 for colour-vision deficiency and 19.0 / 15.7 for
normal vision (floor 15). The validator's chroma floor flags the grey by design: it is the
grey context series of an emphasis chart, not a categorical hue.

`--color-line` and `--color-line-strong` are decorative dividers (and borders of controls
that are identified by their text) and are deliberately below 3 : 1.

### Typography

| Family | Token | Used for |
|---|---|---|
| Newsreader (variable, optical sizes) | `--font-display` | Page titles, panel titles, the landing headline |
| Inter (variable) | `--font-sans` | Interface text, figures in stat tiles |
| JetBrains Mono (variable) | `--font-mono` | IDs, codes, eyebrow labels |

All three are **self-hosted** (`@fontsource-variable/*`): no request goes to a font CDN,
and the browser downloads only the character subsets a page uses. Sizes follow a fixed
scale from `--text-2xs` (11 px) to `--text-display` (fluid, 40–68 px).

### Space, shape, motion, layout

- Spacing on a 4 px grid: `--space-1` (4 px) … `--space-24` (96 px).
- Radii are small and precise: 2, 4, 6 and 10 px, plus pills for badges.
- Durations 120 / 200 / 480 ms with ease-out curves. Motion is off when the operating
  system asks for reduced motion or the reader chooses *Reduced* on the System page.
- Content is at most 90 rem wide with a fluid gutter; layouts adapt at 40 rem (phone),
  56 rem, 64 rem and 72 rem.
- The header navigation holds nine modules. It stays in the header above 72 rem (below
  90 rem the workspace status drops its detail text to make room) and collapses into the
  menu at 72 rem and below.

## The financial network

| What | Encoding | Why |
|---|---|---|
| Entity kind | **Shape**: diamond = economic variable, ring = industry, dot = company, square = country; all in neutral ink | Four categories anywhere on the canvas; shape needs no colour vision and never collides with the emphasis colour. |
| Connectedness | Size grows with the square root of the number of links | Hubs stand out without dwarfing everything else. |
| Relationship strength | Line weight: weak 1, moderate 1.6, strong 2.3 px | An ordinal judgement, shown as an ordinal visual. |
| Direction | Arrowheads | Effects flow from cause to affected; `competes_with` has none. |
| Economic vs structural | Darker line vs lighter, thinner line | Assumptions stand out from classification facts. |
| Selection | Selected node and its links in sky blue; neighbours stay in ink; everything else dims | Answers "what is this connected to?" at a glance. |
| Layout | Columns left → right: variables → industries → companies → countries | Reads in the direction an assumed effect travels. |

Other rules: labels point outwards from the centre and keep a constant on-screen size at
any zoom; every node's hit area is at least 24 px; the tooltip becomes a fixed read-out bar
on narrow screens; on phones the layout turns a quarter to run top-to-bottom and only the
selection is labelled. The **table view** lists exactly the same filtered data for readers
who prefer — or need — text.

## Time-series charts (Phase 2)

One chart form serves both economic series and prices: a single series over time, so no
legend box — the panel title and the unit label name what is plotted.

- **Marks:** a 2 px line in `--viz-series`; value markers (radius 4, with a 2 px ring in
  the surface colour) only when there are at least 12 px per period; the latest value is
  labelled at the line's end, rounded for display.
- **Honesty:** a missing value or a period absent from the data breaks the line — nothing
  is interpolated — and missing periods are marked on the axis with a hollow circle.
  Values flagged for review are **triangles** in `--viz-flag`: a shape of their own, never
  colour alone. A key explains both whenever they appear.
- **Axes:** round-number ticks from one scale (never two y-axes); hairline gridlines; the
  zero line emphasised only when it lies inside the range; calendar-aligned time ticks.
- **Reading values:** a crosshair snaps to the nearest period and a tooltip shows the
  exact value (every published digit), the period and any flags. The chart is operable as
  a slider — arrow keys, Home and End move through the periods and screen readers announce
  each reading — and every chart has a table twin with the exact values.
- **Labels, not colour, for the nature of data:** "Historical · not live", "Sample data —
  not real", "No value published", "Flagged for review", and the three freshness facts
  (period, retrieval time, provider's last update) kept apart.

## The knowledge graph explorer (Phase 3)

The explorer (`/graph`) shows up to nine node types and four evidence statuses at once, so
it keeps the network's rules — shape for kind, neutral ink, sky blue only for emphasis —
and adds line patterns. Full details: [the explorer](graph/explorer.md).

| What | Encoding | Why |
|---|---|---|
| Node type | **Shape**, in neutral ink: dot = company, ring = industry, diamond = economic variable, hollow square = country, hexagon = sector, target = currency, pill = data series, triangle = instrument, inverted triangle = market | Nine categories is past the point where colour stays distinguishable; shapes need no colour vision. Company, industry and variable keep their network shapes |
| Nature | A second ring: dashed for fictional, dotted for sample; none for real records | Fiction and sample data are visible on every node, not only in the panel |
| Data status (series) | Hollow pill = definition only; filled pill = values stored | Whether RUMIN holds values is visible without opening the node |
| Evidence status | **Line pattern**: solid = evidence-backed, long dashes = analyst-created, dash–dot = model assumption, dotted with round caps = unverified | The most important property of an edge, readable in greyscale and print |
| Category | Economic lines 1.6 px, structural 1.1 px, one colour (`--viz-edge-economic`, ≥ 3 : 1) | Assumptions stand out from classification facts without a second colour |
| Size | Grows with the square root of degree, capped at 64 edges | Hubs are visible but never swamp the view; captioned "data coverage, not importance" |
| Distance | Rings by hop count around the focus (radial tree) | Distance from the centre always means the same thing |
| Emphasis | Sky blue for the selection, the hovered item and their connections; everything else dims | The one accent colour keeps its one job |
| Aggregate map | Type marks with counts, joined by pale bands (`--color-line`) whose width grows with the square root of the edge count, capped | Clearly an aggregate: no individual entity is drawn |

Labels keep a constant on-screen size and are written along the radius on crowded rings.
On phones only the centre, the selection and the hovered node are labelled. The legend
lists only the marks in view. As in the network, a table view lists the same nodes and
relationships.

## The Simulation preview (Phase 4)

The Simulation page (`/simulation`) is an instrument, not a dashboard: a form on the left,
results on the right, one accent colour, one moment of motion. Full details, including the
review that shaped it: [the preview](simulation/preview.md).

| What | Encoding | Why |
|---|---|---|
| The headline | A hero figure in the interface sans with proportional digits, the unit set smaller beside it; other headline results as stat tiles with their equation ID | One number leads; units never wrap into the figure |
| Baseline against scenario | `--viz-baseline` grey for the baseline, `--viz-series` sky blue for the scenario, one y-scale; the monthly change as columns from zero on a second plot sharing the x-axis | Emphasis, not categories: the scenario is what the reader changed. Never two y-scales on one plot |
| Bar figures (waterfall, contributions, tornado) | Tables whose bars picture the amount written beside them; 12 px bars from zero with a rounded data end; direction carried by position and sign, never red and green | Exact values stay readable without seeing a bar |
| Sensitivity points | A hollow circle for the input lowered, a filled circle for it raised | Shape, not colour |
| The pathway | Layered flow, read top to bottom; inputs, graph variables and results as nodes; graph relationships keep the explorer's evidence patterns (dash–dot for a model assumption) with arrowheads and a tag giving the coefficient and lag | Structure, not quantity: which input reaches which result, and through which relationship |
| Equations | The display serif, italic, set like a textbook | Formulas read as formulas, apart from interface text |
| Motion | For a new run, nodes appear layer by layer and a sky-blue pulse runs once along each link (about 2.5 s); nothing moves for stored runs or under reduced motion | The one orchestrated moment shows how the change travelled |

## The Scenario Lab (Phase 5)

The Scenario Lab (`/scenarios`) uses the same instrument language at a larger scale:
controls left, the pathway centre, results right, the execution and months along the
bottom. Details: [the interface](scenario-lab/interface.md).

| What | Encoding | Why |
|---|---|---|
| Changes | Sky-blue left rule on each change (in the builder and on the pathway's change steps), the scenario-input diamond | Sky blue is reserved for what the user changes, the relationships the engine propagated along, and the one emphasised series |
| The pathway | Four columns (changes → variables → line items → lines and metrics); one lane per model as a pale surface with a hairline border and its title, version and the graph context it cites; steps as small labelled cards with the value in monospaced figures | Structure first; each model's part reads as one band |
| Link kinds | Ink for applied and computed links, sky blue (thicker) for relationships propagated along the graph, a hairline for the Lab's additions with "−" where a line is subtracted; graph context never drawn as a step | What carried a number is visible at a glance; a drawn connection is never mistaken for a cited one |
| Selection | The chain upstream and downstream stays at full strength, the rest drops to low opacity; the selected step has an accent ring | Follow one change through without losing the rest |
| Replay | Steps not yet reached dim; values change in place; metrics read "Horizon only" | Motion follows the stored months, never an animation |
| Results | A hero figure for the headline line; a table of baseline, scenario and change with the percentage and "raises/reduces profit" under each change; chevrons for disclosure | It reads like a financial statement: "+" and "−" only ever mean signs, never disclosure |
| Charts | Stress bars and the timeline use `--viz-series` for the scenario (the emphasised series) and `--viz-baseline` grey for the other cases; the tornado spans each quantity's range around the execution's value (a hairline rule); every chart has its table | The dataviz rules: one emphasis, thin marks, hairline axes, no second y-scale |
| Status | The execution's stages as numbered chips with their recorded durations; ✓ when stored; the running stage's marker pulses only while the server reports it | Progress is the server's, never simulated |
| Field messages | Red with an alert icon for an error; amber for a warning; neutral with a circle for a value still needed before the first save | A template's first view is a checklist, not a wall of errors |

## Financial Intelligence (Phase 6)

Financial Intelligence (`/intelligence`) is a ledger, not a dashboard: subjects on the left,
findings as ruled rows on the right, each opening into the evidence it rests on. It adds no
colour token. Details: [the interface](intelligence/interface.md).

| What | Encoding | Why |
|---|---|---|
| Evidence grade | A short line sample and the grade's word: heavy solid (observed), thin solid (documented), dashes (curated), short dashes (simulated), dash-dot (assumed), dots (unverified) | The graph's own patterns for relationship evidence, extended to observations and simulations; never colour alone |
| The evidence chain (the signature element) | An ordered list of steps on a thin rule; each step's basis as a small label, its sentence, its value in tabular figures and its records; the step that sets the grade outlined in sky blue and marked *Sets the grade* | One glance says what a statement rests on and which link limits it |
| Findings | Ruled rows grouped by kind of knowledge (observed data, simulations, relationships and exposure, coverage), each with its kind, headline, grade and period; no cards, no scores, no ranking | Rows keep equal weight; the difference between an observation and an assumption lives in the grade |
| Exposure matrix | A table of companies × variables; a cell names the channels (C, R, F) and its border says how the variable reaches the company: solid (directly), dashed (through its industry), dotted (only upstream); a legend under the table; every cell has a sentence for screen readers | A table answers "who is exposed to what" and reads as text |
| Exposure paths | A line of hops from the variable to the entity, each hop drawn with its relationship's evidence pattern; the entity at the end outlined in sky blue | The path is the evidence |
| Drivers | One-hue bars from zero (right for an increase, left for a decrease) in a table, the amount, share and effect per unit printed on every row | The dataviz rules: one hue, values printed, no legend to decode |
| Accent | Sky blue only for the subject in focus in the rail, the chain step that sets the grade and the entity at the end of a path | Restraint: blue marks where to look, never a value |
| Status | Red for a refused threshold field; amber for notices and a stale stored analysis; green for a current one | Status colours only mean status, always with words |

## The AI Analyst (Phase 7)

The Analyst (`/analyst`) reads as a column of research notes, not a chat: no bubbles, no
avatars, no typing effect. It adds no colour token. Details: [the interface](analyst/interface.md).

| What | Encoding | Why |
|---|---|---|
| A note | The question set off by a rule in secondary ink; the headline in the display face (Newsreader); the status as a small word; paragraphs in the body face at reading width (46rem) | An answer is something to read and check, like a memo |
| The evidence margin (the signature element) | Beside each answer, its sources in the order first cited: the id in the mono face, the kind of knowledge as a mark and a word, the title as a link to the record, the period and units, and *Details*. A citation chip (`E2`) in the text links to its source; hovering or focusing either highlights both | Checking an answer is the default, not an extra step |
| Kinds of knowledge | The platform's glyphs ([below](#knowledge-labels)): filled circle observed, ring assumption, filled square a person's figure, hatched square simulated (dashed: a preview, not stored); plus open square a RUMIN record, linked dots a relationship, triangle a finding | The same shape means the same thing on every page |
| Scenario cards | Stored execution: solid border. Preview computed now and not stored: dashed border. Plan that needs figures: the missing figures listed. Figures in the card use the sentences' rounding | Whether a result was stored is visible before it is read |
| Notices | A left rule and a small kind word (*Assumption*, *Limitation*, *Not stored*, *Illustrative*, *Fallback*); refusals as a policy statement with an info icon | Disclosures are part of the answer, not footnotes |
| Series and paths | The Data Explorer's chart (one line, end label, keyboard readout, values as a table); paths as chains of linked records with their evidence and channel | Reuse, so a series or a path reads the same everywhere |
| The method | *How this was answered*, collapsed: tool calls with status and timing in the mono face, the grounding check, who composed the answer | Provenance of the answer itself |
| Accent | Sky blue only for citation chips, links and focus | Blue marks where to look, never a value |

## The 3D universe (Phase 8)

The universe (`/universe/3d`) is the knowledge graph in three dimensions. It adds no colour
token: it reads the graph's own (`--viz-node`, `--viz-node-hollow`, `--viz-edge-*`,
`--viz-dimmed`, `--viz-label*`) and the accent, and re-reads them when the theme changes.
Details: [encoding](universe/encoding.md), [accessibility](universe/accessibility.md).

| What | Encoding | Why |
|---|---|---|
| Height | The stratum of the record's kind: data, drivers, industries, companies, places (top to base), named at each ring's edge | A stable frame of reference; never a magnitude |
| Shape | The 2D glyphs as solids: sphere, hollow sphere, hexagonal prism, cube, ring with a core, octahedron, capsule, pyramid, inverted pyramid | Kind is readable without colour or position |
| Outline, halo | Hollow kinds and records without stored values as outlines; dashed halo fictional, dotted halo sample | As in 2D |
| Lines | Evidence by pattern (measured in screen pixels, so it reads the same near and far), category by weight, direction by an arrowhead | As in 2D |
| Emphasis | Sky blue and weight for the selection and what it touches, or an overlay's modelled pathway (propagated solid, cited dashed); everything else dimmed | Blue marks where to look, never a value |
| Names | DOM text over the canvas in the body face, with a surface-coloured halo; strata names in tracked small capitals; placed by priority, never on other nodes | Legible, never overlapping, never pretending |
| Motion | A 480 ms eased fly-to when the focus changes; a jump under reduced motion; no idle animation | Motion only when asked for |
| Focus | A 2 px sky-blue outline inside the canvas's edge | Visible over the drawing |

## Analysis charts (Phase 9)

The Scenario Lab's grids, Monte Carlo results and the verification register add no colour
token. They follow the `dataviz` method as the earlier charts do: one emphasised series in
`--viz-series`, grey (`--viz-baseline`, secondary ink) for context, amber never used (there
is no flag to raise), thin marks, one axis, values in text tokens and a table twin for
every chart. Details: [advanced analysis](scenario-lab/advanced-analysis.md#the-interface).

| What | Encoding | Why |
|---|---|---|
| Histogram of the draws | Equal-width bins in `--viz-series` from a zero baseline, 2 px apart, 4 px rounded data ends; hairline rules at P5, P50 and P95 (secondary ink), the executed value in `--viz-baseline` (2 px), a threshold dashed (the only dashed mark); rule labels on three rows so close values never overlap; counts ("12 of 1,000 draws"), never a percentage the browser would compute | A distribution's shape with its landmarks; the counts are the backend's |
| Convergence | The running mean as a 2 px `--viz-series` line inside a 12 % wash of ±2 standard errors; the draws on the x-axis | Whether the draws are enough — stated beside it: a narrow band says the mean is precise, not that the distributions are right |
| Rank correlations | A 6 px bar from a centre rule, left for negative and right for positive, the value printed beside it | Direction and strength at a glance, never colour alone |
| Grid | A table: the executed cell washed in `--color-accent-wash` and in bold, a skipped cell reads *skipped* in muted ink, its reason listed under the grid; read by change or by interaction | Exact values first; no heat-map hue to decode |
| Verification | A check or alert icon with *passed* or *failed* in text, the kind of check in small muted type; the summary as a badge (*10 of 10 checks passed*) with *Not verified* always beside it | Status never by colour alone; passing is never shown as "validated" |
| Interaction | Histogram and convergence charts are keyboard sliders (arrows, Home, End, Escape), the bin or checkpoint in `aria-valuetext`; tooltips follow the pointer but never gate a value (the table has them all) | The same model as the time-series charts |

## Knowledge labels

The five epistemic categories use one glyph each, everywhere (badges, legend, landing):

| Category | Glyph | Colour |
|---|---|---|
| Observation | filled circle | ink |
| Assumption | ring | ink |
| Scenario input | diamond | sky blue — the one thing the reader controls |
| Simulated output | hatched square | ink |
| Uncertainty | wave | ink |

The Simulation page labels its inputs and results more finely, with the same shapes where
the meanings match. Circles and rings mark what is **given**, squares what is
**calculated**:

| Simulation label | Glyph |
|---|---|
| Scenario change | sky-blue diamond (as scenario input) |
| Historical data (a stored observation) | filled circle (as observation) |
| Your figure (entered by the user) | filled square |
| Assumption | ring (as assumption) |
| Setting (e.g. the horizon) | short dash |
| Derived (from the inputs alone) | open square |
| Simulated (under the scenario) | hatched square (as simulated output) |

## Components

Shared primitives live in `frontend/src/components/`: `Button` / `ButtonLink`, `Badge`,
`EpistemicBadge`, `StatusIndicator` (always icon + label), `Panel`, `StatTile` (value with
its source), `PageHeader`, `Icon`, `Wordmark`, and the loading, error and empty states in
`States` — every data view uses them, so no screen is ever blank or silently stale.

## Accessibility checklist

- Keyboard: every control is reachable; network and graph nodes are focusable buttons
  (Enter selects, Escape clears, `+`/`−`/`0` zoom; **E** expands a graph node);
  time-series charts, the Monte Carlo histogram and the convergence chart are sliders
  (arrow keys, Home, End); a skip link leads to the main content.
- Screen readers: landmarks and headings on every page; live regions announce counts and
  save results; form errors are listed in a summary that links to each field.
- Focus is always visible (sky-blue ring, ≥ 3 : 1).
- Nothing relies on colour alone; contrast as above; reduced motion honoured.
- Reviewed in Chromium at 1440 × 900, 1280 × 800 and 390 × 844 (the graph explorer and
  Financial Intelligence also at tablet size), in both themes; there are no automated visual
  or screen-reader tests yet.
