# Testing

| Suite | Tool | Tests | Runs against | Command |
|---|---|---|---|---|
| Backend | pytest | 969 (one skipped without a key) | the FastAPI app, the ingestion pipeline, the graph build, the simulation engine, the Scenario Lab, Financial Intelligence and the AI Analyst with a real, migrated database (SQLite; PostgreSQL optional); providers answered by scripted responses; the Anthropic SDK over a mocked transport | `uv run pytest` in `backend/` |
| Frontend unit and pages | Vitest + Testing Library (jsdom) | 320 | the real route table, with `fetch` replaced by a fake API serving recorded responses | `npm test` in `frontend/` |
| Integration | Vitest (Node) | 57 | a live API: the frontend's real service layer over HTTP | `npm run test:integration` with `RUMIN_API_URL` |
| Analyst evaluation | `python -m app.analyst.evaluation` | 33 cases | the configured provider on the configured database (in CI: the grounded composer and seven adversarial scripted models, inside the backend suite) | see [evaluation](analyst/evaluation.md) |
| End-to-end smoke | `scripts/smoke_test.sh` | — | fresh database → migrate → seed → load the catalogue → import a synthetic price file → build the knowledge graph, rebuild it and fail if anything changed → start API → integration suite (including a simulation run and a background scenario execution, both checked against hand calculations) | `make smoke` |
| Graph benchmark | `backend/scripts/benchmark_graph.py`, `frontend/scripts/measure-graph.mjs` | — | synthetic networks up to 20,000 companies; not part of CI | see [performance](graph/performance.md#how-it-was-measured) |
| Scenario Lab benchmark | `backend/scripts/benchmark_lab.py`, `frontend/scripts/measure-lab.mjs` | — | the reference scenario and a large one on SQLite and PostgreSQL; not part of CI | see [performance](scenario-lab/performance.md#how-it-was-measured) |
| Intelligence benchmark | `backend/scripts/benchmark_intelligence.py` | — | the sample network with the reference execution, and synthetic networks up to 20,000 companies; not part of CI | see [performance](intelligence/performance.md#method) |

**No automated test calls a real provider.** Provider behaviour is tested with scripted
HTTP responses whose structure follows the providers' documentation and whose numbers are
**synthetic** (`backend/tests/fakes.py`); price-file tests use made-up prices for a made-up
instrument. Nothing synthetic is shipped or loaded by default. **No automated test calls a
language model either**: the Anthropic provider is tested through the real SDK against a
mocked HTTP transport, and `tests/test_analyst_live.py` (one test, skipped otherwise) calls
the API only when `RUMIN_ANTHROPIC_API_KEY` and `RUMIN_ANALYST_MODEL` are set. The session
running the tests may hold its own `ANTHROPIC_*` variables; tests prove RUMIN ignores them.

`make check` runs linting, formatting checks, type checks, both unit suites and the
OpenAPI snapshot check — everything CI runs except the smoke test. CI
(`.github/workflows/ci.yml`) runs all of it, the backend suite a second time on
PostgreSQL 16, and the smoke test.

## Backend (`backend/tests/`)

Each test gets an application built by `create_app()` with its own settings and a database
created **by the real Alembic migrations** (not `create_all`), so the schema under test is
the one production gets.

| Module | Tests | Covers |
|---|---|---|
| `test_health.py` | 5 | Liveness never touches the database; readiness is 200 when migrated and seeded, and 503 naming the failing check (migrations missing, no dataset, database unreachable) |
| `test_reference_data.py` | 18 | Entities, industries, variables, relationships: ordering, kind filters, pagination and out-of-range limits, 404 envelope, malformed IDs rejected before querying, ISIC classifications, published scenario rules, relationships labelled as assumptions, the type registry |
| `test_network.py` | 7 | Counts match the dataset, every edge connects existing nodes, structural links mirror entity records, degrees, the dataset labelled illustrative, undirected edges flagged, an empty but valid network without data |
| `test_scenarios.py` | 36 | Create, read, list, save a new version (the previous one kept), delete (a new scenario has no execution); shape validation (blank, long or control-character names, 0 or 11 inputs, bad types, unknown fields such as `status`), non-finite numbers, invalid JSON, JSON content type required; domain rules (unknown or non-variable entities, duplicates, percent changes to rates, the five value limits); every problem reported at once; a rejected update changes nothing; oversized bodies, declared or chunked |
| `test_seed.py` | 19 | The sample passes every integrity rule and the honesty rules (labelled illustrative, companies fictional, real entities cite references, no evidence claimed, no numeric financial figures); each integrity rule catches its violation; unknown fields rejected; loading is idempotent and `--reset` replaces data |
| `test_domain.py` | 21 | Every edge type is registered with a meaning; rates accept only percentage-point changes; limit checks, including decimal places despite binary floating point |
| `test_errors_and_security.py` | 14 | Error envelope for unknown routes (404), wrong methods (405), crashes (500, no internals) and database outages (503); request IDs generated or safely reused; security headers and CSP; large responses gzip-compressed for clients that accept it (headers kept, small ones sent as they are); docs can be disabled; CORS allows configured origins and refuses others; unsafe CORS settings rejected |
| `test_migrations.py` | 4 | Migrated schema equals the models exactly; downgrade to empty and upgrade again; foreign keys enforced on SQLite; **Phase 1 drafts become version 1 of themselves** in migration `0005` |
| `test_openapi.py` | 5 | The committed `docs/api/openapi.json` matches the application; errors are documented with the shared envelope; scenario versions and executions are never rewritten (no `PUT`, `PATCH` or `DELETE` on them); simulation runs cannot be replaced or deleted; **schema names are unique across modules** (two schemas with one name would silently rename a type in the contract) |

Phase 2 (financial data):

| Module | Tests | Covers |
|---|---|---|
| `test_data_schema.py` | 9 | Enforced by the database on both engines: provider datasets need a provider; exact decimals round-trip (18 decimal places, 20 integer digits) and values that do not fit are refused, not rounded; trailing zeros are not significant (and huge exponents are refused without being expanded); one current observation per period with revisions alongside |
| `test_ingestion_http.py` | 16 | URL redaction; throttling; retries only for temporary failures, with backoff and a capped `Retry-After`; 401/403 and other 4xx not retried; oversized responses refused |
| `test_provider_worldbank.py` | 20 | Request validation (codes, countries, periods), pagination and the page cap, the error envelope with HTTP 200, `null` records, string counters, malformed JSON, decimals parsed exactly, optional metadata, the provider's last-update date |
| `test_normalize.py` | 12 | Periods (annual, quarterly, monthly; wrong frequency; month 13; year range), period arithmetic across year ends, strict ISO dates, decimals from JSON and from files (separators, symbols and exponents refused), precision, volumes, ISIN check digits, MIC and currency codes |
| `test_quality_rules.py` | 10 | Every rule documented with a consistent outcome; plausibility flagged but never changed; periods in progress; duplicates keep the first; provider flags and units noted; empty, all-missing and gappy series; every price rejection and flag |
| `test_ingestion_pipeline.py` | 27 | A clean run stores exact values with captures (SHA-256, gzip) and summaries; **re-running changes nothing but "last seen"**; revisions keep the previous value; a withdrawn value is a revision; `5.10` = `5.1`; missing values stored as missing; flagged values stored as reported; rejected records kept with what the source sent; all-rejected series fail; empty responses warn; partial failure; circuit breaker; rate limit then success; refused credentials; unreachable provider; malformed response; storage errors roll back the series; unexpected errors fail without leaking details; Ctrl+C cancels; abandoned runs are closed; job status derivation |
| `test_price_import.py` | 10 | A file stored exactly with its licence, attribution and capture (file name only); re-import is idempotent; corrections become revisions; bad rows rejected and recorded; unreadable files fail the job; manifest problems listed; conflicting identifiers, currencies, adjustment bases and dataset ids refused |
| `test_ingestion_cli.py` | 12 | Exit codes (0, 2, 3); the default period range; refusals before anything runs (unknown dataset or series, reversed or future periods, wrong frequency); a second run refused while one is active; price import from the command line; commands that need no database; an unmigrated database explained |
| `test_data_api.py` | 15 | Providers with their terms; curated and provider datasets labelled apart; series coverage and latest values as decimal strings; filters, search (wildcards escaped), sorting and invalid parameters; series detail with licence and quality counts; observations with period, unit and provenance; revisions on request; missing values `null`, never zero; jobs, captures (no bodies) and issues; published rules; no way to start ingestion over HTTP; prices never blended; system data counts |

Phase 3 (knowledge graph):

| Module | Tests | Covers |
|---|---|---|
| `test_graph_algorithms.py` | 91 | BFS by distance with one adjacency call per level; depth and node budgets with what was left out; direction, edge-type and node-type filters; the edges among the outermost nodes; DFS on a 5,000-node chain without recursion; components; every shortest path up to the limit; path bounds and the search budget; degree. **Cross-checks on random graphs**: bidirectional search against plain BFS (500 pairs, two directions), the number of shortest paths against a dynamic-programming count, BFS distances against brute force, components against union–find |
| `test_graph_construction.py` | 30 | A clean world builds without issues; evidence statuses and illustrative flags follow the rules; the same sources always give the same graph and keys; derived edges record how; one node per currency code; the alpha-3 code attached through the catalogue link, or matched only when unambiguous; conflicting and invalid codes attached to no one; **names flagged, never merged** (identical, same name in two countries, contained names, fiction against fact, instrument against company, common words); unknown ISIC divisions flagged; every structural problem rejects its edge; fiction and fact never connected; duplicates and undirected edges stored once; tallies always add up; validity rules |
| `test_graph_names.py` | 22 | Name normalisation (case, accents, punctuation, "The", abbreviations, legal forms only at the end), strong, weak and no-match candidates, code formats |
| `test_graph_build.py` | 9 | The sample network builds with evidence on every edge; **an unchanged rebuild changes nothing**; changes and retirements are recorded and nothing is deleted; the fingerprint notices changed sources; series and instruments join the graph; a failed build changes nothing and leaks no detail; one build at a time; an abandoned build is closed |
| `test_graph_cli.py` | 6 | The printed validation report; `status` notices changed sources; `builds` and `report`; `validate` writes nothing; an unmigrated database explained; distinct exit codes |
| `test_graph_api.py` | 36 | The overview before and after a build, matching the graph, noticing changed sources, and the 30-second freshness cache; the vocabulary; search (partial, identifiers first, filters, ambiguous names); node detail with resolution decisions and live data status; neighbourhoods by depth, with the limit reported and filters; edges and why each exists; paths with bounds and direction; components; builds and issues; **every limit and malformed key rejected with 422** (11 cases); read-only (405); the system's graph capabilities |

Phase 4 (simulation engine). `tests/simulation_support.py` holds shared inputs (the
hand-checked example: a fuel bill of 5,000,000 INR a month) and helpers that prepare runs
without a database. Every number asserted was calculated by hand
([worked example](simulation/airline-fuel-cost.md#worked-example-checked-by-hand)).

| Module | Tests | Covers |
|---|---|---|
| `test_simulation_numbers.py` | 31 | The documented decimal context; `ln` and `exp` correct to 34 digits; impossible calculations raise instead of returning NaN or infinity; half-even rounding to 10 places; the magnitude limit; plain notation; exact percentages; the legal volume factors; prices per volume; **input parsing** (plain numbers read exactly, a float through its shortest form; exponents, separators, symbols, blanks, booleans and non-finite values refused); trailing zeros ignored when counting decimals; **no `eval` or `exec` anywhere in the engine** |
| `test_simulation_transmission.py` | 10 | A shock at its own node; coefficients multiply and lags add along a chain; path contributions add up; **a cycle never feeds a shock back**; the depth limit; a dense graph over the path budget is refused, not truncated; the limits are bounded themselves; effects beyond the horizon listed but not counted; a zero shock propagates nothing; the result does not depend on the order of links or shocks |
| `test_simulation_model.py` | 78 | **The released definition's hash is pinned**; the hash notices any change; versions; inconsistent definitions refused; every equation documented and every statement cited; inputs labelled by kind of knowledge; every invalid input refused with its reason (17 cases); the cross-field rules; a stored observation used exactly with its provenance, and a missing or mismatched one **never filled in**; the graph-channel checks; explicit unit conversion; each mechanism checked by hand (the crude shock, its lag, β, the jet fuel margin, hedges and their expiry, hedges not covering the currency, fare recovery after its lag, the steady state); the bridge closes; an undefined margin refused; **Shapley contributions** (an interaction split evenly, three changes, always adding up); identical inputs give identical hashes, any change changes them, `10` and `10.00` hash the same; every step recorded; sensitivity (defaults, relative variation, points skipped not clipped, an unconfirmed relationship skipped, every limit, the evaluation cap, the deadline) |
| `test_simulation_api.py` | 25 | Models listed and described with the graph relationship that confirms each rule; unknown models and versions; validation that explains every problem and stores nothing; a run stored with everything needed to explain it; **append-only and reproducible** (the same inputs twice: two runs, identical hashes; `PUT`, `PATCH` and `DELETE` answer 405); newest first; an impossible calculation refused and not stored; request sizes; no graph, the wrong airline, a stale graph, **a relationship the graph flagged is not followed**; the explanation and provenance; **a run reproduces from its snapshot after the graph is gone**; a stored exchange rate (ingested through the real pipeline from scripted responses) used with its provenance; sensitivity analyses stored and listed, custom and bounded; **a model changed under the same version refused (409)**; a deprecated version keeps its runs; the database refuses to delete history; the system's capabilities |

Phase 5 (Scenario Lab). `tests/scenario_support.py` holds the reference scenario — "oil,
rupee and rates" on the fictional Aerisca Airways with **hypothetical** round figures —
and its hand-worked lines ([the example](scenario-lab/README.md#the-reference-example)).
Every figure asserted was calculated by hand.

| Module | Tests | Covers |
|---|---|---|
| `test_simulation_timing.py` | 14 | A change lasts from its start to its end month; a lag moves both ends of the window; windows outside the horizon refused; **a percentage-point change stays at its own node** and cannot travel along a log-linear rule; unset timing fields leave earlier definitions (and their hashes) unchanged; **airline 1.1.0 gives 1.0.0's results when changes are permanent**; a six-month change, a change starting in month four, a temporary dollar change as a monthly factor; the transmission record carries the window |
| `test_simulation_models.py` | 23 | Every model defines the shared inputs identically, is timed and labels each output; foreign-currency exposure, floating-rate interest, crude- and gas-linked costs each **match their hand calculation**; a stronger currency reverses the signs; more dollar costs than revenue loses; pass-through and both benchmarks add up; a rate change recorded in percentage points; repricing after the horizon flagged; linked costs cannot exceed operating costs; inconsistent figures refused |
| `test_scenario_lab.py` | 52 | The specification's hash ignores how numbers were typed and round-trips through storage; malformed scenarios and stress cases that break the change rules **refused, not clipped**; every profile matches its model and **no item is claimed twice**; templates built only on implemented models; applicability — by default only when the graph states the exposure, never without it, only when included without a company; every change must be modelled; the evidence and stored-data constraints; cautions for models touching the same costs; the companies tied to the changes; **the lines add the models' items as worked out by hand**; one model agrees with the Lab; interest alone holds operating profit at its baseline; stress cases reuse the models and assumptions; the pathway shows only what the engine computed; timeline events; stages recorded and every model run stored; the same version twice gives the same hashes; cancellation stores nothing; the time limit stops an execution; a version that cannot run fails with its plan; a final execution never runs again, and **a final state is never overwritten** (a run whose execution another process made final stops and stores nothing; recovery leaves an execution that finished in the meantime); the runner refuses work beyond its capacity, recovers executions left by a stopped server and drops queued work when stopped; the threaded runner; one-at-a-time sensitivity across models, points skipped and limits enforced; comparisons difference only like with like; a changed stored result is detected |
| `test_scenario_lab_api.py` | 25 | Saving adds versions and never rewrites one (409 on a stale base version); duplicates remember their origin; an executed scenario cannot be deleted; malformed scenarios refused with every field; bounded request shapes; a plan explains itself and stores nothing; a preview computes without storing; an execution accepted (202) and followed to its results; every line and metric explained, and a line no model produces cannot be; pathways; a scenario that cannot run refused with nothing stored; results only for a completed execution; a final execution cannot be cancelled; **429 beyond the worker pool**; an execution reproducible, its runs ordinary Phase 4 runs; sensitivity stored and listed; comparisons without ranking; templates; the system's capabilities |

Phase 6 (Financial Intelligence). `tests/intelligence_support.py` stores **SYNTHETIC**
exchange-rate and inflation histories (with one revision: 2024 from 83.7 to 84.2) through the
real ingestion pipeline, from scripted responses; the reference execution comes from
`tests/scenario_support.py`. Statistics are checked against values worked by hand.

| Module | Tests | Covers |
|---|---|---|
| `test_intelligence_core.py` | 19 | **Least squares exact** (slope, standard error, *t*); a straight line has no *t*; Student's *t* critical values from the table, the stricter row between two; median, MAD, modified z-score and percentile rank; relative changes need a positive base; thresholds' defaults, overrides and **every invalid value reported at once**; **the grade is the weakest step**; **an insight without a chain cannot exist**; stable insight ids and chains holding each link once; changes relative for levels and in points for rates; a gap breaks the chain; thresholds select changes; a trend called only beyond the critical value; volatility and unusual changes by their definitions; short histories say so; only validated exposure edges make paths; numbers formatted for reading and kept exact as data; shared drivers capped by reach, never invented, the reach index consistent with the paths, and a truncated listing saying that its counts cover the listed companies |
| `test_intelligence_api.py` | 27 | Exposure from validated relationships only (a flagged edge is never used; the evidence filter); **the workspace states each listed company's exposure in full** (for the full listing and a truncated one); a variable's reach, with its total; **a variable followed through the whole graph** (beyond a short listing, each company's paths equal to its own analysis, a short list reporting the total); **drivers are the stored contributions** (Brent 9,225,000 and USD/INR 4,025,000 of operating costs' +13,250,000), and none without an execution; the gathered next steps name each check once and quote the assumed relationships; **every insight rests on an evidence chain** (grade, conditional flag, not-a-forecast, no forbidden words) and every record it cites exists; an industry analysed; unsuitable subjects refused; observed changes detected against thresholds; a series' signals; an observed change interpreted through the stored scenario, labelled and not stored; the overview says what the data cannot support and leads with new observations; **a finding reads the same in the workspace and the dossier**; filters; thresholds validated with their fields; entities with their latest impact; **each company keeps its own latest execution**; the brief carries evidence and rules, not prose; methods document every rule, signal and threshold; **a stored analysis keeps what it read and knows when it is stale**; stored analyses listed and never rewritten (`DELETE` answers 405); invalid requests store nothing; without a graph nothing is invented; the system's capabilities |

Phase 7 (AI Analyst). `tests/analyst_support.py` provides the reference database for
questions: the sample network built into a knowledge graph, the SYNTHETIC histories above,
and the REFERENCE scenario executed on the fictional Aerisca Airways with HYPOTHETICAL
figures. No test calls a language model.

| Module | Tests | Covers |
|---|---|---|
| `test_analyst_router.py` | 95 | Figures (%, points, basis points, doubles and halves, amounts), periods and horizons; the policy screen (injection, secrets, advice, forecasts, live data) and ordinary questions raising nothing; forbidden phrasing; stored text cleaned and instruction-like text withheld; names found by name, alias and measure, the longest winning, *US* a country only in capitals; **every intent** read from representative questions; changes tied to the right variable, falls negative, a rate in percent read as points and said so, a figure tied to nothing left out and said so; series needing a country, a variable taking its related series; a missing subject asking with choices; follow-ups taking the subject from the focus, **a bare figure resizing the previous change or, with none, asking which variable** (offered by unit); an exposure question without a variable asking which; a named country or subject replacing the focus; articles and example sizes; the focus and recent turns bounded |
| `test_analyst_grounding.py` | 35 | Figures extracted with signs, Western and Indian grouping, scales (lakh, crore, million) and units; matched **at the displayed precision** and only against the evidence the sentence cites; signs must match; years, dates and versions word for word; citations must exist; interpretation carries no figures; forbidden phrasing refused except inside a cited quotation; the headline checked against the whole ledger |
| `test_analyst_tools.py` | 13 | The allowlist is exactly the 17 tools; schemas refuse unknown fields; unknown tools refused; invalid arguments refused with the field; the call limit and the deadline; compute tools follow the access context; a slow tool times out and adds no evidence; a transient database error retried once; an unexpected error reported without internals; **every tool answers with evidence that exists and writes nothing**; the period comparison exact; the preview reuses a person's figures and labels them; stored text that reads like an instruction withheld |
| `test_analyst_answers.py` | 11 | Each fact said once (a connection drawn once with its limit once; a series' limitation a notice, not also a caption); a preview naming the lines no model covers once; a stored card explaining what is not modelled, and *contribution*, not *credit*; a declined forecast showing the stored history instead; a listing named by kind and country, saying when it is capped; a bare figure after a connection asking; tool summaries counted in words; **a failing grounded draft withheld in part** with a notice; a clarification repeating the question's figure; an identifier written in an answer is in its evidence |
| `test_analyst_provider.py` | 24 | The Anthropic provider through the **real SDK over a mocked transport**: the request is RUMIN's own (its key and base URL, **`ANTHROPIC_*` variables in the environment ignored**, the cached system prompt, the tools and `submit_answer`) and the loop runs through the registry; thinking can be switched off; every API error class, a refusal and a cut-off answer fall back to the grounded answer with a safe reason; `ANTHROPIC_CUSTOM_HEADERS` stops the provider; the provider is used only when configured; a draft that fails the check is replaced; refused and invalid tool calls are reported back to the model; declined and unclear questions never reach it; the model is skipped when the budget says so; the loop is bounded; the context given to the model is data |
| `test_analyst_api.py` | 23 | Conversations created, listed, renamed and deleted; bodies validated; unknown ids 404; **a question answered with evidence and recorded tool calls**; a follow-up read against the conversation; question length (schema and configured), the turn limit, one pending question and no deletion while answering; **a full pool refuses before storing** (429); a failure stored without internals; a final turn never changes; deleting removes everything; **logs carry ids and timings, never the question or the answer**; capabilities (provider, tools, limits, suggestions from the data); the system's capability; the contract |
| `test_analyst_evaluation.py` | 9 | **The grounded composer passes all 33 cases**, with no fallback; the cases cover every intent; seven adversarial scripted models (inventing a figure, predicting, advising, figures in an interpretation, a forbidden tool, refusing, cut off) never reach the reader |
| `test_analyst_live.py` | 1 | Skipped unless a key and a model are configured: one real question through the Anthropic API, grounded and cited |

Run against PostgreSQL (use an empty, disposable database — the suite drops and recreates
the schema):

```bash
RUMIN_TEST_DATABASE_URL=postgresql+psycopg://rumin:secret@localhost:5432/rumin_test uv run pytest
```

## Frontend (`frontend/tests/`)

Page tests render the **real route table** (`createMemoryRouter(routes)`) inside the real
theme provider, and replace only `fetch`: `tests/utils/api.ts` serves responses captured
from the running API (`tests/fixtures/*.json`) and records every request, so tests assert
exactly what the app sent. The fixtures are themselves checked against the OpenAPI
contract, so they cannot silently drift from the API.

A wait (`findBy…`, `waitFor`) allows 3 seconds and a test 15 (`tests/setup.ts`,
`vite.config.ts`): a full page renders in jsdom in a few hundred milliseconds, and several
times that on a busy CI runner. The longer limits change nothing when a page renders and
still fail when it does not; the suite passes with the machine's CPUs saturated.

The Phase 2 fixtures (`tests/fixtures/data/`) were captured the same way from two
databases: one filled through the real pipeline with **synthetic** responses and a
synthetic price file (every name says "SYNTHETIC"), and one holding the real series
catalogue after a World Bank run that failed because the provider was unreachable.

The Phase 6 fixtures (`tests/fixtures/intelligence/`) are written by
`backend/scripts/capture_intelligence_fixtures.py` from a fresh database: the methods and the
workspace before anything is simulated; after the reference execution, the overview, the
entity list, Aerisca Airways' dossier and brief, an industry's dossier, a refused threshold
and a stored analysis; then, after **SYNTHETIC** histories are stored through the real
pipeline, the files named `synthetic-*` (overview, dossier, series, the stored analysis now
stale) and the list of analyses. The script formats them with the frontend's formatter and
edits nothing by hand. Recapture them whenever an intelligence response changes.

The Phase 5 fixtures (`tests/fixtures/lab/`) are written by
`backend/scripts/capture_lab_fixtures.py`, which builds a fresh database and drives the API
in-process: the templates, the airline template before any figure, the reference scenario
saved, executed, explained, analysed and verified, a second scenario to compare with, and the
definitions of the three models the reference includes. Nothing in them is edited by hand;
the one assembled fixture, the reference preview, is made of the captured plan, results and
pathway and checked against the contract like the others.

| Area | Tests | Covers |
|---|---|---|
| `lib/apiClient` | 12 | Success, error envelope → typed `ApiError`, non-JSON, unreachable, timeout, caller cancellation, accepted non-2xx, 204, base URL |
| `lib/contract` | 48 | Fixtures conform to the contract — the simulation fixtures (model, validation reports, run, explanation, provenance, verification, sensitivity, lists), the Scenario Lab fixtures (templates, scenario and library, execution and history, results, pathway, explanation, sensitivity, verification, comparison, both previews, the included models' definitions) and the Financial Intelligence fixtures (methods, three overviews, entities, three dossiers, the brief, a series, two stored analyses and their list, a refused threshold); the checker catches missing fields, wrong types, bad enum values, nested unions |
| `lib/decimal` | 3 | Exact grouping of every digit, rounding for display half away from zero on the digits themselves (BigInt), plain-decimal recognition |
| `data/chartMath` | 6 | Nice ticks; **no line drawn across a missing value or an absent period**; weekends contiguous but long trading gaps broken; nearest period; calendar-aligned time ticks |
| `hooks/useApiResource` | 6 | Loading → success, request sharing, error and reload, refresh keeps data, no cross-key data, data from a save |
| `network/model` | 15 | Integrity validation (dangling edges, duplicates, self-loops, unknown types, malformed records), indexes, neighbourhoods, filters, search |
| `network/layout` | 9 | Finite, deterministic positions (independent of input order), column order, spacing, empty graph, portrait transpose |
| `network/panZoom` | 7 | Zoom keeps the cursor point fixed, limits, fit-to-view maths |
| `scenarioLab/draft` | 11 | A saved scenario read into the builder's draft and written back unchanged; a fall kept negative and nothing rounded; empty figures left out, never filled in; a stored exchange rate sent by its series; a non-integer month sent as typed for the API to report; updates name their base version; what counts as an unsaved change; the reducer's limits (10 changes, 5 stress cases); model modes, inputs and assumptions edited independently; stress cases by scale or values; the browser checks presence only, never a domain rule |
| `scenarioLab/pathwayLayout` | 9 | On the captured reference pathway: four columns with metrics under the lines; every step placed except graph context, whose links go to the lane header; every computed link drawn once; steps inside their model's lane and lanes apart; no overlaps in a column; lines in accounting order; fits the frame down to a minimum node width; a collapsed lane re-routes its links and hides the ones inside; a step's chain upstream and downstream |
| `scenarioLab/format` | 7 | Compact and full money with signs; changes in the variable's unit (%, pp, its own); metrics and their changes; step values by unit; model unit identifiers read as a reader expects; stage durations from the server's timestamps |
| `app/navigation` | 8 | Landing, navigation between modules, 404, live workspace status, the AI Analyst opened with who answers and nothing sent, System capabilities, theme persistence |
| `analyst/format` | 8 | Citations split out of a paragraph; sources ordered by first citation, unknown ids dropped; **figures rounded half-even at fixed places as the API's sentences are**; percentages and amounts with signs and units; durations; Markdown answers with their cards and sources; table cells escaped and records linked; a failed question and a conversation's header |
| `pages/analyst` | 18 | Against fixtures captured from a real backend (`backend/scripts/capture_analyst_fixtures.py`): starting with the provider stated and suggestions from the API; a model configured but not ready; **asking: the question stored, each recorded step shown (queued, running with its tool call), then the answer**, the URL naming the conversation; a suggestion asked in one click; Shift+Enter and the length limit; a stored conversation as notes with **citations linked to their sources in the margin**, paths, tables, the stored card and what is not modelled; a series as a chart with its table and its limitation said once; **a preview card whose figures read as its sentences do** (+3.60 %); a clarification's option and a follow-up asked; an injection declined; the method (tool calls, the check, who composed it); a question still being answered followed when the conversation opens; a failed question asked again; a refusal (429) shown and retried; rename; delete only after confirming; export and copy as Markdown with sources; **a what-if opened in the Scenario Lab as an unsaved draft**, with only an unstored preview asked for |
| `pages/universe` | 11 | Exactly the API's nodes and links drawn; selection highlights neighbours and dims the rest; Escape and close reset; keyboard selection; search; filters never leave dangling links; table view; phone layout; inconsistent data refused; unreachable API and retry |
| `pages/scenarioLab` | 14 | Against fixtures captured from a real backend: the library — templates with names and units from the API, the ones not offered with the reason, saved scenarios with their headline; comparing two executions, differenced only like with like and not ranked; a saved scenario opened on its stored execution (headline, baseline against scenario, cash flow listed as not modelled, reading writes nothing but the unstored preview); the pathway drawn from what the engine computed, **graph context listed apart with the causation caveat**, a relationship's evidence, β and lag, Escape, not-modelled relationships, the list view; the month replay (values per month, dimmed until reached, metrics "Horizon only"); plan, months, stress (changes in their units, not ranked) and explanation tabs; sensitivity labelled as not Monte Carlo; verification; an edit previewed on the server and labelled, then discarded back to the saved version with nothing saved; an execution followed through the server's stages until final, polling then stopping; a failed execution explained; a missing scenario and an unreachable API; a template's missing figures shown as notes until a save is attempted |
| `intelligence/format` | 3 | Rounding for display only, from the exact strings; grades strongest first and kinds of finding grouped; a cited record linked to the view that shows it, when there is one |
| `pages/intelligence` | 13 | Against fixtures captured from a real backend: the ledger grouped by kind of knowledge, a finding opened into its **evidence chain** with the step that sets the grade; filters by group and by minimum grade, never ranking; the exposure matrix read as text, cell by cell; thresholds sent in the request and **a refusal shown beside its field**; an unreachable API; a dossier describing the entity without inventing anything; exposure paths with their relationships and models; drivers as stored contributions labelled simulated; every source and the brief; **observed values and the model interpretation kept apart** (synthetic values); a subject that is not an entity refused in the API's words; storing an analysis and reading it back stale, with the phone picker naming it; the dashboard's latest findings |
| `pages/dashboard` | 4 | Loading state, live figures from the API, preview → Universe link, unreachable API and recovery |
| `pages/dataExplorer` | 5 | A failed retrieval explained with counts and the command to retry; no bundled prices and how to import; datasets with licence links and attribution; recent runs; stored series with rounded latest values, search, country and "with values" filters |
| `pages/economicSeries` | 6 | Honest labels (historical, sample, flagged); freshness facts; reading the chart from the keyboard, gaps included; the table shows the published literal (`14.250000`); revision history requested and shown; source, licence, review range as an assumption, quality issues; a failed retrieval explained; a missing series |
| `pages/instrumentAndJob` | 5 | Imported prices labelled as sample data with the latest trading day and flags; every price in the table; sources never blended (prices requested per dataset); a failed run target by target; stored responses with their hashes |
| `graph/view` | 11 | The explorer's view model: exactly the answer's nodes and edges; expansions merged without duplicates; never an edge to a node not shown; nodes left out by the limit counted, not dropped silently; pending, failed and skipped expansions reported; shown connections per node; the spanning tree by hops, whatever the edge order; node order; the path view, including "no path" |
| `graph/layout` | 11 | Radial layout: the focus at the centre and every node on the ring of its hop count; deterministic; a minimum spacing on each ring; subtrees inside their parent's wedge; labels along the radius only on crowded rings; a focus without neighbours. Columns for paths. Animation start positions and interpolation |
| `graph/encoding` | 15 | A distinct shape for every node type; evidence told apart by line pattern, not colour; nature rings and hollow series; sizes with a ceiling; node keys parsed and validated; explorer links built the way the build forms keys; filters (the last value cannot be turned off; answers cached per request); bounded history |
| `graph/edgePanel` | 2 | The evidence panel says a catalogued series has no values yet, and that retrieval does not apply to reference data |
| `simulation/format` | 6 | Decimal points moved on the digits (no floating point); money rounded for display in its currency; ratios as percentages and margin changes as percentage points; figure and unit split; signs only on non-zero values; inputs shown exactly as entered |
| `simulation/form` | 7 | Inputs grouped by kind of knowledge; typed values sent as exact strings with units, defaults left out; a stored run's inputs rebuilt with defaults kept as defaults; the hypothetical example fills only its inputs; API error details mapped onto fields; allowed ranges stated |
| `simulation/pathwayLayout` | 6 | Each node close to what it feeds; links that skip a layer routed beside its nodes; no overlaps, deterministic; "cannot fit" reported so the list is shown; a cycle survived; smooth flows |
| `pages/simulation` | 13 | The page against fixtures captured from a real backend: the model before a run (pathway, labels, assumptions); inputs checked on the server with each problem beside its field and a summary whose links move focus to the field; valid inputs with the engine's notes; a run opened at its own address with its headline; a refused run explained; a stored run's inputs loaded into the form; the pathway with the graph relationship used; the pathway animates once for a new run and **never under reduced motion**; the calculation month by month; provenance and the reproducibility check; every input labelled; a sensitivity analysis ranked; a run that cannot be opened |
| `pages/graphExplorer` | 21 | The page against fixtures captured from a real backend: the aggregate map labelled as an aggregate, with the build report; picking from the map; server search with ambiguous names flagged; exactly the API's nodes and edges drawn, with evidence and nature; selection and dimming; assumed exposures labelled "direct" or "via the industry", never as measured; expand, collapse, and a failed expansion retried; back, forward and reset; filters sent to the API; why a relationship exists; paths with the causal-chain caveat, and "no path"; the table view; not-built and stale graphs; an unreachable API; a node not in the graph; an invalid focus key; phone labels |

## Integration (`frontend/tests/integration/`)

Runs the frontend's own service layer (`services/api.ts`) against a live API — no mocks:

- every response type matches the committed OpenAPI contract;
- the live network passes the frontend's integrity check and yields a finite layout;
- a template's starting point, read into the Lab's draft, round-trips (create, read,
  list, a new version that leaves version 1 intact, a stale edit refused with 409, delete,
  then 404);
- **eight invalid inputs** (a fall of 100 % or more, above the maximum, zero, too many
  decimals, a rate moved more than 25 points, a percent change on a rate, an unknown
  variable, the same variable twice) are each refused by the server on the field the
  builder shows the message on;
- unknown fields and malformed JSON get the standard error envelope; CORS admits the dev
  origin and refuses others.

Phase 2 adds `data.integration.test.ts`: providers and datasets (curated and provider data
labelled apart), the series catalogue served with no values until a retrieval runs, the
smoke test's synthetic price file served exactly (decimal strings) and labelled as sample
data, its import recorded as a job with the stored file and no secrets, the system report's
data counts and capabilities, and no way to start ingestion over HTTP.

Phase 3 adds `graph.integration.test.ts` (13 tests), after the smoke test has built the
graph: the overview matches the build and says what the graph is not; the vocabulary;
search; neighbourhoods whose edges all join returned nodes; edges with evidence records
and caveats; paths whose edges join consecutive nodes, with the causal-chain caveat;
components described without calling them economic systems; the API is read-only; and
malformed keys are rejected. Every response is checked against the OpenAPI contract.

Phase 4 adds `simulation.integration.test.ts` (8 tests), run through the page's own form
code: the models listed and described; the form's request validated; the page's
hypothetical example **matching the hand calculation** (gross fuel cost +6,000,000,
hedging −750,000, fare recovery 1,700,000, operating profit −3,550,000, steady state
−3,600,000 a year, the bridge closing); the explanation traced to the graph; a run
reproduced exactly, and identical inputs giving identical hashes; a stored sensitivity
analysis; every invalid input named with nothing stored; no way to replace or delete a
run.

Phase 5 adds three Scenario Lab tests to `api.integration.test.ts`: the templates are built
only on registered models, with demand and supply-chain shocks listed as not offered; a
template planned before its figures exist computes nothing; and the reference scenario,
built through the builder's own draft code, **executed in the background** — followed
through its four recorded stages to `completed`, its lines matching the hand calculation
(profit before tax −6,700,000), its pathway, explanation and reproducibility check — after
which the executed scenario cannot be deleted (409).

Phase 6 adds four Financial Intelligence tests to `api.integration.test.ts`, each response
checked against the contract. The first analyses the workspace, with every finding carrying a
chain and the step that sets its grade; the smoke test's SYNTHETIC price file appears as an
instrument, and its −1.57 % move is reported at a 1 % threshold but not at the default 5 %.
The second builds a dossier whose every path edge is validated, and a brief listing exactly
the dossier's insights. The third refuses an invalid threshold with its field. The fourth
stores an analysis and reads it back unchanged, current and listed.

Phase 7 adds `analyst.integration.test.ts` (4 tests), against the smoke test's API with the
grounded composer (the script sets `RUMIN_ANALYST_PROVIDER=grounded`): the capabilities; a
question asked and polled until answered, grounded, citing only evidence it read, with its
tool call recorded and the conversation titled after it; a what-if previewed (not stored) and
an injection declined without a tool; an over-long question refused before it is stored and
a deleted conversation gone. Every response is checked against the contract.

It creates scenarios (deleting those it can), adds simulation runs and executions, and
creates conversations (deleting them), so point it only at a disposable database — which is
what `scripts/smoke_test.sh` provides.

## Manual and visual checks

Every page was rendered in Chromium (via Playwright) and reviewed from screenshots, with no
console errors, across desktop (1440 × 900, 1280 × 800) and phone (390 × 844) sizes and
both themes — not every page in every combination. For Phase 2, the Data Explorer, series,
instrument and ingestion-run pages were checked with the failed-run database and with a
throwaway database of synthetic data (to see charts), including hover and keyboard reading
of the chart, the table and revision views, dark mode and phone widths. Interactions were exercised in the
real browser too: selection and dimming, deep links (`/universe?focus=…`), the portrait
network on phones, and the scenario save flow. For Phase 3, the Knowledge Graph explorer
was checked at desktop, tablet (820 × 1180) and phone widths in both themes, against the
sample graph and a 20,000-company synthetic graph, with a scripted walk-through of ten
interactions ([UI review](graph/explorer.md#ui-quality-review)). For Phase 4, the
Simulation page was checked at 1440 × 900 in both themes and at 390 × 844, with
screenshots after each change: the form, checking and running, every results tab, the
pathway's motion and reduced motion, keyboard use of the tabs and the monthly chart, and a
stored run reopened ([what the review changed](simulation/preview.md#review)). For Phase 5,
every Scenario Lab screen — the library, a template before its figures, a saved scenario on
its stored execution, the inspector, the month replay and every tab — was shot at 1440 ×
1100 in both themes and at 390 × 900, reviewed and fixed until it read correctly; a script
checked that no Lab page scrolls sideways at seven widths from 360 to 1,920 px. For Phase 6,
the Financial Intelligence views (the workspace with a finding opened, a dossier on each tab,
the thresholds refusal, a stale stored analysis, the dashboard panel) were shot in both themes
and at tablet and phone widths, each run checking for console errors and sideways scrolling
([interface](intelligence/interface.md#accessibility-and-responsiveness)). For Phase 7, the
AI Analyst was driven through twelve questions in a real browser (overview, reach, a series,
a what-if, a stored result, a connection, a bare follow-up figure, a clarification, advice,
an injection, what changed, a forecast), each answer shot at 1440 × 1000, then the
conversation in dark mode, at 900 px and at 390 px, and the hand-over to the Scenario Lab;
every run checked for console errors and sideways scrolling (none remain at 320, 390 and
900 px). The review changed wording (possessives, articles, *contribution* for *credit*),
removed repeated captions and notices, aligned table rounding with the sentences, let long
suggestions wrap, and fixed a follow-up that answered a different question
([interface](analyst/interface.md#accessibility-and-responsiveness)). These checks are not
automated yet (see [known-limitations.md](known-limitations.md)).

## Conventions

- Test behaviour through public interfaces: HTTP for the backend, rendered pages and user
  events for the frontend. Query by role and label, as assistive technology does.
- A bug found in development gets a test first. Phase 1 examples: the layout depended on
  edge order; a heading's accessible name ran two words together. Phase 2 examples:
  decimals such as `5.10…0` were refused as too precise; `1E-18` reached clients in
  exponent form; skipped series looked "never retrieved". Phase 3 examples: "Try again"
  after a failed expansion did not refetch; a series never retrieved was described as
  "not provider data"; names sharing common words made entity resolution quadratic.
  Phase 4 examples: three schema names collided with existing ones, which silently renamed
  types in the contract; a stored exchange rate was refused for having more decimal places
  than a typed value may; a numeric string longer than the length limit got through by
  being read as a whole number. Phase 5 examples: stopping the runner cancelled queued work
  without freeing its places; stress validation reported a change's own error twice; the
  pathway measured its own minimum width and never shrank to its frame; choosing a link in
  the pathway's details lost focus, so Escape stopped working; a model definition that failed
  to load showed "Loading…" for ever. Phase 6 examples: a coverage finding had a simulation
  step without saying it was not a forecast (caught by the check every insight passes); the
  workspace capped exposure edges, so a listed company could miss an exposure; the same
  finding was graded differently in the workspace and the dossier; each company's latest
  execution was read from the 500 most recent rows only; the same sensitivity step was
  suggested twice in two wordings.
- Never weaken a test to make it pass; never skip one.
