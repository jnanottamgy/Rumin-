# Roadmap

RUMIN is built in ten phases. Each adds one layer of capability on the foundation, and each
keeps the rule that observations, assumptions, scenario inputs, simulated outputs and
uncertainty are never blurred.

| Phase | Name | Delivers |
|---|---|---|
| **1** | **Foundation & system architecture** | **Done:** API, database and migrations, domain model, illustrative network, 2D network view, Scenario Lab (inputs only), design system, tests, CI, documentation |
| **2** | **Financial data infrastructure** | **Done in this build:** provider layer (World Bank), licensed price-file import, exact decimals, provenance and revisions, data-quality rules, job tracking, read-only data API, Data Explorer ([report](phases/phase-2-report.md)) |
| 3 | Financial knowledge graph | Graph analytics: paths, centrality, exposure and propagation queries |
| 4 | Simulation engine | Running scenarios: propagating shocks through the model, with stated assumptions and uncertainty |
| 5 | Scenario Lab | Full scenario workflow: runs, comparisons, sensitivity, saved results |
| 6 | Financial intelligence | Indicators, explanations and reports built on data and simulations |
| 7 | AI Analyst | Questions answered from the model's data, assumptions and runs, with citations |
| 8 | 3D financial universe | A Three.js view of the same model and layout |
| 9 | Advanced simulation & validation | Back-testing, calibration, model validation, evidence upgrades |
| 10 | Productization, security & launch | Accounts and access control, deployment, monitoring, hardening |

The Phase 1 plan named FRED as the first data source. The Phase 2 licence review found that
FRED's terms prohibit storing its content in a database, so the World Bank was selected
instead (see [decisions](decisions.md#13-world-bank-indicators-as-the-first-provider-fred-rejected)).

## Data follow-ups (before or alongside Phase 3)

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
