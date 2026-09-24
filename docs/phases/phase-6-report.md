# Phase 6 report — Financial Intelligence

**Status: implemented and verified, locally and in CI.** RUMIN now has a Financial
Intelligence layer. It reads what Phases 2–5 store (observations and their revisions, the
knowledge graph, Scenario Lab executions and their runs) and answers *what changed, who is
exposed and through which relationships, what the stored simulations say, what drives them,
what the result rests on and what to look at next*. Every answer is a **finding** from one of
19 documented rules. Each finding carries the **evidence chain** that produced it and an
**evidence grade**: the weakest step of the chain, not a probability. The plan written before
implementation is in [phase-6-plan.md](phase-6-plan.md); the documentation is in
[`docs/intelligence/`](../intelligence/README.md).

> **What a finding is not.** Not generated text: a rule fills a template with computed
> values. Not a forecast: simulated values hold only under their scenario's figures and
> assumptions, and say so. Not a causal claim: a relationship in the graph says that an
> entity is exposed, never how much or that one thing caused another. Not advice: nothing is
> ranked, scored or recommended, and next steps are analytical checks.

## At a glance

| | In this build |
|---|---|
| **Implemented** | The intelligence engine (`backend/app/intelligence/`, 16 modules): exact statistics, thresholds, the evidence model, validated graph slices, exposure, change detection and revisions, relationship changes, drivers from stored contributions, six signals, 19 insight rules, the model interpretation of observed changes, the module registry, the entity and workspace scopes, the brief; stored analyses (migration `0006`); 16 API operations; the Financial Intelligence interface and the dashboard's *Latest findings*; tests, fixtures from a real backend, a benchmark and documentation |
| **Rules** | 19: observed data D01–D06, simulations S01–S06, relationships and exposure G01, X01, E01–E03, coverage C01–C02 ([rules](../intelligence/rules.md)) |
| **Signals** | 6, each with a definition, method, inputs, period, evidence and limitations: exposure breadth, dependency, trend, volatility, unusual change, scenario sensitivity. No composite score ([signals](../intelligence/signals.md)) |
| **Thresholds** | 9 configurable, each with a documented default, bounds and reason, recorded in every result |
| **Historical data** | None could be retrieved where this was built: the World Bank API is blocked by the environment's network policy, as in Phases 2–5. The graph, executions and every non-observed finding work on the sample |
| **Synthetic data** | Exchange-rate and inflation histories stored through the real ingestion pipeline, used **only** in tests, the `synthetic-*` fixtures and this documentation's examples, labelled SYNTHETIC wherever they appear |
| **Hypothetical data** | The reference execution's company figures ("oil, rupee and rates" on the fictional Aerisca Airways), as in Phase 5 |
| **Fabricated data** | **None.** Nothing is filled in, estimated or invented; what cannot be computed is stated (C01, C02, `not_interpreted`) |
| **Not built** | Exposure sizes with provenance; reports as documents; per-series thresholds; a multiple-testing control; caching; any language model (Phase 7) |
| **Dependencies** | **None added** |

## 1. Inspection of Phases 1–5

Before any change, `make check` passed on commit `fd89cbd` with 712 backend tests (SQLite;
the suite also passed on PostgreSQL 16) and 264 frontend tests, the smoke test passed with 49
integration tests, and CI run #14 was green ([plan, section 1](phase-6-plan.md#1-inspection-of-phases-15)).
What Phase 6 reuses rather than rebuilds: observations with revisions, provenance and
`measure_type` (Phase 2); validated edges with evidence statuses and builds that record which
edges they added, changed and retired (Phase 3); runs with Shapley contributions per change
(Phase 4); executions with `by_change` credits per line, stored sensitivity analyses, scenario
profiles and the planner (Phase 5).

Defects found while inspecting were fixed first (`41cdd3b`). The Lab's stage marker pulsed on
every stage, not only the running one. A malformed selector left failed stages unstyled. The
dashboard labelled every recent scenario "Not simulated". The landing page still described
Phase 4's single model, and three system fixtures predated the Lab.

## 2. What was built

| Layer | Change |
|---|---|
| Engine | `app/intelligence/` (about 6,500 lines): `stats`, `thresholds`, `model` (references, steps, facts, insights, grades, `ChainError`), `graphview` (validated, indexed slices), `exposure`, `series`, `graphchanges`, `drivers`, `interpretation`, `signals`, `insights` (the 19 rules), `registry`, `engine`, `serialize` (and the brief), `fmt`. `INTELLIGENCE_VERSION` 1.0.0 |
| Persistence | Migration `0006_intelligence`: `intelligence_analyses`, append-only; no existing table changed ([data model](../data-model.md#phase-6-stored-intelligence-analyses)) |
| API | 16 operations under `/intelligence` (15 paths): overview, insights, changes, methods, entities and each entity's dossier, brief, exposure, signals and drivers, a variable's reach, a series, an instrument, and stored analyses ([API](../api.md#financial-intelligence)); the OpenAPI snapshot (83 paths) and generated frontend types regenerated; the system lists the capability |
| Frontend | `pages/IntelligencePage.tsx` and `features/intelligence/` (about 4,600 lines): the workspace, the dossier with seven tabs, the stored-analysis view, the thresholds panel, the subjects rail; the dashboard's *Latest findings*; the header navigation re-fitted for nine modules |
| Tests | 46 more backend tests (758), 30 more frontend tests (294), 4 more integration tests (53); fixtures captured from a real backend |
| Tools | `backend/scripts/capture_intelligence_fixtures.py`, `backend/scripts/benchmark_intelligence.py` |
| Documentation | [`docs/intelligence/`](../intelligence/README.md) (13 pages), decisions 54–64, this report, and updates to the README, architecture, API, data model, data dictionary, setup, testing, design system, security, roadmap and known limitations |

## 3. Intelligence architecture

Three layers, each referring to the one below, so any sentence can be followed back to stored
records ([architecture](../intelligence/architecture.md)):

1. **Findings**: facts computed by a module from one bounded read of the store (a change
   between two stored values, an exposure path, a line's stored contributions), each with
   references.
2. **Signals**: defined calculations on findings, with a named level only where a recorded
   threshold decides it.
3. **Insights**: statements produced by numbered rules, each with its evidence chain, facts,
   entities, relationships, period, models, assumptions, limitations, sources and next steps.

Six registered modules (change detection, series signals, exposure, drivers, interpretation,
insights) declare their question, inputs, method and limitations. `GET /intelligence/methods`
serves them with the rules, signals, thresholds and grades. There are two scopes. **An
entity** (the dossier and the brief) needs a handful of queries around one company or
industry. **The workspace** (the overview) reads the first 200 companies by name with every
validated edge their paths use. Reads compute from the current store and write nothing; the
only write is a stored analysis, a fingerprinted snapshot that later says whether it is stale.
Arithmetic is exact decimal throughout.

**The evidence model** is the core of the design ([evidence](../intelligence/evidence.md)).
A step's basis decides its grade: observation, calculation and RUMIN's own records are
*observed*; a relationship takes its evidence status (*documented*, *curated*, *assumed*,
*unverified*); a simulation is *simulated*; assumptions and thresholds are listed but not
graded. The grade of a chain is its weakest step, and a chain with a simulation is marked
conditional on it. `InsightDraft.build` refuses an insight without a chain.

## 4. New analytical capabilities

| Question | How it is answered |
|---|---|
| **What changed?** | Observed changes between consecutive stored values: relative for levels, exchange rates and prices, in percentage points for series already in percent; a gap breaks the chain; tested against thresholds, with provenance (D01). Revisions, both values kept (D06). Edges the latest build added, changed or retired (G01). The headline between two executions of one scenario (S05) ([changes](../intelligence/changes.md)) |
| **How has a series behaved?** | Least-squares trend with a *t* test against Student's critical value (D04), volatility ranked against the series' own earlier windows (D05), a modified z-score for the latest change (D03), all exact and descriptive |
| **Who is exposed, through what?** | Direct, via-industry and upstream paths over validated edges only; counterparties and context listed apart; the models able to simulate each path; a companies × variables matrix; shared drivers (X01); exposure, dependency and counterparties per entity (E01–E03) ([exposure](../intelligence/exposure.md)) |
| **Who is exposed to what just moved?** | D02: an observed change on a series recorded as a related measure of a variable, with the companies the graph states it reaches, and an explicit statement that it does not say the change affected them |
| **What do the simulations say, and what drives them?** | The latest execution's headline (S01); each line's stored Shapley contributions as amounts, shares of the change and points of the baseline, residual reported (S02); effects per unit of each change, as averages, not slopes (S03); the stored sensitivity ranking (S04) ([drivers](../intelligence/drivers.md)) |
| **What would the models make of what was observed?** | S06: the latest observed change of a related series applied alone to the stored scenario, run as an unstored preview and labelled a model interpretation, never an observation |
| **What does it rest on, and what is not known?** | Every finding's chain, assumptions and limitations; C01 (which exposures are simulated, simulatable and backed by data, and which simulated changes have no stated exposure); C02 (what the stored data can support) |
| **What next?** | Rule-based analytical checks: simulate with a template, note a model gap, find evidence for an assumed relationship, retrieve a series, run a scenario or a sensitivity analysis, review a revision |
| **What would an AI Analyst receive?** | The brief `rumin.intelligence.brief/1`: structured facts with references and five narration rules, the first being never to compute ([brief](../intelligence/brief.md)) |
| **What did we conclude then?** | Stored analyses: the result as returned, its thresholds, a fingerprint of what it read and hashes; read back with *current* or *stale* and what changed ([stored analyses](../intelligence/stored-analyses.md)) |

On the sample with the reference execution, the workspace lists 9 findings (S01, seven X01, C02)
and Aerisca Airways' dossier 16 (S01, five S02, three S03, four E01, E02, E03, C01). With the
SYNTHETIC histories stored, the workspace leads with observed changes (INR per US$ +9.38 %, CPI
inflation −1.80 points), their exposure (D02), a revision (83.7 → 84.2) and a trend (t = 8.35
against a critical value of 3.182). The dossier adds S06: operating profit −1,032,064 INR
through the stored scenario ([worked example](../intelligence/README.md#a-worked-example)).

## 5. The interface

A module after the Scenario Lab: subjects on the left, the analysis on the right, three views
(the workspace, a dossier with seven tabs, a stored analysis), and thresholds, tabs and filters
in the URL ([interface](../intelligence/interface.md)). The design uses the existing tokens:
bone surfaces, charcoal ink and stone greys, with the sky-blue accent in exactly three places.
Findings are ruled rows grouped by kind of knowledge; nothing is ranked. The **signature
element is the evidence chain**: each finding opens into its ordered steps, with the step that
sets the grade marked. Grades are drawn with the graph's own line patterns and a word, never
colour alone. Exposure is a table that reads as text, drivers are one-hue bars from zero with
printed values, and the History tab keeps observed data apart from the labelled model
interpretation.

**Skills.** The installed `dataviz` skill was applied to the drivers and the reused series
chart (one hue, values printed, tables, no second axis). The `frontend-design` guidance set
the process: a token plan reviewed against the brief, one signature element, restraint and
screenshot critique. A dashboard of gauges and scores, and cards of equal weight, were
considered and rejected. The module was reviewed from screenshots in Chromium, in both themes
and at tablet and phone widths, with console errors and sideways scrolling checked on every
run.

## 6. API and database

16 operations ([API](../api.md#financial-intelligence)); the reads write nothing; `POST
/intelligence/analyses` answers 201 with `Location`. Status codes follow the existing
conventions: 404 for an unknown entity or record, 422 with field paths for invalid thresholds
(all reported at once, `invalid_threshold`), for a subject that is not an entity and for
malformed requests. There is no route that updates or deletes an analysis (`DELETE` answers
405). One new table, `intelligence_analyses`, with check constraints on scope and subject and
two indexes; no foreign keys, so snapshots outlive rebuilt graph rows.

## 7. Tests

| Suite | Tests | New in Phase 6 |
|---|---|---|
| Backend (SQLite; also run on PostgreSQL 16) | 758 | statistics against hand calculations, thresholds, the grade and chain invariants, changes, trends, volatility, anomalies, validated paths, the shared-driver cap and its truncation note (`test_intelligence_core.py`, 19); the API end to end (`test_intelligence_api.py`, 27): every insight grounded, every cited record existing, the workspace complete per listed company, a variable followed through the whole graph, **a finding identical in the workspace and the dossier**, each company's own latest execution, stored contributions, interpretation labelled and unstored, stored analyses immutable and stale-aware, invalid requests storing nothing |
| Frontend unit and pages | 294 | the page against fixtures captured from a real backend (13), formatting (3), every intelligence fixture checked against the contract (14) |
| Integration (live API) | 53 | the workspace grounded in evidence (and a SYNTHETIC price move reported at 1 % but not 5 %), a dossier and brief from validated edges, a refused threshold, a stored analysis read back unchanged and current |

`make check` (lint, format, types, both suites, the OpenAPI snapshot) and the smoke test pass;
the backend suite passes on PostgreSQL 16. See [testing](../testing.md).

## 8. Performance

Median of 5 runs, in process, SQLite, 4 vCPUs ([performance](../intelligence/performance.md)):

| | sample | 1,000 | 5,000 | 20,000 companies (SYNTHETIC) |
|---|---|---|---|---|
| Overview | 33 ms | 290 ms | 285 ms | 345 ms |
| Entity list | 23 ms | 70 ms | 131 ms | 225 ms |
| Dossier | 36 ms | 32 ms | 45 ms | 36 ms |
| Brief | 33 ms | 28 ms | 32 ms | 32 ms |
| Detected changes | 21 ms | 8 ms | 12 ms | 15 ms |
| Store / read back an analysis | 74 / 25 ms | 66 / 26 ms | 72 / 27 ms | 70 / 24 ms |

Before the scaling work, at 5,000 companies, the overview took 728 ms, the entity list 743 ms and
detected changes 389 ms, and the workspace listed 195 near-identical findings. The sample
dossier is 120 KB of JSON (13 KB compressed). The route's JavaScript is 59 KB (15 KB gzip).

## 9. Defects found and fixed

Found by tests, benchmarks and reviews during the phase, each fixed with a test:

| Defect | Fix |
|---|---|
| C01 carried a simulation step without saying it was not a forecast (caught by the check every insight passes) | the step became a record of the execution's changes and models |
| The workspace capped exposure edges, so a listed company could miss an exposure (`a00d619`) | bounded by companies, never edges; a test compares each listed company with its own analysis |
| At 5,000 companies, the shared-driver rule scanned every company once per variable and listed 195 findings (`a00d619`) | a reach index, edge indexes, and the 12 variables reaching the most companies |
| The same finding (S01) was graded *simulated* in the workspace and *assumed* in the dossier (`1a30fa3`) | both pass the company's paths; a test compares every shared finding field by field |
| Each company's latest execution came from the 500 most recent rows, so an older one could silently disappear (`f8b5b41`) | chosen exactly in the database for the listed companies |
| The same sensitivity check was suggested twice in two wordings; *find evidence* named no relationship and could target one that was not an assumption (`b159fbc`) | one shared step; the assumed relationships quoted and targeted |
| The API described a next-step action no rule produces (`1a30fa3`) | removed from the contract |
| Nine modules pushed the header navigation out of the header (`0cd3b92`) | breakpoints re-fitted; collapses at 72 rem |
| Visually hidden text in scroll frames widened the page on phones | the frames are positioned |
| On a phone, the subject picker read *Workspace* while a stored analysis was open (`5ced698`) | it reads *A stored analysis* |
| A variable's reach searched only the workspace's first 200 companies, and X01 and D02 counted among them, without saying so | the reach walks downstream through the whole graph and reports its total; X01 and D02 say when they count listed companies only |

## 10. Verification against the brief

| Brief | Status |
|---|---|
| Inspect Phases 1–5 and reuse their architecture | ✓ section 1; the layer reads existing tables and changes none; no dependency added |
| Intelligence that combines data, the knowledge graph, simulations and scenarios | ✓ one read per request across all four ([architecture](../intelligence/architecture.md)) |
| Structured, explainable insights: what changed, why, who is exposed, through which relationships, what-if, contributing factors, assumptions, next steps | ✓ 19 rules ([rules](../intelligence/rules.md)); *why* is answered only as far as stored contributions and stated relationships support it, never as causation |
| No vague AI summaries | ✓ no generated text; templates filled with computed values; forbidden words tested |
| Every insight with the insight, supporting data, entities, relationships, time period, model or scenario, confidence/evidence, assumptions, source/provenance, limitations and an evidence chain | ✓ the `Insight` shape; confidence is the evidence grade (the weakest link, not a probability); an insight without a chain cannot be built |
| Change detection with configurable thresholds, observed change distinguished from model interpretation | ✓ 9 thresholds with defaults, bounds and reasons; S06 labelled, unstored and kept apart in the interface |
| Exposure only through validated relationships | ✓ current, validated edges of the latest build; flagged edges listed as not used; `evidence_backed` filter |
| Contributions from actual model outputs | ✓ stored Shapley credits read, residual reported, never recomputed |
| Signals with definition, calculation, inputs, period, evidence and limitations; no meaningless scores | ✓ 6 signals; no composite score |
| Structured objects for a future AI Analyst; the model never calculates | ✓ the brief with narration rules ([brief](../intelligence/brief.md)) |
| A Financial Intelligence interface: bone, charcoal, grey, restrained sky blue; an analytical research instrument | ✓ section 5 |
| APIs | ✓ 16 operations, OpenAPI snapshot and generated types |
| Tests, all previous phases green | ✓ section 7; every Phase 1–5 test still passes |
| Integrity: never fabricate, invent relationships, present assumptions as facts, claim causation, hide uncertainty, present outputs as guaranteed predictions | ✓ SYNTHETIC values only in tests and labelled; exposure only from stated edges; assumed relationships graded *assumed*; no causal language; limitations on every finding; simulated values say they are not forecasts |
| Exposure *sizes*, and reports as documents | **Not built**: the graph states no sizes, and no sourced exposure records exist yet; dossiers, briefs and stored analyses are structured records rather than documents. Both are follow-ups ([roadmap](../roadmap.md#intelligence-follow-ups)) |

## 11. Limitations

The module's list is in [intelligence/limitations.md](../intelligence/limitations.md). The most
important: no real observations were available where this was built, so the observed-data
findings were exercised on SYNTHETIC values; every exposure relationship in the sample is a model
assumption, so exposure findings are graded *assumed* and never sized; the statistics are
descriptive, the trend test's assumptions rarely hold for economic series, and there is no
correction for testing many series; the workspace lists the first 200 companies; drivers come
from the latest execution only; stored analyses have no retention; there is no authentication.

## 12. Technical debt

1. **Every read recomputes.** Nothing is cached per graph build or data version. The overview
   takes about 0.3 s today; real data volumes may need a cache keyed by the fingerprint that
   stored analyses already compute.
2. **The model interpretation (S06) runs on every dossier read**, once per related series
   with a change. It could be cached per execution and observation revision.
3. **`insights.py` holds all 19 rules** (about 1,800 lines); splitting it by family (data,
   simulations, exposure, coverage) would ease review.
4. **Next-step actions and several response fields are free strings** documented in text
   rather than enumerations in the contract. That is how an action no rule produced stayed in
   the API description; enumerations would let the contract tests catch it.
5. **The critical values of Student's t come from a three-decimal table** (1–30, 40, 60 and 120
   degrees of freedom) read conservatively; exact quantiles would need the t distribution
   implemented.
6. **Fixtures are large** (1.4 MB of formatted JSON), and they had to be captured again three
   times this phase; the capture script makes that one command.
7. **Stored analyses keep the full result** (100–230 KB each) uncompressed, with no retention.
8. **No browser end-to-end tests in CI** (carried over): the interface is covered in jsdom and
   by the live integration suite, and was checked by hand in Chromium.

## 13. Recommendations for Phase 7 (AI Analyst)

1. **The brief as the only input.** The Analyst phrases `rumin.intelligence.brief/1` (and the
   overview for workspace questions), following its narration rules, and computes nothing.
2. **Mechanical checking before display.** Every number in an answer must appear in the brief,
   and every sentence must cite an insight id whose chain leads to stored records. An answer
   that fails the check is not shown, and the check is tested against the fixtures.
3. **Grades and labels carried into the words**: *simulated, not a forecast*, *assumed*,
   *interpretation*, and what is not known.
4. **Questions mapped to rules** (*what changed*, *who is exposed*, *what drives this*, *what
   should I check*), with *cannot say* where no rule or data applies.
5. **A data policy, a local or self-hosted model option and authentication** before any
   external model sees data.
6. **Real data first**: run the World Bank retrieval where it is reachable, and add monthly
   market data from licensed sources, so the Analyst has observations to talk about.

See also the [roadmap](../roadmap.md#recommendations-for-phase-7-ai-analyst).

## Quality gates

| Gate | Status |
|---|---|
| **Inspection first** | ✓ baseline checks on `fd89cbd` (CI #14) before any change; inspection defects fixed first |
| **Core workflow** | ✓ overview, dossier, brief, thresholds, filters, stored analyses, freshness |
| **Integrity** | ✓ no fabricated data; SYNTHETIC values confined to tests and labelled; no generated text; every insight grounded |
| **Tests** | ✓ `make check`, the smoke test and the PostgreSQL run pass locally |
| **CI** | ✓ Runs **#15** (`58bf5ba`, the engine and API), **#16** (`80e3a2f`, the interface and fixtures), **#17** (`a00d619`, scale), **#18** (`1a30fa3`), **#19** (`f8b5b41`) and **#20** (`b159fbc`) passed all three jobs: backend on SQLite and PostgreSQL 16, frontend, and the smoke test |
| **Documentation** | ✓ [`docs/intelligence/`](../intelligence/README.md), decisions 54–64 and updates across the docs |

What remains unverified is stated above. No real observation has been analysed. No exposure
relationship is evidence-backed. The statistics have not been validated on real series. The
product has no authentication, and the browser flows are not yet automated in CI.
