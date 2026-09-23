# Technology decisions

Short records of the choices made in Phases 1 to 3, why, and what would make us revisit
them. Phase 2 decisions start at [13](#13-world-bank-indicators-as-the-first-provider-fred-rejected),
Phase 3 decisions at [23](#23-the-knowledge-graph-lives-in-the-existing-relational-database).

## 1. Monorepo with a Python API and a TypeScript web client

**Decision.** One repository: `backend/` (Python, FastAPI) and `frontend/` (React,
TypeScript), sharing one `.env`, one CI workflow and one committed API contract.
**Why.** The API contract, the domain rules and the UI change together; one repository
keeps them in one review. Python is where the later quantitative work (simulation,
statistics, data ingestion) is most productive.
**Revisit if** the simulation engine needs a separately deployed service.

## 2. FastAPI + Pydantic v2

**Why.** Typed request/response validation, generated OpenAPI documentation, dependency
injection for sessions and settings, and good performance, with little code.
**Consequence.** The Pydantic schemas are the API contract; they are exported to
`docs/api/openapi.json` and checked by a test.

## 3. SQLAlchemy 2.0 + Alembic; SQLite in development, PostgreSQL in production

**Why.** SQLite needs no server, so a new contributor runs the whole stack in minutes;
PostgreSQL is the production database. SQLAlchemy abstracts the dialects and Alembic owns
the schema.
**How we keep them equivalent.** Portable column types (enums as `VARCHAR` + `CHECK`,
timezone-aware UTC timestamps, exact `NUMERIC` for values); migrations in batch mode (which
SQLite needs); deterministic constraint names; foreign keys enforced on SQLite too. The
full test suite runs on both, in CI.
**Revisit if** a feature needs PostgreSQL-only capabilities (e.g. recursive graph queries
at scale, JSONB indexing) — then SQLite becomes a convenience for part of the suite only.

## 4. Joined-table inheritance for entities

**Why.** Relationships need one foreign-key target whatever the kinds they connect, while
kind-specific fields (a company's industry, a variable's unit) should be real, typed,
constrained columns rather than a loosely typed JSON blob.
**Alternative rejected.** One wide table with nullable kind-specific columns (weak
integrity), or one table per kind with polymorphic relationship endpoints (no real
foreign keys).

## 5. Curated relationships stored; structural links derived

**Why.** "Company X operates in industry Y" is already a column of the company; storing it
again as a relationship could contradict it. It is derived when the network is built.
Economic relationships are judgements that need a rationale, a polarity, a strength and an
evidence level — they are stored as records.

## 6. Reference data from a validated, versioned file

**Why.** The sample network is curated content, reviewed like code. The loader validates
shape and cross-record integrity before writing, is idempotent, and records the file's
checksum, so what is in the database can always be traced to an exact file.

## 7. No simulation endpoint, no AI integration, no market data in Phase 1

**Why.** An endpoint or screen that appears to simulate or predict would present invented
numbers as results. Instead the capability list states what is planned and when, the
Scenario Lab saves inputs only, and the AI Analyst page explains what it will do.

## 8. React 19 + TypeScript + Vite + React Router

**Why.** A mainstream, well-supported stack: strict typing end to end (types generated
from the API contract), fast builds, code-split routes. React Router's data router gives
per-route error boundaries and lazy loading.
**Not added.** A state-management library (the app state is server data plus local UI
state; a 140-line cached hook covers it) and a component library (the design system is
small and specific; generic components would fight it). Both can be added when the need
is real.

## 9. SVG + d3-force for the 2D network; renderer-agnostic model and layout

**Why.** At tens to a few hundred nodes, SVG gives crisp text, real DOM nodes for
accessibility (focus, roles, labels) and straightforward testing. `d3-force` (the only
d3 module used) relaxes a deterministic layered layout; the model and layout are pure
TypeScript with no DOM, so they can feed a WebGL/Three.js renderer later.
**Revisit when** graphs reach thousands of nodes: move layout to a Web Worker and
rendering to canvas/WebGL (Phase 3 and 8).

## 10. Plain CSS with design tokens and CSS Modules

**Why.** No runtime styling cost, no framework lock-in; tokens in one file make themes a
remapping of semantic variables; CSS Modules scope class names per component.

## 11. Tooling: uv, Ruff, mypy (strict); npm, Biome, TypeScript strict; pytest, Vitest

**Why.** Fast, reproducible installs from lock files (`uv.lock`, `package-lock.json`);
one tool each for lint + format (Ruff, Biome); strict type checking on both sides; tests
that run in seconds so they are run often.

## 12. Security posture for a local-only foundation

**Decision.** No authentication in Phase 1 — documented, and the API is intended for
local use only. Everything else a foundation should get right is in place: validation of
every input, a single error envelope without internals, security headers, a strict CSP on
API responses, a body-size limit, explicit CORS origins (no wildcard, no credentials), no
secrets anywhere in the code. See [security.md](security.md).

# Phase 2

## 13. World Bank Indicators as the first provider; FRED rejected

**Decision.** The first provider is the World Bank Indicators API (v2): no key, CC BY 4.0
(commercial use with attribution), good India coverage.
**Why not FRED.** Its API terms (June 2024) prohibit storing FRED content in a database,
and RUMIN stores data by design. Alpha Vantage's free tier is non-commercial; RBI has no
official API; MoSPI needs a token (it is the next provider).
**Revisit when** MoSPI access is arranged (monthly official Indian CPI, WPI, IIP).

## 14. Market prices only from files the user is licensed to use

**Decision.** No price data is bundled or fetched. Daily prices enter only through
`import-prices`, with a manifest declaring the licence and attribution.
**Why.** Exchange data is licensed; free APIs restrict commercial use. Importing the user's
own licensed files keeps RUMIN honest about rights and still exercises the full pipeline.

## 15. Exact decimals everywhere

**Decision.** `Decimal` from JSON parsing (`parse_float=Decimal`) to storage
(`NUMERIC(38, 18)`; a canonical string on SQLite, whose `NUMERIC` is floating point) to the
wire (decimal strings) to the screen (BigInt-based formatting). Values that do not fit are
rejected, never rounded.
**Why.** Financial values must not drift through binary floating point, and "refuse,
don't round" keeps every stored digit the provider's.

## 16. Revisions instead of overwrites

**Decision.** One current row per period (a partial unique index); a change supersedes it
and inserts a new revision; identical data only updates "last seen".
**Why.** Providers revise data. Overwriting would lose what RUMIN was told and when; the
history is what makes a past analysis reproducible.

## 17. Keep the exact bytes received

**Decision.** Every response and imported file is stored gzip-compressed with its SHA-256;
each value points to its capture.
**Why.** Provenance you can verify, and re-processing without asking the provider again.
**Cost.** Storage — small for annual series (tens of KB per run); `RUMIN_STORE_SOURCE_BODIES`
can turn the bodies off (hashes and metadata remain).

## 18. Structural problems reject, plausibility problems flag

**Decision.** A record that cannot be what it claims (bad number, wrong period, high below
low) is rejected and kept as an issue with its raw content; a well-formed but unusual value
is stored exactly and flagged. Nothing is corrected.
**Why.** Silent correction invents data; silent dropping loses it. Both are recorded.

## 19. Job status derived from targets

**Decision.** Items succeed, fail or are skipped; the job's status is computed from them,
with a `partially_failed` status of its own.
**Why.** A run where some series failed is neither "completed" nor "failed"; reporting it
as either would misstate what is stored.

## 20. Ingestion from the command line only (until authentication)

**Why.** Without authentication, an HTTP trigger would let anyone make RUMIN call providers
and write data. The job model is ready for a scheduler or an authenticated endpoint.

## 21. No new dependencies

**Decision.** HTTP via the standard library (`urllib`) behind a small transport interface;
CSV, gzip, hashing from the standard library; the chart hand-written in SVG (scales, ticks
and gap handling are ~200 lines, unit-tested).
**Why.** Fewer supply-chain risks and nothing to keep up to date; the transport interface
lets tests script responses without a network.
**Revisit if** providers need HTTP/2, connection pooling at scale, or charts become
numerous enough to justify a charting library.

## 22. The series catalogue is curated like code

**Decision.** Which series to retrieve, and how to describe them (unit, measure, basis,
review range, links to Phase 1 variables with the difference stated), lives in a validated
JSON file under version control — never values.
**Why.** Describing a series honestly is editorial work that deserves review; the file is
validated in full before anything is written.

## 23. The knowledge graph lives in the existing relational database

**Decision.** Seven graph tables in the same PostgreSQL (production) / SQLite
(development) database, with traversal in Python. No Neo4j, no graph extension, no
second store.
**Why.** Relational, graph-database and hybrid designs were compared before any code was
written ([graph architecture](graph/architecture.md)). Every query the product needs is
bounded — neighbourhoods up to 3 hops and 200 nodes, paths up to 6 hops, whole-graph work
once per build — and runs in milliseconds on indexed edge tables (measured to 108,000
edges, [performance](graph/performance.md)). Keeping one database keeps provenance joins,
migrations, backups and the CI matrix as they are. A graph database would add a service
to install, secure and back up (Neo4j Community is GPLv3) without making any needed query
possible.
**Revisit if** interactive traversals need more than about 4 hops over millions of edges,
or analysts need ad-hoc pattern queries. The next step would be a hybrid: PostgreSQL stays
the source of truth, and a graph engine (or Apache AGE) is fed from it.

## 24. The graph is a derived, rebuildable projection

**Decision.** The graph is built from the stored records by a command, never edited by
hand. Keys are deterministic (`company:co_deltrin_refining`; edges `e-` + 16 hex of
SHA-256 over type, source and target). Builds compare content hashes and add, change or
retire rows. Nothing is deleted. Graph tables have no foreign keys into the source tables.
**Why.** Rebuilding from unchanged sources changes nothing (checked on every CI run), so a
build is safe to repeat. Every node and edge can be traced to its source records, and the
graph's membership at any build can be reconstructed. Reloading reference data is never
blocked by graph rows.
**Consequence.** Earlier attribute values are overwritten (only membership history is
kept), and the graph is only as current as its last build. The overview says when it is
stale.

## 25. Evidence status, not confidence scores

**Decision.** Every edge has one of four evidence statuses — evidence-backed,
analyst-created, model assumption, unverified — set by the rule that built it and
restricted per edge type. Illustrative, historical and quality flags are separate
properties. There is no numeric confidence, and the curated `strength` stays an
illustrative, ordinal label that is never used as a weight.
**Why.** A number such as "0.8" would need a defined meaning and a method to estimate it,
and none exists for these records. A status says truthfully what supports an edge, and
"evidence-backed" is defined as "a source states it", not "verified".
**Revisit if** relationships are ever estimated from data. An estimate would then carry its
own method, sample and uncertainty, not a bare score.

## 26. Entity resolution never merges by name

**Decision.** Records are joined only through identifiers (ISO, ISIC, MIC) and explicit
links (a series' catalogue link to a country). Similar names are flagged (identical after
normalisation) or noted (contained or reordered), never merged. Fiction is never matched
with fact. Every decision is logged.
**Why.** Names collide constantly in finance: parents and subsidiaries, the same trading
name in different countries, unrelated firms sharing common words. A wrong merge silently
joins different legal entities and cannot be undone without the original records. A
missed merge is visible and fixable.
**Consequence.** Duplicates stay as separate nodes until a curator fixes the source.
Candidate pairs are found by blocking (a word shared by more than 100 names is not used),
so a partial match made only of common words is not searched for. Exact and reordered
duplicates always are.

## 27. Level-synchronous traversal in Python, always bounded

**Decision.** BFS fetches the edges of a whole level in one query (a `UNION ALL` of two
partial-index searches). Shortest paths use bidirectional BFS. Every traversal has a hard
depth, node and path limit, and reports what a limit cut off.
**Why.** `d + 1` round trips for a depth-*d* neighbourhood, whatever its size. Recursive
SQL (CTEs) was rejected: SQLite and PostgreSQL differ in cycle handling, and budgets,
filters and path reconstruction are clearer, and testable against brute force, in
Python. An `OR` across the two endpoint columns made SQLite scan every edge (517 ms for a
node's detail at 20,000 companies; 6 ms after the change).
**Revisit if** traversals need depths or sizes where round trips dominate. See 23.

## 28. A read-only graph API; builds from the command line

**Decision.** Twelve `GET` endpoints. `POST`, `PUT`, `PATCH` and `DELETE` answer 405.
Builds run only from `python -m app.graph build` (or `make graph`).
**Why.** RUMIN has no authentication yet (see 12 and 20). A write endpoint would let
anyone change the relationships others read, and a build endpoint would let anyone start
expensive work.
**Revisit** with authentication and roles (Phase 10): curated relationship edits would
need review, an audit trail and versioning.

## 29. The explorer draws; the server decides

**Decision.** The web explorer receives nodes, edges, labels, meanings and caveats from
the API and only arranges and draws them. Filters are sent to the server, which does the
traversal. Layouts are deterministic (a radial tree by hops, columns for paths), with no
force simulation. The first view is an aggregate map of node types, not the whole graph.
**Why.** Relationship logic in one place (the backend) cannot drift between clients, and
the Phase 4 engine and a future 3D view will read the same answers. A deterministic
layout gives the same picture for the same data, so expansion is stable and distance from
the centre always means hops. Opening on a map avoids an unreadable picture of every node.
**Revisit if** views need thousands of nodes: canvas or WebGL rendering and a layout in a
Web Worker.

## 30. No centrality, weighted paths or community detection yet

**Decision.** Phase 3 computes degree, components, density and provenance coverage only,
each with a definition, calculation, interpretation and limitations. Degree is labelled
"data coverage, not importance", and no company ranking is computed.
**Why.** On a small, partly fictional graph, centrality would mostly measure which records
were loaded and would be read as importance. Weights would need measured strengths, which
do not exist. Clusters would reflect how the sample was written.
**Revisit if** the graph holds enough real, sourced relationships for such measures to
describe something other than the data's coverage, and a use case needs them.

## 31. Freshness is cached for 30 seconds per API process

**Decision.** The overview's "current or stale" answer, which reads and hashes every
source record, is kept for 30 seconds per process. A new build invalidates it at once.
**Why.** The check costs about 6 seconds at 20,000 companies. Paying it on every overview
request would make the explorer's first view slow. A source change showing as stale up to
30 seconds late is an acceptable, documented delay.
**Revisit** with a cheaper change signal (a per-table checksum or change counter written
when sources change), which would remove both the cost and the delay.

## 32. Still no new dependencies

**Decision.** Phase 3 adds no runtime or development dependency. The graph algorithms,
layouts and glyphs are written in the project (and tested). Browser checks used a
Playwright installation outside the project.
**Why.** As in 21: less supply-chain risk and nothing to keep up to date. The algorithms
needed are small, and hand-written versions can be tested against brute force.
**Revisit if** the graph needs algorithms whose correct implementation is substantial
(for example, community detection on large graphs). NetworkX or igraph would then be
evaluated like any dependency.
