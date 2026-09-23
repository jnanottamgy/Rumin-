# The Graph Explorer

The web client's **Knowledge Graph** page (`/graph`) shows the graph built by the backend.
Every node, line and number on it comes from the read-only graph API. The explorer
arranges and draws those answers. It contains **no relationship logic**: it never
creates, infers, weights or ranks a relationship. Code: `frontend/src/features/graph/` and
`frontend/src/pages/GraphExplorerPage.tsx`.

## Three modes

| Mode | What it shows | When |
|---|---|---|
| **Map** | An aggregate map of node *types*: one mark per type with its count, and pale bands for the edges between types. It is labelled as an aggregate: a band counts relationships between *kinds* of node, not between individual entities. Beside it are the latest build's validation report, the metrics with their definitions, and a list of well-connected nodes to start from | The first view. It also appears after an invalid link |
| **Explore** | A node's neighbourhood on a radial layout. Distance from the centre is always hops | After a search, a click on the map, or a link such as `/graph?focus=company:co_deltrin_refining` |
| **Paths** | The shortest paths between two nodes, laid out left to right | From "Find a path from here" in a node's panel, or `/graph?from=…&to=…` |

A reader never starts with the whole graph drawn at once. The map summarises it, and
each neighbourhood is capped (see [limits](#limits-and-states)).

## Reading the picture

Colour is never the only signal. Every property below also has a shape, a line pattern
or a word, so the picture reads in greyscale and for colour-blind readers.

**Nodes: shape is the type.**

| Type | Mark | Type | Mark |
|---|---|---|---|
| Company | filled dot | Currency | target (dot in a ring) |
| Industry | ring | Data series | pill (hollow = definition only, filled = values stored) |
| Economic variable | diamond | Instrument | triangle |
| Country | hollow square | Market | inverted triangle |
| Sector | hexagon | | |

- **Size** grows with the square root of the node's degree, capped at 64 edges, so a hub
  cannot swamp the view. Degree is data coverage, not importance.
- **Nature** has its own ring: dashed for **fictional**, dotted for **sample** data. Real
  records have none.
- **Hidden connections**: a small plus marks a node with more edges than are drawn.
  Its panel says how many.

**Lines: pattern is the evidence status.**

| Status | Line |
|---|---|
| Evidence-backed | solid |
| Analyst-created | long dashes |
| Model assumption | dash–dot |
| Unverified | dotted, with round caps |

- **Width**: economic relationships (curated or assumed) are slightly heavier than
  structural links (classifications and record fields).
- **Arrows** show direction. `competes_with` has none.
- **Emphasis**: sky blue marks only what is selected or hovered, and its connections.
  It never encodes data.
- **Rings**: faint circles mark each hop from the centre.

The legend lists only the marks in the current view. Every line has a sentence form:
*"Deltrin Refining — operates in → Refined petroleum products"*, which appears in
tooltips, panels and the table view.

## Interactions

| Action | How |
|---|---|
| Search | By name, subtitle or identifier (ISO code, ISIC code, ISIN, MIC, provider series key). Results are fetched from the server 200 ms after typing stops, with earlier requests cancelled. An exact identifier comes first, and names shared by several nodes are marked *ambiguous*, with a subtitle to tell them apart |
| Focus | Choose a search result, a node on the map's list, or "Explore from here" in a panel |
| Select | Click a node or a line, or press Enter or Space on a focused node. The side panel shows its details |
| Expand | Double-click a node, press **E**, or use "Show neighbours (+n)" in its panel. This fetches up to 40 direct neighbours. "Hide its neighbours" collapses them again |
| Depth | 1, 2 or 3 hops around the focus |
| Show at most | 50, 100 or 150 nodes on the canvas (the API's own cap is 200 per request) |
| Filter | Node types, evidence statuses, relationship types (grouped as economic or structural), direction to follow (any, outgoing, incoming), and "Include illustrative". Filters are sent to the API, which does the traversal. The explorer does not hide lines itself. Hidden node kinds are not traversed either, and the filter's note says so. The centre always stays |
| Paths | Pick two nodes, a maximum number of hops (1–6) and a number of paths (1–10) |
| Navigate | Drag to pan; scroll, trackpad pinch or two-finger touch to zoom; the **+**, **−** and **0** (fit) keys or buttons. **Esc** clears the selection |
| History | Back and Forward restore exactly what was on screen (mode, focus, depth, expansions, selection, path query), without new requests. "Reset view" returns to the focus at depth 1, with no expansions, and fits it to the screen |
| Share | The address bar holds the focus or the path query, so a view can be bookmarked |
| Table | "Table" switches the canvas for two tables, nodes and relationships, with the same selection |

### Panels

- **Node:** subtitle, nature, identifiers with the record that stated each one, the
  source records it was built from, data availability for series and instruments (read
  live: "Definition only — no values stored" or the number of values and their period),
  relationships by type and direction, the **variables assumed to affect it**, entity
  resolution decisions, and quality checks.

  For a company, the variables are split into those stated **for the company itself**
  and those stated **for its industry**. The second group carries the note that
  companies in one industry can be affected very differently.
- **Relationship:** the sentence, **"Why this connection exists"** (the API's
  explanation), the evidence status and its definition, the qualifiers as the source
  states them (assumed polarity; strength labelled *illustrative*), every evidence record
  (source record, dataset and version, statement, rule, transformation, citation,
  retrieval and recording times), the validity period, and **"What it does not mean"**.
  A link is shown only if it is a web link.
- **Paths:** each path as a list of sentences, with the note that a path is not an
  influence or causal chain.

Pages elsewhere in the app link into the explorer: an entity's details ("Open in the
knowledge graph — identifiers, provenance and paths"), and the "Knowledge graph" line on
a series page and an instrument page, open the matching node.

## Layouts

Both layouts are deterministic, with no force simulation. The same data always gives the
same picture, so an expansion moves existing nodes only as much as it must.

- **Radial tree (Explore).** The explorer computes a breadth-first tree from the focus
  over the lines shown. Each node sits on the ring for its hop count, in the middle of a
  wedge of the circle proportional to the number of leaves below it. Children share
  their parent's wedge, so a subtree stays together and lines rarely cross. Each ring's
  radius grows until neighbouring nodes on it are at least 24 units apart (pixels at 100 %
  zoom). When a ring holds
  more than 10 nodes, their labels are written along the radius, pointing outwards.
  Cost: O(n log n).
- **Columns (Paths).** Position along the path runs left to right, and alternative
  paths are stacked vertically. All shortest paths have the same length, so a node has
  one column whichever path it is on.

Changes animate for 420 ms. With reduced motion (the system setting, or the app's own
motion setting) nodes move instantly.

**Labels.** In small views (up to 45 nodes) every node is labelled. In larger views,
labels are kept for the centre, its direct neighbours, the selection and anything
hovered or connected to it. On phones only the centre, the selection and the hovered
node are labelled, and the table view lists everything. Long names are shortened on the
canvas and shown in full in tooltips and panels.

## Limits and states

| Situation | What the explorer does |
|---|---|
| The graph has not been built | An empty state with the command to build it (`python -m app.graph build`) |
| The sources changed after the last build | A warning notice: the graph shows the data as it was, and names the rebuild command |
| A neighbourhood is larger than the node limit | "The node limit cut this neighbourhood short (left out: *n* company, …). Raise the limit, lower the depth or add filters." |
| More nodes than "Show at most" | "*n* nodes not drawn: the view is capped at 100 nodes" |
| An expanded node is hidden by a filter | "*n* expanded nodes hidden by the current filters" |
| An expansion fails | An alert with "Try again". The rest of the view stays usable |
| Nothing around the focus matches the filters | "No relationships around … match the current filters", with "Reset filters" |
| A node with no relationships | "… has no recorded relationships in the graph" |
| A link names a node that does not exist | One error message where the canvas would be, and a pointer to it in the panel. The Map mode stays available |
| No path within the hop limit | "No chain of at most *n* hops links A and B with the current filters. That means RUMIN holds no such chain of records — not that the two are unrelated in the world." |
| A path search hits its budget | "The search stopped at its limit of explored nodes (*n*); shorter filters or fewer hops may help." This is different from "no path" |

Answers are cached per request (up to 300), so going back or re-selecting costs nothing.
History keeps up to 60 steps.

## Accessibility

- **A table twin.** Everything the canvas shows can be read and operated from the table
  view, by keyboard or screen reader.
- **Keyboard.** Nodes are focusable, and Enter, Space, **E**, Esc and the zoom keys work
  on the canvas. Every control has a label, and the focus ring is visible.
- **Screen readers.** A live region announces what the view shows ("9 nodes · 18
  relationships within 1 hop of Deltrin Refining") and when it is loading. The canvas's
  label explains the keys. Notices use `status`, and failures use `alert`.
- **Colour.** Every encoding is redundant (shape, pattern or text). The explorer uses the
  app's design tokens, whose contrast was checked in both themes
  ([design system](../design-system.md#contrast-checked-wcag-22)): lines use
  `--viz-edge-economic` (3.0 : 1 light, 3.9 : 1 dark), marks `--viz-node`, and text the
  ink tokens. The faint hop rings are decorative.
- **Motion.** Reduced motion is respected.

## UI quality review

The explorer was reviewed in a real browser (Chromium via Playwright) at desktop
(1440 × 900), tablet (820 × 1180) and phone (390 × 844) widths, in light and dark themes,
against the running backend, with no console errors. A scripted walk-through checked
ten interactions: search and the address bar, expand with **E**, back and forward, reset,
the evidence-backed filter (only solid lines left), resetting filters, depth 2, picking
from the map, the edge panel, a missing node and an invalid key. Each criterion below is
one the Phase 3 brief asked for.

| Criterion | What was checked | Finding |
|---|---|---|
| Information hierarchy | The header states the build, whether it is current and "Not a map of the whole economy" before any picture. Then come the mode switch, the canvas or table, and the details panel. The overview ends with "Read this first" | Kept |
| Search usability | Server search by name, code or identifier; exact identifiers first; ambiguous names marked, with subtitles to tell them apart; "nothing matches" said in words; a keyboard combobox | Kept |
| Graph readability | The aggregate map first; capped neighbourhoods; rings by hop; line patterns for evidence; label rules | **Fixed:** labels were clipped at the canvas edge (padding now in screen pixels, capped at 20 % of the canvas); the map's bands were faint in dark mode (stronger token) |
| Details panel clarity | Node and edge panels in fixed sections: "Why this connection exists", evidence records, "What it does not mean" | **Fixed:** the path pickers showed raw keys (now names); a catalogued series never retrieved read "not provider data" (now "Not yet — no values have been retrieved"; found while writing this documentation) |
| Responsive behaviour | Three widths in both themes | **Fixed:** labels overlapped on phones (now only the centre, the selection and the hovered node) |
| Loading states | The page, panels and expansions ("Loading neighbours…") each show their own loading state; the status line adds "Loading…" | Kept |
| Error states | An unreachable API (with retry), a failed expansion (alert and "Try again"), a missing node | **Fixed:** "Try again" did not refetch; a missing node showed two error boxes (now one, with a pointer in the panel) |
| Empty states | Not built (with the command), no relationships, filters that remove everything, no path | **Fixed:** a filter that removed every line left a blank canvas (now a notice with "Reset filters") |
| Keyboard navigation | Tab through nodes; Enter, Space, **E**, Esc, **+**, **−**, **0**; the table view | Kept |
| Accessible labels | The canvas's label explains the keys; every node and control is labelled; a live status line; pressed states on mode buttons | Kept |
| Mobile usability | Filters fold into one "Filters" button; a compact legend; the phone label rule | Kept, after the label fix |
| Visual consistency | Shape for kind and sky blue for emphasis, as on the Universe page; the same tokens and components | **Fixed:** the footer still said "Phase 2" |

Nothing essential sits behind an extra layer: the evidence status is on every line (its
pattern), in the tooltip and in the panel, and a relationship's evidence is one click
away.

Measured rendering times are in [performance](performance.md#the-explorer).

## Tests

- `frontend/tests/graph/` (39 tests): the view model (merging, limits, expansions,
  spanning tree, path view), both layouts (determinism, rings, minimum spacing, wedges,
  columns, animation), the encoding (every type and status has a distinct mark, key
  parsing, links into the explorer), filters and history, and the edge panel's
  retrieval wording.
- `frontend/tests/pages/graphExplorer.test.tsx` (21 tests): the page against fixtures
  captured from a real backend, covering the map, search, selection, exposures,
  expansion and collapse, retry, history, filters, evidence, paths, the table view,
  not-built and stale graphs, errors, invalid keys and phone labels.
- `frontend/tests/integration/graph.integration.test.ts` (13 tests): the service layer
  against a live API, in the smoke test (see [`docs/testing.md`](../testing.md)).
