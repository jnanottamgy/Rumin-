# The knowledge graph

RUMIN's knowledge graph connects the records RUMIN already holds — reference data
(countries, industries, companies, economic-variable definitions and curated
relationships), the Phase 2 series catalogue and imported price files — into one graph
of **nodes** (entities) and **edges** (relationships), where every edge says why it
exists.

It is built from the command line (`make graph`, or `python -m app.graph build` in
`backend/`), served read-only at `/api/v1/graph`, and explored in the web client at
**/graph**.

> **What it is not.** The graph connects the records RUMIN holds. It is not a map of the
> economy, most of its companies are fictional, and an edge is not evidence of
> causation, of an exposure's size, or of a correlation. Read
> [concepts](concepts.md) before drawing conclusions from it.

## Reading order

| Document | What it answers |
|---|---|
| [Concepts](concepts.md) | What nodes, edges, paths and components are — and the difference between a connection, an exposure, a correlation, causation, a model assumption and an evidence-backed relationship |
| [Architecture](architecture.md) | Why the graph lives in the existing relational database; how builds, the API and the explorer fit together |
| [Node model](nodes.md) | The nine node types, their keys, natures (real, fictional, sample) and fields |
| [Edge model](edges.md) | Edge fields, direction, evidence status, validity, illustrative and historical edges |
| [Relationship types](relationship-types.md) | The 18 edge types: meaning, endpoints, direction, allowed evidence and what each does *not* mean |
| [Entity resolution](entity-resolution.md) | How records become nodes without merging different entities that share a name |
| [Construction pipeline](construction.md) | The 21 construction rules, the 26 validation rules, the build report and rebuilds |
| [Provenance](provenance.md) | The evidence behind every edge, and how to answer "why does this connection exist?" |
| [Algorithms and metrics](algorithms.md) | Neighbourhoods, BFS, DFS, shortest paths, components, degree and density — with complexity, limits and caveats |
| [Explorer](explorer.md) | The web explorer: encoding, interactions, layouts, limits and accessibility |
| [Data-quality limitations](limitations.md) | What the graph cannot tell you, and why |
| [Performance](performance.md) | Measured build and query times on synthetic graphs up to 108k edges, bottlenecks and limits |
| [Phase 4 integration](phase-4-integration.md) | How a future simulation engine may use the graph — and what it must not assume |

The API is documented in [`docs/api.md`](../api.md#knowledge-graph); testing in
[`docs/testing.md`](../testing.md); the tables in [`docs/data-model.md`](../data-model.md).

## Quick start

```bash
make graph          # build (or rebuild) the graph from the current sources
make graph-status   # the latest build and whether the sources changed since
```

Then open <http://localhost:5173/graph>. The first view is an aggregate map of node
types; search for a node (for example "Deltrin" or the ISO code "IN") to explore its
neighbourhood.

The build prints a validation report whose numbers come from the run itself:

```
GRAPH VALIDATION REPORT

Nodes processed: 50
Valid nodes: 50
Flagged nodes: 0
Rejected nodes: 0

Edges processed: 97
Valid edges: 97
Flagged edges: 0
Rejected edges: 0
```

(Those are the figures for the illustrative sample dataset plus the World Bank series
catalogue, with no price files imported.)
