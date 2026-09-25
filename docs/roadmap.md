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
| **6** | **Financial intelligence** | **Done:** findings from 19 documented rules over stored observations, validated graph relationships and stored executions, each with its evidence chain and grade (the weakest link); change detection, revisions, trends, volatility and unusual moves against configurable thresholds; exposure paths and a companies × variables matrix; drivers from stored contributions; model interpretations of observed changes; dossiers per company and industry; a structured brief for the AI Analyst; stored, fingerprinted analyses that know when they are stale; the Financial Intelligence interface ([report](phases/phase-6-report.md)). Exposure sizes and reports as documents were left for later ([why](phases/phase-6-report.md#10-verification-against-the-brief)) |
| **7** | **AI Analyst** | **Done:** questions answered from RUMIN's records through 17 allowlisted, read-only tools over the Phase 2–6 services (one compute tool: an unstored scenario preview); an evidence ledger with eight kinds of knowledge; every figure cited and checked mechanically against its evidence, unsupported parts never shown; RUMIN's grounded composer by default and an optional Claude model through the official SDK, held to the same check with fallback; conversations with focus, follow-ups and clarifications; guardrails for advice, forecasts, live data, injection and secrets; bounded work and cost; the evidence-margin workspace with the Scenario Lab hand-over; a 33-case evaluation set ([report](phases/phase-7-report.md)). A language model has **not** been measured: no key was available ([why](analyst/providers.md#not-verified-here)) |
| **8** | **3D financial universe** | **Done in this build:** the knowledge graph in three dimensions (`/universe/3d`) — strata by kind, the graph's own marks, the whole build within a budget, neighbourhoods and paths through the 2D explorer's state, every record's provenance and evidence in the same panels, overlays of stored executions (changed, simulated, propagated, cited, not simulated, with their stored results), a keyboard model and a list twin, rendering on demand, lazily loaded Three.js ([report](phases/phase-8-report.md), [guide](universe/README.md)). Hardware GPU frame rates were not measured: none was available ([why](universe/performance.md)) |
| **9** | **Advanced simulation & validation** | **Done in this build:** on a stored execution of the Scenario Lab, sensitivity to chosen quantities one at a time or **two together with their interaction**, and **Monte Carlo** under distributions the user states (uniform, triangular, discrete; a recorded seed; percentiles with the interval the draws support, shares, histogram, rank correlations, convergence diagnostics; rejected draws counted, never adjusted), stored append-only and re-run to compare; a **verification register** for every model version (hand-calculated reference cases, stated properties, documented limits, reproducibility) shown in the product beside what is not verified; the four kinds of analysis stated where they are used; a corrected one-at-a-time method ([report](phases/phase-9-report.md), [guide](scenario-lab/advanced-analysis.md)). Estimation, calibration and back-testing were **not** done: no observations are stored in this environment and the companies are fictional ([why](simulation/verification.md#what-is-not-verified)) |
| **10** | **Productization, security & launch** | **Done in this build:** a product audit ranked by severity; accounts, server-side sessions, viewer, analyst and admin roles and ownership enforced by the backend, with account locks, per-address limits and a security audit trail; *People* for administrators; production images, compose, nginx (TLS, CSP, rate limits), metrics, JSON logs, a tested backup, restore and rollback; a getting-started guide; a browser launch suite with axe on a desktop and a phone, run in CI and against the production stack; the [launch readiness assessment](phases/phase-10-report.md#launch-readiness). **Not deployed to a production host, not load-tested and not formally assessed** ([report](phases/phase-10-report.md)) |

The Phase 1 plan named FRED as the first data source. The Phase 2 licence review found that
FRED's terms prohibit storing its content in a database, so the World Bank was selected
instead (see [decisions](decisions.md#13-world-bank-indicators-as-the-first-provider-fred-rejected)).

## Data follow-ups

1. **Verify a live World Bank run** on a machine with internet access and review the data
   in the Data Explorer (the build environment blocked the provider).
2. **MoSPI provider** for official monthly Indian CPI, WPI and IIP (needs an access token:
   the first real secret, server-side only).
3. **Review workflow** for flagged values and rejected records (reviewer, decision, note).
4. **Scheduled refreshes**, now that accounts exist, using the existing job model.
5. **Series ↔ variable views** in the Universe and the Scenario Lab: show the latest
   related observation next to a variable, with the stated difference in measure.
6. **Company data policy.** Decide scope and licensing before ingesting any real company
   figures. Real and fictional entities stay strictly separated.
7. **Retention policy** for stored response bodies.

## Platform follow-ups worth doing early

- Choose a licence for the repository.
- ~~Add dependency and secret scanning to CI~~ (Phase 10).
- ~~Add browser end-to-end tests (Playwright) for the main flows, and run them in CI~~
  (Phase 10).
- ~~Decide the authentication model before any multi-user or hosted use~~ (Phase 10: local
  accounts with server-side sessions; an identity provider can be added).

## Launch follow-ups (after Phase 10)

In the order the [readiness assessment](phases/phase-10-report.md#launch-readiness) ranks
them:

1. **A qualified review of the legal questions** in [privacy](privacy.md#areas-for-qualified-review)
   (data protection, professional confidentiality, securities regulation, data licences, the
   model provider's terms), and a privacy notice in the product.
2. **A first deployment on the intended host** with a real certificate, followed by
   `scripts/verify_deployment.sh`, a restore drill and the alerts in
   [operations](operations.md#metrics).
3. **Multi-factor authentication or single sign-on** before anyone outside the team signs in.
4. **A formal security assessment** (a penetration test) before a public launch.
5. **Load testing** of sign-in, the pages, executions and the Analyst at the expected number
   of users.
6. **Separation between clients or engagements** (several workspaces), or one deployment per
   workspace until then.
7. **Quotas and retention** for stored records per person, and a procedure to erase or
   export one person's data.
8. **A shared job queue** (PostgreSQL-backed) before more than one API process.
9. **A session with people who use assistive technology**, and Firefox and Safari runs of the
   launch suite.
10. **Base images pinned by digest** and scanned in CI.

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
2. **Retention and quotas** for runs, executions and analyses per person (they have owners
   since Phase 10; the limits are not built).
3. **An explanation paged by month** for larger models (36 months is about 101 kB today).
4. **More stored inputs** with their provenance: a monthly exchange rate, a monthly policy
   rate, and jet fuel prices from a licensed source, once available.
5. **Estimated parameters**: β and the lags estimated from stored series, each with its
   method, sample and uncertainty, entering as inputs with provenance — not possible in
   Phase 9, where no observation is stored; then **back-testing** against observed outcomes,
   reported in the verification register.
6. **Correlated draws** (a rank-correlation structure between quantities), **variance-based
   (Sobol) indices** and **Latin hypercube sampling** for the Monte Carlo analysis; Monte Carlo
   on single Simulation-page runs; a **reverse stress test** (the changes that would breach a
   threshold).

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
6. **The Phase 9 analyses in the launch suite**: since Phase 10 CI builds and executes a
   scenario from a template in a browser with `axe-core`; the grid and Monte Carlo forms are
   covered by the page and integration suites only.
7. **Analyses on a queue** once analyses may take longer than a request (today at most two
   compute at once per process, each within 20 seconds).

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
7. **Retention for stored analyses**, now that they have an author (Phase 10).

## Analyst follow-ups

1. **Measure a language model** on the evaluation set with a key (`python -m app.analyst.evaluation`
   with `RUMIN_ANALYST_PROVIDER=anthropic`): pass rate, fallbacks, latency and tokens per
   question. Decide the default provider from that, not before.
2. **Real questions.** Log, with consent, the questions the router reads as `unsupported` or
   `clarify`, and grow the evaluation set and the vocabulary from them.
3. **Checking words, not only figures.** Superlatives and rankings ("the largest", "most
   exposed") can be wrong without a figure; check them against the ordering in the cited
   evidence.
4. **Streaming** (server-sent events) if model answers feel slow; the polling contract can
   stay for clients that prefer it.
5. **Per-person budgets and retention** (conversations became private in Phase 10); a queue
   and a token budget shared across API processes.
6. **More questions**: comparing two stored scenarios, several subjects at once, questions
   about a stored analysis, and a tool over the Phase 6 brief for a model that works better
   from it.
7. **Reports**: a conversation exported as a document whose every figure keeps its citation.

## Universe follow-ups

1. **Measure on a GPU.** The Phase 8 measurements ran on software WebGL; record frame times
   on an integrated and a discrete GPU, and on a phone, for the sample and at the budget.
2. **Layout off the main thread** (a Web Worker) before raising the 500-node budget.
3. **Fetch an overlay's missing records** by key, so a neighbourhood can show an overlay
   whole without switching to the universe.
4. **Compare two executions** as an overlay (`overlay.ts` is the extension point).
5. **Relationships from the keyboard on the canvas** (today they are reached through the node
   panel and the list).
6. **A screen-reader session** with a user, beyond the automated checks.

## Recommendations for Phase 10 (productization, security and launch)

Written at the end of Phase 9 ([report](phases/phase-9-report.md#17-recommendations-for-phase-10)):

1. **Authentication and ownership first.** Runs, executions and analyses are append-only but
   unowned and unlimited; per-user limits and retention come with accounts.
2. **A shared job queue** for executions and analyses before running several API processes:
   today's pools and the two-analysis semaphore are per process.
3. **Automated browser checks in CI**, starting from the Phase 9 review (walk-through,
   `axe-core`, sideways scrolling at 390 px).
4. **Observability**: durations, rejected draws, 429s and failed executions are the first
   capacity and quality signals.

## Recommendations for Phase 8 (3D financial universe)

Written at the end of Phase 7. Phase 8 built the view over the **knowledge graph** rather
than the Phase 1 network (the graph carries provenance and evidence for every record, and the
2D network stays at `/universe`); items 2, 4 (paths → 3D, *Ask the Analyst* from a node) and
5 were done; the synthetic measurements went to 2,000 nodes and 8,000 edges rather than
20,000 companies, because the universe never draws a build that large at once (it grows by
neighbourhoods, which the graph benchmarks already cover); *Open in the Scenario Lab from an
exposure* and item 6 were not done (no model key was available, and this environment's network
policy blocks `api.worldbank.org`).

The recommendations as written:

1. **Reuse the model and the layout.** The network's model, filters, selection and layout are
   pure and renderer-agnostic (Phase 1); a Three.js renderer should consume them, keep the 2D
   Universe as the default and accessible fallback (with its table view), and load lazily so
   no other page pays for it. Three.js would be the first frontend dependency since Phase 1:
   record the decision.
2. **Encode only what exists.** Depth, height and glow must not suggest magnitudes RUMIN does
   not hold. Keep the kinds of knowledge and evidence statuses readable by shape and pattern,
   never colour alone, as in 2D and the graph explorer.
3. **Budgets first.** Measure frame time and memory on the 20,000-company synthetic networks
   the graph benchmarks use; instanced meshes, level of detail and a WebGL-unavailable
   fallback before any visual polish.
4. **Connect to the Analyst and the Lab.** *Show in the universe* from an answer's paths (the
   paths block already carries node keys), *Ask about this* from a selected node into the
   Analyst with that node as the subject, and *Open in the Scenario Lab* from an exposure.
5. **Accessibility and motion.** Keyboard navigation between nodes, a screen-reader summary of
   the selection, no motion until asked for and none under reduced motion.
6. **Before or alongside it**: measure a Claude model on the evaluation set (Analyst
   follow-up 1) and run the World Bank retrieval where it is reachable, so answers and views
   are shown on real observations rather than SYNTHETIC ones.

## Recommendations for Phase 7 (AI Analyst)

Written at the end of Phase 6. Items 2–4 were done in Phase 7 (a mechanical grounding check
before display; grades and labels carried into answers as kinds of knowledge; questions mapped
to intents answered by the rules and data that exist, *not held by RUMIN* otherwise). Item 1
changed: the Analyst reads through tools over the same services the brief is built from
(dossiers, exposure, drivers, findings), which also reach series, paths, scenarios and
previews the brief does not hold. Item 5 is partly done: a language model is optional and off
by default, its key never leaves the backend, and data sent to it is limited to tool results;
a local model option and authentication remain open.

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
