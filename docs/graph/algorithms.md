# Algorithms and metrics

The graph algorithms are in `backend/app/graph/algorithms.py`: plain Python with no
database or HTTP code, tested against brute-force implementations on random graphs.
Metrics are in `backend/app/graph/metrics.py`. This page covers what each algorithm
does, what it costs, how the API limits it and what its answer does **not** mean.

## How the algorithms see the graph

Each algorithm reads the graph through one method, `Adjacency.incident(nodes)`, which
returns every edge touching a **set** of nodes in a single call:

- `SqlAdjacency` (`app/graph/store.py`) answers each call with **one indexed query**, a
  `UNION ALL` of two searches on the partial indexes over current edges (by source and
  by target). The API uses it.
- `MemoryAdjacency` holds the edges in memory. Builds and tests use it.

Breadth-first search asks for the edges of a whole level at once ("level-synchronous"
traversal), so a search of depth *d* makes *d* round trips to the database, however
many nodes each level holds. The tests count the calls to check this.

**Terms.** The graph is **directed** and **multi-relational**: two nodes can be joined
by several edges of different types, and one type (`competes_with`) is undirected. A
**hop** is one edge. Every edge counts as length 1. There are no weights, because nothing
in the data measures the strength or cost of a relationship.

**Determinism.** Neighbours are always visited in the order (edge type, neighbour key,
edge key). The same graph and the same request therefore give the same answer, in the
same order, whatever order the database returns rows in.

## Filters

Every traversal takes the same filter (`EdgeFilter`). The API exposes each part:

| Filter | API parameter | Effect |
|---|---|---|
| Direction | `direction=any\|out\|in` | `any` ignores direction. `out` follows edges from source to target only. `in` follows them from target to source only. Undirected edges are followed both ways in every mode |
| Edge types | `edge_type` (repeatable) | Only edges of these types are followed |
| Node types | `node_type` (repeatable, neighbourhoods only) | The traversal enters only nodes of these types. The node it starts from is always included |
| Evidence status | `evidence_status` (repeatable) | Only edges with these statuses are followed, e.g. only `evidence_backed` |
| Illustrative data | `include_illustrative=false` | Edges touching the fictional sample network or sample data are skipped |

A filter changes the answer, not the graph. A path that exists only through
model-assumption edges disappears when you ask for evidence-backed edges only. That
difference is worth knowing when you read a result.

## Breadth-first search (BFS)

**What it does.** It visits nodes in order of distance from a start node: first the
start, then every node one hop away, then every node two hops away, and so on. The first
time BFS reaches a node, it has found that node's shortest distance in hops.

**How.** `bfs()` keeps a frontier (the nodes on the current level), fetches the edges of
the whole frontier in one call, and makes every newly found neighbour the next level.
It also keeps each edge between two nodes it has already found, and records how each node
was first reached (its parent node and edge).

**Cost.** Time O(V + E) over the part of the graph visited, memory O(V), and one
`incident` call per level.

**Bounds.** `max_depth` hops and `max_nodes` nodes. When the node budget runs out, the
neighbours BFS could not take are returned in `unexplored`, so the caller can say what
was left out instead of hiding it.

## Neighbourhood (an induced subgraph)

**What it does.** It returns the nodes within *d* hops of a centre, and **every edge
among them**, not only the edges BFS used to reach them. Two neighbours of a company
that also supply each other are shown as joined.

**How.** A BFS to depth *d* finds the nodes. BFS never expands the outermost level, so
one more `incident` call adds the edges among those outer nodes. The total cost is
`d + 1` queries.

**Example.** `GET /api/v1/graph/nodes/company:co_deltrin_refining/neighborhood?depth=1`
returns 9 nodes and 18 edges in 2 queries. Eight edges touch Deltrin. The other ten
join its neighbours to each other, such as *Anvaya Bank — lends to → Aerisca Airways*.

**API limits.** `depth` 1–3 (default 1). `max_nodes` 2–200 (default 60). The response
reports `truncated`, `unexplored_count`, `unexplored_by_type` (e.g. `{"company": 140}`)
and the number of `queries` used.

## Depth-first search (DFS)

**What it does.** It goes as deep as possible along one branch before backtracking.
DFS answers "what can be reached from here?" but, unlike BFS, says nothing about
distance.

**How.** `dfs()` is iterative and uses an explicit stack of neighbour iterators, so a
long chain cannot exhaust Python's call stack (a test runs it on a chain of 5,000
nodes). It returns nodes in the order first visited.

**Cost.** Time O(V + E), memory O(V). It makes one `incident` call per node, so it runs
on the in-memory adjacency during a build. It is not exposed as an endpoint.

## Connected components

**What it does.** It finds groups of nodes that can reach each other along edges,
ignoring direction ("weakly connected" components).

**How.** `connected_components()` starts a DFS from each node not yet assigned. It runs
once per build, over the whole graph in memory. Each node stores its component number
(1 is the largest). Ties are broken by the smallest node key.

**Cost.** Time O(V + E) per build. `GET /api/v1/graph/components` only reads the stored
numbers (at most 50 components are listed, default 10), so the request does not walk the
graph.

**Example.** The sample graph is **one component of 50 nodes**. Countries and currencies
link almost every record to every other.

**Does not mean.** Being in one component does not make entities economically
integrated. A long chain through a classification or a currency connects almost anything
and says nothing.

## Shortest paths (bidirectional BFS)

**What it does.** It finds up to `limit` shortest paths between two nodes, measured in
hops, with at most `max_depth` hops.

**How.** `shortest_paths()` grows one BFS from each end and always expands the smaller
frontier, until the two searches meet. With branching factor *b* and distance *d*, this
explores about 2·*b*^(*d*/2) nodes instead of *b*^*d*. When the searches meet, the
shortest length is the smallest sum of forward and backward distance over the nodes both
have reached. Each side keeps **every** shortest predecessor of a node, so all shortest
paths can be listed, not just one. Paths are sorted by their node and edge keys, and
duplicates are removed.

**Why this is correct.** Suppose the searches meet after *a* forward levels and *b*
backward levels. Any path of length ≤ *a* + *b* passes through a node that both searches
reached. So once they meet, no shorter path can still be undiscovered. The tests compare
the result with plain BFS on 500 random source–target pairs, in both `any` and `out`
directions, and compare the number of paths with a dynamic-programming count of all
shortest paths.

**Bounds.** `max_depth` 1–6 hops (default 4), `limit` 1–10 paths (default 3), and a search
budget of 5,000 nodes, which the user cannot change. When the budget runs out, the
answer is `budget_exhausted: true`, which says the search could not decide. It is not
"no path". The response also reports `nodes_explored`.

**Example.** From Aerisca Airways (a fictional airline) to the Brent crude oil price, with
no filters, there are **5 shortest paths of 3 hops**, found after exploring 28 nodes:

```
Aerisca Airways ← supplies — Deltrin Refining — operates in → Refined petroleum products ← affects costs of — Brent crude oil price
Aerisca Airways — is domiciled in → India ← is measured for — India CPI inflation ← influences — Brent crude oil price
Aerisca Airways — operates in → Air transport ← supplies — Refined petroleum products ← affects costs of — Brent crude oil price
Aerisca Airways — operates in → Air transport ← affects costs of — Jet fuel price (U.S. Gulf Coast) ← influences — Brent crude oil price
Aerisca Airways ← affects costs of — USD/INR exchange rate — influences → India CPI inflation ← influences — Brent crude oil price
```

(The second path, through the country, shows why direction and edge-type filters matter.
Its middle steps link *records about India*, not an economic mechanism.)

**Does not mean.** A path shows how **records** are connected in RUMIN's data. It is not
an influence, transmission or causal chain. A shorter path is not a stronger
relationship. Hops ignore the evidence status, so a path can mix a classification with a
model assumption. Filter by evidence status when that matters. The API repeats this in
every answer (`note`).

## Degree

**What it does.** It counts the edges touching each node. For directed edges it also
counts incoming and outgoing edges. An undirected edge counts once in the total and in
neither direction.

**How.** `degrees()` makes one pass over the edges during each build (O(E)). The values
are stored on the node, so reading them costs nothing.

**Example.** India has 19 edges: its companies, the variables measured for it, the
series covering it and its currency.

**Does not mean.** Degree measures **how much RUMIN's data says about a node, not how
important the node is**. A country or a currency is a hub by construction. Wherever the
explorer lists nodes by degree ("Start from a well-connected node", and the "most edges
first" sort), it says so. It is a way to find a starting point, across all node types,
and not a ranking of companies.

## Graph metrics

Each build computes six metrics over the graph it stored, and records them in
`graph_builds.metrics`. `GET /api/v1/graph/overview` returns them with the four fields
below, and the explorer shows those fields beside each number. **None of them is an
economic indicator.** They describe RUMIN's data.

| Metric | Definition | Calculation | Interpretation | Limitations | Sample graph |
|---|---|---|---|---|---|
| **Nodes** | Entities in the graph | Count of current nodes, in total and per type | How much the graph describes | Counts what RUMIN holds, not the economy. The graph is a small, partly fictional sample and far from complete | 50 (12 companies, all fictional) |
| **Edges** | Relationships between nodes | Count of current edges, in total, per type and per evidence status | How many recorded relationships connect the entities | An edge records that a source states a relationship. It says nothing about the relationship's size or strength, and it is not evidence of causation | 97 (41 model assumptions, 32 analyst-created, 24 evidence-backed) |
| **Connected components** | Groups of nodes that can reach each other, direction ignored | DFS from each unvisited node | One component means every record is linked to every other by some chain | Being in one component does not make entities economically integrated | 1 (largest 50, no isolated nodes) |
| **Average degree** | Mean number of edges touching a node | 2 × edges ÷ nodes. Median and maximum are also given | How densely records are linked on average | Degree reflects data coverage, not importance. Hubs are connected by construction | 3.88 (median 3, maximum 19) |
| **Density** | Share of possible node pairs that are directly connected | Node pairs joined by at least one edge ÷ *n*(*n* − 1)/2. Direction and parallel edges are ignored | Close to 0 is sparse; close to 1 means nearly every node is linked to every other | Sparse is normal for real-world graphs. The value says nothing about the economy | 0.0792 |
| **Provenance coverage** | Share of edges with at least one evidence record, and with a citation | Edges with evidence ÷ all edges; edges whose evidence cites a source ÷ all edges | Evidence should be 100 %: an edge without evidence is rejected. The citation share shows how many edges point to an outside source | A citation shows where a statement came from. It does not mean the statement was verified | 97 of 97 with evidence, 32 cited, 8 derived |

A build also records the counts by node type, nature, edge type, category and evidence
status, the number of illustrative edges (65), the flagged nodes and edges (0), and the
number of duplicate statements merged into one edge (0).

## What is deliberately not implemented

| Not built | Why |
|---|---|
| **Centrality** (betweenness, PageRank, eigenvector) | A centrality score would be read as importance, or as a ranking of companies. On this graph it would mostly measure which records were loaded: countries and currencies would come first by construction. The brief made centrality optional; it can be added later with the same caveats as degree, if a use justifies it |
| **Weighted shortest paths** | Weights would need a measured strength or cost for each relationship. None exists. The curated "strength" is an illustrative, ordinal label written by a curator, and using it as a distance would present an assumption as a measurement |
| **Community detection / clustering** | On a small, partly fictional graph, clusters would reflect how the sample was written, and could be mistaken for real industry groupings |
| **Correlation or causal discovery** | The graph holds no time series values, and edges are not derived from data (see [concepts](concepts.md)). The Phase 2 series stay in their own tables |
| **Recursive SQL (CTEs) for traversal** | SQLite and PostgreSQL handle cycles differently, and node budgets, filters and path reconstruction are clearer and testable in Python. See [architecture](architecture.md#traversal-level-synchronous-bounded) |

## Tests

`backend/tests/test_graph_algorithms.py`:

- **Unit tests.** Each algorithm on small hand-drawn graphs: BFS order and one call per
  level, depth and node budgets, direction, edge-type and node-type filters, the edges
  among the outermost nodes, DFS on a 5,000-node chain without recursion, components,
  every shortest path up to the limit, path bounds, the node budget and degree.
- **Cross-checks on random graphs.** Bidirectional search against plain BFS (25 seeds ×
  2 directions × 10 pairs). The number of shortest paths against a dynamic-programming
  count (10 seeds). BFS distances against a brute-force BFS (10 seeds). Components
  against union–find (10 seeds).

`test_graph_api.py` checks the same limits over HTTP: out-of-range depth, node count,
path length and number of paths are rejected with 422, and a truncated neighbourhood
says so.
