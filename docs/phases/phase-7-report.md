# Phase 7 report — AI Analyst

**Status: implemented and verified locally (SQLite and PostgreSQL 16); a language model has
not been called.** RUMIN now has an AI Analyst that answers questions about its own records in
plain language: companies and industries, exposure and the relationships behind it, stored
series, connections in the graph, stored scenarios and why their lines moved, what-ifs, what
changed, findings, models, templates and what data is held. It reads RUMIN only through **17
allowlisted tools** over the services Phases 2–6 built, and every figure it writes **cites the
evidence it came from**, shown in a margin beside the answer. A mechanical **grounding check**
decides what is shown: an answer, or a part of one, whose figures are not in its evidence never
reaches a reader. The plan written before implementation is in
[phase-7-plan.md](phase-7-plan.md); the documentation is in [`docs/analyst/`](../analyst/README.md).

> **What an answer is not.** Not a forecast: simulated figures hold only under their
> scenario's changes and entered figures, and say so. Not advice: questions for investment
> decisions get the context for one, never the decision. Not live: every value has the period
> it describes and the time it was read. Not a causal claim: a relationship is *stated in the
> knowledge graph*. Not invented: the Analyst computes no figure of its own.

## At a glance

| | In this build |
|---|---|
| **Implemented** | `backend/app/analyst/` (policy, vocabulary and parsing, router, context, 17 tools and their registry, evidence ledger, answer blocks, grounded composer, grounding check, three providers, orchestrator, turn runner, evaluation set); migration `0007` (sessions, turns, tool calls); 8 API operations; the `/analyst` workspace with the evidence margin and the Scenario Lab hand-over; tests, fixtures captured from a real backend, an evaluation CLI and documentation |
| **Providers** | RUMIN's **grounded composer** (default; no language model; offline); an **Anthropic** provider through the official SDK, optional, held to the same check with fallback; a scripted provider for tests |
| **Language model** | **Not called.** No API key for the product existed where RUMIN was built. The provider is tested through the real SDK against a mocked HTTP transport; a live test runs only with a key and a model configured |
| **Evaluation** | 33 cases; the grounded composer passes 33 (median 27 ms per question); seven adversarial scripted models never reach a reader |
| **Synthetic data** | The exchange-rate and inflation histories of `tests/intelligence_support.py`, stored through the real ingestion pipeline, used **only** in tests, fixtures and documentation examples, labelled SYNTHETIC |
| **Hypothetical data** | The REFERENCE scenario's company figures on the fictional Aerisca Airways, as in Phases 5–6 |
| **Fabricated data** | **None.** Nothing is filled in, estimated or invented; what RUMIN does not hold is said |
| **Dependencies** | **One added**: the official `anthropic` SDK (1.8.0), with `jiter`, `docstring-parser` and `sniffio`, imported only by the Anthropic provider ([decision 72](../decisions.md#72-one-new-dependency-the-official-anthropic-sdk)) |

## 1. Inspection of Phases 1–6

Before any change, on commit `ca76bcb` (CI run #22 green), `make check` passed with 758 backend
tests and 294 frontend tests, and the smoke test with 53 integration tests
([plan, section 1](phase-7-plan.md#1-inspection-of-phases-16)). Every read the Analyst needed
already existed as a typed service; the Scenario Lab's bounded runner, its polling contract and
its preview-without-storing were the patterns to reuse. The `/analyst` page was a placeholder.
The session's own Anthropic settings were present in the environment and had to be kept out of
the product.

## 2. What was built

| Layer | Change |
|---|---|
| Analyst core | `app/analyst/` (about 9,400 lines): `policy`, `vocabulary`, `parsing`, `router` (24 intents), `context`, `evidence`, `answer`, `composer`, `grounding`, `orchestrator`, `runner`, `evaluation`, `tools/` (registry and 17 tools), `providers/` (grounded, anthropic, scripted). `ANALYST_VERSION` 1.0.0 |
| Persistence | Migration `0007_analyst`: `analyst_sessions`, `analyst_turns`, `analyst_tool_calls`; no existing table changed ([data model](../data-model.md#ai-analyst-phase-7)) |
| API | 8 operations under `/analyst`: capabilities; sessions (list, create, read, rename, delete); turns (ask: 202 and poll; read) ([API](../api.md#ai-analyst)); the OpenAPI snapshot (88 paths) and the generated frontend types regenerated; the system reports the capability as available |
| Frontend | `pages/AnalystPage.tsx` and `features/analyst/` (about 3,000 lines): conversations, notes with answer blocks, the evidence margin, the method trace, following a turn as it is answered, export and copy; the Scenario Lab opens a hand-over draft unsaved |
| Tests | 301 backend tests (1,059 in all, one skipped without a key), 27 frontend tests (321), 4 integration tests (57); fixtures captured from a real backend |
| Tools | `backend/scripts/capture_analyst_fixtures.py`; `python -m app.analyst.evaluation` |
| Documentation | [`docs/analyst/`](../analyst/README.md) (10 pages), decisions 65–72, this report, and updates to the README, architecture, API, data model, data dictionary, environment, setup, testing, design system, security, roadmap and known limitations |

## 3. Architecture and provider choices

A question is screened, routed (intent, records named, figures, periods, the conversation's
focus), answered by a provider through the tool registry, checked, and stored with every tool
call ([architecture](../analyst/architecture.md)).

- **Two providers behind one tool layer** ([decision 65](../decisions.md#65-two-providers-behind-one-tool-layer-rumins-own-composer-by-default)).
  The grounded composer makes the Analyst useful, deterministic and fully testable without a
  key, and is what answers whenever a model cannot. The Anthropic provider can word answers
  more freely, but only through the same tools, and its draft must pass the same check.
- **The official SDK, configured explicitly**
  ([decision 68](../decisions.md#68-the-model-is-configuration-the-sdk-never-reads-the-environment)).
  No model identifier is written in the repository (`RUMIN_ANALYST_MODEL`). The client gets
  RUMIN's key, base URL, timeout and retries, so inherited `ANTHROPIC_*` variables are never
  used. The loop is manual and bounded; the answer arrives as a structured `submit_answer`;
  the system prompt is cached; adaptive thinking unless turned off.
- **No vector database, no embeddings, no retrieval index.** RUMIN's records are structured
  and already served by typed services; the vocabulary of names is loaded from the database
  per turn, and tools query exactly what a question needs. Retrieval is therefore a tool call,
  with its result as evidence, not a similarity search.
- **Asynchronous turns** on a bounded pool, polled, as the Scenario Lab's executions are
  ([decision 69](../decisions.md#69-conversations-are-stored-turns-are-answered-on-a-bounded-pool-and-polled)).

## 4. Tools and data sources

The 17 tools and the services they reuse are listed in [tools](../analyst/tools.md): the
graph (search, dossiers, exposure, a variable's reach, paths, one relationship), stored data
(series with provenance and revisions, an exact period comparison, what changed), Financial
Intelligence (findings with grades), the Scenario Lab (stored scenarios, executions with their
drivers, a line's explanation, an unstored preview or a plan) and the catalogues (models,
templates, data coverage). All read except `preview_scenario`, which computes and stores
nothing. Every call is validated, time-limited, isolated in its own session and thread,
recorded, and turned into evidence before the provider sees it.

## 5. Retrieval and citation

Every tool result becomes numbered evidence (E1, E2 …) with one of eight **kinds of
knowledge** (observed, RUMIN record, relationship, finding, entered by a person, assumption,
simulated, preview), its source and a link to it, period, units, retrieval time, evidence
status or grade, models and versions, assumptions, provenance and exact values. Answer text
cites ids inline; tables, series, paths and scenario cards cite per row, path or line. The
**grounding check** requires every figure (at its displayed precision; signs, Indian and
Western grouping, lakh and crore, percentages, points and basis points), date and version to
be in the evidence its sentence cites, every citation to exist, interpretation to carry no
figures, and no predictive, causal or advisory phrasing. A model's failing draft is replaced by
RUMIN's; failing parts of RUMIN's own draft are withheld with a notice
([evidence and grounding](../analyst/evidence.md)).

## 6. The interface

The `/analyst` workspace reads as research notes, not a chat
([interface](../analyst/interface.md)): conversations on the left; each answer with its
headline and status, cited paragraphs and RUMIN's own displays (tables, the Data Explorer's
series chart, relationship paths, scenario cards: stored, preview or plan), notices,
clarifications and follow-ups; and beside it the **evidence margin**, the phase's signature
element, listing the sources in citation order with their kind of knowledge (the platform's
glyphs, never colour alone), links and details. *How this was answered* lists the tool calls
that ran with their timings, the check and the provider. Steps appear as the server records
them; there is no typing effect. A what-if opens in the Scenario Lab as an unsaved draft.
Conversations can be renamed, exported as Markdown and deleted.

**Skills and tools used.** The `claude-api` skill for the SDK's current request shapes (the
manual tool loop, adaptive thinking, prompt caching, typed errors); the `frontend-design`
guidance (one signature element, restrained accent, the existing tokens rather than new ones);
the `dataviz` rules for the series chart (one line, direct end label, values as a table);
Playwright with the pre-installed Chromium for the visual review; `pip-audit` and `npm audit`
for the dependency check; an independent review agent for the security review (section 9).

## 7. Tests and evaluation

| Suite | Tests | New in Phase 7 |
|---|---|---|
| Backend (SQLite; also run on PostgreSQL 16) | 1,059 (1 skipped) | router and parsing (95), grounding (85), tools (25), answers (11), the Anthropic provider through the real SDK over a mocked transport, with environment isolation (36), the API end to end (39), the evaluation and adversarial models (9), a live test skipped without a key (1); the security review's findings account for 90 of them |
| Frontend unit and pages | 321 | the page against fixtures captured from a real backend (18), figures, citations, links and export (9), the navigation test rewritten (8) |
| Integration (live API) | 57 | capabilities; a question answered, grounded and citing only what it read; a preview not stored and an injection declined; an over-long question refused before storing; a deleted conversation gone |

**Evaluation** ([evaluation](../analyst/evaluation.md)): 33 cases covering every intent, each
with its expected intent, statuses, tools, evidence kinds, notices and text, plus the
grounding check and forbidden phrases. The grounded composer passes **33 of 33** with no
fallback (median 27 ms, three runs); seven adversarial scripted models (inventing a figure,
predicting, advising, figures in an interpretation, calling a tool outside the allowlist,
refusing, being cut off) are each replaced before a reader sees them. **A Claude model was not
evaluated.**

`make check` and the smoke test pass; the backend suite passes on PostgreSQL 16.

## 8. Defects found and fixed during the phase

| Defect | Found by | Fix |
|---|---|---|
| The data-coverage answer wrote the graph's build number without it being in its evidence; on SQLite it equalled another count and passed by accident | CI run #23 (the first push of the Analyst's backend, `f17ff94`) failed on PostgreSQL with it; reproduced locally | the build number is part of the evidence; a test asserts it |
| A grounded answer that failed the check was still shown, contradicting "an answer that fails the check is not shown" | review while adding tests | failing parts are withheld with a notice; tested |
| A clarification repeating the question's figure ("change by 30%?") failed the check | a new test | the question's figures are evidence (*Your question, as read*) |
| "What about 30%?" after a question with no change to resize answered a company overview | the browser review | asks which variable, offering variables by the figure's unit |
| "Which companies are exposed?" listed every company matching nothing ("Records matching ''") | the browser review | asks which variable; listings are titled by kind and country and say when capped |
| A follow-up naming a country ("India's GDP growth") was answered about the previous company | review of the router | a named country is not replaced by the focus |
| Table figures rounded differently from the sentences beside them (−18.43 % against −18.42 %) | the browser review | the interface rounds as the API does (half-even, fixed places) |
| The Analyst's knowledge marks contradicted the platform's glyphs (a ring meant *entered by a person*, not *assumption*) | the design-system review | the marks follow the knowledge labels |
| Repeated text: a series' limitation as caption and notice, a path's caveat twice, one not-modelled reason per line | the browser review | said once |
| Wording: "Aerisca Airways's", "the India CPI inflation", "1 stored executions", "credit" for a Shapley contribution | the browser review | possessives, articles and plurals fixed; *contribution*, as elsewhere in RUMIN |
| A phone-width page scrolled sideways (a status note and long follow-up buttons could not wrap) | the browser review | they wrap; checked at 320, 390 and 900 px |
| A reopened conversation with a question still being answered showed it as failed; retrying after a polling error asked the question twice | review of the conversation hook | a pending turn is followed; retry reads the stored turn again |

## 9. Security and privacy

Summarised in [security](../security.md#ai-analyst-phase-7) and
[guardrails](../analyst/guardrails.md): the allowlist of read-only tools with strict inputs; no
SQL, code, network, file or write tool; the grounding check as the gate; injection screening
and stored text treated as cleaned data; the key read only from `RUMIN_ANTHROPIC_API_KEY`,
never logged, stored or returned, with the SDK kept away from inherited `ANTHROPIC_*`
variables; bounded work and cost (question length, turns, one pending question, the pool, a
deadline, tool calls, model requests, tokens per day); logs without questions, answers or
secrets; conversations deletable; answers rendered as text and links followed only inside
RUMIN. Dependencies: `pip-audit` and `npm audit` found no known vulnerabilities.

**An internal security review** was run before pushing: an independent review agent read the
Analyst's code and tried to break it. It found no way for a model to act beyond the
read-only tools, reach the environment's credentials or render HTML, and it verified the
allowlist, input validation, CORS and headers and the fixtures. It found four medium and
eight lower-severity problems, all verified against the code and all fixed with tests before
the push (the full table is in [security](../security.md#the-internal-review-of-the-ai-analyst)):

- **Evidence could be planted.** A model's search words were copied into evidence text, so
  it could write a date or a quotation into the evidence it then cited. Evidence now holds
  only what RUMIN read.
- **Figures in other forms slipped past the check** (`$5m`, `INR900 crore`, `.75%`, `5-45%`,
  `five hundred crore`, `½`, `5 000`, `(5)`), and a percentage could match a count. The check
  now reads more forms, fails on anything it cannot read, and matches a figure only against
  a value of its kind: every tool marks its percentages and percentage-point changes
  (`value_units`, a new field of the evidence schema).
- **A model's follow-up questions were shown unchecked**; they are now held to the rules of
  a question and of the answer's text.
- **A turn could stay *running* forever** when its answer could not be stored (a malformed
  `submit_answer`, a NUL character), blocking its conversation. Every claimed turn now ends
  completed or failed; abandoned turns expire; the model's answer is validated and cleaned.
- Lower: SQL error logs carried the question (`hide_parameters`); two simultaneous questions
  answered 500 (now 409); model requests could outlive the deadline (each timeout ends at it,
  retries only while it allows, and RUMIN's fallback has its own budget); unknown tool names
  escaped the call limit; some stored text and format characters reached the model
  uncleaned; `http://localhost.attacker.example` passed the base-URL check; the key appeared
  in a `repr`; `/\evil.example` passed the browser's internal-link check; the token budget
  ignored cached tokens.

This is an internal review, not a formal security assessment; RUMIN remains a local,
single-user application without authentication until Phase 10.

## 10. Verification against the brief

| Brief | Status |
|---|---|
| Inspect Phases 1–6, run their tests, reuse the architecture | ✓ section 1; tools call the existing services; one dependency added, justified |
| Answer natural-language questions from RUMIN's data, graph, simulations, scenarios and intelligence | ✓ 24 intents over 17 tools; [what you can ask](../analyst/README.md#what-you-can-ask) |
| A typed tool layer reusing services, with routing and orchestration | ✓ sections 3–4 |
| Only supported claims; never fabricate; citations with source, period, retrieval time, units, provenance, evidence status, model version and assumptions | ✓ the evidence ledger and the grounding check (section 5) |
| Distinguish observed, user-provided, assumptions, simulated and interpretation; state uncertainty | ✓ eight kinds of knowledge; interpretation labelled and figure-free; notices for assumptions, missing data and limitations |
| Guardrails: no investment decisions, no guarantees, validated calculations, no arbitrary code | ✓ [guardrails](../analyst/guardrails.md); no computation of its own |
| Modular AI architecture: sessions, routing, tool registry and execution, retrieval, provider abstraction, response generation, citation validation, history, errors and observability; schema validation, timeouts, bounded retries, no secrets to the frontend, no needless infrastructure | ✓ section 3; no vector database |
| A premium analyst workspace: follow-ups, suggestions, visible tool activity, citations and evidence, tables and charts, scenario cards, warnings, history, copy and export; bone, charcoal, grey, restrained sky blue; responsive and accessible; loading, empty and error states | ✓ section 6 |
| Multi-turn context, a fresh conversation, saved sessions | ✓ [conversations](../analyst/conversations.md) |
| API endpoints | ✓ 8 operations, contract and generated types |
| Security: existing approach, validation, allowlists, timeouts, safe errors, rate and cost controls, injection protection, access checks, logging without secrets | ✓ section 9; access checks have one place (`Access`) until authentication exists (Phase 10) |
| Tests and an evaluation set; deterministic mocks separate from real integration tests; Phases 1–6 green | ✓ section 7; the live model test is separate and was not run |
| Documentation and this report | ✓ |
| A language model answering through the tools | **Built, not verified live**: no key was available. Tested through the real SDK over a mocked transport |

## 11. Limitations

The module's list is in [analyst/limitations.md](../analyst/limitations.md). The most important:
no language model has been measured; the grounded composer understands the phrasings it was
written for; figures are checked mechanically but a model's wording without figures is not;
the Analyst computes nothing of its own, so questions needing new arithmetic get the records,
not the figure; answers are about an illustrative network and SYNTHETIC stored values; there is
no authentication, and the pool and token budget are per process.

## 12. Technical debt

1. **The router is rules.** 24 intents, curated aliases and regular expressions. It is
   deterministic and tested, but each new phrasing is code; real questions should drive it
   (roadmap, Analyst follow-up 2).
2. **`composer.py` is large** (one method per intent, about 1,900 lines); splitting it by
   family (records, data, scenarios, policy) would ease review.
3. **The grounding check reads figures with regular expressions.** They cover the formats
   RUMIN writes and the common ones a model might (tested), and anything else that looks like
   a figure fails the check rather than being skipped; the cost is that a model's correct
   answer in an unusual notation is replaced by RUMIN's. Which values are percentages is
   stated by each tool (`value_units`): a new tool must say so too, or its percentages can
   only be quoted as bare numbers.
4. **Polling, not streaming**; a model's text appears only when the turn completes.
5. **Fixtures** (200 KB) were captured several times during the phase; the capture script makes
   it one command, but each backend wording change means a new capture.
6. **No browser end-to-end tests in CI** (carried over); the workspace was reviewed by hand in
   Chromium with a scripted walk-through that is not part of CI.
7. **Conversations have no retention policy** and no per-user ownership until authentication.

## 13. Recommendations for Phase 8

See [the roadmap](../roadmap.md#recommendations-for-phase-8-3d-financial-universe): build the
3D universe as another view over the existing, renderer-agnostic network model and layout
(lazy-loaded, the 2D view and its table kept as the accessible default); encode only what
exists, by shape and pattern as elsewhere; set frame-time and memory budgets on the 20,000-
company synthetic networks first; link it to the Analyst (*Show in the universe* from an
answer's paths, *Ask about this* from a node) and the Scenario Lab; and, before or alongside
it, measure a Claude model on the evaluation set with a key and run the World Bank retrieval
where it is reachable.

## Quality gates

| Gate | Result |
|---|---|
| Backend tests (SQLite) | 1,058 passed, 1 skipped (the live model test, without a key) |
| Backend tests (PostgreSQL 16) | 1,058 passed, 1 skipped |
| Frontend tests | 321 passed |
| Lint, format, types (ruff, mypy, Biome, tsc) | clean |
| OpenAPI snapshot | current (88 paths) |
| Smoke test | passed: fresh database, graph built and rebuilt unchanged, 57 integration tests |
| Evaluation (grounded composer) | 33 of 33 |
| Dependency audit | `pip-audit`: none; `npm audit`: none |
| CI | CI_PLACEHOLDER |
