# Phase 3 plan — Financial knowledge graph

Written before implementation, after auditing Phases 1 and 2. It records what was found,
what was decided and why, and the order of work. The Phase 3 report will record what was
actually delivered.

## 1. Audit of Phases 1 and 2

**Verified state.** CI runs #2 and #3 on GitHub (the Phase 2 code) passed: 256 backend
tests (SQLite and PostgreSQL 16), 142 frontend tests, 26 integration tests, lint, types,
build and contract checks. No known defects.

| | Finding |
|---|---|
| **A. Already implemented** | *Phase 1:* `entities` with 3 real countries (ISO 3166-1 alpha-2, ISO 4217 currency), 8 ISIC Rev. 4 industries, 7 economic-variable definitions (with publishers) and 12 fictional companies; 41 curated relationships in 7 types, all `illustrative` model assumptions with written rationales; a relationship-type registry (meaning, direction, allowed endpoint kinds); `GET /api/v1/network`, which projects entities, relationships and 3 structural link types on every request (30 nodes, 71 edges); the Universe page (layered layout, SVG, pan and zoom, selection, filters, table view, deep links, keyboard access). *Phase 2:* 11 World Bank series, each linked to a Phase 1 country (2 also to a variable, with the difference in measure stated); instruments from licensed price files (ISIN, MIC, symbol, currency, optional country); provider datasets with licence and attribution; read-only API conventions; writes from the command line only |
| **B. Incomplete** | The "network" is recomputed per request: no stable edge identity, no provenance per edge (structural links carry only a `derived_from` column name), no traversal, paths, components or metrics. Phase 2 data (series, instruments, currencies) is not connected to the network. No entity resolution: countries are identified by ISO alpha-2 in Phase 1 and by ISO alpha-3 in the World Bank catalogue; currencies appear as bare codes in three tables. Capability `graph_analytics` is declared "planned for Phase 3" |
| **C. Reusable** | *Backend:* app factory, error envelope, `Page[T]`, portable enum columns, UTC datetimes, naming conventions, migrations with drift and downgrade tests, the relationship-type registry (its meanings carry into the graph), the rule-registry pattern of `quality.py`, job-status derivation, the ingestion CLI's structure and exit codes. *Frontend:* `usePanZoom`, `fitTransform`, `toScreen`, `edgeGeometry` (arrowhead trimming), the encoding conventions (shape = kind, sky blue = emphasis only), `useApiResource`, `States`, `Panel`, `Badge`, the page-test harness, design tokens |
| **D. Needs refactoring** | Very little, and no rewrite of working code. The Universe keeps its own 4-kind encoding; the graph explorer gets its own. `system.py` flips `graph_analytics` only when it is real. `/api/v1/network` and the Universe page stay unchanged (their relation to the graph is documented) |
| **E. Schema changes** | Migration `0003`: seven new tables (below). No change to Phase 1 or 2 tables. No foreign key from the graph into source tables: the graph is a rebuildable projection, so `seed --reset` and ingestion must never be blocked by graph rows. Sources are referenced by table and record ID in provenance rows |
| **F. In Phase 3** | Graph schema; a provenance-aware, repeatable construction pipeline; entity resolution; validation with a report; traversal, paths, components and degree; a read-only graph API; an interactive Graph Explorer; tests, measurements and documentation (sections 3–14) |
| **G. Postponed** | Graph database; weighted paths and "influence" scores (no defined weights); betweenness or PageRank (not meaningful on 50 nodes, easily misread as importance); a manual review workflow for flagged candidates; importing analyst relationships with citations; commodity and financial-institution nodes (no structured source); any simulation (Phase 4); 3D (Phase 8) |

## 2. Architecture decision

| Criterion | A. Relational (existing database) | B. Graph database (e.g. Neo4j) | C. Hybrid |
|---|---|---|---|
| Fit with the architecture | Same database, migrations, backups, CI matrix | A second datastore to install, secure and back up | Two stores kept in sync |
| Query needs (depth ≤ 3, paths ≤ 6 hops, components) | Level-by-level queries on indexed edges | Native, but not needed at this depth | Native |
| Dataset size (≈ 50 nodes, ≈ 100 edges; thousands foreseeable) | Trivial | Over-provisioned | Over-provisioned |
| Provenance | Joins to datasets, series, captures and jobs in one transaction | Must be copied or joined across stores | Split across stores |
| Development and maintenance | SQL + Python the team already uses | New query language (Cypher), new driver | Both, plus synchronisation |
| Deployment | Nothing new | New service; licence to check (Community edition is GPLv3) | New service |

**Decision: A.** Graph tables live in the existing PostgreSQL/SQLite database; algorithms
run in Python. Traversal is *level-synchronous*: one indexed query fetches the edges of the
whole frontier, so a depth-3 neighbourhood costs 3 queries, whatever its size. Recursive
CTEs were considered and rejected: SQLite and PostgreSQL differ in cycle handling, and
node budgets, filters and path reconstruction are clearer in code.

**Revisit when** interactive traversals need more than about 4 hops over millions of
edges, or analysts need ad-hoc graph pattern queries. The next step would be the hybrid:
PostgreSQL stays the source of truth and a graph engine (or the Apache AGE extension) is
fed from it.

**The graph is a derived projection.** Sources of truth stay where they are (Phase 1
reference tables, Phase 2 series and instruments). `python -m app.graph build` turns
them into nodes, edges and evidence. Keys are deterministic, so a rebuild with unchanged
sources changes nothing; each build records what was added, changed or retired.

## 3. Domain model

### Node types (only those the data supports)

| Type | Built from | Key | Identifiers | Nature |
|---|---|---|---|---|
| `country` | `countries` | `country:<record id>` | ISO 3166-1 alpha-2; alpha-3 learned from World Bank links | real |
| `currency` | country currency, series currency, instrument currency | `currency:<iso code>` | ISO 4217 | real |
| `sector` | ISIC Rev. 4 section of each industry's division | `sector:isic4-<letter>` | ISIC section | real |
| `industry` | `industries` | `industry:<record id>` | ISIC Rev. 4 division | real |
| `company` | `companies` | `company:<record id>` | RUMIN reference ID only | fictional (all today) |
| `economic_variable` | `economic_variables` | `variable:<record id>` | RUMIN reference ID | real (definitions) |
| `data_series` | `economic_series` | `series:<series id>` | provider series key | real |
| `instrument` | `instruments` (user-imported only) | `instrument:<id>` | ISIN, MIC + symbol | real or sample |
| `market` | instrument MIC | `market:<mic>` | ISO 10383 MIC | real or sample |

Every node has: key, type, display name, a disambiguating subtitle, identifiers,
description, nature (`real`, `fictional`, `sample`), quality status, the source records it
was built from, timestamps, and the builds that added, last changed and retired it.

**Not implemented, and why.** *Financial institution:* the only institutions are two
fictional banks, already companies in ISIC section K. *Commodity:* variables are prices
of commodities, but no field identifies the commodity. *Providers and datasets:* they are
provenance, not entities; as nodes they would become hubs that make unrelated series look
connected.

### Edge types

Edges read as sentences: *source — label → target*.

| Type | Reads | From → to | Built from | Evidence status |
|---|---|---|---|---|
| `supplies_to`, `lends_to`, `competes_with`, `affects_costs`, `affects_revenue`, `affects_financing`, `influences` | as in Phase 1 | as in Phase 1 | curated `relationships` | model assumption (illustrative today) |
| `in_industry` | operates in | company → industry | `companies.industry_id` | analyst-created |
| `domiciled_in` | is domiciled in | company → country | `companies.country_id` | analyst-created |
| `measured_for` | is measured for | variable → country | `economic_variables.country_id` | analyst-created |
| `in_sector` | belongs to | industry → sector | ISIC Rev. 4 structure | evidence-backed |
| `has_currency` | has currency | country → currency | `countries.currency_code` (ISO 4217) | evidence-backed |
| `covers` | covers | series → country | series country (provider metadata) | evidence-backed |
| `related_measure_of` | is a related measure of | series → variable | catalogue link + stated difference | analyst-created |
| `expressed_in` | is expressed in | series → currency | the provider's unit | evidence-backed |
| `listed_on` | is listed on | instrument → market | price-file manifest | unverified |
| `quoted_in` | is quoted in | instrument → currency | price-file manifest | unverified |
| `associated_with` | is associated with | instrument → country | price-file manifest (meaning not stated) | unverified |

**Evidence statuses** (one per edge, each with a written definition):

- **Evidence-backed** — stated by a cited external source or standard (ISIC, ISO 4217, a
  provider's metadata). RUMIN transcribed it; it did not measure or validate anything.
- **Analyst-created** — a link written by a RUMIN curator, with its reasoning (a fictional
  company's industry; a series recorded as a related measure of a variable).
- **Model assumption** — an assumed economic relationship with a rationale; not an
  empirical finding. Phase 1's evidence level (`illustrative` today) is kept with it.
- **Unverified** — declared in data supplied to RUMIN (a price-file manifest); recorded,
  not checked.

Two further facts are shown separately: **illustrative** (the edge touches a fictional or
sample node, or comes from illustrative data) and **historical** (its validity period
ended). Edges carry optional `valid_from`/`valid_to`; no current source provides them.

**No confidence score.** No methodology exists to calibrate one. Phase 1's `strength` is
an ordinal, illustrative label and is shown as such, never converted to a number.

**Rules for creating edges.** An edge exists only because a specific field states the
relationship. Appearing in the same dataset, table or file never creates one. A shortest
path is a connection between records, not an influence or causal chain.

## 4. Construction pipeline

`build`: start a build record → extract source records (Phase 1 and 2 tables) → resolve
entities → create node candidates → validate nodes → create edge candidates from the rules
above → resolve endpoints → validate edges → attach evidence → detect duplicates → persist
(insert new, update changed, retire missing; never delete) → compute degree and connected
components → finish the build record with counts, a diff and the validation report.

One transaction: readers see the previous graph until the new one is complete; a failed
build is rolled back and recorded as failed. A source fingerprint (dataset checksums,
catalogue version, source records, rules version) tells the API when the graph is older
than its sources.

## 5. Entity resolution

1. **Record key:** a source record always maps to the same node (keys are deterministic).
2. **Exact identifiers:** ISO 4217 codes, ISO 3166 codes, ISIC codes, ISIN, MIC. Derived
   nodes (currency, sector, market) are merged by their code, and each merge is logged.
3. **Provider identifiers:** a World Bank series names its country by ISO alpha-3 and links
   to a Phase 1 country; the alpha-3 code becomes an identifier of that node, unless
   another node claims it (a conflict: flagged, attached to neither).
4. **Normalised names:** case, accents, punctuation, `&`/`and` and legal suffixes (Ltd,
   Limited, Pvt, Inc, Corp, PLC…) are normalised for comparison only; original names are
   kept.
5. **Candidates:** equal normalised names (strong) or one name's words contained in the
   other's (weak), between companies, and between instruments and companies (possible
   issuer).
6. **Decision:** merge only on an identifier or an explicit link. A name match is never a
   merge: it is flagged for review with its rationale. Fictional and real records are never
   matched.
7. **Audit log:** every non-trivial decision (merge, identifier claim, candidate, conflict)
   is stored per build with the original values and the reason.

Tests cover false matches: same name in different countries, abbreviations, a fictional
company named like a real instrument, a subsidiary whose name contains its parent's.

## 6. Validation

Rules in a registry (like Phase 2's quality rules), each with a severity and an outcome:
missing identifier, unknown node type, missing name, missing provenance, identifier
conflict, invalid identifier, possible duplicate, unknown classification, unresolved
reference; unknown edge type, missing source or target node, endpoint types not allowed,
reversed direction, self-loop, duplicate edge, missing evidence, invalid validity period,
real/fictional mismatch, unsupported merge. Rejected items are not stored as graph data
(they stay as issues); flagged items are stored with quality status `warning`. The build
report states processed, valid, flagged and rejected counts, computed from the run.

## 7. Algorithms

Pure functions over an adjacency interface (in-memory for tests, batched SQL for the API):

- **Neighbourhood / BFS**: depth ≤ 3, node budget, type and direction filters.
  O(V + E) over the explored part, O(V) memory, one query per level.
- **DFS** (iterative): connected components at build time, O(V + E).
- **Shortest paths**: bidirectional BFS, unweighted (hops), ≤ 6 hops, up to 10 paths,
  optional "follow edge direction". Never described as influence or causation.
- **Connected components** (weak, direction ignored): count, sizes, isolated nodes. A
  component is a set of records reachable from each other, not an integrated economy.
- **Degree and density**, with definitions and limitations. Degree reflects how much
  RUMIN's data says about a node, not importance; nothing is ranked as better.

Weighted paths, betweenness and PageRank are not implemented (section 1, G).

## 8. API (read-only, `/api/v1/graph`)

`overview` (build, staleness, metrics, the type-level aggregate map), `types`
(node/edge types and evidence statuses), `nodes` (search by name or identifier, filter
by type, related node and nature; paginated), `nodes/{key}` (identifiers, sources,
resolution, degree, data availability, exposures for companies and industries),
`nodes/{key}/neighborhood`, `edges`, `edges/{id}` (evidence and "why this connection
exists"), `paths`, `components`, `builds`, `builds/{id}`, `issues`. Safe defaults and hard
caps on depth, nodes, paths and page size; validated keys; no write endpoint (no
authentication yet).

## 9. Graph Explorer (`/graph`)

- Opens on an **aggregated map**: one mark per node type, lines labelled with relationship
  counts, clearly marked as an aggregate.
- **Search** with type glyphs and disambiguation; **focus** a node → its neighbours on a
  radial layout; **expand** neighbours progressively (loading and error states, no
  duplicates, a visible-node cap, collapse and reset); **filters** by node type,
  relationship type and evidence status.
- **Details**: a node's identifiers, sources, data availability and exposures (direct,
  via its industry, or modelled, each labelled); an edge's evidence, provenance,
  validity and limitations.
- **Path finder** with a caveat; **history** (back and forward); **table view** twin;
  legend; pan and zoom; keyboard access; phone layout; motion that explains changes
  (nodes grow out of the node they came from), disabled under reduced motion.
- **Layout:** a radial tree around the focus (deterministic, readable at this size),
  not a free force simulation.

## 10. Snapshots

Builds are numbered. Nodes and edges record the build that added, last changed and
retired them, so the graph's membership at any build can be reconstructed, and each build
records its source fingerprint. Earlier attribute values are not kept (documented).

## 11. Performance, security, testing, documentation

- **Performance:** indexes on edge endpoints and types; server-side filtering and caps;
  measurements on synthetic graphs of increasing size (build, neighbourhood, paths,
  search) and of layout and rendering in the browser.
- **Security:** read-only API; builds from the command line only; every parameter
  validated; bounded traversal; no raw SQL built from input; internal errors never leaked.
- **Tests:** normalisation, resolution (including false matches), validation rules,
  algorithms (checked against brute force on random graphs), idempotent rebuilds and
  diffs, API contracts and limits, explorer behaviour, integration against a live API.
- **Docs:** graph architecture, model and relationship dictionary, entity resolution,
  construction, algorithms and metrics, API, provenance, limitations, performance,
  testing, Phase 4 integration; then the Phase 3 report.

## 12. Phase 4 interface

A small read interface (`app/graph`) returns typed subgraphs, paths, edge metadata and
evidence. The API uses it, and the simulation engine will too. Graph edges are not
equations: Phase 4 must model and validate each simulated relationship separately and
may use only edges whose type and evidence status its model accepts.

## 13. Order of work

1. This plan.
2. Schema, migration `0003`, node/edge registry.
3. Construction: extraction rules, resolution, validation, persistence, report, CLI.
4. Algorithms.
5. API, OpenAPI snapshot, generated types.
6. Graph Explorer.
7. Tests, measurements, visual review.
8. Documentation, report, push, CI.
