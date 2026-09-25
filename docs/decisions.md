# Technology decisions

Short records of the choices made in Phases 1 to 10, why, and what would make us revisit
them. Phase 2 decisions start at [13](#13-world-bank-indicators-as-the-first-provider-fred-rejected),
Phase 3 decisions at [23](#23-the-knowledge-graph-lives-in-the-existing-relational-database),
Phase 4 decisions at [33](#33-one-narrow-domain-first-an-airline-fuel-cost-shock),
Phase 5 decisions at [43](#43-several-narrow-models-composed-by-line-items),
Phase 6 decisions at [54](#54-statements-come-only-from-numbered-rules-with-evidence-chains),
Phase 7 decisions at [65](#65-two-providers-behind-one-tool-layer-rumins-own-composer-by-default),
Phase 8 decisions at [73](#73-plain-threejs-loaded-only-with-the-3d-page),
Phase 9 decisions at [79](#79-advanced-analyses-re-evaluate-stored-executions-through-one-evaluator),
Phase 10 decisions at [88](#88-local-accounts-and-server-side-sessions-in-an-httponly-cookie).

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

## 54. Statements come only from numbered rules, with evidence chains

**Decision.** Financial Intelligence states nothing except through one of 19 documented rules
(D01–D06, S01–S06, G01, X01, E01–E03, C01–C02). A rule fills a sentence template with
computed values and attaches the chain of steps that produced it, each with its basis and
references. An insight without a chain cannot be built (`ChainError`), and a test checks
every insight the API returns for its chain, grade, not-a-forecast limitation and forbidden
words ("will", "caused", "guarantee", "recommend", …). No language model generates text.
**Why.** The brief asks for intelligence that can be checked, not summaries. A template with
computed values can be traced to records and tested. Free text cannot, and it invites
causal and predictive language the data does not support.
**Consequence.** RUMIN says nothing that no rule covers. Findings are fewer and plainer than a
generated summary, and every one can be walked back to stored records.
**Revisit** when an AI Analyst phrases findings (Phase 7): it may reword the brief (decision
62) but must cite insight ids and quote only its numbers.

## 55. The evidence grade is the weakest link, not a probability

**Decision.** Every insight is graded by the weakest step of its chain: observed > documented >
curated > simulated > assumed > unverified. Relationships are graded by their Phase 3
evidence status, simulations as simulated, and observations, calculations and RUMIN's own
records as observed. A chain with a simulation is marked conditional on it. The grade is
shown as a word and a line pattern, never as a number.
**Why.** As in 25: a confidence score would claim a precision nobody has. The weakest link says
what a statement actually rests on. An exposure finding built on an assumed relationship is
*assumed*, however exact the arithmetic around it.
**Consequence.** On the sample network, every exposure finding is *assumed*, which is the honest
grade of illustrative data.
**Revisit** if evidence-backed relationships with measured effects become common, and the
graph starts to carry effect sizes with uncertainty.

## 56. Thresholds are configuration, recorded with every result; no composite score

**Decision.** What counts as a change, a trend, high volatility, an unusual move or a
concentrated dependency is decided by nine named thresholds. Each has a documented default,
bounds and a reason, can be overridden per request (query parameters, or the body of a
stored analysis), is validated with its field, and is recorded in every result. Signals
report the quantities they compute. There is no composite or risk score.
**Why.** A detected change is a test result, and a reader must see which test. Scores that
combine unlike quantities (a count of relationships, a t statistic, a simulated amount)
mean nothing definable.
**Revisit** per-series thresholds when monthly and daily data arrive.

## 57. Exact, descriptive statistics written in the project

**Decision.** Changes, least-squares trends with a t test, sample standard deviations,
percentile ranks, and the modified z-score (median and MAD) are computed in exact decimal
arithmetic in `stats.py`. The critical values of Student's t come from the standard table,
taking the stricter row between two. No statistics library is added.
**Why.** The calculations are few and short, exactness makes results hashable and reproducible
(as in 35), and hand-checked tests pin every one. A library would bring floating point and a
dependency for no gain.
**Consequence.** No estimation, forecasting or multiple-testing correction exists, and the
documentation says so.
**Revisit** with Phase 9 (probabilistic simulation, estimation), where a statistics library
would be evaluated like any dependency.

## 58. Exposure comes only from validated edges, and says *that*, never *how much*

**Decision.** Exposure paths use only edges current in the latest completed build that passed
every validation rule: direct, via the industry, and up to two `influences` hops upstream.
Supply and credit relationships and context (industry, sector, country, currency,
competitors) are listed apart, never as exposure. Every path keeps each edge's evidence
status, and an `evidence_backed` filter keeps only cited ones.
**Why.** The graph records that a company is exposed, not by how much (25, 45). Treating a
connection as a size or a cause would invent numbers.
**Revisit** when exposures carry measured sizes with provenance.

## 59. Stored results are read, never recomputed; interpretations are labelled previews

**Decision.** Contributions, sensitivities and results are read from stored executions and
runs, and their residuals are reported. The one place Financial Intelligence runs models is
S06, the *model interpretation* of an observed change. It applies the change alone to a
stored scenario version, runs it as a preview, never stores it, and labels it an
interpretation in its statement, chain and limitations.
**Why.** Recomputing would duplicate the engine and could disagree with what was stored.
Setting an observed change beside what the models make of it is useful only if the two are
never confused.
**Revisit** if interpretations should be kept; they would then need their own stored
records and provenance, like executions.

## 60. Reads recompute from the store; stored analyses are fingerprinted snapshots

**Decision.** Every read computes its analysis from the current store and writes nothing.
`POST /intelligence/analyses` stores a snapshot (the result as returned, its thresholds, a
fingerprint of everything it read, and SHA-256 hashes of both) in `intelligence_analyses`
(migration `0006`). Snapshots are never updated, recomputed or deleted. Reading one back
compares its fingerprint with the store and reports it as current or stale, with what
changed.
**Why.** An analysis must always reflect the latest revision of every value, and a record of
what was concluded must never silently change. A snapshot that knows it is stale serves
both.
**Revisit** retention and deletion with authentication (Phase 10); caching reads if they
become slow.

## 61. The workspace is bounded by companies, never by edges

**Decision.** The workspace lists the first 200 companies by name, with every validated edge
their paths use, and the latest execution of each (chosen in the database). The coverage
reports the total and that the listing is truncated. Reads that could grow (values per
series, revisions, executions per entity, graph changes, shared-driver findings) each have a
stated bound.
**Why.** An early version capped the edges, which could show a listed company without an
exposure it has. Bounding the companies keeps each listed company complete, and a test
compares each with its own analysis. Measured on SYNTHETIC networks of up to 20,000
companies, the overview stays near 0.3 s.
**Revisit** with search and paging over companies, or with precomputed exposure per build.

## 62. A versioned brief for the AI Analyst; the model never calculates

**Decision.** `GET /intelligence/entities/{key}/brief` returns `rumin.intelligence.brief/1`: the
entity's observations, exposures, relationships, drivers, simulation results, entered
figures, assumptions, every insight with its chain, limitations and next steps, and five
narration rules. The first rule is to quote numbers only from the brief and never compute
new ones.
**Why.** Phase 7 will phrase findings with a language model. Giving it structured facts with
references and rules, rather than asking it to analyse, keeps every number traceable, and
lets its output be checked mechanically.
**Revisit** the format with Phase 7; a breaking change needs `/2`.

## 63. A ledger with evidence chains, not a dashboard of scores

**Decision.** The interface lists findings as ruled rows grouped by kind of knowledge, each
opening into its evidence chain (the module's signature element). Grades are line patterns
with a word, reusing the graph's patterns, never colour alone. Exposure is a table of
companies × variables, drivers are one-hue bars from zero with printed values, and
thresholds, tabs and filters live in the URL. The sky-blue accent is kept for the subject in
focus, the step that sets a grade and the entity at the end of a path.
**Why.** Gauges, scores and equal cards are the generic answer and would present undefined
numbers. The ledger fits a system whose rule is "no statement without evidence".
**Revisit** never for the principle; the layout may change.

## 64. Still no new dependencies

**Decision.** Phase 6 adds no runtime or development dependency. The statistics, the evidence
model, the rules, the brief and the interface are written in the project and tested.
**Why.** As in 21, 32, 42 and 53.
**Revisit** with Phase 9's statistical needs (see 57).

## 65. Two providers behind one tool layer; RUMIN's own composer by default

**Decision.** The AI Analyst drafts answers through a provider interface with two real
providers: RUMIN's **grounded composer** (per-intent templates filled from tool results; no
language model) and an **Anthropic** provider (a Claude model through the official SDK). The
grounded composer is the default, answers every clarification and refusal, and is the
fallback whenever the model fails or its draft fails the check. A scripted provider exists
for tests only.
**Why.** The Analyst must be useful, testable and honest without a key, offline and on a
fresh install, and a model's answer needs something safe to fall back to. One tool layer,
one evidence ledger and one check for all providers mean a model can change how an answer is
worded, never what it rests on.
**Revisit** the default once a model has been measured on the evaluation set (see 70).

## 66. Tools are an allowlist over existing services; one compute tool, never stored

**Decision.** 17 tools, each a typed input model (unknown fields refused), a time limit and a
renderer into evidence, over services Phases 2–6 built. 16 read; `preview_scenario` computes
a what-if through the Scenario Lab's preview and stores nothing. No SQL, code, shell, file,
network or write tool. Each call runs in its own thread and session; a transient database
error is retried once.
**Why.** A question should never be able to reach further than the API already does, and
the Analyst should compute no figure of its own. Reusing the services keeps one definition of
every number.
**Revisit** with Phase 10's access control (the `Access` context is where per-user checks go).

## 67. Every figure cites evidence, and one check decides what is shown

**Decision.** Tool results become a numbered evidence ledger (kind of knowledge, source and
link, period, units, provenance, exact values). Answer text cites ids inline. The grounding
check requires every figure (at its displayed precision), date and version to be in the
evidence its sentence cites, every citation to exist, no figures in interpretation, and no
predictive, causal or advisory phrasing. A model's failing draft is replaced; failing parts of
RUMIN's own draft are withheld with a notice.
**Why.** Citations only help if they are true. A mechanical check makes "never fabricate" a
property of the system rather than a request to a model. Holding RUMIN's own templates to the
same check found a real defect when the suite ran on PostgreSQL
([evaluation](analyst/evaluation.md#results)).
**Revisit** if the check proves too strict for useful model answers; never to let an
unsupported figure through.

## 68. The model is configuration; the SDK never reads the environment

**Decision.** No model identifier is written in the repository: `RUMIN_ANALYST_MODEL` names
it. The SDK client is built with RUMIN's own key, base URL (`https://` only), timeout and
retries, so `ANTHROPIC_*` variables in the process environment are never used; a set
`ANTHROPIC_CUSTOM_HEADERS` stops the provider. The manual tool loop is bounded (model
requests, tool calls, deadline, daily token budget), ends with a structured `submit_answer`,
caches the system prompt and uses adaptive thinking unless turned off.
**Why.** Model choice is a deployment decision that changes faster than code. A server
process often inherits credentials meant for something else; picking them up silently would
spend someone else's account or send data where it was not meant to go.
**Revisit** when the SDK or the API changes the relevant defaults.

## 69. Conversations are stored; turns are answered on a bounded pool and polled

**Decision.** Migration `0007` stores sessions, turns and tool calls. Asking reserves a place
in a bounded pool (the Scenario Lab's design: 2 answering, 8 waiting, 429 beyond, before
anything is stored), stores the turn and answers 202; the reader polls. A turn is claimed and
finished with conditional updates, never answered twice, final once answered. Tool calls are
stored as they end, so the interface shows each step as it happens. Conversations can be
deleted.
**Why.** Answers take from milliseconds to tens of seconds with a model; polling reuses the
Lab's proven pattern and works through any proxy. Storing every tool call is what lets the
interface show how an answer was found, and lets a reviewer check it later.
**Revisit** streaming (server-sent events) if model answers feel slow; a shared queue across
processes with Phase 10.

## 70. An evaluation set scores the Analyst, adversarial models included

**Decision.** `app/analyst/evaluation.py` holds 33 cases (expected intent, statuses, tools,
evidence kinds, notices, text), run in the tests for the grounded composer and for seven
misbehaving scripted models, and from the command line for any provider.
**Why.** "The Analyst works" needs a measurable meaning before a model is trusted with it, and
the claim that no unsupported answer reaches a reader needs adversaries to test it.
**Revisit** by adding real users' questions as they arrive.

## 71. The evidence margin is the interface's signature element

**Decision.** Each answer reads as a research note: the question, the headline, cited
paragraphs and RUMIN's own displays (tables, the Data Explorer's chart, paths, scenario
cards, notices), and beside it a margin of the sources it cites, in citation order, each
with its kind of knowledge (label and shape, never colour alone), link and details. The
method (tool calls with timings, the check, the provider) is one click away. No typing
effect: steps appear as the server records them.
**Why.** An analyst's answer is only as good as the reader's ability to check it; putting the
sources beside the sentences makes checking the default, not an extra step. Generic chat
bubbles would hide exactly that.
**Revisit** never for the principle; the layout may change.

## 72. One new dependency: the official Anthropic SDK

**Decision.** Phase 7 adds `anthropic` (with `jiter`, `docstring-parser` and `sniffio`),
imported only by the Anthropic provider. Everything else (router, tools, ledger, check,
composer, interface) is written in the project.
**Why.** The official SDK is the documented way to call Claude from Python: typed errors,
retries with backoff, timeouts and the current request shapes. Writing an HTTP client for it
would duplicate that and drift. `pip-audit` found no known vulnerability in the lock file.
**Revisit** with each SDK major version.

## 73. Plain Three.js, loaded only with the 3D page

**Decision.** The 3D universe draws with `three` (and `@types/three` for development), used
directly, behind a small renderer contract (`rendererTypes.ts`). The renderer is imported
only when the canvas mounts and only when the browser has WebGL 2, as its own chunk (553 kB
minified, 139 kB gzip); the rest of the product does not load it.
**Why.** A 3D graph needs a WebGL scene graph, instancing and shaders; writing those against
raw WebGL would be a renderer project of its own. React Three Fiber was considered: it adds a
reconciler and more packages for a scene this simple, while the explorer's pattern is already
a pure model feeding a renderer. Keeping the meaning in plain data (`scene.ts`) and the
renderer behind a contract lets the tests run the host with a stand-in, keeps disposal
explicit, and keeps the draw calls few (about twenty for any graph size). `npm audit` reports
no known vulnerability.
**Revisit** with each Three.js release that changes `WebGLRenderer` or instancing.

## 74. Height is kind, never importance

**Decision.** Each kind of record sits on a stratum (data, drivers, industries, companies,
places), in the Phase 1 network's order turned upright; within a stratum a seeded force
layout places connected records near each other. Node size is by kind only, and depth,
height and brightness encode no magnitude.
**Why.** In three dimensions every channel competes with perspective. Using height for a
categorical, stable property gives the reader a frame of reference (an assumed effect reads
downwards) without implying that anything is bigger or matters more. A second size channel
(degree, as in 2D) would be unreadable under perspective.
**Revisit** if the graph gains a genuinely ordinal dimension worth the vertical axis.

## 75. The whole build only within a budget

**Decision.** The universe draws the whole current build only when it holds at most 500
nodes and 2,500 edges (read 500 per page, at most six requests). A larger build starts from a
search and grows by neighbourhoods, through the 2D explorer's own state and limits.
**Why.** Everything is laid out and labelled on the main thread; measured, the first layout
takes about half a second at the budget in this environment. A hard budget keeps the page
responsive and honest (a truncated read says so) without a second data path.
**Revisit** with a Web Worker layout or a level-of-detail view.

## 76. Overlays come only from stored, completed executions

**Decision.** A scenario overlay reads one stored execution, and only if it completed: its
plan (the stated changes and the simulated entity), its modelled pathway (propagated and
cited links that carry a graph edge key, and the graph edges no included model simulates)
and its results. Figures appear only in the panel, from the stored strings; the canvas shows
roles, never values.
**Why.** An overlay that inferred impacts from graph relationships, or recomputed anything,
would turn the graph's recorded or assumed links into claimed effects. The Scenario Lab
already records exactly what a model propagated and what it did not; the universe only shows
it where it sits in the graph.
**Revisit** to compare two executions (the extension point is `overlay.ts`).

## 77. The list is the canvas's twin, and the keyboard operates the canvas

**Decision.** A *List* view shows every node and relationship in view as tables, opens the
same panels, is remembered on the device, and replaces the canvas when WebGL 2 is missing or
the context is lost. The canvas is one tab stop (`role="application"`): arrow keys move the
selection to the nearest node on screen, with Enter, E, C, Escape, zoom, turn and reset keys.
The selection is announced politely; the camera jumps instead of flying under reduced
motion; the previous view stays mounted while the next one loads so focus is kept.
**Why.** A 3D canvas cannot be read by assistive technology or used without a pointer by
itself; the list makes every record reachable, and the keyboard model makes the canvas
itself usable. Nothing may depend on seeing the canvas.
**Revisit** never for the principle.

## 78. Rendering on demand; names in the DOM, placed by priority

**Decision.** The universe draws a frame only when something changes (scene, size, theme,
camera, or a fly-to frame) — no idle loop. Nodes are instanced per shape with a coarser
silhouette mesh for their outlines; edges are one instanced quad per edge with a screen-space
pattern shader. Names are DOM elements over the canvas, placed greedily by priority, kept off
other nodes and inside the canvas, at most 36 at a time.
**Why.** An analytical view should cost nothing while it is read. Instancing keeps draw calls
constant as the graph grows; the coarser outline mesh halved the triangles; DOM names stay
sharp, use the product's type, and never pretend a label that does not fit was written.
**Revisit** if names need to be selectable on the canvas itself.

## 79. Advanced analyses re-evaluate stored executions through one evaluator

**Decision.** Grids and Monte Carlo analyses work only on a **completed, stored** execution
of the Scenario Lab. One `Evaluator` (`scenario_lab/evaluation.py`) re-evaluates the
execution's stored model runs with some quantities changed — the Phase 4 engine's
`evaluate_result`, each model's rules, the graph channel check against the run's stored
snapshot, the Lab's aggregation — and one-at-a-time sensitivity, the grid and Monte Carlo all
call it.
**Why.** A second engine, or a statistical shortcut around the models, would give results the
product could not explain or reproduce. A stored execution fixes everything the analysis does
not vary, so its figures are conditional on exactly what is recorded, and a re-run can prove
it. Sharing the evaluator also shared the fix in [85](#85-a-methods-defect-is-fixed-by-versioning-the-method-not-by-rewriting-results).
**Revisit** if an analysis needs to vary what an execution fixed (the horizon, the set of models).

## 80. Distributions are stated, bounded and never clipped

**Decision.** A Monte Carlo quantity takes one of three distributions — uniform, triangular,
discrete (2–12 values, positive weights) — stated by the user. Every endpoint must pass the
input's own range rule and decimals; draws are rounded half to even to those decimals; a
whole-month input takes only a discrete distribution. A draw that breaks a model's rule is
**rejected and counted by rule, never adjusted**; fewer than 100 accepted draws give no
summary. Quantities are drawn independently, and every analysis with more than one says so.
The starting points offered in the interface are the models' default variations as uniform
ranges, labelled as the user's assumption.
**Why.** RUMIN holds no observations to estimate a distribution from, so a distribution is an
assumption and must be visible as one. Bounded supports inside the valid range make clipping
unnecessary; clipping or re-drawing would silently reshape the stated distribution. Normal
or lognormal distributions would need truncation to stay valid. Correlated draws need a
stated correlation structure, which is a separate design.
**Revisit** with correlated draws (a rank-correlation structure) and empirical distributions
once observations are stored.

## 81. Python's Mersenne Twister with a recorded seed, in exact decimals

**Decision.** Draws use `random.Random(seed).random()`, one number per quantity per draw in
request order (even for a rejected draw), turned into values by the inverse transform in
34-digit decimal arithmetic. The seed is recorded; the server picks one with
`secrets.randbits(53)` when none is given; seeds are at most 2⁵³ − 1. NumPy is not used.
**Why.** Python guarantees `random()`'s sequence for a given seed across versions, so a stored
analysis reproduces exactly, which `verify` checks by hash. Decimal arithmetic keeps the
engine's exactness through the transform. 2⁵³ − 1 is the largest integer a browser reads
exactly from JSON; a larger seed would be shown and re-sent wrongly. No new dependency was
needed for 2,000 draws taking a few seconds at most.
**Revisit** if analyses need far more draws (then vectorised sampling, with its own
reproducibility guarantee recorded in `sampler_version`).

## 82. Percentiles only as precise as the draws support; shares, never probabilities

**Decision.** Percentiles follow Hyndman–Fan type 7 (Excel's `PERCENTILE.INC`); P5, P50 and
P95 carry a distribution-free interval between two order statistics with its **exact**
binomial coverage (computed in fractions). The share of draws below zero or at or below a
threshold is labelled a share of draws under the stated distributions. Rank correlations
(Spearman, average ranks) describe association within the sample. Diagnostics — the running
mean with ±2 standard errors, the two halves compared, the relative standard error — are
shown with every result.
**Why.** A percentile from a few hundred draws has sampling error; printing it alone would
claim precision it lacks. Calling a share a probability would present the user's assumptions
as a forecast. Variance-based (Sobol) indices would need many more evaluations and a design of
their own; a rank correlation is honest about what it is.
**Revisit** with variance-based indices once analyses can run longer.

## 83. Two quantities together: the grid and its interaction term

**Decision.** A grid varies two different quantities over their default variation or listed
values plus the executed value (at most 7 × 7), and reports for every cell the value, its
change from the execution and the interaction *f(a, b) − f(a, b₀) − f(a₀, b) + f(a₀, b₀)*;
a cell that breaks a rule is skipped with its reason and the interactions that need it are
not computed. The summary says whether the effects simply add (within 10⁻⁶).
**Why.** One-at-a-time analysis cannot show that a weaker rupee makes a crude rise costlier;
the interaction term isolates exactly that, is zero along the executed row and column by
construction, and can be checked by hand (the crude × rupee case is, to the rupee).
**Revisit** for three-way interactions — better served by variance-based indices.

## 84. A verification register, never "validated"

**Decision.** Every registered model version has a register of checks run live through the
engine: the model page's worked example (hand calculations on hypothetical figures) to the
output quantum, stated properties (no change no effect, the bridge, months adding up,
contributions adding up, linearity, direction, unit invariance), documented limits and
reproducibility. Each register lists what is **not** verified — parameters not estimated,
no back-testing, assumed graph relationships, fictional sample data — and the product never
uses the word "validated". A new model cannot be registered without its checks (a test fails).
**Why.** The brief asked for model validation. Without observations, what can honestly be
established is that the arithmetic matches hand calculations and the stated properties hold;
showing that, beside what it does not establish, makes the models' status visible instead of
implied. Running live (45–110 ms) means the register can never disagree with the code.
**Revisit** when observations allow estimation and back-testing: they join the register as
new kinds of check.

## 85. A method's defect is fixed by versioning the method, not by rewriting results

**Decision.** The one-at-a-time analysis's aggregation used the executed revenue, operating
costs and interest expense when the analysis varied them, so operating margin and interest
coverage did not move. The fix passes the varied figures (method 1.1.0); migration 0008 adds
`method_version`, marks every stored analysis `1.0.0`, and the API adds a caveat to a `1.0.0`
analysis that ranked a margin or coverage by one of those figures. No stored result is
changed.
**Why.** Stored analyses are append-only records of what was computed; rewriting them would
break their hashes and the audit trail. A version and a caveat tell the reader exactly which
figures to distrust and why, and a re-run gives correct ones.
**Revisit** never for the principle.

## 86. Analyses run in the request, two at a time

**Decision.** An analysis is computed synchronously in its request, within a deadline (Monte
Carlo 20 s, grid 10 s) after which nothing is stored; a process-wide semaphore lets two
compute at once and refuses a third with 429 before any work.
**Why.** The measured worst case (2,000 draws × 8 quantities over 36 months) takes about 6 s,
so a background queue with polling would add states and failure modes for no benefit today;
the semaphore keeps a burst from occupying every worker thread.
**Revisit** with a shared queue (Phase 10) or if analyses grow longer.

## 87. No model chaining, estimation or back-testing in Phase 9

**Decision.** Phase 9 adds no chaining of one model's output into another's input, and no
parameter estimation, calibration or back-testing.
**Why.** No model's output is a documented input of another, and the Lab already combines
models through an accounting aggregation with explicit line contracts: chaining the fuel-cost
change into another model's operating costs would count it twice. Estimation and
back-testing need observations; none are stored in this environment (the World Bank retrieval
is blocked by the network) and the sample companies are fictional, so any estimate would be
fabricated. Both are recorded as not done, with the reason, in the verification register and
the roadmap.
**Revisit** when a model with a documented input contract exists, and when observations are
stored.

## 88. Local accounts and server-side sessions in an HttpOnly cookie

**Decision.** Accounts are local (e-mail and password), created by administrators; there is
no self-registration. A sign-in opens a server-side session: 256 random bits in an
`HttpOnly`, `SameSite=Lax` cookie (`Secure` and `__Host-` in production), stored only as
their SHA-256, with an idle (120 minutes) and an absolute (12 hours) expiry.
**Why.** A server-side session can be ended at once — sign-out, deactivation, a password
change, *sign out everywhere* — and a role change applies to the next request, which a
self-contained token (a JWT) cannot do without a revocation list. A cookie scripts cannot
read keeps the token away from any injected script, and hashing it means a stolen database
opens no session. Administrators create accounts because RUMIN is a team tool and has no
mail service to confirm addresses.
**Revisit** with single sign-on (an identity provider in front of the same sessions) or
multi-factor authentication, both recommended before anyone outside the team signs in.

## 89. Three roles and ownership in one shared workspace; conversations stay private

**Decision.** Roles: *viewer* (read, the Analyst), *analyst* (also create and run), *admin*
(also manage people). Everything in the workspace is readable by every member; only a
record's owner or an administrator changes it; Analyst conversations are visible to their
owner only, administrators included. Enforced in the backend on every route, with a test
that walks the route table; the interface only mirrors it.
**Why.** Phases 5–9 built one shared workspace, where a scenario is meant to be compared,
analysed and discussed by the team; per-record sharing would have changed every read path.
Conversations hold free text that may be personal, so they are private.
**Revisit** when clients or engagements need separation inside one deployment (several
workspaces); until then, one deployment per workspace.

## 90. Cross-site changes are refused by origin, not by tokens

**Decision.** A request that changes data under `/api/` is refused when its `Origin` is not
RUMIN's own (or a listed origin) or the browser marks it `Sec-Fetch-Site: cross-site`;
`SameSite=Lax` cookies and JSON-only bodies add layers. No CSRF token.
**Why.** Every browser RUMIN supports sends `Origin` on such requests and Fetch Metadata,
and the API accepts only JSON, which a cross-site form cannot send; a token would add
state and a round-trip for no additional protection here. It also means the web server
must pass the browser's `Host` unchanged, which the dev server and nginx do.
**Revisit** if a non-browser client with cookies, or an older browser, must be supported.

## 91. Argon2id with the library's defaults, and a length-first password policy

**Decision.** Passwords are hashed with Argon2id through `argon2-cffi` (RFC 9106's
low-memory profile), rehashed at sign-in when the parameters change. The policy follows NIST
SP 800-63B: 12 to 128 characters, no composition rules, common passwords and one's own
e-mail or name refused.
**Why.** An established library and a memory-hard function; no homemade cryptography.
Composition rules make passwords harder to remember, not harder to guess.
**Revisit** with a breached-password check, or when an identity provider owns passwords.

## 92. Guessing is slowed per address, per account from an address, and per account

**Decision.** Four limits: an address waits after 20 failures in 10 minutes; an address waits
for one account after 5 failures for it in 15 minutes; an account locks for 15 minutes after 50
failures from anywhere since its last successful sign-in (the count restarts when the lock
ends); nginx allows 10 sign-in requests a minute per address. The first two live in the API
process's memory, the third in the database, counted by one `UPDATE … RETURNING`. A success
clears only its own account-and-address window. Unknown accounts cost the same Argon2 work,
get the same message and pass through the first two limits alike.
**Why.** The first design locked the account itself after 5 failures and refused even the
right password, so anyone could keep chosen accounts (every administrator) locked with one
request per lock period; the independent review found it, with a lost-update race in the
count and a success that cleared the address's failures. Now someone guessing from one
place locks out only themselves; locking an account for everyone needs 50 failures, which the
address limits spread over many addresses; the total guesses per account stay within NIST SP
800-63B's 100. Accepted: people behind one NAT share the address limits, and the account
lock (after 50 failures) answers 429 where an unknown account would still answer 401.
**Revisit** before a public launch (limits shared across processes; a uniform answer for the
account lock) or if a shared office is locked out in practice.

## 93. Accounts are deactivated, never deleted

**Decision.** There is no way to delete an account through RUMIN; deactivation ends its
sessions and keeps its records' author.
**Why.** Scenarios, executions and analyses are immutable history; deleting their author
would leave unexplained records, and the audit trail would lose its subjects.
**Revisit** when an erasure duty applies ([privacy](privacy.md#areas-for-qualified-review)):
an anonymising erasure that keeps the records and replaces the person.

## 94. Production refuses development settings at start-up

**Decision.** With `RUMIN_ENVIRONMENT=production` the API does not start on SQLite, with local
or `http://` CORS origins, or with insecure cookies, and names every problem; the
interactive documentation is off unless asked for.
**Why.** A deployment made by copying development settings is the most likely
misconfiguration; failing loudly at start-up costs nothing.
**Revisit** when a new setting has a dangerous development default.

## 95. One API process per deployment

**Decision.** The production image runs one uvicorn process (`--workers 1`) and the compose
file one API container.
**Why.** The scenario and Analyst runners and their queues (47, 69), the two-analysis limit
(86), the per-address sign-in throttle (92), the Analyst's token budget and the metrics
live in the process. A second process would split every limit and could not see or recover
another's work. One process served the measured single-user loads with medians of
milliseconds.
**Revisit** with a shared job queue and shared limits (PostgreSQL or Redis) when one process
is not enough.

## 96. Metrics in the Prometheus text format, without a client library

**Decision.** `GET /metrics` renders counters, gauges and histograms kept in the process:
requests by route template and status, durations, requests in flight, security events, the
queues. It answers administrators and listed scraper addresses; nginx does not serve it.
**Why.** The format is small and stable, and one process (95) needs no multi-process
aggregation, so a dependency would add nothing. Route templates keep the number of series
bounded and put no identifier in a label.
**Revisit** with several processes (the client library's multi-process mode) or
OpenTelemetry tracing.

## 97. Docker Compose on one host, nginx in front, migrations by hand

**Decision.** The production stack is a compose file: PostgreSQL on an internal network, the
API and nginx, each unprivileged, read-only and without capabilities; nginx terminates TLS,
sends the security headers and limits requests. Migrations are a deliberate step after a
backup, never run at start-up. Backups are `pg_dump` archives; rollback runs the previous
release's images, restoring the pre-upgrade backup when the release migrated.
The API connects as `rumin`, which owns its database and nothing else; the `postgres`
superuser is used only inside the database container, for restores.
**Why.** The smallest deployment a team can run and inspect on one host, with nothing
irreversible happening on start-up; a failed migration then leaves the old release running.
A non-superuser role keeps a flaw in the API from becoming control of the database server
(`COPY … TO PROGRAM`, new roles).
**Revisit** for high availability (managed PostgreSQL, several hosts, an orchestrator).

## 98. A strict Content-Security-Policy, enforced in the launch suite too

**Decision.** The web app's policy allows scripts, styles, fonts and connections from its own
origin only: no inline script (the theme script is a file), no `eval`, no `data:` fonts
(Vite never inlines fonts). `vite preview` sends the same policy, read from the nginx
snippet, so the launch suite runs under it.
**Why.** A policy is only safe to ship if the product is tested under it: run against the
production stack, the suite found a font Vite had inlined as a `data:` URI and the policy
blocked.
**Revisit** if a feature needs a third-party origin (it would be listed explicitly).

## 99. A browser launch suite with axe, on a desktop and a phone, in CI

**Decision.** Playwright opens every page and runs the core workflows in Chromium at
1440 × 900 and 390 × 844, with `axe-core`, console and overflow checks and timings, on a
fresh database in CI; the same suite runs against the production stack by URL.
**Why.** The Phase 10 audit's accessibility and phone defects came back unnoticed between
phases; the suite then found defects no unit test could (a sticky panel covering *Save and
execute*, a page widened by a long name, repeated region names, the blocked font).
**Revisit** to add Firefox and WebKit, visual comparisons, and sessions with people who use
assistive technology, which no automated rule replaces.
