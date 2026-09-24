# Phase 7 plan — AI Analyst

Written before implementation, after inspecting Phases 1–6 and running their checks. It
records what was found, what was decided and why, and the order of work. The Phase 7
report will record what was delivered.

## 1. Inspection of Phases 1–6

**Verified state before any change** (commit `ca76bcb`, CI run #22 green): `make check`
passed with 758 backend tests (SQLite; the suite also passes on PostgreSQL 16) and 294
frontend tests, the OpenAPI snapshot was current, and the smoke test passed: a fresh
database, the graph built and rebuilt with no change, then 53 integration tests against the
live API.

| | Finding |
|---|---|
| **Reusable as it is** | Every read an analyst needs already exists as a service with typed responses: graph search, nodes, edges with their evidence, paths (Phase 3); series, observations with provenance and revisions (Phase 2); models and runs (Phase 4); scenarios, templates, plans, **previews that compute without storing**, executions, results and explanations (Phase 5); and Financial Intelligence (Phase 6): dossiers, exposure, drivers, changes, findings with evidence chains, and the **entity brief** with its narration rules, designed for this phase |
| **Patterns to follow** | The Lab's bounded worker pool (reserve a place, store, submit; 429 when full; inline mode for tests; recovery at start-up); polling with `poll_after_ms`; the error envelope with field paths; append-only records with hashes; fixtures captured from a real backend |
| **The environment** | `api.anthropic.com` and PyPI are reachable. **No API key for the product exists**, so no request to a language model can be made from here. The session's own Anthropic settings (for example a base URL) are present in the environment and must never be picked up by the application |
| **What is missing** | No conversation storage, no router, no tool layer, no citation model, no language-model integration. The `/analyst` page is a placeholder and the system reports the capability as planned |
| **Constraints** | No authentication (Phase 10): every route is open to whoever can reach the API, so the analyst must never reach further than the API already does. Exact decimals. Nothing fabricated. 64 KiB request bodies. No model identifier may be written into the repository: the model is configuration |
| **Skills** | `claude-api` (the Anthropic Python SDK, the manual tool loop, error classes, prompt caching); `frontend-design` (plan tokens against the brief, one signature element, avoid the generic tells); `dataviz` (charts in answers); `financial-calculator` (never assume silently; show the numbers, do not tell people what to do); `security-review` and `code-review` (review passes before the report). The example skills for artifacts and slides do not apply to an application's own interface |

## 2. What the AI Analyst is

A research assistant inside RUMIN that answers questions **from RUMIN's records and
services, through a fixed set of tools**, and shows where every figure came from. It
explains, compares, traces relationships, reads simulation results and helps build
scenarios. It does not forecast, does not decide investments, and does not state anything
it cannot cite. When RUMIN lacks what a question needs, it says so and says what would
supply it.

## 3. Two providers, one tool layer

| Provider | What composes the answer | Available |
|---|---|---|
| **Grounded** (default) | RUMIN's own router, planner and templates, filled from tool results. No language model: every sentence is built from evidence | Always, offline |
| **Anthropic** (optional) | A Claude model through the official `anthropic` SDK, calling the same tools in a loop RUMIN controls; its answer must pass the same grounding check, or the grounded answer is shown instead | When `RUMIN_ANALYST_PROVIDER=anthropic`, an API key and a model are configured |
| **Scripted** (tests only) | A deterministic stand-in that replays tool calls and text, to test the loop without a network | Tests |

The provider sits behind one interface, so the rest of the system (router, tools, evidence,
validation, storage, interface) is the same for all three. Both real providers answer the
same evaluation set.

Why a grounded provider at all: it makes the Analyst useful and fully testable without a
key, and it is the fallback whenever a model's draft fails the grounding check. Why the
official SDK: it is the documented way to call Claude from Python (typed errors, retries,
timeouts), and it keeps provider-specific code in one module. It is the first runtime
dependency added since Phase 1.

## 4. Architecture

```
 question ──► policy (length, injection markers, advice / forecast / live-data requests)
                │
                ▼
             router: intent + entities (companies, industries, variables, series,
                     scenarios, models) + magnitudes + periods; session focus for "it"
                │                         ▲
                │ clarification ◄─────────┘ (ambiguous or missing subject)
                ▼
        ┌─ grounded planner ──► tool calls ─┐        ┌─ anthropic loop ─┐
        │   (per intent)                    │   or   │ model ⇄ tools    │
        └───────────────────────────────────┘        └──────────────────┘
                          │                                   │
                          ▼                                   ▼
       tool registry: allowlisted, typed arguments, timeouts, bounded retries,
       read-only services (one compute tool: scenario preview, never stored)
                          │
                          ▼
       evidence ledger (E1, E2 … each with its source, period, units, provenance,
       evidence status or grade, model version and assumptions)
                          │
                          ▼
       answer blocks (text with citations, tables, series, paths, scenario cards,
       notices) ──► grounding check (every figure found in the evidence it cites)
                          │
                          ▼
       stored turn: question, answer, evidence, every tool call with its timing
```

`backend/app/analyst/`: `policy`, `vocabulary` and `parsing`, `router`, `context`,
`tools/` (registry and tools), `evidence`, `answer` (block types), `composer` (the grounded
templates), `grounding` (the check), `providers/` (grounded, anthropic, scripted),
`orchestrator` (one turn), `runner` (the bounded pool), `evaluation` (the question set and
its scorer).

## 5. Tools

Each tool has a name, a description, a typed input model (unknown fields refused), a
handler that calls an existing service, a time limit, and a function that turns its result
into evidence. None writes anything.

| Tool | Answers | Service reused |
|---|---|---|
| `search_records` | which companies, industries, variables, series, scenarios, models match a name | graph search, data catalogue, scenarios |
| `get_entity_dossier` | what RUMIN knows about a company or industry | Phase 6 dossier |
| `get_exposure` | which variables reach an entity, through which relationships | Phase 6 exposure |
| `get_variable_reach` | which companies a variable reaches | Phase 6 variable reach |
| `find_paths` | how two records are connected in the graph | Phase 3 paths |
| `get_relationship` | one edge with its evidence, rationale and caveat | Phase 3 edge detail |
| `get_series` | a series' stored values, provenance, trend, volatility, revisions | Phase 2 observations, Phase 6 series analysis |
| `compare_periods` | the exact change between two stored periods | Phase 6 statistics (exact decimals) |
| `list_changes` | what changed in data, graph and executions | Phase 6 changes |
| `get_findings` | the workspace's or an entity's findings, with grades | Phase 6 insights |
| `list_scenarios`, `get_execution` | stored scenarios, an execution's results and drivers | Phase 5 results, Phase 6 drivers |
| `explain_line` | why a line of an execution changed | Phase 5 explanation |
| `preview_scenario` | what the models compute for a what-if, **not stored** | Phase 5 preview |
| `list_models`, `list_templates` | which models and templates exist, what they need | Phases 4–5 |
| `get_data_coverage` | what data RUMIN holds and what is missing | Phase 6 coverage |

## 6. Evidence, citations and labels

Every tool result becomes evidence: an id (E1, E2 …), a kind of knowledge (**observed**
data, a RUMIN **record**, a **relationship** with its evidence status, a **user figure**, a
model **assumption**, a **simulated** result, a **preview** computed on request, a Phase 6
**finding** with its grade), the source record and a link to it, the period, retrieval time,
units and currency, and for simulations the models, versions and assumptions. Answer text
cites evidence ids. The **grounding check** extracts every figure from the text (signs,
separators, percentages, points, lakh and crore) and requires it to appear, at the displayed
precision, in the evidence the sentence cites. A citation to a missing id fails. For the
grounded provider the check is an invariant tested on every evaluation question; for a
language model it is the gate. A model may add **interpretation** and **general knowledge**
only in paragraphs labelled as such, and those may not contain figures.

## 7. Guardrails, security and privacy

- **Investment decisions**: context, risks, assumptions and alternatives, never a decision.
  **Forecasts**: declined, with history and scenarios offered. **Live or unknown data**:
  RUMIN says it does not hold it.
- **Language**: no causal or predictive phrasing ("will", "caused", "guarantee",
  "should buy"), checked like Phase 6's findings.
- **Injection**: retrieved text is data: delimited, stripped of control characters, capped
  in length, never followed as instruction. Tools are allowlisted with validated arguments;
  no SQL, shell or code; no write except the conversation itself.
- **Limits**: question length, turns per session, tool calls per turn, a deadline per turn,
  model tokens per turn and per day, a bounded pool (429 when full).
- **Access**: RUMIN has no authentication yet. The analyst reaches only what the API
  already serves, and every tool call passes an access context, so that per-user checks
  have one place to go in Phase 10.
- **Privacy**: conversations are stored so they can be reopened, and can be **deleted**.
  Logs record ids, intents, tools, timings and token counts, never the question or answer.
  The API key stays in the backend.

## 8. Conversation and context

A session keeps a **focus** (the entity, series, scenario or execution under discussion), so
"and its revenue exposure?" resolves. A new explicit subject replaces the focus. Data is
fetched again on every turn: no earlier tool result is reused as current. A language model
receives the focus and a bounded summary of recent turns (questions and headlines), not the
full history.

## 9. API and database

Migration `0007_analyst`: `analyst_sessions`, `analyst_turns` (question, status, intent,
answer, evidence, grounding result, provider, usage, timings; final turns never change) and
`analyst_tool_calls` (tool, arguments, status, a bounded result, hash, timing). Under
`/api/v1/analyst`: capabilities (provider, tools, limits, suggested questions from the actual
data), sessions (create, list, read, rename, delete), turns (ask: 202 and poll; read). Every
response follows the existing conventions.

## 10. Interface

The `/analyst` workspace replaces the placeholder: sessions on the left, the conversation
in the centre, and an **evidence margin**: each answer reads as a research note whose
sources sit beside the sentences that cite them. That margin is the signature element. Also:
a method trace listing the tool calls that actually ran, with their timings; tables and
series charts (the `dataviz` rules, reusing the Data Explorer's chart); scenario cards
with "Open in the Scenario Lab" (the user, not the model, saves and executes); exposure
paths drawn as in Phase 6; notices for assumptions and missing data; clarification choices;
suggested questions; copy and export. There is no typing animation: an answer appears when
it exists, and steps appear as the server records them.

## 11. Testing and evaluation

Router, parsing, tools (validation, allowlist, timeouts, retries), evidence and grounding,
the composer per intent against the sample database, the orchestrator with the scripted
provider (tool loop, refused tools, invented figures, injection, failures, retries), the
Anthropic adapter through the real SDK against a mocked HTTP transport (request shape,
tool loop, errors, refusals), the API (sessions, turns, polling, deletion, limits, 429), and
the page against fixtures captured from a real backend. An **evaluation set** of
representative questions, each with its expected intent, tools, evidence kinds, required
disclosures and forbidden content, is scored for both the grounded provider and adversarial
scripted runs. A live test against the Anthropic API runs only when a key is configured,
and is reported as not run here. Phases 1–6 must stay green.

## 12. Order of work

1. Core: evidence, answer blocks, vocabulary, parsing, router, policy, context.
2. Tools and the registry.
3. The grounded planner and composer; the grounding check.
4. The Anthropic provider and the scripted provider; the orchestrator.
5. Storage (migration `0007`), the runner, the API, OpenAPI and generated types.
6. The interface, and the Scenario Lab handoff.
7. Tests, the evaluation set, fixtures, visual review, security review.
8. Documentation, the report, commit, push, CI.
