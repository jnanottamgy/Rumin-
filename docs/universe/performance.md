# Performance

Measured in this build's environment: a production build (`vite build`, `vite preview`) in
headless Chromium 141 whose WebGL runs on **SwiftShader**, a CPU rasteriser (ANGLE on Vulkan
SwiftShader). No GPU was available. Numbers that depend on rasterisation (time until pixels
are on screen) are therefore much slower than on any hardware GPU and are reported as an
upper bound, not as what a reader will see; JavaScript timings (layout, scene, labels, the
CPU side of a frame) do not depend on the GPU.

## Budgets and what bounds them

| | Bound | Where |
|---|---|---|
| Whole build drawn at once | ≤ 500 nodes and ≤ 2,500 edges (at most six 500-row pages) | `UNIVERSE_BUDGET` |
| Neighbourhood | the explorer's limits: ≤ 3 hops, ≤ 200 nodes per answer, a visible-node limit of 50–150 | Phase 3 |
| Paths | ≤ 10 paths of ≤ 6 hops | Phase 3 |
| Names on the canvas | ≤ 36 node names + the strata's | `labels.ts` |
| Pixel ratio | capped at 2 | `renderer.ts` |
| Remembered positions (stability across views) | ≤ 6,000 | `UniverseCanvas.tsx` |

## The sample graph (50 nodes, 97 edges), through the page

| Measure | Result |
|---|---|
| Navigation start to the first 3D frame (production build, local API, a cold browser context; median of 5) | whole universe 548 ms · with an overlay 615 ms · a neighbourhood 497 ms (the canvas is in the page at 295–375 ms; loading Three.js, compiling the shaders and drawing take the rest) |
| Draw calls | 19 (the whole universe), 12 (a neighbourhood) |
| Triangles | 20,002 (whole universe) |
| CPU time per frame while turning the view (40 frames) | median 1.2 ms, p95 3.8 ms |
| Key press to painted frame on SwiftShader | median 70 ms, p95 145 ms |
| Frames requested while idle (3 s) | **0** — rendering is on demand |
| Leaving and re-entering the page (client-side navigation, 10 visits to warm up, then 40 more; precise memory, forced garbage collection) | heap 9.18 → 9.59 MB; a heap-snapshot diff over the 40 visits shows **no retained universe object** (no detached DOM node, React fiber, typed array or Three.js object) — the only kinds that grew by 40 or more are 140 short strings (the dashboard's SVG marker identifiers) and 81 plain objects (2 KB). No canvas is left behind, and no *too many WebGL contexts* warning appears |
| Console errors or warnings across 14 captures and the checks | 0 |

## Synthetic graphs (measurement only)

A scratch harness (not committed) generated **SYNTHETIC** graphs — random nodes of every kind
and random edges, no financial meaning — and drove the real modules (`layout3d`,
`buildScene`, `createRenderer`, `placeLabels`) outside the page.

| Nodes / edges | 50 / 100 | 500 / 2,500 (the budget) | 2,000 / 8,000 (beyond it) |
|---|---|---|---|
| First layout | 71 ms | 514 ms | 1,735 ms |
| An expansion (+10 % nodes, previous positions kept) | 36 ms | 324 ms | 1,437 ms |
| Scene model | 0.6 ms | 2.7 ms | 4.8 ms |
| Upload to the renderer (`setScene`) | 8 ms | 8 ms | 21 ms |
| CPU time per frame (median) | 0.7 ms | 0.6 ms | 0.6 ms |
| Frame until pixels, SwiftShader (median) | 32 ms | 384 ms | 1,203 ms |
| Name placement per frame | 1.5 ms | 4.2 ms | 11.1 ms |
| Draw calls / triangles | 16 / 23,064 | 18 / 234,702 | 18 / 913,538 |
| Heap before → loaded → after disposal | 18.4 → 22.4 → 20.0 MB | 20.4 → 22.8 → 22.0 MB | 22.9 → 46.4 → 26.7 MB |
| Context lost after disposal | yes | yes | yes |

The draw-call count does not grow with the graph (instancing: one call per shape and per
kind of mark).

A first run of that check suggested a leak of about 0.1–0.4 MB per visit, on the 2D explorer
too. The retainer path led to the browser's DevTools protocol: the measuring script kept an
element handle for every page it waited on, and each handle kept a whole unmounted page
alive. With the handles released, the growth disappeared. The figures above are from the
corrected script.

## What the measurements changed

The first measurements, before these changes, were:

| Change | Before → after |
|---|---|
| Outline hulls use a coarser silhouette mesh; spheres and tori have fewer segments | triangles −49 to −55 % (e.g. 445,790 → 234,702 at 500 nodes); SwiftShader frame 505 → 384 ms at 500 nodes |
| Fewer layout ticks for larger views (300 up to 300 nodes, 180 up to 1,000, then 120; expansions 150 / 90); neighbour lists built without copying | first layout at 500 nodes 748 → 514 ms |
| Names checked against nearby nodes only (a 48 px grid) | name placement at 2,000 nodes 19.5 → 11.1 ms |
| The whole-build hook returns the same object while nothing changed | the filtered view, the scene and a redraw were being recomputed on every render |

## Bundle

| Chunk | Minified | gzip | Loaded |
|---|---|---|---|
| `UniverseSpacePage` | 52 kB (+ 11 kB CSS) | 18 kB | with the page |
| `renderer` (Three.js and the renderer) | 553 kB | 139 kB | only when the canvas mounts and WebGL 2 is available |
| The application entry | 258 kB | 82 kB | unchanged by Phase 8 (Three.js is not in it) |

Vite warns that the renderer chunk is over 500 kB; it is loaded lazily and only by the 3D
page, so the warning is left visible rather than silenced.

## Known costs

- **The layout runs on the main thread.** At the 500-node budget, the first layout takes about
  half a second and an expansion about a third of a second in this environment. A Web Worker
  would remove the pause; it is not needed for the sample (71 ms).
- The first frame compiles the shaders (0.3–2 s on SwiftShader; much less on a GPU).
- Names are placed on every frame of a camera movement (4 ms at 500 nodes).

## Reproducing

`node scripts/measure-universe.mjs` in `frontend/` times the pure work — first layout, an
expansion, the scene model, a filter change in Universe mode (filter the whole build and
derive the view again) and name placement — on the same SYNTHETIC graphs, in Node through
Vite. On the machine that built Phase 8 (medians):

| Graph | First layout | Expansion +10 % | Scene | Filter change | Names |
|---|---|---|---|---|---|
| 50 nodes / 100 edges | 33 ms | 21 ms | 0.1 ms | 1.5 ms | 0.3 ms |
| 500 / 2,500 | 497 ms | 277 ms | 1.0 ms | 22 ms | 2.3 ms |
| 2,000 / 8,000 | 2,195 ms | 1,834 ms | 2.4 ms | 96 ms | 5.0 ms |

A filter change does not lay the graph out again: every node keeps its remembered position,
so the layout runs no ticks. Search is the graph API's (Phase 3, measured in
[graph performance](../graph/performance.md)).

The browser figures above came from Playwright scripts run against a production build with
software WebGL; they are described here rather than committed, like the visual reviews of
earlier phases.
