# Technology decisions

Short records of the choices made in Phases 1 and 2, why, and what would make us revisit
them. Phase 2 decisions start at [13](#13-world-bank-indicators-as-the-first-provider-fred-rejected).

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
