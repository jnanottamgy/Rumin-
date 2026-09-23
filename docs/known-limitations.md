# Known limitations

Phase 1 is a foundation. This page lists what it does **not** do, so nothing is mistaken
for a capability. In the app, the System page shows which capabilities exist and which are
planned (and for which phase), read from the API.

## Product

- **No simulation.** Scenarios are saved as drafts of inputs only. There is no engine, no
  run endpoint, no results, no forecasts. Planned for Phase 4.
- **No observed data.** The database holds no prices, rates, exchange rates, financial
  statements or time series. Economic variables are defined (with sources) but not
  measured. Data ingestion is Phase 2.
- **Illustrative sample only.** The 12 companies are fictional. The 41 relationships are
  modelling assumptions written for demonstration, each with a rationale, none estimated
  or validated. Do not use them to reason about real companies or markets.
- **No AI analyst.** The page explains the planned feature; no model is connected and no
  request is made. Phase 7.
- **No graph analytics.** No centrality, paths or propagation beyond direct neighbours.
  Phase 3.
- **2D only.** The 3D financial universe is Phase 8; the data model and layout are ready
  for a second renderer.
- **Small-graph rendering.** SVG and a synchronous layout are right for tens to a few
  hundred nodes; thousands will need a Web Worker layout and canvas/WebGL rendering.
- **English only**, no localisation; numbers use an English locale format.

## Platform

- **No authentication or authorisation.** Anyone who can reach the API can change data.
  Local use only until Phase 10. See [security.md](security.md).
- **No rate limiting, audit log or backups.**
- **Not containerised.** `docker-compose.yml` provides PostgreSQL only; the API and web
  client run on the host. Deployment is Phase 10.
- **Single dataset.** The loader handles one active dataset; versioned, multi-source
  datasets arrive with the Phase 2 data infrastructure.
- **Scenario history.** Replacing a scenario overwrites it; there is no version history
  or concurrent-edit protection (last write wins).

## Verification

- **Docker image not pulled in the build environment.** Docker Hub was unreachable where
  Phase 1 was built, so `docker compose up` itself was not run; the compose file was
  validated with `docker compose config`, and the PostgreSQL path was verified against a
  local PostgreSQL 16 server (migrations, seed and the full backend suite pass). CI runs
  the backend suite on a PostgreSQL 16 service container.
- **CI not yet observed running.** The workflow was written and its commands were run
  locally; its first run on GitHub will confirm it.
- **No automated browser end-to-end, visual-regression or screen-reader tests.** Pages
  were checked manually in Chromium at desktop and phone sizes in both themes; component
  and page behaviour is covered by the jsdom test suite.
- **Browsers**: developed and checked in Chromium. Firefox and Safari were not tested;
  the code uses only widely supported web platform features.
- **No load or performance testing** beyond measuring the build size and the layout time.

## Repository

- **No licence file.** The owners need to choose one; until then all rights are reserved.
