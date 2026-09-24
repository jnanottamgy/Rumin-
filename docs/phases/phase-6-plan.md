# Phase 6 plan — Financial Intelligence

Written before implementation, after inspecting Phases 1–5 and running their checks. It
records what was found, what was decided and why, and the order of work. The Phase 6
report will record what was delivered.

## 1. Inspection of Phases 1–5

**Verified state before any change** (commit `fd89cbd`, CI run #14 green): `make check`
passed with 712 backend tests (SQLite; the suite also passes on PostgreSQL 16) and 264
frontend tests, and the OpenAPI snapshot was current. The smoke test passed: a fresh
database, the graph built and rebuilt with no change, then 49 integration tests against the
live API.

| | Finding |
|---|---|
| **Reusable as it is** | *Phase 2:* observations with revisions (a new row per revision, the old one kept), provenance down to the capture and job, `measure_type` on every series (`level`, `change`, `rate`, `ratio`, `exchange_rate`), price bars per dataset. *Phase 3:* current, validated edges with an evidence status on each; the relationship registry with its caveats; builds that record which rows each build added, changed and retired (`first_build_id`, `changed_build_id`, `retired_build_id`); `GraphReader`; the Lab's validated-edge reader (`scenario_lab/graph.py`). *Phase 4:* runs that store **Shapley contributions** per output and per change, with `entity_id` indexed. *Phase 5:* executions whose lines store **`by_change`** credits per variable (they add up to the line's change within 10⁻⁹), stored sensitivity analyses, comparisons, profiles saying which model covers which exposure |
| **What the store actually holds** | A fresh database has **no observations and no prices**: all 11 catalogue series are annual World Bank series, and `api.worldbank.org` is blocked by this environment's network policy (403 at the proxy), as in Phases 2–5. Two series are recorded as related measures of variables (INR per USD annual average → USD/INR; CPI inflation → India CPI). The graph's 21 exposure-type relationships (`affects_costs`, `affects_revenue`, `affects_financing`, `influences`) are all **model assumptions** on fictional companies; none is evidence-backed. Company figures exist only as the typed figures of scenarios |
| **Missing for intelligence** | No change detection, trend, volatility or anomaly calculation anywhere; no quality rule compares new data with stored history. No build-to-build comparison of the graph. No way to find executions or runs by company (the index exists, no query uses it). No object that gathers what RUMIN knows about one entity with its evidence |
| **Constraints** | Nothing is fabricated: tests and fixtures use synthetic data, named as such, sent through the real ingestion pipeline. Exact decimals throughout. Released model definitions and stored runs never change. 64 KiB request bodies; no authentication (local use). No new dependencies |
| **Installed skills** | `dataviz` (form, colour by job, marks, interaction, accessibility) is used for every chart. `frontend-design` (read from `/mnt/skills/public/frontend-design`) sets the process: a token plan reviewed against the brief, one signature element, restraint, screenshots for critique. No other frontend, visualisation, animation, accessibility or performance skill is installed: the claude.ai skills searched for those topics returned nothing, and the example skills (artifact builders, theme factory, canvas design, generative art) build standalone artifacts, not an application's own interface. `financial-calculator` shares the "show your work" principle |

Defects found while inspecting, fixed separately: the Lab's stage marker pulses on every
stage (it should only pulse on the running one) and a malformed selector leaves failed
stages unstyled; the dashboard labels every recent scenario "Not simulated"; the landing
page still describes Phase 4's single model; three system fixtures predate the Lab.

## 2. What Financial Intelligence is

A layer that **analyses** what RUMIN already stores — observations, the knowledge graph,
simulation runs and scenario executions — and returns **findings**: structured facts, each
with the evidence chain that produced it. It answers *what changed, why, who is exposed,
through which relationships, what the models say would happen, which factors contribute
most, which assumptions drive the result, and what to look at next*.

It is not a chatbot and generates no free text. Every sentence is filled from a template
with computed values; every value carries a reference to the record or calculation it came
from. It never forecasts, never ranks companies as investments, and never turns a
relationship into a causal claim.

## 3. Architecture

```
          observations ─┐   graph (validated edges) ─┐   runs + executions ─┐
                        ▼                             ▼                       ▼
   ┌───────────────────────── analysis context (one read per request) ─────────────────────┐
   │ modules: changes · series signals · exposure · drivers · scenario sensitivity ·        │
   │          relationship changes · historical comparison · cross-entity                   │
   └───────────────▲──────────────────────────────┬──────────────────────────────────────┘
        thresholds │ (defaults + overrides,        │ findings (facts with references)
        recorded)  │  recorded with every result)  ▼
                          signals (defined, method, inputs, limitations)
                                          │
                          insight rules (each a documented rule id)
                                          ▼
                insights with evidence chains ─── entity brief (facts for the AI Analyst)
                                          │
                     stored analyses (append-only, hashed, with their sources)
```

- `app/intelligence/`: one module per question, registered in a **module registry**
  (id, question, inputs, method, limitations, version), so new modules plug in without
  touching the others.
- **Findings** are facts; **signals** are defined calculations on findings; **insights**
  are rule-based statements over findings and signals. Each layer references the one
  below, so any sentence can be walked back to records.
- **Thresholds** are configuration, not claims: documented defaults, overridable per
  request within bounds, recorded in every result.
- **Stored analyses** (`intelligence_analyses`, migration `0006`) keep what was concluded,
  from which sources (graph build, observation revisions, executions), with hashes; a
  stored analysis says when newer data has superseded it. Everything else is computed on
  request from the current store.

## 4. Change detection

| Kind | Basis | What is compared |
|---|---|---|
| Value change | **observed** | consecutive reported periods of a series (current rows): relative change for `level` and `exchange_rate` series, percentage points for `change`, `rate` and `ratio` series (their values are already percentages); a gap breaks the chain |
| Price move | **observed** | consecutive closes of an instrument within one dataset |
| Data revision | **observed** | a superseded value and the value that replaced it |
| Relationship change | **recorded** (RUMIN's own records) | edges the latest build added, changed or retired, against the previous build |
| Execution change | **simulated** | two completed executions of one scenario (Phase 5 comparison) |

A change is *detected* when it meets the threshold for its measure (defaults: 5 % for
levels and exchange rates, 1 percentage point for rates and percentages, 5 % for daily
closes). Every change reports the values as published, both periods, the threshold it met,
and the provenance of both values. Observed changes and model interpretations are kept
apart: an interpretation (below) is a separate finding labelled *simulated*.

## 5. Exposure analysis

**Validated** means: current in the latest completed build and `quality_status =
validated` (it passed every validation rule of the build). The evidence status is kept on
every step and shown; a filter keeps only evidence-backed chains (which, on the sample
graph, returns none — and says so).

For a company (or an industry): **direct** exposures (`affects_*` stated for the company),
**via its industry** (stated for its primary industry; said to be industry-level),
**upstream** variables that `influence` an exposed variable (at most two hops), **supply
and credit relationships** (`supplies_to`, `lends_to`, in both directions, with the
registry's caveats) and **context** (industry, sector, country, the country's currency —
each with the caveat that it is not an exposure). Exposures are grouped by the variable's
category (commodities, exchange rates, interest rates, inflation). Each exposure also says
which registered model can simulate it and which stored series measure it. Connections of
other types are counted, never presented as exposure.

## 6. Contribution analysis

Read from stored results, never recomputed: an execution's lines with their `by_change`
credits (Shapley values from the model runs, combined by the Lab), expressed as amounts,
as percentage points of the line's baseline, and as shares of the change; a run's
contributions per output. The sum is checked against the line's change and the residual
reported. Ratios (margin, coverage) have no attribution, and the result says so.

## 7. Signals

| Signal | Subject | Definition (summary) |
|---|---|---|
| Exposure breadth | company | distinct variables reaching the company through validated relationships, by channel and directness |
| Dependency | company | the largest share of the company's exposure paths that pass through one variable; counterparties by kind |
| Trend | series, instrument | least-squares slope over a window, with its *t* statistic; a direction only when \|t\| exceeds the two-sided critical value of Student's *t* (5 % by default) |
| Volatility | series, instrument | standard deviation of changes in the latest window against every earlier window of the same length (ratio and percentile) |
| Anomaly | series, instrument | modified z-score of the latest change against earlier changes (Iglewicz and Hoaglin: 0.6745·(x − median)/MAD; 3.5 by default) |
| Scenario sensitivity | company | per stored execution: each change's contribution to the headline line, per unit of the change, and the stored sensitivity ranking if one exists |

Every signal carries its definition, method, inputs (with references), period, evidence,
limitations and the thresholds used. There is no composite score.

## 8. Insights and evidence chains

An insight is produced by a named rule (for example *I05 simulated driver*) from findings
and signals. It holds: the statement, supporting data, entities, relationships, period,
the model or scenario used, an **evidence grade** (the weakest step of its chain:
observed, documented, curated, assumed, unverified — plus whether it is conditional on a
simulation), assumptions, provenance, limitations, the **evidence chain** (ordered steps,
each with its basis and reference) and **next steps** (rule-based: run a template that
covers an exposure, ingest a series, find evidence for an assumed relationship). No
insight exists without a chain; a test enforces it.

The **entity brief** gathers, for one entity, the observations, drivers, relationships,
simulation results, signals, insights, assumptions, evidence and limitations as one
structured object with references — the facts a future AI Analyst may phrase, never
compute.

## 9. API and database

Under `/api/v1/intelligence`: `GET /overview`, `GET /insights`, `GET /changes`,
`GET /entities`, `GET /entities/{id}` (the brief), `/entities/{id}/exposure`,
`/entities/{id}/signals`, `/entities/{id}/drivers`, `GET /variables/{id}/exposure`
(cross-entity), `GET /series/{id}` (series signals), `GET /methods` (modules, signal
definitions, insight rules, default thresholds), and `POST /analyses` (201), `GET
/analyses`, `GET /analyses/{id}`. Threshold overrides are validated (422 with field paths).
Migration `0006_intelligence` adds `intelligence_analyses` (append-only).

## 10. Interface

A **Financial Intelligence** module (`/intelligence`, and `/intelligence/{entity}` for a
dossier) after the Scenario Lab in the navigation.

Token plan (the brief fixes the identity; nothing new is invented): bone surfaces, charcoal
ink, stone greys for context, sky blue only for the subject in focus and the step of an
evidence chain being read; status colours only for data-quality warnings. Newsreader for
titles, Inter for text, tabular figures for numbers. Evidence grades are encoded by the
graph's existing line patterns plus a label, never by colour alone.

Layout: a left rail of subjects (the workspace, then each company with its exposure
channels), and a main column with the findings ledger. The **signature element** is the
evidence chain: each finding opens into its steps — observation, relationship,
calculation, simulation, result — each linked to its record. The dossier adds the exposure
diagram (upstream variable → exposed variable → channel → company), drivers (contribution
bars per line, one hue, labelled rows), signals with their methods, history (related series
and executions) and sources. Charts follow `dataviz`: one emphasised series, grey context,
tables beside charts, no dual axes.

Review against the brief: a dashboard of gauges and scores would be the generic answer and
is rejected; so are cards of equal weight for every finding. The ledger with chains is
specific to a system whose rule is "no statement without evidence".

## 11. Testing

Hand-checked statistics; change detection on synthetic series sent through the real
pipeline (revisions included) and on price files; exposure against the sample graph's
known ground truth; contributions against the reference execution (operating costs:
Brent 9,225,000, USD/INR 4,025,000); signals; insight rules and the chain invariant;
stored analyses; every endpoint and its validation; frontend pages against fixtures
captured from a real backend; the live API in the smoke test. Phases 1–5 must stay green.

## 12. Order of work

1. Core: registry, evidence model, thresholds, exact statistics.
2. Exposure analysis (graph).
3. Change detection and series signals (data, graph builds).
4. Drivers and scenario sensitivity (runs, executions).
5. Signals, insight rules, next steps, the entity brief.
6. Stored analyses (migration `0006`), API, OpenAPI, generated types.
7. The interface.
8. Tests, performance, visual review; then documentation, the report, commit, push, CI.
