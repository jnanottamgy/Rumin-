# Graph architecture

How the knowledge graph is stored, built, served and shown — and why it lives in the
existing relational database rather than a graph database.

## The decision: graph tables in the existing database

The graph is stored in seven tables of RUMIN's PostgreSQL (production) or SQLite
(development) database, and its algorithms run in Python. Three options were compared
before any code was written ([Phase 3 plan](../phases/phase-3-plan.md#2-architecture-decision)):

| Criterion | Relational (chosen) | Graph database (e.g. Neo4j) | Hybrid |
|---|---|---|---|
| Fit | Same database, migrations, backups and CI matrix | A second datastore to install, secure and back up | Two stores kept in sync |
| Queries needed (depth ≤ 3, paths ≤ 6 hops, components) | Level-by-level queries on indexed edges | Native, but not needed at this depth | Native |
| Size (50 nodes today; measured to 21k nodes and 108k edges) | Fast enough — see [performance](performance.md) | Over-provisioned | Over-provisioned |
| Provenance | Joins to datasets, series and captures in one transaction | Copied or joined across stores | Split across stores |
| Maintenance | SQL and Python the project already uses | New query language and driver | Both, plus synchronisation |
| Deployment | Nothing new | A new service (Neo4j Community is GPLv3) | A new service |

PostgreSQL is sufficient for Phase 3 because every query the product needs is bounded:
neighbourhoods up to 3 hops and 200 nodes, paths up to 6 hops with a 5,000-node search
budget, and whole-graph work (components, degree, metrics) done once per build. A graph
database would add an operational burden without making any of these queries possible
that are impossible now.

**Revisit when** interactive traversals need more than about 4 hops over millions of
edges, or analysts need ad-hoc pattern queries. The next step would be a hybrid in which
PostgreSQL remains the source of truth and a graph engine (or the Apache AGE extension)
is fed from it.

## A derived, rebuildable projection

The graph never replaces the records it is built from:

```
 Phase 1 reference data          Phase 2 data                      the graph
 ───────────────────────         ─────────────────────             ──────────────────────
 countries, industries,    ┐     economic_series (catalogue)  ┐    graph_builds
 companies, economic_      ├──►  instruments (price files)    ├──► graph_nodes, graph_node_identifiers
 variables, relationships, │     datasets (licence, version)  │    graph_edges, graph_edge_evidence
 datasets                  ┘                                  ┘    graph_resolution_decisions, graph_issues
                         python -m app.graph build  (read → assemble → validate → persist)
```

- **No foreign keys into source tables.** Reloading the sample dataset
  (`seed --reset`) or ingesting a series is never blocked by graph rows. Evidence names
  its source by table and record ID; the next build retires anything whose source has
  gone.
- **Deterministic keys.** A node's key comes from its type and source ID
  (`company:co_deltrin_refining`, `currency:inr`, `sector:isic4-c`); an edge's key is
  `e-` plus 16 hex characters of SHA-256 over (type, source key, target key). The same
  sources always give the same keys, so rebuilding changes nothing.
- **Never deleted, only retired.** Each node and edge records the build that added it,
  last changed it and — once its source disappears — retired it. The graph's membership
  at any past build can be reconstructed. Earlier *attribute values* are not kept: a
  changed description overwrites the old one (documented in
  [limitations](limitations.md)).
- **Builds are recorded.** Each build stores its validation counts, its changes
  (added / changed / retired / unchanged), the datasets and versions it read, a SHA-256
  fingerprint of every source record, and its metrics. The API compares that fingerprint
  with the current sources to say whether the graph is up to date.

## Components

```
        command line                                     web client (/graph)
  python -m app.graph build │ validate │ status │…         GraphExplorerPage
                │                                            │  useGraphExplorer (state, history, cache)
                ▼                                            │  view.ts (merge) · layout.ts (radial, columns)
   app/graph/build.py ── one build at a time,                │  GraphCanvas · TypeMap · panels · PathFinder
        │               stale-build recovery                 │
        ├─ sources.py      read every source record + fingerprint      HTTP, read-only
        ├─ rules.py        21 construction rules  ──┐                  ▼
        ├─ resolution.py   entity resolution        │        app/api/v1/graph.py (12 GET routes)
        ├─ validation.py   26 validation rules      ├─ assemble.py     │
        ├─ metrics.py      components, degree, density…                ▼
        └─ persist.py      add · change · retire (bulk)      app/services/graph.py
                                                                       │
   app/graph/algorithms.py  BFS, neighbourhood, DFS, components,       ▼
                            bidirectional shortest paths, degree  app/graph/store.py
                            (pure; tested against brute force)    SqlAdjacency, GraphReader
                                        │                              │
                                        └──────────────────────────────┴──► database
```

| Module | Responsibility |
|---|---|
| `app/domain/graph_types.py` | The vocabulary: 9 node types, 18 edge types (meaning, endpoints, direction, allowed evidence, caveat) and 4 evidence statuses |
| `app/graph/sources.py` | Reads every source record into plain records; `fingerprint()` hashes them |
| `app/graph/rules.py` | Construction rules N01–N09 (nodes) and R01–R12 (edges), each with its evidence |
| `app/graph/resolution.py` | Entity resolution: identifiers, explicit links, name comparison that flags but never merges |
| `app/graph/validation.py` | The 26 validation rules and the edge checks |
| `app/graph/assemble.py` | Runs rules → resolution → validation into a draft graph with its issues and decisions |
| `app/graph/persist.py` | Writes the draft: add, change, retire by content hash |
| `app/graph/build.py`, `cli.py` | The build lifecycle and the command line |
| `app/graph/algorithms.py` | Graph algorithms over an `Adjacency` interface (in memory or SQL) |
| `app/graph/store.py` | `SqlAdjacency` (one indexed query per BFS level) and `GraphReader`, the read interface the API — and Phase 4 — use |
| `app/services/graph.py` | API logic: limits, filters, summaries, explanations |
| `frontend/src/features/graph/` | The explorer; no relationship logic, only what the API returns |

## Traversal: level-synchronous, bounded

A neighbourhood of depth *d* is found by breadth-first search that fetches the edges of
the **whole frontier** in one indexed query per level, plus one query for the edges among
the outermost nodes: `d + 1` round trips whatever the neighbourhood's size. The queries
use partial indexes on active edges by source and by target, combined with `UNION ALL`
(an `OR` across the two columns made SQLite scan every edge — see
[performance](performance.md)). Recursive SQL (CTEs) was rejected: SQLite and PostgreSQL
differ in cycle handling, and node budgets, filters and path reconstruction are clearer
in code.

Every traversal is bounded by the API — depth ≤ 3, ≤ 200 nodes, paths ≤ 6 hops, ≤ 10
paths, a 5,000-node path-search budget — and every truncation is reported.

## Writes and security

Builds run from the command line only; the API has no write endpoint (`POST`, `PUT`,
`DELETE` answer 405), because RUMIN has no authentication yet. One build runs at a time;
a build left `running` for over an hour (a crashed process) is marked failed by the
next one. A failed build rolls back its graph changes and records a short, safe error
summary — never a stack trace. See [`docs/security.md`](../security.md).

## Snapshots and history

Builds are numbered. Nodes and edges carry `first_build_id`, `changed_build_id` and
`retired_build_id`, so "what did the graph contain at build *n*?" is a query:
*first ≤ n and (retired is null or retired > n)*. One gap: a node or edge that was
retired and later restored keeps no record of the interval in which it was absent.
Each build's issues and resolution decisions are kept per build.

Full event sourcing (every change as an event) was not built. If needed later, a
`graph_node_versions` / `graph_edge_versions` table written by `persist.py` would record
every change without altering the rest of the design.
