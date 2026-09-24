# Roadmap

RUMIN is built in ten phases. Each adds one layer of capability on the foundation, and each
keeps the rule that observations, assumptions, scenario inputs, simulated outputs and
uncertainty are never blurred.

| Phase | Name | Delivers |
|---|---|---|
| **1** | **Foundation & system architecture** | **Done:** API, database and migrations, domain model, illustrative network, 2D network view, Scenario Lab (inputs only), design system, tests, CI, documentation |
| **2** | **Financial data infrastructure** | **Done:** provider layer (World Bank), licensed price-file import, exact decimals, provenance and revisions, data-quality rules, job tracking, read-only data API, Data Explorer ([report](phases/phase-2-report.md)) |
| **3** | **Financial knowledge graph** | **Done:** a graph of every record RUMIN holds (9 node types, 18 edge types) with evidence on every edge, conservative entity resolution, validation and build reports, neighbourhoods, shortest paths, components and metrics, a read-only graph API and the Knowledge Graph explorer ([report](phases/phase-3-report.md)). Centrality and propagation were deliberately left out ([why](decisions.md#30-no-centrality-weighted-paths-or-community-detection-yet)) |
| **4** | **Simulation engine** | **Done:** a versioned model registry and its first model (an airline fuel-cost shock: crude oil, jet fuel and the exchange rate through hedging and a lagged fare pass-through), exact decimals, propagation only along confirmed graph relationships, Shapley contributions, one-at-a-time sensitivity, append-only runs with provenance and verification, the simulation API and the Simulation preview ([report](phases/phase-4-report.md)). Monte Carlo was deliberately deferred ([why](decisions.md#39-one-at-a-time-sensitivity-points-outside-a-range-are-skipped)) |
| **5** | **Scenario Lab** | **Done:** versioned scenarios executed through the model registry (five models, six versions), a planner that says which models apply and why, a bounded background runner with recorded stages, cancellation and time limits, the Lab's aggregation equations, the modelled pathway with graph context kept apart, baseline against scenario, months with a replay, stress cases, one-at-a-time sensitivity, explanations from stored runs, history, reproducibility checks and comparisons, templates built on implemented models, and the Scenario Lab interface ([report](phases/phase-5-report.md)). Demand and supply-chain shocks were deliberately left out ([why](decisions.md#43-several-narrow-models-composed-by-line-items)) |
| **6** | **Financial intelligence** | **Done in this build:** findings from 19 documented rules over stored observations, validated graph relationships and stored executions, each with its evidence chain and grade (the weakest link); change detection, revisions, trends, volatility and unusual moves against configurable thresholds; exposure paths and a companies × variables matrix; drivers from stored contributions; model interpretations of observed changes; dossiers per company and industry; a structured brief for the AI Analyst; stored, fingerprinted analyses that know when they are stale; the Financial Intelligence interface ([report](phases/phase-6-report.md)). Exposure sizes and reports as documents were left for later ([why](phases/phase-6-report.md#10-verification-against-the-brief)) |
| 7 | AI Analyst | Questions answered from the model's data, assumptions and runs, with citations |
| 8 | 3D financial universe | A Three.js view of the same model and layout |
| 9 | Advanced simulation & validation | Back-testing, calibration, model validation, evidence upgrades |
| 10 | Productization, security & launch | Accounts and access control, deployment, monitoring, hardening |

The Phase 1 plan named FRED as the first data source. The Phase 2 licence review found that
FRED's terms prohibit storing its content in a database, so the World Bank was selected
instead (see [decisions](decisions.md#13-world-bank-indicators-as-the-first-provider-fred-rejected)).

## Data follow-ups

1. **Verify a live World Bank run** on a machine with internet access and review the data
   in the Data Explorer (the build environment blocked the provider).
2. **MoSPI provider** for official monthly Indian CPI, WPI and IIP (needs an access token:
   the first real secret, server-side only).
3. **Review workflow** for flagged values and rejected records (reviewer, decision, note).
4. **Scheduled refreshes** once authentication exists, using the existing job model.
5. **Series ↔ variable views** in the Universe and the Scenario Lab: show the latest
   related observation next to a variable, with the stated difference in measure.
6. **Company data policy.** Decide scope and licensing before ingesting any real company
   figures. Real and fictional entities stay strictly separated.
7. **Retention policy** for stored response bodies.

## Platform follow-ups worth doing early

- Choose a licence for the repository.
- Add dependency and secret scanning to CI.
- Add browser end-to-end tests (Playwright) for the main flows, and run them in CI.
- Decide the authentication model before any multi-user or hosted use.

## Graph follow-ups

1. **A cheaper freshness check**: a change counter or per-table checksum written when
   sources change, so the overview no longer reads every record (about 6 s at 20,000
   companies) and "stale" appears at once.
2. **Skip unchanged rebuilds** when the source fingerprint matches the latest build, and
   compute components once per build.
3. **A review workflow** for entity-resolution candidates and validation issues, shared
   with the data-quality review (data follow-up 3).
4. **Real, sourced relationships**: citations for curated relationships, and a policy for
   adding documented real-company relationships (see data follow-up 6).
5. **Attribute history** (`graph_node_versions` / `graph_edge_versions`) if earlier
   descriptions or qualifiers must be reconstructable, not only membership.
6. **Search at scale**: a trigram or full-text index for node search on PostgreSQL.

## Simulation follow-ups

Done in Phase 5: scenarios connected to models (the Scenario Lab), executions compared side
by side, four more models on the same engine, and presentation read from each model's
scenario profile in the Lab. Still open:

1. **Presentation declared in the model definition for the Simulation page** too
   (headline, baseline-and-scenario pairs, monthly series), replacing its naming
   conventions.
2. **Retention and quotas** for runs, executions and analyses, with authentication
   (Phase 10).
3. **An explanation paged by month** for larger models (36 months is about 101 kB today).
4. **More stored inputs** with their provenance: a monthly exchange rate, a monthly policy
   rate, and jet fuel prices from a licensed source, once available.
5. **Estimated parameters** (Phase 9): β and the lags estimated from stored series, each
   with its method, sample and uncertainty, entering as inputs with provenance.

## Scenario Lab follow-ups

1. **Cache the plan per graph build.** Most of a preview's 50–130 ms is spent reading the
   graph's exposures again; they change only with a build.
2. **A shared execution queue** (PostgreSQL-backed) before running several API processes,
   with the same states, limits and recovery.
3. **Push instead of polling** (server-sent events) for execution stages, if executions
   grow longer.
4. **Paths, not steps**: changes that rise gradually or decay, per change rather than one
   timing for the whole scenario.
5. **A volume model** designed so that the other models read its volumes rather than hold
   them fixed — the precondition for demand-shock templates.
6. **Persisted sensitivity requests from the page**: choose the quantities and points (the
   API accepts them; the page runs the defaults).
7. **Browser end-to-end tests** of the Lab's main flow in CI (see the platform follow-ups).

## Intelligence follow-ups

1. **Real observations.** Run the World Bank retrieval where it is reachable and review
   the observed-data findings on real values (every one shown so far used SYNTHETIC
   values). Then add monthly exchange and policy rates and fuel prices from licensed
   sources, so windows, anomalies and volatility have enough history (data follow-ups 1–2).
2. **Exposure sizes with provenance** (still open from the Phase 6 recommendations below):
   shares of revenue in dollars, of costs in fuel, of debt at a floating rate, as sourced
   records, so exposure can say *how much* where a source does.
3. **Evidence-backed relationships** for the exposures that matter, so findings can be graded
   better than *assumed* (graph follow-up 4).
4. **Per-series thresholds and a multiple-testing control** once many series are stored.
5. **Reports as documents**: a dossier or a stored analysis rendered as a document with every
   figure traceable, still without generated narrative.
6. **Search and paging over companies** instead of the first 200 by name, or exposure
   precomputed per build.
7. **Retention for stored analyses** with authentication (Phase 10).

## Recommendations for Phase 7 (AI Analyst)

Phase 7 should phrase what Phase 6 computes, never compute it:

1. **The brief as the only input.** The Analyst receives `rumin.intelligence.brief/1` (and the
   overview for workspace questions) and answers only from it, following its narration
   rules.
2. **Mechanical checking before display.** Every number in an answer must appear in the brief,
   and every sentence must cite an insight id whose chain leads to stored records. An answer
   that fails is not shown, and the check is tested.
3. **Grades and labels carried into the answer**: *simulated, not a forecast*, *assumed*, and
   what is not known, stated where they apply.
4. **Questions mapped to rules**: *what changed*, *who is exposed*, *what drives this result*,
   *what should I check next*, each answered by the rules and data that exist, and *cannot say*
   otherwise.
5. **A local or self-hosted model option** and a clear data policy before any external model
   sees data, together with authentication (Phase 10).

## Recommendations for Phase 6 (financial intelligence)

Written at the end of Phase 5. Items 1 and 3 were done in Phase 6 (indicators from executions
became the drivers and signals; reports became dossiers, briefs and stored analyses, as
structured records rather than documents); items 2 and 4 remain open (see the intelligence
follow-ups above).

Phase 6 should build on what Phase 5 stores rather than beside it:

1. **Indicators from executions**: margin and coverage under stress, the sensitivities that
   dominate, and the changes each company is most exposed to — computed from stored
   executions and analyses, each with the execution it came from.
2. **Exposure sizes with provenance.** The graph says *that* a company is exposed; Phase 6
   should add *how much* (shares of revenue in dollars, of costs in fuel, of debt at a
   floating rate) as sourced records with evidence, so templates can offer figures a user
   confirms instead of entering from scratch.
3. **Reports assembled from stored records**: a scenario's pathway, results, explanation and
   verification as a document, with every figure traceable to its execution and run — no
   generated narrative.
4. **Data before models**: monthly exchange and policy rates and fuel prices from licensed
   sources, so market baselines can come from stored data rather than typed values.
