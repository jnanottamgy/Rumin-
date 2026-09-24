# Limitations

What Financial Intelligence does not do, and what its findings cannot support. Each finding
also carries its own limitations. This page covers the layer as a whole.

## The data it has

- **No real observations were available where it was built.** The catalogue lists 11 World
  Bank series, but the World Bank API is blocked by this environment's network policy, as in
  Phases 2–5. Every observed-data finding shown in the tests, fixtures and documentation
  (D01–D06, S06) was produced from **SYNTHETIC** values stored through the real ingestion
  pipeline, and is labelled as such. The code paths are exercised end to end; the findings
  about India's exchange rate and inflation are not real.
- **Annual series only.** The catalogue holds annual series, so windows are years (5 by
  default). The anomaly signal needs 10 consecutive annual values (the latest change and 8
  earlier ones), and volatility needs 14 (a 5-change window and 8 earlier windows). Monthly
  or daily market data would need a licensed source (see the [roadmap](../roadmap.md)).
- **Related series are not the variables.** A World Bank annual average is recorded as a
  *related measure* of a variable defined as a daily market rate or a monthly index, and the
  curator's stated difference is shown with every finding that uses it. S06 applies such a
  change to the variable, which is an interpretation and is labelled as one.

## Exposure

- **Every exposure relationship in the sample is a model assumption.** On the sample network,
  every exposure finding is graded *assumed*, and the `evidence_backed` filter returns
  nothing. This is the honest state of illustrative data, not a defect of the grading.
- **Exposure is not size.** The graph states that an entity is exposed, never how much.
  Breadth and dependency count relationships, not money. Sizes exist only in simulations,
  with figures the user typed.
- **Only what the graph records.** An exposure the graph does not state is invisible, and
  C01 says when a simulation covers a variable without a stated exposure. Upstream
  transmission is followed for at most two `influences` hops.
- **The workspace lists the first 200 companies by name.** Beyond that, the coverage says it
  is truncated, and X01 and D02 say that their counts cover the listed companies only. A
  dossier has no such limit, and a variable's reach is searched through the whole graph (the
  first 200 of the companies reached are listed, with the total). Industries are listed up
  to 200.

## Statistics

- **Descriptive, not predictive.** Trends, volatility and unusual changes describe the stored
  history, and none is a forecast.
- **The trend test's assumptions rarely hold.** It assumes independent, normally distributed
  residuals, which economic series (autocorrelated, trending, with breaks) often violate. A
  called trend describes its window. Small windows (the default 5 annual values) have little
  power.
- **No correction for multiple tests.** Each series is tested on its own at the chosen level.
  Across many series, some trends will be called by chance: at 5 %, about one in twenty
  series with no trend at all. The level is shown with every trend, and it can be lowered
  (0.01).
- **Volatility windows overlap** and are not independent, so the percentile is descriptive.
  Volatility is compared with the series' own past only.
- **No seasonal adjustment**, and changes are between consecutive periods, not year on year.
  This matters for sub-annual data, which RUMIN does not yet hold.
- **Thresholds apply to the whole request.** There are no per-series or per-entity
  thresholds.

## Simulations

- **Conditional, not forecasts.** Every simulated finding holds only under its scenario's
  changes, figures and assumptions. The figures are typed by the user, and the models'
  parameters have never been estimated from data or back-tested (Phases 4–5).
- **The latest execution only.** A dossier's drivers come from the entity's latest completed
  execution, compared with the previous execution of the same scenario. Earlier executions
  are listed but not analysed. The workspace shows each listed company's latest execution.
- **Shapley splits interactions evenly** between the changes involved. Effects per unit are
  averages over the scenario's change, not slopes. Ratios are not attributed.
- **S06 applies one observed change as a step** for the scenario's timing. It assumes the
  change holds over the simulated months and ignores every other change in the scenario.
- **No second-round effects**: the layer reads what the models computed and adds no
  behaviour of its own.

## Rules and next steps

- **A fixed catalogue of 19 rules.** A statement no rule makes is not made. There is no free
  text, no summarisation and no language model.
- **No ranking and no recommendations**, by design. The order is by kind of knowledge, and
  next steps are analytical checks (simulate, find evidence, retrieve data, run a
  sensitivity analysis, review a revision), never investment actions.
- **Relationship changes compare the latest two builds only.** A changed edge can be named,
  but its earlier attributes cannot be shown.

## Stored analyses

- **Append-only, with no retention or deletion.** Each snapshot is 100–220 KB of JSON. Deleting
  them needs an authorised owner and an audit record (Phase 10).
- **The fingerprint is conservative.** Any new value in a series the analysis read, any new
  execution in the workspace, or a rebuilt graph marks a stored analysis stale, even if
  recomputing it would give the same findings. It says *what* changed, not whether the
  findings did.

## Operation

- **Every read recomputes.** Nothing is cached between requests. An overview takes about
  0.3 s from 1,000 to 20,000 companies, and a dossier about 30 ms ([performance](performance.md)).
- **No authentication and one API process**, as for the rest of RUMIN.
- **No browser end-to-end tests in CI.** The interface is covered in jsdom against fixtures
  captured from a real backend, the live API by the integration suite, and the pages were
  checked by hand in Chromium.
- **The brief has no consumer yet.** It is designed for the Phase 7 AI Analyst, and nothing
  in Phase 6 phrases it.
