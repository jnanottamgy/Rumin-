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

## Knowledge graph (Phase 3)

The full list, with reasons, is in [`docs/graph/limitations.md`](graph/limitations.md).

- **It connects the records RUMIN holds, not the economy.** 50 nodes and 97 edges from the
  sample dataset and the series catalogue. All 12 companies are fictional, and 65 edges
  touch them.
- **No edge is empirically validated.** 41 edges are model assumptions, 32 were written by
  a curator, and 24 transcribe a standard or a provider's metadata ("evidence-backed"
  means a source states it, not that it was verified). None of the curated relationships
  cites an outside source.
- **No sizes, correlations or causes.** An assumed effect has no magnitude, timing or
  certainty, and paths link records, not mechanisms. No correlation is computed.
- **Duplicates are flagged, not merged**, and there is no review workflow or outside
  registry lookup. Some partial name matches made only of common words are not searched
  for.
- **As of the last build.** Nothing rebuilds automatically. "Stale" can appear up to 30
  seconds late on a running API. Only membership history is kept, not earlier attribute
  values.
- **Measured to about 21,000 nodes and 108,000 edges** on synthetic data. At that size the
  first overview request after a build or restart takes about 6 s, and an unchanged
  rebuild about 16 s.
- **Read-only and unauthenticated.** No write endpoint. Builds run from the command line.

## Simulation (Phase 4)

The full list, with reasons, is in [`docs/simulation/limitations.md`](simulation/limitations.md).

- **Not forecasts, not advice, not validated.** A run is the arithmetic consequence of the
  inputs and assumptions shown, with everything else held constant. No parameter has been
  estimated from data and no result has been back-tested: the crude-to-jet-fuel
  elasticity, the lags, the hedge terms and the fare pass-through are assumptions with
  neutral defaults.
- **Narrow models.** Phase 4's model: an airline's fuel cost, operating profit and margin
  under changes in crude oil, jet fuel and the exchange rate. Phase 5 adds four more, each as
  narrow (foreign-currency revenue and costs, floating-rate interest, crude- and
  gas-linked costs). RUMIN holds no company accounts, so every company figure comes from the
  user. The sample airlines are fictional, and the graph
  relationship the model relies on is an illustrative model assumption.
- **Deterministic only.** Uncertainty is shown by one-at-a-time sensitivity, which shows
  no interactions and is not a confidence interval. No Monte Carlo (Phase 9).
- **Simple dynamics.** Monthly steps; a change is a step of constant size (since Phase 5 it
  can start later and last a number of months, but it cannot follow a path); no
  seasonality; hedging and fare pass-through are a share and a number of months each.
- **One relationship travels through the graph** (crude oil → jet fuel). Coefficients and
  lags are inputs, never inferred from the graph or from data.
- **Little stored data is used.** Only the exchange rate can come from stored data (the
  latest annual World Bank average), and none is stored where Phase 4 was built, because
  the World Bank retrieval was blocked.
- **Storage grows without limit.** Runs, scenario versions, executions and analyses are
  append-only, there is no retention policy, and anyone who can reach the API can add them.

## Scenario Lab (Phase 5)

The Lab's own list is in [scenario-lab/limitations.md](scenario-lab/limitations.md). In
short:

- **Five narrow models, fixed volumes.** A change no model simulates cannot be executed;
  there is no demand or supply-chain model, so no such template.
- **Partial statements.** Revenue, operating costs, operating profit, interest expense,
  profit before tax, operating margin and interest coverage — only the lines an included
  model reaches. No cash flow, tax, working capital or balance sheet.
- **Constant baselines.** The user's annual figures × horizon ÷ 12: inputs, not forecasts.
- **Deterministic and one-at-a-time.** Stress cases and sensitivity move magnitudes; there
  are no probabilities (Phase 9).
- **No second-round effects.** Relationships the graph states beyond what the included
  models declare are listed as not modelled, never followed.
- **An in-process worker pool.** 2 executions at once and 8 waiting per API process; a
  stopped server's executions are marked failed, not resumed; the page polls. Run one API
  process: a second one's start-up recovery would mark the first one's running executions
  interrupted (they stop and store nothing; no final execution changes).

## Financial Intelligence (Phase 6)

The module's own list is in [intelligence/limitations.md](intelligence/limitations.md). In
short:

- **No real observations yet.** The World Bank was unreachable where RUMIN was built, so every
  observed-data finding shown so far (changes, revisions, trends, volatility, unusual moves,
  model interpretations) was produced from SYNTHETIC test values, labelled as such.
- **Assumed exposure, never size.** Every exposure relationship in the sample is a model
  assumption, so every exposure finding is graded *assumed*. The graph says that a company is
  exposed, never how much.
- **Descriptive statistics only.** Trends, volatility and unusual moves describe the stored
  history, are not forecasts, and are not corrected for testing many series at once. The trend
  test's assumptions rarely hold for economic series.
- **A fixed set of 19 rules.** Nothing is said outside them. There is no ranking, no score and
  no recommendation; next steps are analytical checks.
- **Bounded workspace.** The first 200 companies by name; beyond that the coverage says it is
  truncated. A dossier has no such limit.
- **Stored analyses are append-only**, with no retention or deletion until authentication
  exists, and their fingerprint marks them stale conservatively.

## AI Analyst (Phase 7)

The module's own list is in [analyst/limitations.md](analyst/limitations.md). In short:

- **No language model has been measured.** No API key was available where RUMIN was built, so
  the optional Claude provider is tested only through the real SDK against a mocked transport.
  By default RUMIN's grounded composer answers, and a model is held to the same check.
- **It reads the phrasings it was written for.** The grounded composer understands 24 kinds of
  question about the names RUMIN holds; others are asked to be clarified or answered as outside
  RUMIN's records. The reading is always shown, but a misreading is possible.
- **Figures are checked, words less so.** Every figure, date and version must be in the
  evidence it cites and forbidden phrasing is refused, but a model could still misdescribe
  evidence in words without figures ("the largest").
- **No computation of its own**: no totals, weightings, conversions or forecasts; answers are
  about the illustrative network and whatever data is stored (SYNTHETIC values where RUMIN was
  built).
- **Conversations are open to anyone who can reach the API** until authentication (Phase 10),
  and the worker pool and token budget are per API process.

## 3D universe (Phase 8)

The module's own list is in [universe/limitations.md](universe/limitations.md). In short:

- **Measured on software WebGL only.** No GPU was available where RUMIN was built; frame
  times on real hardware have not been recorded.
- **The whole build is drawn only up to 500 nodes and 2,500 edges**; larger builds start from
  a search and grow by neighbourhoods. The layout runs on the main thread (about 0.5 s at the
  budget in this environment).
- **One overlay at a time**, showing an execution's modelled pathway and line results;
  records an overlay mentions but the current view lacks are counted, not fetched.
- **Keyboard selection on the canvas covers nodes**; relationships are reached through the
  node panel and the list. No screen-reader session with a user has been run.

## Product

- **Deterministic results on stated inputs.** The Simulation page runs one model at a time;
  the Scenario Lab composes the five registered models for one company. Every figure comes
  from the user's figures and the models' stated assumptions; no result is a forecast
  ([above](#simulation-phase-4), [the Lab](#scenario-lab-phase-5)).
- **Illustrative network.** The 12 companies are fictional. The 41 relationships are
  modelling assumptions written for demonstration, each with a rationale, none estimated
  or validated. Do not use them to reason about real companies or markets.
- **Graph analytics are limited on purpose.** The knowledge graph (Phase 3) offers
  neighbourhoods, shortest paths in hops, components, degree and density. There is no
  centrality, no weighted path and no community detection, and effects are propagated
  only by the simulation engine, along relationships its model declares:
  see [above](#knowledge-graph-phase-3).
- **Small-graph rendering.** The 2D views use SVG and a synchronous layout, right for tens
  to a few hundred nodes; the 3D universe (Phase 8) renders with WebGL but still lays out on
  the main thread.
- **English only**, no localisation; numbers use an English locale format.

## Platform

- **No authentication or authorisation.** Anyone who can reach the API can read all data,
  save scenarios, execute them, add simulation runs, store analyses, and read, ask in and
  delete AI Analyst conversations. Local use only until Phase 10. For the same reason ingestion cannot
  be started over HTTP. See [security.md](security.md).
- **No inbound rate limiting, audit log or backups.** Outbound requests to providers are
  throttled; the API itself is not.
- **Not containerised.** `docker-compose.yml` provides PostgreSQL only. Deployment is
  Phase 10.

## Verification (general)

- **No automated browser end-to-end, visual-regression or screen-reader tests.** Pages
  were checked in Chromium at desktop and phone sizes in both themes (the graph explorer
  also at tablet size, with a scripted walk-through that is not part of CI); behaviour is
  covered by the jsdom suite and the live integration suite.
- **Browsers:** developed and checked in Chromium only.
- **No load testing** (concurrent users), including of the AI Analyst's pool. The knowledge
  graph, the Scenario Lab and Financial Intelligence were benchmarked on one machine, the graph and the intelligence reads on
  synthetic networks of up to 20,000 companies ([graph](graph/performance.md),
  [Lab](scenario-lab/performance.md), [intelligence](intelligence/performance.md)).

## Repository

- **No licence file.** The owners need to choose one; until then all rights are reserved.
