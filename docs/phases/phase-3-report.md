# Phase 3 report — Financial knowledge graph

**Status: implemented and verified, locally and in CI.** RUMIN now builds a knowledge
graph from every record it holds. It serves the graph through a read-only API and shows it
in an interactive explorer. Every edge carries the evidence that explains it. The plan
written before implementation is in [phase-3-plan.md](phase-3-plan.md); the full
documentation is in [`docs/graph/`](../graph/README.md).

> **What the graph is not.** It connects the records RUMIN holds: 50 nodes and 97 edges from
> the illustrative sample dataset and the World Bank series catalogue. It is **not** a map of
> the economy or of the financial ecosystem, and most of its companies are fictional. No edge
> is a measured effect, a correlation or a causal finding, and no edge has been empirically
> validated.

## At a glance: what exists, and what kind of knowledge it is

| Category | In this build |
|---|---|
| **Implemented functionality** | Graph schema (7 tables, migration `0003`); a repeatable build from the command line (21 construction rules, entity resolution, 26 validation rules, a validation report from the run itself, add/change/retire by content hash); bounded BFS, neighbourhoods, DFS, components, bidirectional shortest paths, degree and six documented metrics; 12 read-only API endpoints; the Knowledge Graph explorer (`/graph`); a typed read interface for Phase 4; tests, benchmarks and documentation |
| **Planned functionality** | A cheaper freshness check; skipping unchanged rebuilds; a review workflow for flagged candidates and issues; citations for curated relationships; attribute history; indexed text search ([roadmap](../roadmap.md#graph-follow-ups-before-or-alongside-phase-4)) |
| **Evidence-backed relationships** | **24 edges**: industry → ISIC section (8), country → currency (3), series → country (11) and series → currency (2). Each transcribes a standard (ISIC Rev. 4, ISO 4217) or a provider's metadata (World Bank WDI). "Evidence-backed" means *a source states it*; RUMIN did not verify it |
| **Model assumptions** | **41 edges**: the curated relationships (supplies 13, lends to 6, competes with 1, affects costs 7, affects revenue 6, affects financing 3, influences 5). Each has a written rationale, an *assumed* polarity and an *illustrative* strength. None was estimated or validated, and none cites an outside source |
| **Analyst-created relationships** | **32 edges** written by a curator in the reference records: company → industry (12), company → country (12), variable → country (6), series → variable (2) |
| **Sample data** | All **12 companies are fictional**, and **65 of 97 edges** are illustrative because they touch them. Synthetic data appears only in tests, the smoke test (a three-day price file) and the benchmarks (networks of up to 20,000 "Synthetic Company" records). None is shipped or loaded by default |
| **Unverified relationships** | **None in the sample graph.** Instrument links (market, currency, country) come from price-file manifests and are always `unverified`. The smoke test's synthetic instrument adds two |
| **Historical information** | No edge states a validity period, so none is historical. Each build records when every node and edge was added, changed or retired. Series values stay in the Phase 2 tables (historical, never live); a series node only says whether values are stored |
| **Future functionality** | The simulation engine (Phase 4) may *read* the graph through the prepared interface. No simulation, forecast or propagation exists. The graph never computes an effect's size |

## 1. Phase 2 audit findings

Before any design work, Phases 1 and 2 were audited ([plan, section 1](phase-3-plan.md#1-audit-of-phases-1-and-2)).
CI runs #2 and #3 on the Phase 2 code had passed: 256 backend tests on SQLite and
PostgreSQL 16, 142 frontend tests, 26 integration tests. No defects were known.

- **Already implemented.** 3 real countries, 8 ISIC industries, 7 variable definitions and
  12 fictional companies, with 41 curated relationships in 7 types. The Universe page
  showed them through `GET /api/v1/network`. Phase 2 added 11 World Bank series linked to
  Phase 1 countries (2 also to variables, with the difference in measure stated) and
  instruments from licensed price files.
- **Incomplete.** The network was recomputed on every request. It had no stable edge
  identity, no provenance per edge, and no traversal, paths or metrics. Phase 2 data
  (series, instruments, currencies) was not connected to it. Nothing resolved identity
  across sources: countries appear as ISO alpha-2 codes in Phase 1 and alpha-3 codes in the
  World Bank catalogue, and currencies as bare codes in three tables.
- **Reusable.** The app factory, error envelope, pagination, enum columns, migration
  tests, the relationship-type registry (whose meanings carry into the graph), the
  rule-registry pattern, the CLI's structure and exit codes; on the frontend, pan and
  zoom, the encoding conventions, the resource hook and the page-test harness.
- **Needed no refactoring.** `/api/v1/network` stayed unchanged, and the Universe page
  only gained a link into the graph; their relation to the graph is documented. The
  system report's `graph_analytics` capability was switched to available only when it
  was real.
- **Postponed on purpose.** A graph database, weighted paths and influence scores (no
  defined weights), centrality (easily read as importance), a review workflow, and
  commodity and financial-institution nodes (no structured source for them).

## 2. Graph architecture

The graph is a **derived, rebuildable projection** stored in seven tables of the existing
database ([architecture](../graph/architecture.md)):

```
 Phase 1 reference data + Phase 2 catalogue and instruments
        │  python -m app.graph build
        ▼
 read sources ─► rules (N01–N09, R01–R12) ─► entity resolution ─► validation (26 rules)
        ─► metrics ─► persist (add · change · retire, by content hash) ─► build record
        ▼
 graph tables ─► GraphReader (typed, read-only) ─► /api/v1/graph (12 GET routes) ─► explorer
                                                └─► Phase 4 (prepared interface, not used yet)
```

- **Deterministic keys** (`company:co_deltrin_refining`; edges `e-` + 16 hex of SHA-256 over
  type, source and target), so rebuilding unchanged sources changes nothing.
- **Never deleted, only retired**, so the graph's membership at any build can be
  reconstructed.
- **No foreign keys into source tables**, so reloading reference data is never blocked by
  the graph.
- **Level-synchronous, bounded traversal**: one indexed query per BFS level.
- **Snapshots**: every build stores its time, rules version, datasets and versions read, a
  fingerprint of every source record, its counts and its changes. Full event sourcing was
  judged unnecessary; attribute history is a documented follow-up.

## 3. Technology decisions

Recorded as ADRs 23–32 in [decisions](../decisions.md#23-the-knowledge-graph-lives-in-the-existing-relational-database):

| Decision | Why |
|---|---|
| **Relational, not a graph database** (23) | Relational, graph-database and hybrid designs were compared before coding. Every query needed is bounded, and runs in milliseconds on indexed edge tables up to 108,000 edges. Neo4j would add a service (GPLv3 for Community) without enabling any needed query. Revisit beyond ~4-hop traversals over millions of edges |
| **A derived projection** (24) | Safe to rebuild; traceable to sources; reference data can be reloaded freely |
| **Evidence status, not confidence scores** (25) | No method exists to estimate a meaningful number; the status says truthfully what supports an edge |
| **Never merge by name** (26) | A wrong merge silently joins legal entities and cannot be undone; a missed one is visible |
| **Traversal in Python, always bounded** (27) | Portable across SQLite and PostgreSQL; testable against brute force; limits reported |
| **Read-only API; builds from the command line** (28) | No authentication yet |
| **The explorer draws, the server decides** (29) | Relationship logic in one place; deterministic layouts; an aggregate map first |
| **No centrality, weights or clustering yet** (30) | On this graph they would measure the data's coverage and be misread |
| **Freshness cached for 30 s** (31) | The check reads every source record |
| **No new dependencies** (32) | The algorithms are small and tested against brute force |

Stack unchanged: Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, SQLite and PostgreSQL 16;
React 19, TypeScript, Vite, SVG.

## 4. Node types

Only types the stored data supports ([node model](../graph/nodes.md)):

| Type | Built from | Identifier | Sample graph |
|---|---|---|---|
| Country | `countries` | ISO 3166-1 alpha-2 (alpha-3 attached from the catalogue) | 3 |
| Currency | ISO 4217 codes named by countries, series and instruments | ISO 4217 | 3 |
| Sector | The ISIC Rev. 4 section of each industry's division | ISIC section | 6 |
| Industry | `industries` | ISIC Rev. 4 division | 8 |
| Company | `companies` | none (all fictional) | 12 |
| Economic variable | `economic_variables` (definitions, no values) | none | 7 |
| Data series | The Phase 2 series catalogue | provider series key | 11 |
| Instrument | Imported price files | ISIN when given | 0 |
| Market | The MIC in a price-file manifest | ISO 10383 MIC | 0 |

**Not implemented, and why:** *financial institution* (the two banks are company records
in the banking industry; no separate institution data exists) and *commodity* (commodity
prices are economic-variable definitions such as the Brent crude price; there is no
commodity entity source). Each node has an internal key, type, display name, subtitle,
description, nature (real, fictional or sample), quality status, identifiers with the
record that stated each, source references, degree, component, and build and row
timestamps. Nodes hold **no financial values**.

## 5. Edge types

18 types, each with a meaning, allowed endpoints, direction, allowed evidence statuses and
a statement of what it does **not** mean ([relationship types](../graph/relationship-types.md)):

| Category | Types (sample graph count) |
|---|---|
| Economic, curated or assumed | `supplies_to` (13), `lends_to` (6), `competes_with` (1, undirected), `affects_costs` (7), `affects_revenue` (6), `affects_financing` (3), `influences` (5) |
| Structural, from records and classifications | `in_industry` (12), `domiciled_in` (12), `measured_for` (6), `in_sector` (8), `has_currency` (3), `covers` (11), `related_measure_of` (2), `expressed_in` (2) |
| From price-file manifests (unverified) | `listed_on`, `quoted_in`, `associated_with` (0 in the sample) |

Each edge has an evidence status, an illustrative flag, a quality status, an optional
validity period (never guessed) and qualifiers kept from the source (assumed polarity,
illustrative strength, rationale). There is **no confidence score** and **no weight**
([edge model](../graph/edges.md)).

## 6. Database schema

Migration `0003_knowledge_graph` adds seven tables and changes no existing one
([data model](../data-model.md#phase-3-knowledge-graph)):

| Table | Holds |
|---|---|
| `graph_builds` | One row per build: status, rules version, source fingerprint, datasets read, validation counts, changes, metrics, a safe error summary |
| `graph_nodes` | Nodes, with content hash and first / changed / retired build |
| `graph_node_identifiers` | External identifiers; `UNIQUE (scheme, value)` |
| `graph_edges` | Edges, with content hash and build columns |
| `graph_edge_evidence` | Why each edge exists (at least one per edge) |
| `graph_resolution_decisions` | Every entity-resolution decision, per build |
| `graph_issues` | Every validation issue, per build |

Partial indexes on current rows serve every read. Migrations are tested up, down and
against the models on SQLite and PostgreSQL.

## 7. Entity resolution

**Conservative by design: identifiers and explicit links join records; names never do**
([entity resolution](../graph/entity-resolution.md)).

1. Every record that exists in its own right keeps its own node.
2. Records naming the same valid code (ISO 4217, ISIC section, MIC) share one node: **13
   decisions** in the sample graph.
3. A World Bank series' alpha-3 code is attached to the country its catalogue entry links
   to: **11 decisions**. A code claimed by two countries is attached to neither.
4. Names are normalised (case, accents, punctuation, "The", abbreviations, legal forms).
5. Identical normalised names are **flagged** for review. Contained or reordered names are
   **noted**. Fiction is never matched with fact. **Nothing is merged.**
6. Every decision is logged with the values compared and the reason.

The sample graph has no flagged candidates. Tests cover the false matches that must not
happen: "ANVAYA BANK LTD." vs "Anvaya Bank", the same name in two countries, "Tata Steel"
inside "Tata Steel Europe", a real instrument named like a fictional company. Candidate
pairs are found by blocking. A word used by more than 100 names is not used to find
pairs, so a partial match made only of common words is not searched for, a documented and
tested trade-off.

## 8. Construction process

`python -m app.graph build` ([construction](../graph/construction.md)): read and
fingerprint every source record → make nodes (N01–N09) → resolve entities → make edges
with evidence (R01–R12) → validate (26 rules: structural problems **reject**, doubtful
identity **flags**, information is **noted**) → describe and compute metrics → persist by
content hash → record the build. One transaction: a failed build changes nothing. One
build at a time; a crashed build is closed after an hour.

The report's numbers come from the run itself:

| Source data | Nodes processed / valid / flagged / rejected | Edges processed / valid / flagged / rejected |
|---|---|---|
| Sample dataset + series catalogue | 50 / 50 / 0 / 0 | 97 / 97 / 0 / 0 |
| … + the smoke test's synthetic price file | 52 / 52 / 0 / 0 | 99 / 99 / 0 / 0 |
| Synthetic benchmark, 20,000 companies | 20,948 / 20,948 / 0 / 0 | 107,920 / 107,832 / 0 / **88** |

The 88 rejections are the sector links of fictional benchmark industries: an
evidence-backed edge may not touch fictional data (`reality_mismatch`). **Rebuilding
unchanged sources changes nothing**, at every size tested and on every CI run.

## 9. Provenance

Every edge answers "why does this connection exist?" from stored records
([provenance](../graph/provenance.md)). Each evidence record holds: the rule; the source
kind, table and record; the dataset and version; what the source says; the
transformation; whether the edge is direct or derived, and from what; the citation (only
if the record has one, and a link only if it is a web link); and when the data was
retrieved and recorded, kept apart. In the sample graph **97 of 97 edges have evidence, 32
cite an outside source and 8 are derived** (industry → sector from the ISIC table). An
edge without evidence is rejected. Nodes list the source records they were built from.

## 10. Algorithms

[Algorithms and metrics](../graph/algorithms.md):

| Algorithm | Use | Cost and bounds |
|---|---|---|
| BFS, level-synchronous | Neighbourhoods, hop distances | O(V + E); one query per level; depth ≤ 3, ≤ 200 nodes, cut-offs reported |
| Neighbourhood (induced subgraph) | The explorer's views | `d + 1` queries |
| DFS, iterative | Components during builds | O(V + E); no recursion |
| Weakly connected components | Build metrics, `/components` | Once per build |
| Bidirectional BFS | Up to 10 shortest paths of ≤ 6 hops | ~2·b^(d/2) nodes; 5,000-node budget |
| Degree | Sizes, "start from a well-connected node" | Once per build; labelled "data coverage, not importance" |

**Metrics** (each with definition, calculation, interpretation and limitations, served by
the API and shown in the explorer): nodes 50, edges 97, components 1, average degree
3.88 (median 3, max 19), density 0.0792, provenance coverage 100 % (32 cited). **Not
implemented on purpose:** centrality, weighted paths, community detection, correlation or
causal discovery. A path shows how records connect; the API says in every answer that it
is not a causal chain.

## 11. API endpoints

Twelve `GET` endpoints under `/api/v1/graph` ([API reference](../api.md#knowledge-graph)):
`overview`, `types`, `nodes` (search), `nodes/{id}`, `nodes/{id}/neighborhood`, `edges`,
`edges/{id}`, `paths`, `components`, `builds`, `builds/{id}` and `issues`. Filters: edge
type, node type, evidence status, direction, illustrative data. Limits: depth ≤ 3,
≤ 200 nodes, ≤ 6 hops, ≤ 10 paths, a 5,000-node path budget; anything out of range is a
422, and keys are validated by pattern. Writes answer 405. The OpenAPI snapshot and the
frontend's generated types include every endpoint.

## 12. Frontend features

The **Knowledge Graph** page (`/graph`, [explorer](../graph/explorer.md)):

- **Aggregation, clearly labelled.** It opens on a map of node *types* with counts, and bands
  that count relationships between *kinds* of node. It is labelled as an aggregate, so no
  band is mistaken for an individual relationship. Choosing a type (e.g. Industries)
  lists its nodes; choosing one explores it, with its companies and related entities.
- **Search** by name, code or identifier, with ambiguous names marked.
- **Neighbourhoods** on a deterministic radial layout (distance = hops), depth 1–3, up to
  150 nodes drawn, with step-by-step expansion, collapse, history, reset and shareable
  links.
- **Filters** by node type, relationship type, evidence status, direction and
  illustrative data. They are applied on the server.
- **Panels**: a node's identifiers, sources, data status, resolution decisions and
  quality checks; a relationship's evidence, status definition, validity and "What it
  does not mean".
- **Financial interpretation, with distinctions.** For a company, the variables assumed
  to affect it are split into *stated for the company* (direct) and *stated for its
  industry* (indirect). Each carries its evidence status: evidence-backed (documented),
  model assumption (modelled) or unverified. In the sample all are model assumptions.
  Supplier relationships are never inferred from industry membership, and an industry
  assumption is never presented as affecting every company equally.
- **Paths** between two nodes, with the causal-chain caveat.
- **Encoding**: shape for node type, a ring for fictional or sample records, line pattern
  for evidence status, sky blue only for emphasis. A legend, a table view, keyboard
  access and reduced motion are supported.
- **Cross-links** from entity, series and instrument pages. The System page reports the
  knowledge-graph and graph-analytics capabilities as available.

**UI quality review** (information hierarchy, search, readability, panels, responsive
behaviour, loading, error and empty states, keyboard, labels, mobile, consistency): done
in Chromium at three widths and both themes. It led to nine fixes, listed in the
[explorer's UI review](../graph/explorer.md#ui-quality-review).

## 13. Performance findings

Measured on synthetic data on one machine (4 vCPUs, SQLite 3.45 and PostgreSQL 16.13); the
numbers describe that machine only ([performance](../graph/performance.md)).

| At 20,000 companies (20,948 nodes, 107,832 edges) | SQLite | PostgreSQL |
|---|---|---|
| First build / unchanged rebuild | 21.1 s / 16.2 s | 38.1 s / 16.6 s |
| Node detail | 6 ms | 13 ms |
| Neighbourhood, depth 1–3 (≤ 200 nodes) | 10–44 ms | 12–64 ms |
| Shortest paths | 12 ms | 19 ms |
| Overview: first request / cached | 6.1 s / 0.6 ms | 5.9 s / 1.3 ms |

Four bottlenecks were found by profiling and fixed:

- Quadratic name comparison: 4.79 s → 0.13 s at 1,000 companies.
- An `OR` query that scanned every edge: node detail 517 → 6 ms.
- Row-by-row persistence: first build 42.0 → 21.1 s.
- Per-request source hashing: 6.9 s → 0.6 ms when cached.

Remaining: the first overview request after a build or restart (~6 s at this size), the
unchanged rebuild (~16 s), a `LIKE` search scan (37–62 ms) and a ~100 ms re-render on
selection at 150 nodes. In the explorer, merging and layout take under 2 ms per change at
150 nodes. At the sample graph's size every request takes a few milliseconds.

## 14. Testing results

| Suite | Result |
|---|---|
| Backend (pytest) | **450 passed** on SQLite and on PostgreSQL 16 (194 new graph tests: algorithms 91, construction 30, names 22, build 9, CLI 6, API 36) |
| Frontend (Vitest) | **202 passed** (60 new: view, layout, encoding, edge panel, explorer page) |
| Integration (live API) | **39 passed** (13 new graph tests), inside the smoke test |
| Smoke test | Passed: the graph builds (52 nodes, 99 edges) and **a rebuild changes nothing** |
| Lint, format, types, build, OpenAPI snapshot, generated types | Clean |
| CI | Runs **#4** (`3bf91bf`, schema, build and API), **#5** (`e3bd8c6`, explorer) and **#6** (`3d5c0e4`, tests and performance) passed all three jobs: backend on SQLite and PostgreSQL 16, frontend, and the end-to-end smoke test |

Algorithms are cross-checked against brute force on random graphs. That covers 500
source–target pairs for shortest paths, all shortest paths counted by dynamic
programming, BFS distances, and components against union–find. Entity-resolution tests
pin the false matches that must not happen. Details: [testing](../testing.md).

## 15. Security

([security](../security.md#knowledge-graph-phase-3))

- The graph API is **read-only**: writes answer 405, and builds run only from the
  command line.
- **Every parameter is validated** before a query: key patterns, enumerations, capped
  repeated filters, and length-limited search with control characters refused and
  wildcards escaped.
- **Traversal is bounded** in depth, nodes, hops, paths and path budget, and every
  cut-off is reported.
- **Failures are safe**: the standard error envelope, and a failed build stores a
  generic summary with no stack trace.
- **Relationship data is validated twice**: when loaded, and by the build's 26 rules.
- The explorer renders no raw HTML and only `http(s)` links.
- **No credentials exist or are exposed.** `npm audit` and `pip-audit` found no known
  vulnerabilities (2026-09-23).

**Not production-secure:** there is no authentication and no rate limiting. The overview's
freshness check reads whole tables, at most once every 30 s per process.

## 16. Known limitations

([graph limitations](../graph/limitations.md) · [all limitations](../known-limitations.md))

- **Coverage.** The graph covers RUMIN's records, not the economy: 50 nodes, 12 of them
  fictional companies.
- **No validated edges.** No edge is empirically validated. "Evidence-backed" means
  transcribed from a standard or a provider's metadata, not verified.
- **No measured exposures.** An assumed effect has no size, timing or certainty. Nothing
  measures an exposure, a correlation or a cause.
- **Duplicates are flagged, not merged.** There is no review workflow and no outside
  registry lookup.
- **As of the last build.** "Stale" can appear up to 30 s late, and only membership
  history is kept.
- **Tested scale.** Measured to about 21,000 nodes; the first overview after a restart
  is slow at that size.
- **Explorer rendering.** SVG, up to 150 nodes drawn.

## 17. Phase 4 integration plan

([Phase 4 integration](../graph/phase-4-integration.md)) **Graph edges are not equations.**
An edge gives a simulation the entities, stated relationships, direction, evidence status,
provenance and validity. It gives no magnitude, lag, functional form or uncertainty.
Phase 3 prepared, and does not use:

- `GraphReader`, a typed, read-only interface (nodes, edges, evidence, subgraphs,
  neighbourhoods, paths, exposures) with the same bounded filters the API uses;
- deterministic keys that map scenario shocks (`scenario_shocks.variable_id`) to variable
  nodes;
- build IDs and fingerprints to pin a simulation run to a graph state.

The suggested approach for Phase 4 has six steps:

1. Pin the build.
2. Start from the scenario's shocked variables.
3. Treat traversed edges as *candidate* channels only.
4. Choose accepted evidence statuses explicitly, and record the choice.
5. Keep every simulated relationship's parameters, sources and validation in the
   simulation's own tables, linked to graph edges for provenance.
6. Label results that rest on model assumptions or illustrative data as such.

No simulation logic lives in the graph, its API or its rendering code.

## Quality gates

| Gate | Status |
|---|---|
| **Architecture:** graph architecture documented; Phase 1 and 2 work preserved; graph layer separated from the frontend; future simulation considered | ✓ ([architecture](../graph/architecture.md)); `/api/v1/network` unchanged, the Universe page unchanged apart from a link into the graph, no Phase 1/2 table altered; traversal and filtering on the server only; [Phase 4 integration](../graph/phase-4-integration.md) |
| **Data model:** node model; edge model; relationship types documented; provenance preserved; temporal metadata strategy documented | ✓ 9 node and 18 edge types; evidence on every edge; validity periods only when stated, build history per node and edge ([architecture](../graph/architecture.md#snapshots-and-history)) |
| **Construction:** nodes from structured data; relationships validated; duplicate handling; entity resolution; repeatable | ✓ 21 rules, 26 validation rules; duplicates stored once with every record as evidence; resolution flags and never merges; unchanged rebuilds change nothing (tested, and checked on every CI run) |
| **Algorithms:** neighbourhood traversal; BFS; DFS where useful; bounded path queries; metrics documented | ✓ cross-checked against brute force; DFS used for components; paths ≤ 6 hops with a node budget; six metrics with definition, calculation, interpretation and limitations |
| **API:** endpoints work; query limits; filtering; errors handled; documentation | ✓ 12 endpoints; limits → 422; filters by type, status, direction, illustrative data; standard error envelope; [API reference](../api.md#knowledge-graph) and OpenAPI |
| **Frontend:** search; node selection; relationship inspection; expansion; provenance accessible; loading, error states; responsive | ✓ tested in jsdom (21 page tests) and checked in Chromium at three widths, both themes |
| **Testing:** unit; integration; construction; entity resolution; frontend | ✓ 450 backend (SQLite and PostgreSQL), 202 frontend, 39 integration; CI green |
| **Security:** inputs validated; traversal limits; no credentials exposed; write operations protected | ✓ no write endpoints (405); builds from the command line only |
| **Documentation:** graph architecture; data dictionary; relationship semantics; known limitations; Phase 4 plan | ✓ [`docs/graph/`](../graph/README.md) (14 pages), plus updates to the data model, data dictionary, API, decisions, security, testing, design system, setup, roadmap and README |

What remains unverified or open is stated above: no edge is validated against the world,
the benchmarks describe one machine, and the product has no authentication.
