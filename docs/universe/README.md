# The 3D Financial Universe

The 3D universe (`/universe/3d`) shows RUMIN's **knowledge graph** in three dimensions. It is a
view, not a model: everything it draws is read from the graph API (Phase 3) and, for scenario
overlays, from stored executions of the Scenario Lab (Phase 5). It computes no financial
figure, invents no relationship and stores nothing.

> The sample graph is built from an **illustrative** dataset: its companies are fictional
> and its relationships are recorded or assumed, never measured. Height in the universe says
> what a record **is**, never how large or important it is.

## Opening it

- **Universe → The knowledge graph in 3D**, or `/universe/3d` directly.
- From the **2D graph explorer**: *Open in 3D* keeps the focus or the path shown.
- From the **Scenario Lab**: a completed execution offers *See it in the 3D universe*, which
  opens the universe with that execution laid over it (`?execution=<id>`).
- From the **AI Analyst**: each relationship path offers *Shortest paths between them in 3D*.

The URL mirrors what is shown (`?focus=`, `?from=&to=`, `?execution=`), so a view can be
linked to and shared.

## What it shows

| Mode | What is drawn | How it is loaded |
|---|---|---|
| **Universe** | The whole current build | Only when the build is within the budget (≤ 500 nodes and ≤ 2,500 edges, read 500 per page); a larger build starts from a search instead |
| **Neighbourhood** | A focus, its neighbours to a chosen depth (1–3 hops), and the neighbours of nodes expanded one by one | By the 2D explorer's state (`useGraphExplorer`): the same requests, limits and history |
| **Paths** | The shortest paths between two nodes (≤ 10 paths, ≤ 6 hops) | One request |
| **Scenario overlay** (on any mode) | What a stored execution changed, simulated, propagated, cited and left out, with its stored results | The execution, its pathway and its results — three read-only requests |

Every record opens the 2D explorer's panels: a node's identifiers, sources, entity
resolution, quality checks and relationships; an edge's evidence records, rule, dataset,
qualifiers and what the edge does **not** mean. A *List* view shows the same nodes and
relationships as tables — the canvas's twin and its fallback.

## Guides

- [Architecture](architecture.md) — modules, data flow, the renderer contract and its lifetime
- [Encoding](encoding.md) — strata, marks, names on the canvas, colour roles
- [Interaction](interaction.md) — camera, pointer, keyboard, modes, history, links
- [Scenario overlays](overlays.md) — what an overlay shows, where each part comes from, and
  what it never claims
- [Accessibility](accessibility.md) — the list twin, keyboard use, focus, announcements,
  reduced motion, themes, fallbacks, automated checks
- [Performance](performance.md) — budgets, measurements on the sample and on synthetic
  graphs, what was optimised
- [Limitations](limitations.md)

## Running it

```bash
make install                        # once
make migrate seed catalog graph     # a database with the sample dataset and a graph build
make backend                        # the API on http://127.0.0.1:8000
make frontend                       # in another terminal: http://127.0.0.1:5173/universe/3d
```

The 3D view needs **WebGL 2**. Without it — or when the browser reclaims the graphics
context — the page says so and shows the list instead. To see an overlay, execute a scenario
in the Scenario Lab and follow *See it in the 3D universe*, or choose it in *Scenario
overlay* above the canvas.
