# Technology decisions

Short records of the choices made in Phases 1 to 5, why, and what would make us revisit
them. Phase 2 decisions start at [13](#13-world-bank-indicators-as-the-first-provider-fred-rejected),
Phase 3 decisions at [23](#23-the-knowledge-graph-lives-in-the-existing-relational-database),
Phase 4 decisions at [33](#33-one-narrow-domain-first-an-airline-fuel-cost-shock),
Phase 5 decisions at [43](#43-several-narrow-models-composed-by-line-items).

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
**Since Phase 4** a simulation engine exists, built so that its results are calculations
from stated inputs, never invented (decisions 33–42). **Since Phase 5** scenarios are
executed through the model registry (decisions 43–53); a change no registered model
simulates is refused, not approximated.

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

## 33. One narrow domain first: an airline fuel-cost shock

**Decision.** The first model answers one question: how a change in crude oil, jet fuel or
the exchange rate reaches one airline's fuel cost, operating profit and margin, with
hedging and a lagged fare pass-through. Five candidates were compared on data available,
financial relevance, mathematical clarity, validation potential and extensibility
([plan](phases/phase-4-plan.md#2-the-domain-an-airline-fuel-cost-shock)).
**Why.** It uses the most of what RUMIN already holds: the graph states the crude → jet
fuel → air transport channel, the variables have defined units, and the World Bank series
can supply a historical exchange rate. Its core is an accounting identity (volume × price
× exchange rate), so round inputs give results checkable by hand, and it still exercises
unit conversion, currencies, frequencies, lags and graph propagation. The closest
alternative, interest rates on financing costs, lacked data (one annual lending rate).
**Consequence.** RUMIN holds no company accounts, so the airline's figures always come
from the user, and the sample airlines stay fictional.
**Revisit** when the next question needs its own model (see 34); the registry takes it
without changes to the engine.

## 34. Models are code, versioned and hashed; no formula language

**Decision.** A model is a frozen, typed definition plus a `check` and a `compute`
function, registered in code. Its canonical JSON is hashed (SHA-256); the first run of a
version stores the definition and hash, a later run whose code differs is refused (409),
and a test pins every released hash. There is no formula language: nothing is ever
evaluated from text (`eval`, `exec` or a parser).
**Why.** A formula language would be a second programming language to secure, test and
explain, and user-supplied formulas would be executable input. Python functions are
typed, linted, unit-tested and reviewed like the rest of the code. Pinning the hash means
a released model cannot change silently: stored runs keep meaning what they meant.
**Consequence.** Any change, even to a description, needs a new version number; old
versions stay registered so their runs can still be verified.
**Revisit if** analysts need to define models themselves. A restricted, parsed expression
language with a whitelist of operations would then be designed and reviewed as its own
component, never `eval`.

## 35. Exact decimals, refused rather than repaired

**Decision.** All model arithmetic runs in one `Decimal` context: 34 significant digits,
half-even rounding, traps on overflow, invalid operations and division by zero, with
correctly rounded `ln` and `exp`. Outputs are rounded to 10 decimal places; magnitudes
stay below 10²⁰ so every stored value fits `NUMERIC(38, 18)`. Units convert only between
the units a model lists, with exact factors. Values out of range, with too many decimals,
in an unlisted unit or missing are **refused** with a reason, never clipped, rounded,
converted or filled in.
**Why.** Binary floating point gives results that differ by platform and cannot be
reconciled to the cent; exact, correctly rounded arithmetic gives the same hashes on every
machine, so a run can be verified anywhere. Repairing input silently would present a
result for a question the user did not ask. This extends decision 15 to calculations.
**Revisit if** a model needs heavy numerical work (matrix algebra, optimisation), where
floating point with stated tolerances would be the honest choice, with reproducibility
defined by tolerance rather than by hash.

## 36. The graph carries shocks only through declared transmission rules

**Decision.** A shock travels along a graph edge only when a model's transmission rule
declares that edge type between those nodes, the latest graph build contains it as a
current, validated edge, and the shock needs it. Coefficients and lags are model inputs
(assumptions with defaults and rationales), never read from edges. Propagation is
log-linear along simple paths only (cycle protection), at most 4 hops deep and 500 paths,
and every path is recorded. Other edges near the model's variables are listed as "not
used", never followed. A missing edge refuses the shock with the reason.
**Why.** The graph's edges say that a relationship exists and what supports it; they carry
no measured size (decision 25). Propagating along any edge would invent effects.
Declaring rules keeps the model's causal claims explicit, reviewable and testable, and
checking the graph keeps the model honest about what RUMIN's data actually states.
**Revisit** when coefficients are estimated from data (Phase 9); an estimate would enter
as an input with its own provenance, not as an edge weight.

## 37. Shapley values for contributions

**Decision.** When several changes act at once, each output's change is attributed with
Shapley values: the model is evaluated with every subset of the non-zero changes, and each
change gets its average marginal effect over all orders. At most six changes are
attributed (64 evaluations).
**Why.** Changes interact (a weaker rupee makes a crude rise costlier). Adding changes one
after another credits the interaction to whichever comes last, so the answer depends on an
arbitrary order. Shapley values add up to the total exactly, treat changes symmetrically
and need no judgement to apply.
**Revisit if** a model has more than six simultaneous changes; grouped or sampled
attributions would then be needed, stated as approximate.

## 38. Runs are append-only and verifiable from their own snapshot

**Decision.** A run stores the definition hash, every input with its source, the graph
and data snapshots, every calculation step, the outputs, contributions and bridge, and
the inputs and result hashes. There is no update or delete (405); a sensitivity analysis
keeps its run (a restricting foreign key); running the same inputs again creates a new
run. Verification re-executes from the stored snapshot alone and compares hashes.
**Why.** An explanation must describe the calculation that happened, not the one current
code and data would do. Re-reading the graph or the latest observation during
verification would test today's data, not the run. Storing rather than recomputing makes
every stored number traceable to its step.
**Consequence.** Storage grows with use (about 16–17 kB of JSON per 12-month run) and
there is no retention policy yet.
**Revisit** with authentication (Phase 10): retention, archiving and deletion by an
authorised owner, with an audit record.

## 39. One-at-a-time sensitivity; points outside a range are skipped

**Decision.** Sensitivity varies one input at a time around a stored run (defaults per
input, or absolute, relative or listed values), evaluates every output at every point,
and ranks inputs by the spread of one metric. A point outside an input's range, or one the
model refuses, is skipped and listed with the reason, never clipped. Limits: 8 inputs,
7 points each, 60 evaluations, 10 seconds; a request over a limit is refused whole.
Monte Carlo is deferred; runs record `random_seed: null` so that probabilistic runs can
be reproduced later.
**Why.** One-at-a-time analysis answers "what moves the result most" exactly and
explainably. Distributions would need estimated uncertainty for each input, which RUMIN
does not have; drawing from invented distributions would present made-up probabilities.
Clipping a point would report the result of a different question.
**Revisit** when inputs have estimated distributions (Phase 9), and for two-way grids when
interactions matter.

## 40. Runs are created by `POST /simulations`

**Decision.** The brief suggested `POST /simulations/run`; RUMIN creates a run with
`POST /api/v1/simulations` (201 with `Location`), like `POST /scenarios`. Validation
without storing is `POST /simulations/validate`, and verification is
`POST /simulations/{id}/verify`.
**Why.** The existing API creates resources by posting to their collection. A verb in the
path would be the only one of its kind. `validate` and `verify` are actions that store
nothing, so they are verbs.

## 41. The browser calculates nothing

**Decision.** The Simulation page renders definitions and results the API returns: form
fields from the input definitions, the pathway from the model's declared links, the
tables and charts from stored outputs. Every figure it shows is an exact decimal string
from the server that the page only formats (a sign, grouping, a unit, a shifted decimal
point for percentages). Values become floating-point numbers only to position marks in a
chart, never to produce a figure. The page's presentation helpers still find
baseline-and-scenario pairs by naming convention.
**Why.** Financial logic in one place cannot drift between clients, is tested in one
language, and is covered by the run's hashes. A figure calculated in the browser would
have no step, no provenance and no hash.
**Revisit** when a second model arrives: its presentation (pairs, monthly series,
headline) should be declared in its definition rather than inferred from names.
**Since Phase 5** the Scenario Lab reads what each model contributes from its declared
scenario profile (decision 46), and the Lab page calculates nothing either; the Simulation
page's naming convention remains, as technical debt.

## 42. Still no new dependencies

**Decision.** Phase 4 adds no runtime or development dependency. Exact arithmetic uses the
standard library's `decimal`; hashing uses `hashlib`; Shapley values, propagation,
sensitivity, the pathway layout and the charts are written in the project and tested.
**Why.** As in 21 and 32. Every calculation that matters is small enough to write and
verify by hand, and a numerical library would bring binary floating point back into the
path (see 35).
**Revisit** with Monte Carlo or estimation (Phase 9), where a statistics library would be
evaluated like any dependency.

## 43. Several narrow models, composed by line items

**Decision.** Composition in the Scenario Lab needs more than one model, so Phase 5 adds
four narrow ones — foreign-currency revenue and costs, floating-rate interest, crude-oil-
linked costs, natural-gas-linked costs — and a version 1.1.0 of the airline model (timed
changes, a monthly exchange-rate factor), each exact, documented and anchored in
relationships the knowledge graph already states. They combine only through the line items
their profiles declare (decision 46). No demand or supply-chain model is added, and neither
gets a template.
**Why.** A narrow model can be checked by hand; a broad one hides its assumptions. Every
model holds volumes fixed (fuel consumed, dollars invoiced, debt outstanding), so a demand
change combined with them would contradict them, and the graph's supplier relationships
carry no quantities. Offering those templates would present invented pathways.
**Consequence.** `airline_fuel_cost` 1.0.0 stays registered unchanged, so its Phase 4 runs
remain verifiable; the engine extensions (a change's start and duration; percentage-point
shocks applied as level changes at their own node, never carried along log-linear rules)
leave every existing result and definition hash unchanged, and the engine version stays
1.0.0.
**Revisit** when a volume model is designed — with the other models reading its volumes
rather than holding them fixed.

## 44. Scenarios are versioned; a save never overwrites

**Decision.** A scenario has a stable identity and immutable, numbered versions. A save
that changes anything adds a version, one that changes nothing adds none, and one made from
an older version than the latest (`base_version`) is refused with 409. Restoring saves the
old content as a new version. An execution refers to a version; an executed scenario cannot
be deleted (409). Phase 1 drafts became version 1 in migration `0005`.
**Why.** An execution's inputs must never change after the fact, or its results would stop
describing a question anyone asked. Last-write-wins (the Phase 1 behaviour) silently loses
edits.
**Revisit** with authentication (Phase 10): ownership, retention and deletion by an
authorised owner, with an audit record.

## 45. The graph decides whether a model applies, never how much

**Decision.** A model is included by default only when a company is chosen **and** the
graph states the exposure the model requires (directly or through the company's industry).
Otherwise it is *available* to include by hand, with the reason. The amounts always come
from the user's figures and the model's equations. The relationships that made a model
apply are served as `context_only` and drawn apart from the ones the engine propagated
along.
**Why.** The graph records that a company is exposed — as a curated fact or an assumption —
not by how much (decision 25). Using it to choose models is what it can support; using it to
size effects would invent numbers.
**Revisit** when exposures carry measured sizes with provenance (Phase 6).

## 46. Scenario profiles with a closed list of line items

**Decision.** Each model declares a scenario profile: the variables it accepts, the line
items it contributes to (from a closed list per line), the exposures that make it apply,
and cautions for quantities another model already carries. No two models may claim the same
item of the same line; the planner blocks such a plan. The Lab's equations (AG0–AG7) add the
items into lines and check operating profit against each model's own figure.
**Why.** Double counting is the classic error of composing models (the airline model already
converts its fuel bill at the new exchange rate; the foreign-currency model must not count it
again). A closed list makes the rule checkable by the planner rather than a note in the docs.
**Revisit** when models overlap legitimately (a share of the same cost); the profile would
then need explicit shares that sum to one.

## 47. Executions run on a bounded in-process pool, in recorded stages

**Decision.** `POST /scenarios/{id}/executions` answers 202 and runs the execution on a
thread pool inside the API process: 2 at once, 8 waiting, 20 seconds each; a full queue
answers 429 before anything is stored. The four stages are stored with their times as they
happen; cancellation and the time limit are checked between stages and models; a failed,
cancelled or timed-out execution stores only its state and reason; an execution left
unfinished by a stopped server is marked failed at the next start. Every change of an
execution's state is a conditional update that applies only while it is not final, so a
final execution never changes, even when two processes disagree about it. Tests run
executions inline.
**Why.** Executions take milliseconds to a fraction of a second, so a job queue with its own
broker and workers would add operations for no gain today; a bounded pool keeps the API
responsive and refuses overload explicitly. Recording stages as they happen lets the page
show real progress instead of an animation.
Recovery assumes one API process: a process that starts cannot tell another live process's
executions from abandoned ones, so it marks them interrupted too (the conditional updates
make that run stop and store nothing, rather than overwrite the state).
**Revisit** with several API processes or longer executions (Phase 9 Monte Carlo): a shared
queue (for example PostgreSQL-backed) with the same states, and leases instead of
start-up recovery.

## 48. Previews are computed, never stored

**Decision.** `POST /scenarios/preview` plans and computes a scenario exactly as an
execution would, and stores nothing. The page asks for one 450 ms after the last edit,
cancels older requests, keeps the previous figures dimmed while waiting, and labels what it
shows as a live preview; stored executions are labelled as such.
**Why.** Seeing the pathway and the result move while editing is what makes the Lab an
instrument, but a stored record for every keystroke would bury the executions that matter.
Labelling keeps a preview from being mistaken for a reproducible result.
**Revisit** if previews become slow (they take 50–130 ms here): cache the plan per graph
build.

## 49. Stress cases and sensitivity move magnitudes; nothing is clipped or sampled

**Decision.** Stress cases are other magnitudes of the same changes (a multiple, or values),
evaluated with the same models and assumptions; a value outside a variable's limits is
refused with its field. Sensitivity moves one quantity at a time around a stored execution
(at most 8 quantities, 7 points, 60 evaluations) and skips, with the reason, points a model
refuses. Neither is called Monte Carlo, and nothing is ranked or recommended.
**Why.** As in 39: exact, explainable answers to "what if it were bigger?" and "what matters
most?", without inventing distributions. Ranking cases would need an objective the user has
not stated.
**Revisit** with estimated distributions (Phase 9).

## 50. The pathway draws only what the engine computed

**Decision.** The pathway is assembled from each model's declared pathway and its run, joined
by the Lab's equations. Links say what they are — applied, propagated along a graph
relationship (with β and lag), computed by an equation, added by the Lab — and graph
context is listed in the model's lane header, not drawn as a step. The graph's other
relationships from the changed variables are listed apart as *not modelled*.
**Why.** A drawn connection reads as causation. Showing only computed links, and keeping
cited context visibly apart, lets the user see exactly which relationships carried numbers.
**Revisit** never for the principle; the drawing may change.

## 51. Lines nobody models are not shown

**Decision.** A line appears only when an included model contributes to it. Profit before
tax appears only when an interest model is included (it needs the interest baseline). Cash
flow is never shown. Baselines are the user's annual figures × horizon ÷ 12, held
constant, and labelled as inputs, not forecasts.
**Why.** Showing an unmodelled line as unchanged would claim that nothing happens to it,
which the Lab does not know. A cash-flow figure would need working capital, tax and
investment, which no model covers.
**Revisit** when models for those items exist.

## 52. Responses are compressed

**Decision.** Responses over 1 KiB are gzip-compressed when the client accepts it
(Starlette's `GZipMiddleware`, part of FastAPI's dependencies).
**Why.** A Scenario Lab preview is about 115 KB of JSON and is requested after every pause in
editing; compressed it is 15 KB, for about 5 ms of server time. The API returns no secrets
and there is no authentication, so compression does not expose a secret to
length-based attacks.
**Revisit** with authentication (Phase 10): compressed responses that mix secrets with
attacker-controlled input would then need review.

## 53. Still no new dependencies

**Decision.** Phase 5 adds no runtime or development dependency. The runner uses the standard
library's thread pool; the aggregation, pathway assembly and layout, comparison and
sensitivity are written in the project and tested; compression uses middleware FastAPI
already ships.
**Why.** As in 21, 32 and 42.
**Revisit** with a shared job queue (see 47).
