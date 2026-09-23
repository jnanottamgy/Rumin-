# Known limitations

What RUMIN does **not** do, so nothing is mistaken for a capability. In the app, the System
page shows which capabilities exist and which are planned (and for which phase), read from
the API; the Data Explorer shows what data is actually stored.

## Data (Phase 2)

- **Nothing is live.** All provider data is historical and retrieved on demand from the
  command line. There is no market feed, no streaming, no intraday data, no scheduler.
- **One provider, annual data.** Eleven World Bank WDI series (India, with the United
  States and the United Arab Emirates for context). WDI is mostly annual and published
  with a lag of a year or more; recent years are usually listed without values.
- **No official monthly Indian statistics yet.** MoSPI (CPI, WPI, IIP) is the next provider
  and needs an access token; RBI offers no official API.
- **No market prices unless you import them.** RUMIN ships no price data. Prices enter only
  from files you are licensed to use; RUMIN records the licence you declare but cannot
  verify it.
- **No adjustments or conversions.** Prices are not adjusted for splits, bonuses or
  dividends (an adjusted close is stored only if the file supplies one); no currency
  conversion; no rebasing or deflating of series.
- **No financial statements** (company results, balance sheets) and no company-level data.
- **Review ranges are assumptions.** A value outside a series' review range is flagged, not
  judged wrong; the ranges were chosen by RUMIN, not the provider.
- **No review workflow.** Flagged values and rejected records are recorded as issues with
  review status `unreviewed`; nobody can mark them reviewed yet.
- **Revisions are detected only when data is re-fetched.** A provider's change is recorded
  at the next run that covers the period; values absent from a later response are kept
  (absence is not treated as withdrawal).
- **Issues are recorded per run.** Re-running records the same flags again for that run.
- **Stored response bodies are not pruned.** They are small for annual data; there is no
  retention policy yet (`RUMIN_STORE_SOURCE_BODIES=false` keeps hashes only).
- **The chart and tables load up to 500 observations per series and 10,000 trading days
  per instrument**, and say so when more exist.
- **Keyed providers are not implemented.** The design (environment variables, URL
  redaction, `authentication_failed`) is ready, but no provider needs a key yet.

## Verification (Phase 2)

- **No live World Bank retrieval was verified where Phase 2 was built.** The build
  environment's network policy blocks `api.worldbank.org`: a real run was attempted and
  correctly recorded as `failed` (every request refused at the proxy, then the circuit
  breaker skipped the rest). The provider adapter is tested against scripted responses that
  follow the documented format. **The first real run should be checked by a person**
  (`make ingest`, then the Data Explorer and `python -m app.ingestion job <id>`).
- **Provider terms were read through search results**, not by opening the providers' pages
  directly (also blocked). Re-read them in full before commercial use.
- **Synthetic data in tests and screenshots.** Automated tests and interface checks use
  formula-generated data whose names say "SYNTHETIC"; none of it is shipped or loaded by
  default.

## Product

- **No simulation.** Scenarios are saved as drafts of inputs only. There is no engine, no
  run endpoint, no results, no forecasts. Planned for Phase 4.
- **Illustrative network.** The 12 companies are fictional. The 41 relationships are
  modelling assumptions written for demonstration, each with a rationale, none estimated
  or validated. Do not use them to reason about real companies or markets.
- **No AI analyst.** The page explains the planned feature; no model is connected. Phase 7.
- **No graph analytics.** No centrality, paths or propagation beyond direct neighbours.
  Phase 3.
- **2D only.** The 3D financial universe is Phase 8.
- **Small-graph rendering.** SVG and a synchronous layout are right for tens to a few
  hundred nodes; thousands will need a Web Worker layout and canvas/WebGL rendering.
- **English only**, no localisation; numbers use an English locale format.

## Platform

- **No authentication or authorisation.** Anyone who can reach the API can read all data
  and change scenarios. Local use only until Phase 10. For the same reason ingestion cannot
  be started over HTTP. See [security.md](security.md).
- **No inbound rate limiting, audit log or backups.** Outbound requests to providers are
  throttled; the API itself is not.
- **Not containerised.** `docker-compose.yml` provides PostgreSQL only. Deployment is
  Phase 10.
- **Scenario history.** Replacing a scenario overwrites it (last write wins).

## Verification (general)

- **No automated browser end-to-end, visual-regression or screen-reader tests.** Pages
  were checked in Chromium at desktop and phone sizes in both themes; behaviour is covered
  by the jsdom suite and the live integration suite.
- **Browsers:** developed and checked in Chromium only.
- **No load or performance testing** beyond query design, build size and layout time.

## Repository

- **No licence file.** The owners need to choose one; until then all rights are reserved.
