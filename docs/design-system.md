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
  time-series charts are sliders (arrow keys, Home, End); a skip link leads to the main
  content.
- Screen readers: landmarks and headings on every page; live regions announce counts and
  save results; form errors are listed in a summary that links to each field.
- Focus is always visible (sky-blue ring, ≥ 3 : 1).
- Nothing relies on colour alone; contrast as above; reduced motion honoured.
- Reviewed in Chromium at 1440 × 900, 1280 × 800 and 390 × 844 (the graph explorer also at
  820 × 1180), in both themes; there are no automated visual or screen-reader tests yet.
