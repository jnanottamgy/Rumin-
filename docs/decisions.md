# Technology decisions

Short records of the choices made in Phase 1, why, and what would make us revisit them.

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
