# Roadmap

RUMIN is built in ten phases. Each adds one layer of capability on the foundation, and each
keeps the rule that observations, assumptions, scenario inputs, simulated outputs and
uncertainty are never blurred.

| Phase | Name | Delivers |
|---|---|---|
| **1** | **Foundation & system architecture** | **Done in this build:** API, database and migrations, domain model, illustrative dataset, 2D network, Scenario Lab (inputs only), design system, tests, CI, documentation |
| 2 | Financial data infrastructure | Observed data from cited sources: time series, provenance, data quality |
| 3 | Financial knowledge graph | Graph analytics: paths, centrality, exposure and propagation queries |
| 4 | Simulation engine | Running scenarios: propagating shocks through the model, with stated assumptions and uncertainty |
| 5 | Scenario Lab | Full scenario workflow: runs, comparisons, sensitivity, saved results |
| 6 | Financial intelligence | Indicators, explanations and reports built on data and simulations |
| 7 | AI Analyst | Questions answered from the model's data, assumptions and runs, with citations |
| 8 | 3D financial universe | A Three.js view of the same model and layout |
| 9 | Advanced simulation & validation | Back-testing, calibration, model validation, evidence upgrades |
| 10 | Productization, security & launch | Accounts and access control, deployment, monitoring, hardening |

## Phase 2 — next steps

The goal: replace "defined but not measured" with real, sourced observations, without
weakening provenance.

1. **Observation storage.** `series` (variable, source, unit, frequency, licence) and
   `observations` (series, period, value as exact decimal, source reference, retrieval
   time). Append-only with vintages, so "what did we know on date X" can be answered and
   revised figures never overwrite history. Everything served with
   `epistemic_category: observation`.
2. **Source connectors** for the variables already defined, starting with public sources:
   FRED (Brent, jet fuel, Henry Hub, USD/INR, federal funds), the Reserve Bank of India
   (policy repo rate) and MoSPI (CPI). Scheduled, idempotent, retried, rate-limited; each
   source's licence and attribution terms reviewed before use. Provider API keys (FRED
   requires one) are the first real secrets: server-side only, from the environment or a
   secret store.
3. **Data quality.** Unit and frequency checks, gap detection, outliers *flagged* (never
   silently corrected), freshness monitoring, and a visible "last retrieved" on every
   figure.
4. **Time-series API and charts.** `GET /api/v1/variables/{id}/observations?from=&to=`,
   and variable charts in the Universe's detail panel and the Scenario Lab (the current
   value next to the change being entered).
5. **Company data policy.** Decide scope and licensing before ingesting any real company
   figures (e.g. statutory filings). Real and fictional entities stay strictly separated.
6. **Dataset governance.** Multiple versioned datasets; a review workflow for relationship
   changes; evidence-level upgrades (`documented`, `estimated`) that require references.

## Phase 1 follow-ups worth doing early

- Choose a licence for the repository.
- Add dependency and secret scanning to CI.
- Add browser end-to-end tests (Playwright) for the main flows, and run them in CI.
- Decide the authentication model before any multi-user or hosted use — ideally before
  Phase 2 stores licensed data.
