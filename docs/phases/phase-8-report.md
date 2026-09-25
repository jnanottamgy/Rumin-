# Phase 8 report — 3D Financial Universe

Phase 8 adds the **3D Financial Universe** (`/universe/3d`): RUMIN's knowledge graph in three
dimensions, as an analytical view over the existing, read-only APIs. It draws the records and
relationships the graph holds, opens every record's provenance and evidence, lays a stored
scenario execution over the graph, and computes nothing. The plan is in
[phase-8-plan.md](phase-8-plan.md); the guides are in [docs/universe](../universe/README.md).

## At a glance

| | |
|---|---|
| **What it is** | A view over the Phase 3 knowledge graph and the Phase 5 stored executions. No backend change: every read already existed |
| **Modes** | Universe (the whole build, within a budget) · Neighbourhood (a focus, grown one expansion at a time) · Paths (shortest paths between two records) · a scenario overlay on any of them |
| **Encoding** | Height is kind (five strata), shape is kind, a halo is nature, line pattern is evidence status, weight is category, sky blue is emphasis only. Nothing is sized or placed by importance |
| **Inspection** | The 2D explorer's node and edge panels: identifiers, sources, entity resolution, quality checks, relationships, evidence records, what an edge does not mean |
| **Overlays** | Only stored, **completed** executions: stated changes, the simulated entity, relationships a model propagated (rule, coefficient, lag, model) or only cited, relationships no model simulates, and the stored line results |
| **Accessibility** | A list twin and fallback, a keyboard model for the canvas, visible focus, polite announcements, reduced motion, both themes, `axe-core`: no violations in seven views |
| **Performance** | Rendering on demand (no idle frames), about twenty draw calls at any size, first frame 0.5–0.6 s after navigation; measured on software WebGL only |
| **Dependency** | `three` 0.186.1 (and `@types/three` for development), loaded only by this page |
| **Tests** | Frontend 380 (+59), integration 60 (+3), backend 1,058 + 1 skipped (unchanged) — see [quality gates](#quality-gates) |

## 1. Inspection of Phases 1–7

The inspection is recorded in the [plan](phase-8-plan.md#1-inspection). In short: the graph
(50 nodes and 97 edges in the sample build, one component, 65 illustrative edges) and its API
already served everything a 3D view needs, read-only and bounded; `useGraphExplorer` already
held the exploration state (focus, depth, expansions, selection, paths, filters, history); a
stored execution already recorded its modelled pathway with graph edge keys, the edges no
included model simulates and its results. Nothing needed to be added to the backend. The
baseline before the phase: backend 1,058 passed and 1 skipped (SQLite and PostgreSQL 16),
frontend 321, smoke 57, CI green.

## 2. What was built

- **The page** (`pages/UniverseSpacePage.tsx`, lazy route `/universe/3d`): mode and stage
  switches, Back and Forward, depth and visible-node limit, search, filters, the scenario
  overlay picker, *Reset view*, the status line and a polite selection summary, *Moving
  around* (controls) and *How to read the universe* (legend), the details panel, the list
  view, and loading, empty, partial, error, too-large, not-built and stale states. The URL
  mirrors what is shown (`?focus=`, `?from=&to=`, `?execution=`).
- **The feature** (`features/universe/`, 4,400 lines with the page): strata, a deterministic
  and incremental 3D layout, the scene model, camera maths, keyboard navigation, name
  placement, the overlay model, the whole-build and overlay loaders, the canvas host and the
  Three.js renderer ([architecture](../universe/architecture.md)).
- **Partial-data notices shared with the 2D explorer** (`features/graph/ViewNotices.tsx`,
  moved out of the explorer's page): no relationships (or none matching the filters), a
  neighbourhood cut short by the node limit, nodes not drawn, expansions hidden by filters, a
  failed expansion with *Try again*; and, in Universe mode, *Filters are on: … of … shown*.
- **Links in and out**: *Open in 3D* from the 2D explorer (keeping the focus or path); *The
  knowledge graph in 3D* from the Universe page; *See it in the 3D universe* on a completed
  execution in the Scenario Lab; *Shortest paths between them in 3D* on each of the Analyst's
  relationship paths; from a node, *Open in the 2D explorer*, *Open in Financial
  Intelligence* and *Ask the Analyst about it* — the last puts a drafted question in the
  Analyst's box and **never sends it** (`handedQuestion`, read as text only).
- **Fixtures captured from a real backend** (`backend/scripts/capture_universe_fixtures.py`)
  and a measurement script (`frontend/scripts/measure-universe.mjs`).

## 3. Key technical and design decisions

Recorded as decisions [73–78](../decisions.md#73-plain-threejs-loaded-only-with-the-3d-page):

| # | Decision | Why |
|---|---|---|
| 73 | **Plain Three.js**, behind a small renderer contract, loaded only when the canvas mounts and WebGL 2 is present | A WebGL scene graph, instancing and shaders without writing a renderer; React Three Fiber adds a reconciler for a scene this simple. Meaning stays in tested plain data (`scene.ts`), the host is testable with a stand-in, disposal is explicit |
| 74 | **Height is kind, never importance** (data, drivers, industries, companies, places); size by kind only | Every channel competes with perspective; a stable categorical height gives a frame of reference without implying magnitude |
| 75 | **The whole build only within a budget** (≤ 500 nodes, ≤ 2,500 edges); otherwise start from a search and grow by neighbourhoods | Layout and names run on the main thread; the budget keeps the page responsive. The sample (50 nodes) justifies showing it whole by default, as the brief allows when the data and its performance profile justify it |
| 76 | **Overlays only from stored, completed executions**; roles from the pathway, figures only in the panel | An overlay that inferred impacts from graph edges or recomputed anything would turn recorded or assumed links into claimed effects |
| 77 | **The list is the canvas's twin; the keyboard operates the canvas** | Nothing may depend on seeing or pointing at the canvas |
| 78 | **Rendering on demand; names in the DOM, placed by priority** | An analytical view should cost nothing while it is read; DOM names stay sharp and never pretend a name that does not fit was written |

Other choices: the layout is seeded `d3-force` (already a dependency) in the horizontal plane
with per-stratum repulsion, previous positions fixed and new nodes started beside the node
that brought them in; edges are one instanced quad each with a screen-space pattern shader
(so dashes read the same near and far); picking is done in screen space on the same frame's
projections; colours are read from the design tokens and re-read on a theme change.

## 4. How the explorer uses actual graph data

- **Universe**: every node and edge of the current build, read 500 per page through the graph
  API (`GET /graph/nodes?sort=name`, `GET /graph/edges`), only when the build's counts are
  within the budget; a build that grows past the budget while it is read is shown partially,
  with a notice. **Neighbourhood** and **Paths**: the 2D explorer's own requests, limits and
  cache.
- **Filters** apply to the API requests, and to the whole build in the browser with the API's
  meaning (an illustrative relationship is left out, not the records it joins).
- **Inspection**: node and edge details from the graph API, shown as the 2D explorer shows
  them; a missing field is shown as unavailable.
- **Overlays**: `GET /scenario-executions/{id}`, then — only when it completed — its
  `/pathways` and `/results`. Pathway identifiers are mapped to graph keys
  (`change:var_x` and `model:variable:var_x` → `variable:var_x`); model outputs and result
  lines map to none. Figures are the stored strings, shown only in the panel.
- **No data is invented.** The sample's companies are fictional and 65 of its 97
  relationships illustrative; the page says so (header badges, the details hint, *Fictional
  company*, *Simulated*, *Not a forecast*). The integration test checks, against a live API,
  that every overlay record is a current node, every marked relationship a current edge
  between the records it names, and every figure the stored result.

## 5. Installed skills inspected and used

| Skill | Inspected | Used | Contribution |
|---|---|---|---|
| `dataviz` | Read in full at the start of the phase (the procedure and its references: choosing a form, the colour formula and validator, marks and anatomy, interaction, components, anti-patterns) | **Yes**, throughout | The form (a network: identity and connection, not magnitude — so no size, height or brightness encodes a quantity); colour by job (one accent for emphasis, no categorical hues, text in ink tokens); thin marks and selective direct labels with collision management; a hover layer on every node and line; a legend and a table twin; and *render it and look at it*, which drove the Chromium review and its fixes. No categorical palette exists, so the palette validator had nothing to validate ([encoding](../universe/encoding.md#how-the-dataviz-skill-was-applied)) |
| `code-review` | Invoked on the staged Phase 8 change (medium effort) | **Yes**, before committing | Four correctness findings, each verified in the code, fixed and covered by a regression test ([§ 8](#8-defects-found-and-fixed-during-the-phase)) |
| `frontend-design` | Named in the Phase 7 plan; loading it was attempted | **Unavailable** | The Skill tool reports it unknown in this session |
| 3D, spatial navigation, motion, accessibility, responsive design, frontend performance, onboarding | Looked for in the installed list | **None installed** | Sound practice instead: WCAG 2.2 criteria, `prefers-reduced-motion`, measured budgets, `axe-core` |
| `kapture-browser-automation` | Description read | No | It drives Chrome through an extension this environment does not have; the review used Playwright with the pre-installed Chromium |
| `run` | Description read | No | The app was launched and driven with Playwright scripts directly (production build, live API) |
| `artifact-design`, `artifact-diagramming`, `artifact-capabilities` | Descriptions read | No | They govern pages published as claude.ai Artifacts, not an application's interface |
| `security-review`, `simplify`, and the document, configuration and workflow skills (`docs`, `docx`, `pdf`, `pptx`, `xlsx`, `skill-creator`, `import-memory`, `morning`, `session-start-hook`, `update-config`, `keybindings-help`, `fewer-permission-prompts`, `loop`, `claude-api`, `workflow-authoring`, `init`) | Descriptions read | No | Not about this phase's interface; `security-review` is planned for Phase 10, whose subject it is |

## 6. Tests run and results

| Suite | Result | What Phase 8 added |
|---|---|---|
| Frontend (Vitest, jsdom) | **380 passed** (34 files) | `universe/model` (22: strata, layout, camera, keyboard, names, scene, overlay, filters), `universe/canvas` (13: the host with a stand-in renderer — picking, hover, drag, wheel, keyboard, motion, emphasis, disposal, context loss, stability, a flight that outlives a scene change, a hovering mouse then a touch), `pages/universeSpace` (23: through the real route table against captured fixtures — see [testing](../testing.md#frontend-frontendtests)), plus assertions on the Scenario Lab, Analyst and 2D explorer links |
| Integration (live API) | **60 passed** | `universe.integration.test.ts` (3): the whole build read page by page and matching the build's counts and the contract; the real build laid out and marked the same way twice; the reference scenario executed and laid over, every record and relationship present, every figure the stored result |
| Backend (pytest) | **1,058 passed, 1 skipped** on SQLite and on PostgreSQL 16 | No application code changed; one Phase 7 test made independent of the clock ([§ 8](#8-defects-found-and-fixed-during-the-phase)) |
| Lint, format, types, contract | Clean (`ruff`, `mypy`, Biome, `tsc`, the OpenAPI snapshot) | — |

The Chromium review is described in [§ 7](#7-browser-review-accessibility-and-performance);
it is not automated.

## 7. Browser review, accessibility and performance

Run on a production build against a live API in headless Chromium 141 with **software** WebGL
(SwiftShader); no GPU was available.

- **Visual review**: the universe, a selection, an overlay, a neighbourhood, paths, the
  legend and help, the list and a filtered view, at 1440, 900 and 390 px in both themes —
  14 captures, no console error or warning, no sideways scrolling.
- **Keyboard**: the canvas is reached in one tab stop (27th on the page), shows a visible
  focus ring, arrow keys move the selection by screen direction with the selection announced,
  E opens a neighbourhood with focus kept, Escape clears.
- **`axe-core` 4.13** (run in the browser, not added to the project): no violations in the
  universe (light, dark), an overlay (light, dark), a neighbourhood, paths and the list.
- **Motion**: a fly-to draws 19 frames with motion allowed and 1 under reduced motion; no
  frame is requested while idle.
- **Performance** ([details](../universe/performance.md)): first frame 497–615 ms after
  navigation (median of five, cold context); 19 draw calls and 20,002 triangles for the whole
  sample; CPU per frame while turning median 1.2 ms. SYNTHETIC graphs: first layout 71 ms
  (50 nodes), 514 ms (500 nodes, the budget), 1.7 s (2,000); an expansion at the budget
  about 0.3 s; frame on software WebGL 32 ms, 384 ms and 1.2 s; draw calls 16–18 at every
  size; a filter change 1.5–96 ms.
- **Memory and cleanup**: over 50 client-side visits, a heap-snapshot diff shows no retained
  universe object (no detached DOM node, React fiber, typed array or Three.js object); the
  WebGL context is lost after disposal; no canvas is left behind.

## 8. Defects found and fixed during the phase

| Found by | Defect | Fix |
|---|---|---|
| Page tests | A whole-number change was written without its trailing zero: **+20 % read "+2 %"** (a regular expression stripped zeros that `formatRounded` never adds) | The expression removed; the test asserts +20 %, +5 % and +0.5 percentage points |
| Chromium review | **No relationship line was drawn**: the edge shader did not compile (`half` is reserved in GLSL ES) | Renamed; the review now fails on any console error |
| Chromium review | The canvas's **focus ring was invisible** (an inset shadow is painted beneath the canvas) | An inset outline |
| Chromium review | **Focus was lost** after E or Enter: the canvas unmounted while the next view loaded, so Escape did nothing | The previous view stays mounted, the status says it is loading, the camera waits for the new focus; a regression test |
| Chromium review | Names covered nodes, overlay records went unnamed in dense areas, strata names were clipped on phones, the first framing was loose | Names start beyond the node's edge and keep off other nodes; overlay, selection and focus names may move a line or cover a node; strata names are kept inside; framing fits every point |
| `axe-core` | The overlay's results table scrolled without being reachable from the keyboard | A named, focusable region |
| Measurement | Triangles about 1,000 per node; 0.75 s first layout at the budget; 19.5 ms name placement at 2,000 nodes | A coarser outline mesh (−49 to −55 % triangles), fewer layout ticks for larger views (748 → 514 ms), a grid for name obstacles (→ 11.1 ms) |
| Hanging test run | The whole-build hook returned a new object on every render, so the filtered view, the scene and a redraw were recomputed each time (and looped once the page held the previous view) | The hook's result is memoised |
| Self-review | Filters that excluded every record showed **"Loading the universe…" forever** — a fake loading state | *No records match the filters* with *Reset filters* |
| Self-review | *Include illustrative* also removed every non-real node in Universe mode, unlike the API (which removes illustrative relationships only) | The API's meaning, with a unit test |
| Self-review | The partial-data notices of the 2D explorer (node limit, failed expansion, hidden expansions) were missing in 3D | The notices moved into a shared component used by both |
| `code-review` | Frames scheduled during a flight kept an old draw closure, so names and picking positions could reflect the scene before a selection | Every frame calls the latest draw; a regression test that fails without the fix |
| `code-review` | An overlay opened while its execution ran stayed "not completed" until a reload | Re-read at the server's interval (0.25–5 s) until final, with *Check now*; a failed or cancelled one says it has nothing to lay over |
| `code-review` | *Reset view* in Neighbourhood mode also discarded the reader's expansions and depth | Camera only, like R; Back restores earlier views |
| `code-review` | A hovering mouse was tracked as a touch, so a later one-finger drag zoomed | Only pressed pointers are tracked; a regression test that fails without the fix |
| Backend suite on SQLite | A **Phase 7 test failed when the clock read 02:45**: it looked for the searched "45" and "2031" in the whole stored evidence, whose read time comes from the clock | The test now uses a fixed clock that holds those very figures (2031-01-01 02:45:45.452031), checks the read time is the clock's, and looks for the planted words everywhere else — so it cannot pass or fail by the time of day |
| Measurement | A first leak measurement suggested about 0.1–0.4 MB retained per visit (on the 2D explorer too) | The measuring script's own element handles retained the pages; with them released, nothing is retained. Recorded in [performance](../universe/performance.md) |

## 9. Deviations from the plan

- **Phones get the 3D view by default**, not the list first: the review found it legible at
  390 px; the list is one tap away. The panel moves under the canvas below 64 rem (planned:
  60 rem), as in the 2D explorer.
- **An overlay's missing records are counted, not fetched**: the panel says how many are not
  in the view and offers the whole universe.
- **Measurements went to 2,000 nodes and 8,000 edges**, not the 20,000-company networks of the
  graph benchmarks: the universe never draws a build that large at once, and neighbourhoods
  of large builds are the graph API's, already benchmarked.
- **Scenario Lab executions only** are offered as overlays; Phase 4 simulation runs are not
  (they carry no graph build or pathway keyed to graph edges). `overlay.ts` is the extension
  point.
- **No transitions for expansion or filtering**: new records appear in place (beside the
  record that brought them in); only the camera moves.

## 10. Security and privacy

No server surface was added: Phase 8 changed no backend code, schema or route. Names from the
database are written with `textContent` and React text, never as HTML. Browser work is bounded
(the budget, the explorer's limits, 36 names, a pixel ratio of 2, 6,000 remembered
positions), GPU resources are released on leaving, and a question handed to the Analyst is
text that is never sent by itself. `npm audit` reported no vulnerability after adding
`three` ([security](../security.md#3d-universe-phase-8)).

## 11. Completion gate

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Integrated with the actual graph data and APIs | **Met** | Reads the graph API only; integration test against a live API; fixtures captured from a real backend |
| 2 | Core exploration, navigation and inspection work end to end | **Met** | Search, focus, expand and collapse, filters, node and edge panels, paths, camera controls, Back and Forward, progressive neighbourhoods: page tests and the Chromium walk-through |
| 3 | Overlays use only real supported outputs | **Met** | Completed stored executions only; roles from the pathway; figures from the results, compared with the stored results in the integration test |
| 4 | Polished, accessible, responsive, consistent | **Met, with stated limits** | Three widths × two themes reviewed; `axe-core` clean in seven views; keyboard model; no screen-reader session with a user; software WebGL only |
| 5 | Performance checked against realistic sizes | **Met, with stated limits** | The real sample through the page; SYNTHETIC graphs to four times the budget; no hardware GPU measured; the layout runs on the main thread |
| 6 | Tests pass, or failures documented | **Met** | [Quality gates](#quality-gates) |
| 7 | Nothing silently removed or broken | **Met** | Phases 1–7 suites pass; the 2D explorer's notices moved into a shared component with its tests unchanged |
| 8 | Documentation updated | **Met** | `docs/universe/` (8 guides), decisions 73–78, README, architecture, design system, testing, security, roadmap, known limitations |
| 9 | Report written, with the skills used | **Met** | This report, [§ 5](#5-installed-skills-inspected-and-used) |

## 12. Known gaps and limitations

See [universe/limitations.md](../universe/limitations.md). The ones that matter most: frame
rates on real GPUs are unmeasured; the layout blocks the main thread for about half a second at
the budget; one overlay at a time, of Scenario Lab executions only; relationships cannot be
selected from the keyboard on the canvas (they are in the node panel and the list); the visual
and accessibility review is not automated.

## 13. How to run and verify

```bash
make install && make migrate seed catalog graph
make backend                       # API on http://127.0.0.1:8000
make frontend                      # http://127.0.0.1:5173/universe/3d
cd frontend && npm test            # unit, canvas and page tests
make smoke                         # fresh database, live API, the integration suite
cd frontend && node scripts/measure-universe.mjs   # layout, scene, filter and name timings
```

To see an overlay, execute a scenario in the Scenario Lab and follow *See it in the 3D
universe*. Without WebGL 2 the page shows the list and says why.

## 14. Recommendations for Phase 9

Phase 9 (advanced simulation and validation) should build on the engine and the Lab, not on
this view; but two things connect them: an execution's month-by-month values and stress cases
could become overlays once validated (the extension point is `overlay.ts`), and any new model
relationship must keep carrying a graph edge key so the universe can show where it acts.

## Quality gates

| Check | Result |
|---|---|
| `make check` (ruff, mypy on 230 files, Biome, `tsc`, both suites, OpenAPI snapshot), backend on PostgreSQL 16 | Passed: frontend 380, backend 1,058 passed and 1 skipped (the skipped test needs a model key), contract unchanged |
| Backend on SQLite | 1,058 passed, 1 skipped — after the clock-dependent test was fixed (it failed once, at 02:45) |
| `make smoke` (fresh database, live API, integration suite) | Passed: 60 tests |
| `npm audit` | No vulnerability |
| Chromium review, keyboard pass, `axe-core` | 14 captures without a console error or warning; focus kept; no violations in seven views |
| CI | Recorded after the push |
