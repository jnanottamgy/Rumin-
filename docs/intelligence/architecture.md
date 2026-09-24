# Architecture

Financial Intelligence is a read-only analysis layer over what Phases 2–5 store. It adds
one table, for stored analyses, and changes no existing table or result.

```
 observations, revisions,        knowledge graph            Scenario Lab executions,
 price bars (Phase 2)            (Phase 3: validated        their model runs and
                                  edges, builds)             sensitivity analyses (4–5)
          │                             │                              │
          ▼                             ▼                              ▼
 ┌──────────────────────── one bounded read per request ─────────────────────────┐
 │  series.py          graphview.py → exposure.py      drivers.py                 │
 │  changes, revisions  validated slice, paths,        stored contributions,      │
 │  (exact decimals)    counterparties, context        per-unit effects, rankings │
 │  graphchanges.py     (what the latest build changed)  interpretation.py (S06)  │
 └──────────────┬──────────────────────┬─────────────────────────┬────────────────┘
      findings  │ (facts with refs)    │                         │
                ▼                      ▼                         ▼
        signals.py: trend, volatility, anomaly, exposure breadth, dependency,
                    scenario sensitivity (each with definition, method, inputs, limits)
                │  thresholds.py (defaults, bounds, reasons; recorded in every result)
                ▼
        insights.py: 19 rules → insights with evidence chains (model.py grades them)
                │
                ▼
        engine.py: the entity scope (dossier) and the workspace scope (overview)
                │
       ┌────────┴──────────┬──────────────────────────┐
       ▼                   ▼                          ▼
  serialize.py → API   the entity brief           stored analyses
  (exact decimals as   (brief format /1)          (intelligence_analyses,
   strings)                                        append-only, fingerprinted)
```

## Three layers

| Layer | What it is | Example |
|---|---|---|
| **Findings** | Facts computed by a module from stored records, each with references | a change between two stored values, an exposure path, a line's stored contributions |
| **Signals** | Defined calculations on findings: a question, a definition, a method, inputs, a period, evidence and limitations; a named level only where a recorded threshold decides it | *trend: rising (t = 8.35, critical value 3.182)*, *dependency: concentrated (50 % of paths)* |
| **Insights** | Statements produced by a numbered rule from findings and signals, with the evidence chain, facts, entities, relationships, period, models, assumptions, limitations, sources and next steps | *D04 … has been rising over 2021 to 2025: +4.2 INR per USD per year* |

Each layer refers to the one below, so any sentence can be followed back to stored records:
an insight's chain lists the observations, calculations, relationships, records and
simulations it rests on, each with references (`dataset`, `series`, `observation`,
`graph_build`, `graph_edge`, `execution`, `run`, `sensitivity_analysis`, …).

## The module registry

`registry.py` declares six modules. Each has an id, the question it answers, the stores it
reads, its method, what it produces, its limitations and a version. `GET
/intelligence/methods` serves the registry together with the signal definitions, the rules,
the thresholds and the grades, so any result can be read against the method that produced it.

| Module | Question |
|---|---|
| `change_detection` | What changed in the stored data and in RUMIN's records? |
| `series_signals` | How has a series behaved over its latest window, against its own history? |
| `exposure` | Which economic variables reach an entity, through which validated relationships? |
| `drivers` | What drives a simulated result, and what does it rest on? |
| `interpretation` | What would the stored scenario's models say about the change just observed? |
| `insights` | What should a reader know, and what should they look at next? |

A new module must meet the same contract. It declares itself in the registry, writes
nothing, reads within bounds and reports truncation. Anything it states must go through a
rule that attaches a chain.

## Two scopes

**An entity** (a company or an industry), `engine.analyse_entity`: the exposure map
around it (a handful of queries); its completed executions, newest first (at most 20); the
drivers of the latest one and of the previous execution of the same scenario; the stored
series recorded as related measures of its exposure variables, with their signals; the
model interpretation of each such series' latest change through the stored scenario; its
signals; and every insight about it. This is the dossier, and the source of the
[brief](brief.md).

**The workspace**, `engine.analyse_workspace`: the exposure of the listed companies (the
first 200 by name, with every validated edge their paths use), every stored series and
instrument with two or more values, the relationships the latest build changed, the latest
completed execution of each listed company, shared drivers, and coverage. This is the
overview.

A finding that both scopes produce is identical in both. A test compares every insight the
overview and a dossier share, field by field.

## What is computed and what is stored

Every read computes the analysis from the current store and writes nothing. Nothing is
cached between requests, so a read always reflects the latest graph build, the latest
revision of every value and every completed execution. The only writes are **stored
analyses** (`POST /intelligence/analyses`): a snapshot of the result, the thresholds it
used, a fingerprint of everything it read and hashes of both. They are never updated or
deleted, and reading one back says whether it is still current ([stored
analyses](stored-analyses.md)).

The layer never recomputes what another phase stored. Contributions are the Shapley credits
the model runs stored (Phase 4) as the Lab combined them (Phase 5). Exposure is what the
graph states (Phase 3). Values are the current revisions of stored observations (Phase 2).
The one exception is labelled as such: **S06** runs the stored scenario's models as a
preview on an observed change, and that result is computed on request, never stored, and
called a model interpretation ([changes](changes.md#model-interpretation-s06)).

## Numbers

Every calculation uses the engine's decimal context: 34 significant digits, half-even
rounding, and traps on invalid operations. The same stored values always give the same
digits, so results can be hashed and reproduced. Stored values are never rounded. Derived
values are rounded half-even to 10 decimal places, like every engine output, and the API
serves all of them as exact decimal strings. The browser only rounds them for display and
calculates nothing.

## Bounds

Every read is bounded, and a truncated read says so.

| Read | Bound | When it is reached |
|---|---|---|
| Companies in the workspace (exposure, matrix, entity list, impacts) | first 200 by name, with every validated edge their paths use | `coverage.truncated`; the page says "X of the first 200 (N in the graph)" |
| Industries in the entity list | 200 | |
| Upstream `influences` hops | 2 | stated on every upstream path |
| Values read per series or instrument | the latest 2,000 | |
| Values and changes served with a series analysis | the latest 400 values, 60 changes | |
| Revisions per series | 50; at most 5 revision findings per series | |
| Executions per entity | the latest 20 completed | |
| Graph changes per build | 500 | |
| Shared-driver findings (X01) | 12, the variables reaching the most companies | the matrix still shows every variable |
| X01 and D02 counts | the listed companies | the headline says *of the listed companies*, and a limitation names the bound |
| Companies a variable reaches (`/variables/{key}/exposure`, a series' `reached`) | the first 200 by name among every company it reaches in the graph | `total` and `truncated` (`reached_total` for a series) |
| Assumptions listed on one simulated finding | 12, then "… and N more stated with the model runs" | |

## Code

| Path | Contents |
|---|---|
| `app/intelligence/model.py` | references, steps, facts, insights, the grades and `evidence_of` ([evidence](evidence.md)) |
| `app/intelligence/stats.py`, `thresholds.py`, `signals.py` | exact statistics, thresholds, signal definitions ([signals](signals.md)) |
| `app/intelligence/graphview.py`, `exposure.py` | validated graph slices and exposure ([exposure](exposure.md)) |
| `app/intelligence/series.py`, `graphchanges.py`, `interpretation.py` | changes, revisions, relationship changes, S06 ([changes](changes.md)) |
| `app/intelligence/drivers.py` | contributions and sensitivity from stored results ([drivers](drivers.md)) |
| `app/intelligence/insights.py` | the 19 rules ([rules](rules.md)) |
| `app/intelligence/engine.py`, `serialize.py`, `registry.py`, `fmt.py` | the scopes, serialisation and the brief, the registry, number wording |
| `app/services/intelligence.py`, `app/api/v1/intelligence.py`, `app/schemas/intelligence.py` | the service, 16 operations, their schemas ([API](../api.md#financial-intelligence)) |
| `app/models/intelligence.py`, `migrations/versions/0006_intelligence.py` | stored analyses |
