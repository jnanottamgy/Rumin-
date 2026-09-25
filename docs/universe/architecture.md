# Architecture

The 3D universe is a frontend feature over existing, read-only APIs. **No backend change was
needed**: the graph API already served everything (overview, vocabulary, node pages, edge
pages, node and edge details, neighbourhoods, paths), and the Scenario Lab already stored each
execution's modelled pathway and results.

```
UniverseSpacePage (/universe/3d)
 ├─ useGraphExplorer (Phase 3)       focus, depth, expansions, selection, paths, filters, history
 ├─ useWholeGraph                    the whole build, page by page, within the budget
 ├─ useScenarioOverlay               a stored execution + its pathway + its results
 ├─ universeView / explorer view     → GraphView (the shape the 2D panels and table read)
 ├─ NodePanel · EdgePanel · PathFinder · GraphSearch · GraphFilters · GraphTable (Phase 3)
 ├─ OverlayPicker · OverlayPanel · UniverseLegend
 └─ UniverseCanvas                   layout, scene, camera, pointer, keyboard, names, tooltip
      └─ renderer (Three.js, lazy)   instanced marks, edge shader, halos, strata rings
```

## Modules — `frontend/src/features/universe/`

| Module | Role | Tests |
|---|---|---|
| `strata.ts` | Node kind → stratum (height) | unit |
| `layout3d.ts` | A seeded, deterministic force layout in the horizontal plane (`d3-force`), with the height fixed by stratum; nodes already placed keep their positions; new ones start beside the node that brought them in | unit (determinism, stability under growth) |
| `scene.ts` | What the renderer draws, decided without it: one record per node and per edge with position, shape, size, outline, halo, line pattern, weight, arrowhead, tone (normal, emphasis, dimmed) and overlay role; which names matter most | unit |
| `camera.ts` | Orbit camera maths: rotate, zoom, pan, framing (fit every point from the default angles), fly-to interpolation | unit |
| `keyboard.ts` | Keys → actions; the nearest node in a screen direction | unit |
| `labels.ts` | Which names to write and where: priority, sides, collisions, obstacles, the strata's names | unit |
| `overlay.ts` | A stored execution, its pathway and its results → graph keys, node roles, edge roles, stated changes, stored lines | unit, on fixtures captured from a real backend |
| `universeView.ts` | The explorer's filters applied to the whole build; the whole build as a `GraphView` | page and integration |
| `useUniverseData.ts` | `readWholeGraph` (paged, budgeted), `useWholeGraph`, `useScenarioOverlay` | page and integration |
| `rendererTypes.ts` | The contract between the host and the renderer (types only, so the host never imports Three.js) | — |
| `renderer.ts` | Three.js: one instanced mesh per shape (fill and outline hull), a screen-space edge shader (pattern, width, anti-aliasing, near-plane clipping), arrowheads, halo billboards, strata rings, projection, disposal, context loss | Chromium review and measurements |
| `webgl.ts` | WebGL 2 detection without loading Three.js | page tests |
| `UniverseCanvas.tsx` | The React host: lazy renderer, size and pixel ratio, rendering on demand, the camera, picking, pointer, wheel, keyboard, names, tooltip, theme colours | canvas tests with a stand-in renderer |
| `UniversePanels.tsx` | The legend, the overlay picker and the overlay panel | page tests |

The page is `frontend/src/pages/UniverseSpacePage.tsx`, a lazy route.

## Data flow

1. The page reads the graph overview and vocabulary (the same cached resources as the 2D
   explorer).
2. **Universe mode**: when the build is within the budget, `readWholeGraph` reads every node
   (`GET /api/v1/graph/nodes?limit=500&offset=…&sort=name`) and every edge
   (`GET /api/v1/graph/edges?limit=500&offset=…`), at most six requests. A build that grows
   past the budget while it is read is shown partially, with a notice.
3. **Neighbourhood and Paths**: `useGraphExplorer`, unchanged from Phase 3 — the same
   requests, limits, cache and history as the 2D explorer.
4. **Overlay**: `GET /scenario-executions/{id}`; if and only if it is *completed*, its
   `/pathways` and `/results`. `buildOverlay` maps pathway node keys to graph keys
   (`change:var_x` and `model:variable:var_x` → `variable:var_x`; model outputs and result
   lines map to none) and keeps the results' strings as stored.
5. `UniverseCanvas` lays the view out (`layout3d`), builds the scene (`buildScene`), hands it
   to the renderer with the palette read from the design tokens, and draws on demand.

## The renderer contract

The host talks to the renderer only through `UniverseRenderer` (`setScene`, `setOrbit`,
`resize`, `render`, `project`, `info`, `dispose`). That keeps every decision that carries
meaning in plain, tested data (`scene.ts`), lets the tests run the host with a stand-in
renderer (jsdom has no WebGL), and keeps Three.js out of the page's own chunk:

- `webgl.ts` checks for WebGL 2 first; without it the host reports `webgl` and the page shows
  the list — Three.js is never downloaded.
- The renderer is imported only when the canvas mounts (`import("./renderer")`, a separate
  chunk).
- A lost context (`webglcontextlost`) reports `context-lost`; the page shows the list and
  offers to try again (which mounts a new canvas).
- On unmount, every geometry, material and instanced mesh is disposed, then the renderer, and
  the context is released (`forceContextLoss`). Measured in Chromium over 50 visits: no
  universe object is retained after leaving the page, and the context is lost after disposal
  (see [performance](performance.md)).

## Rendering on demand

Nothing animates in an idle loop. A frame is drawn after the scene, the size, the theme or
the camera changes, and on each frame of a fly-to (480 ms, eased; none under reduced motion).
Measured: no animation frame is requested in three seconds of idle, and none after a camera
move has been drawn.

## Why plain Three.js

React Three Fiber was considered and not adopted: it adds a reconciler and more packages for
a scene this simple, and the explorer's pattern is already a pure model feeding a renderer.
Plain Three.js keeps the scene explicit, its disposal visible and its draw calls few (about
twenty for any graph size: one per shape for fills and for outlines, one for all edges, one
for arrowheads, one for halos, one for the strata rings). See
[decision 73](../decisions.md#73-plain-threejs-loaded-only-with-the-3d-page).
