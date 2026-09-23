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

## Knowledge labels

The five epistemic categories use one glyph each, everywhere (badges, legend, landing):

| Category | Glyph | Colour |
|---|---|---|
| Observation | filled circle | ink |
| Assumption | ring | ink |
| Scenario input | diamond | sky blue — the one thing the reader controls |
| Simulated output | hatched square | ink |
| Uncertainty | wave | ink |

## Components

Shared primitives live in `frontend/src/components/`: `Button` / `ButtonLink`, `Badge`,
`EpistemicBadge`, `StatusIndicator` (always icon + label), `Panel`, `StatTile` (value with
its source), `PageHeader`, `Icon`, `Wordmark`, and the loading, error and empty states in
`States` — every data view uses them, so no screen is ever blank or silently stale.

## Accessibility checklist

- Keyboard: every control is reachable; network nodes are focusable buttons (Enter
  selects, Escape clears, `+`/`−`/`0` zoom); a skip link leads to the main content.
- Screen readers: landmarks and headings on every page; live regions announce counts and
  save results; form errors are listed in a summary that links to each field.
- Focus is always visible (sky-blue ring, ≥ 3 : 1).
- Nothing relies on colour alone; contrast as above; reduced motion honoured.
- Reviewed in Chromium at 1440 × 900, 1280 × 800 and 390 × 844, in both themes; there are
  no automated visual or screen-reader tests yet.
