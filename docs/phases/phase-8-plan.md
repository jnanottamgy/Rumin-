# Phase 8 plan — 3D Financial Universe

Written after inspecting Phases 1–7, running their tests (backend 1,058 passed and 1
skipped on SQLite and PostgreSQL 16; frontend 321; smoke 57; CI run #25 green) and the
installed skills.

## 1. Inspection

| | Finding |
|---|---|
| **The knowledge graph (Phase 3)** | Nine node types, fifteen edge types, four evidence statuses, builds with freshness. The current build of the curated sample holds **50 nodes and 97 edges** in one connected component: 12 companies (fictional), 8 industries, 6 sectors, 3 countries, 3 currencies, 7 economic variables, 11 data series; 24 edges evidence-backed, 32 analyst-created, 41 model assumptions; 65 illustrative. It is small and sparse |
| **Graph API** | Everything the 3D view needs exists and is read-only: overview (build, freshness, type map, metrics), types (vocabulary, evidence-status definitions), node search (partial, by identifier, ≤ 500 per page), node detail (identifiers, sources, resolution, relationships by type, issues, data availability, exposures), neighbourhood (≤ 3 hops, ≤ 200 nodes, with what the limit left out), edges (≤ 500 per page), edge detail (every evidence record, rule, dataset, citation, what the edge does not mean), shortest paths (≤ 10 paths, ≤ 6 hops), components, builds |
| **The 2D explorer (Phase 3)** | `useGraphExplorer` already holds the exploration state: focus, depth, expansions in order, selection, path queries, filters, a visible-node limit, back and forward over snapshots, cached answers and retry. `view.ts` derives what to draw; `encoding.ts` decides what marks mean (shape by type, ring by nature, fill by data availability, line pattern by evidence status, arrowhead by direction, weight by category, sky blue for emphasis only). Panels for nodes and edges, search, filters, legend, table and path finder are separate components |
| **Simulations and the Scenario Lab (Phases 4–5)** | A stored execution records the graph build it planned against and its freshness, the scenario's changes, the entities the graph says are exposed (with the edges and the models that simulate each tie), and — through `GET /scenario-executions/{id}/pathways` — its **modelled pathway**: links that carry a graph edge key, marked `transmission` (propagated by a model rule, with its coefficient and lag) or `cited` (context only, no values), and the graph edges around the changes that **no included model simulates**, with the reason. Results hold each line's baseline, change and percent change |
| **Intelligence and the Analyst (Phases 6–7)** | Node keys (`company:…`, `variable:…`) are shared across the product; the Analyst's paths block carries them; the Analyst page takes a conversation from the URL but no drafted question |
| **Frontend** | React 19, TypeScript, Vite, `d3-force`; no 3D library. Tests run in jsdom (no WebGL). Chromium with software WebGL (SwiftShader) is available for the visual review and frame-time measurements. The Universe module (Phase 1, a 2D network of the sample tables) says *3D universe planned for Phase 8* |
| **What is missing** | A 3D renderer; a layout in three dimensions; an overlay of a stored execution on the graph; links from other pages into a 3D view; a drafted question for the Analyst. **No backend change is needed**: every read exists |

**Skills.** The bundled `dataviz` skill was read in full (choosing a form, the colour
formula and its validator, marks and anatomy, interaction, components, anti-patterns) and
applies to the 3D view's encoding, legend, hover, table twin and colour roles. The
`frontend-design` skill named in the Phase 7 plan could **not** be loaded in this session
(the skill tool reports it unknown); no 3D, motion or accessibility skill is installed.
`kapture-browser-automation` needs a browser extension this environment does not have, so
the visual review uses Playwright with the pre-installed Chromium. The document skills
(docs, docx, pdf, pptx, xlsx), `skill-creator`, `import-memory` and `morning` do not apply
to an application's interface.

## 2. What the 3D universe is

A **view over the knowledge graph**, not a new model: read-only, drawn from the graph API
and, for overlays, from stored executions. It is reached from the Universe page (which
keeps its 2D network), the graph explorer, the Analyst's paths and the Scenario Lab.

| Mode | What is shown | Loaded |
|---|---|---|
| **Universe** | The whole current build | Only when it is within the budget (≤ 500 nodes and ≤ 2,500 edges: at most six requests); otherwise the page starts from a node |
| **Neighbourhood** | A focus, its neighbours to a chosen depth, and the neighbours of nodes expanded one by one | Progressively, by the explorer (≤ 150 visible nodes, 40 per expansion) |
| **Paths** | The shortest paths between two nodes | One request |
| **Scenario overlay** (on any mode) | A stored execution: the variables it changed, the entity it simulated, the relationships a model **propagated**, those it **cited**, and those around its changes that **no model simulates**; its line results | The execution, its pathway and its results (three requests); missing nodes of the overlay are read by key |

### Spatial encoding

- **Strata by kind** (vertical position): data series, instruments and markets at the top;
  economic variables; sectors and industries; companies; countries and currencies at the
  base. The order follows the Phase 1 network's columns (drivers → industries → companies
  → places), so an assumed effect reads downwards. Each stratum is labelled at its edge. Kind
  is also given by **shape** and in every panel and the list: position is never the only
  channel.
- **Within a stratum**, a seeded force layout places connected nodes near each other
  (`d3-force`, already a dependency, in the horizontal plane; the vertical position is
  fixed). The same data always gives the same picture. When the view grows, **nodes already
  placed keep their positions**; new ones start beside the node that brought them in.
- **Nothing is sized by importance.** Node size is by kind only. (In 2D, size also grows
  gently with a node's number of edges; in 3D, perspective already changes apparent size, so
  a second size channel would be unreadable.) Depth, height and brightness encode no
  magnitude.

### Marks (the 2D encoding, in three dimensions)

| Channel | Encodes |
|---|---|
| Shape | Node type: company sphere, industry ring (torus), sector hexagonal prism, country cube, currency ring with a core, economic variable octahedron, data series capsule, instrument cone, market inverted cone |
| Fill | Neutral ink; hollow kinds and series or instruments with no stored values are drawn as outlines |
| Halo | Nature: a dashed ring for fictional records, a dotted ring for sample data, none for real |
| Line pattern | Evidence status: solid (evidence-backed), dashes (analyst-created), dash-dot (model assumption), dots (unverified) — as in 2D, never colour |
| Line weight | Category: economic relationships heavier than structural ones |
| Arrowhead | Direction |
| Sky blue | Emphasis only: the selection and what it connects to; in an overlay, the modelled pathway |

Overlay roles add labelled marks, never new colours for data: **propagated** (sky blue,
solid, heavier), **cited** (sky blue, dashed), **not simulated** (the edge's own pattern,
dimmed, marked in the list). Changed variables and the simulated entity carry a label
(*Changed in the scenario*, *Simulated entity*). Values appear only in the overlay panel,
labelled *Simulated* or *Hypothetical input*, from the stored execution.

## 3. Interaction

- **Camera**: rotate (drag), pan (right-drag or Shift+drag), zoom (wheel or pinch), focus a
  node (double-click, or *Focus*), **reset view**, and a fly-to of 480 ms when the focus
  changes — none under reduced motion (the camera jumps). The camera never moves on its own.
- **Keyboard** (the canvas is focusable, with its keys described): arrow keys move the
  selection to the nearest node in that direction on screen; Enter focuses it; E expands,
  C collapses; Shift+arrows rotate; + and − zoom; R resets the view; Escape clears the
  selection. Back and Forward (the explorer's history) restore what was on screen.
- **Hover and selection**: hover shows a tooltip (name, kind, nature) and highlights the
  node's relationships; a click selects a node or an edge and opens its panel — the 2D
  explorer's node and edge panels, with provenance, evidence and identifiers.
- **Search, filters, depth, visible-node limit, paths**: the 2D explorer's components and
  state, unchanged.
- **Links out**: open the same focus in the 2D explorer; ask the Analyst about a node (a
  drafted question, never sent without the person); open a company or industry in
  Financial Intelligence; open an overlay's execution in the Scenario Lab.

## 4. Accessibility, fallbacks and responsiveness

- **The list is the twin.** A *List* view shows every visible node and edge with kind,
  nature, evidence status and links, and is the default when WebGL is unavailable, when the
  context is lost, or when the person prefers it (remembered on the device).
- The canvas has a text summary (what is shown, the selection) announced politely; the
  selection is always also in the side panel as text.
- Reduced motion: no camera animation. No motion is decorative.
- Theme: colours are read from the design tokens, so the scene follows light and dark.
- Layout: side panel beside the canvas on wide screens; below it under 60rem; on phones the
  list is offered first and the canvas is full width.

## 5. Architecture

`frontend/src/features/universe/`:

| Module | Role | Tested |
|---|---|---|
| `strata.ts` | Kind → stratum | unit |
| `layout3d.ts` | Deterministic, incremental layout (strata + seeded force) | unit |
| `scene.ts` | Render data from the view, the layout, the selection and the overlay: instances per shape, edge segments with pattern, weight and emphasis, halos, labels to show | unit |
| `camera.ts` | Orbit camera maths, framing, fly-to interpolation | unit |
| `keyboard.ts` | Arrow-key navigation by screen direction | unit |
| `labels.ts` | Label priority and collision | unit |
| `overlay.ts` | A stored execution's pathway and plan → graph keys and roles | unit, on fixtures captured from a real backend |
| `useUniverse.ts` | Whole-build loading within the budget; overlay loading | page tests |
| `renderer.ts` | Three.js: instanced meshes, a pattern shader for edges, arrowheads, halos, picking, rendering on demand, disposal, context loss | Chromium review and measurements |
| `UniverseCanvas.tsx` | React host: lazy import of the renderer, resize, pointer and keyboard, labels, tooltip, WebGL detection | page tests with a stand-in renderer |

`pages/UniverseSpacePage.tsx` at `/universe/3d` (lazy route). The renderer factory is
injected, so page tests run with a stand-in and the real renderer only in a browser.

**One new dependency: `three`** (and its types). React Three Fiber was considered: it adds a
reconciler and more packages for a scene this simple, and the explorer's pattern is a pure
model feeding a renderer; plain Three.js keeps the scene explicit, its disposal visible and
its draw calls few. It loads only with the 3D page.

**Performance budgets** (measured in Chromium with software WebGL, and on the pure work in
Node): the sample universe renders at interactive frame rates; 2,000 nodes and 8,000 edges
(synthetic, for measurement only) stay usable; one draw call per shape and one for all
edges; rendering only when something changes; the device pixel ratio capped at 2; every
geometry, material and the renderer disposed on leaving the page.

## 6. Testing

- Unit: strata, layout (determinism, stability under growth), scene data, camera maths,
  keyboard navigation, labels, overlay mapping, the universe budget.
- Page (jsdom, stand-in renderer, fixtures captured from a real backend): the universe and
  neighbourhood modes, search → focus, selection → panels, expand and collapse, filters,
  paths, the overlay's identity, roles and values, the list twin, WebGL unavailable,
  loading, empty, partial and error states, links out.
- Integration (live API): the reads the page makes.
- Chromium review: screenshots at 1440, 900 and 390 px in both themes; frame times and
  memory on the sample and on synthetic graphs.
- Regression: every suite of Phases 1–7.

## 7. Order of work

1. Dependency and ADR; pure modules with tests.
2. Renderer and canvas host; the page, route, module entry and links.
3. Overlay; fixtures captured from a real backend; page and integration tests.
4. Chromium review, accessibility pass, measurements; fixes.
5. Documentation (`docs/universe/`), decisions, the Phase 8 report; commit, push, CI.
