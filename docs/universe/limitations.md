# Limitations

## What the universe is not

- **Not a map of the economy.** It draws the records RUMIN holds and the relationships the
  knowledge graph records. The sample's companies are fictional and most of its relationships
  are illustrative (65 of 97); none is a measured effect, a correlation or a causal finding.
- **Not a measure of importance.** Height is kind, size is kind, and the names written first
  when space is short are the most connected records — a legibility rule, not a ranking.
- **Not a simulation.** An overlay shows one stored execution as it was recorded. The
  universe computes no figure and never runs a model.

## Scope left out of Phase 8

- **One overlay at a time**, and only an execution's modelled pathway and line results.
  Comparisons, stress cases, sensitivity and month-by-month values stay in the Scenario Lab.
- **Missing overlay records are not fetched.** When a neighbourhood does not reach some of an
  overlay's records, the panel counts them and offers the whole universe (when it fits the
  budget); it does not read the missing records one by one, as the plan had proposed.
- **No 3D for large builds as a whole.** Above 500 nodes or 2,500 edges the page starts from
  a search and grows by neighbourhoods; there is no level-of-detail or clustering view of a
  large build.
- **Phones get the 3D view by default.** The plan proposed the list first on phones; the
  review found the canvas legible at 390 px, so the canvas stays the default there and the
  list is one tap away.
- **No touch-specific gestures** beyond drag, two-finger pinch and tap; no rotate gesture.

## Performance and platform

- Measured only on **software WebGL** (SwiftShader) in this environment: no GPU was
  available, so no hardware frame rate has been measured. See [performance](performance.md).
- **The layout runs on the main thread**: at the 500-node budget, about 0.5 s the first
  time and 0.3 s per expansion in this environment (71 ms for the sample).
- The renderer chunk (Three.js) is 553 kB minified (139 kB gzip), loaded only by this page.
- Requires **WebGL 2**; without it the list is shown. There is no WebGL 1 or 2D-canvas
  fallback renderer.

## Accessibility

- The canvas itself is operated with the keyboard by moving a selection between nodes on
  screen; relationships cannot be selected from the keyboard on the canvas — they are in the
  node panel and the list.
- The accessibility checks are automated (`axe-core`) plus a keyboard pass; no screen-reader
  session with a user was run.
