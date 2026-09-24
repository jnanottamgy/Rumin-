# Changes and interpretation

*What changed?* has four answers in RUMIN, and they are kept apart everywhere they appear:
changes in **observed** data, **revisions** of observed data, changes in **RUMIN's own
records** (the knowledge graph), and changes between **simulated** results. A fifth thing
is not a change at all: the **model interpretation** of an observed change, which is
computed on request and labelled as such. `GET /intelligence/changes` returns the first
four, each in its own list, with notes that say what each is.

## Observed changes

Computed in `backend/app/intelligence/series.py` from the **current** stored values: the
latest revision of each period, with its provenance down to the dataset, ingestion job and
captured response (Phase 2).

- A change is computed only between **consecutive** periods of a series, or consecutive
  closes of one price dataset. A gap breaks the chain, and missing values are never treated
  as zero.
- It is **relative** (percent of the earlier value, which must be positive) for `level` and
  `exchange_rate` series and for prices. It is a difference in **percentage points** for
  `change`, `rate` and `ratio` series, whose values are already percentages.
- A change is **detected** when |change| is at least its threshold: `relative_change_percent`
  (5 %), `point_change` (1 point) or `price_move_percent` (5 %). Only changes in the latest
  window are tested (5 years, 8 quarters, 12 months or 20 trading days by default).
- A change involving a value that ingestion flagged with a quality warning is marked
  `flagged`.
- Every change reports both values as published, both periods, its unit, the threshold it
  met, and the provenance of both values.

Rule **D01** turns the latest change into a finding when it meets its threshold. **D02**
adds, in the workspace, which companies the graph states are exposed to the variable the
series measures. It names who is exposed and says explicitly that it does not say the change
affected them. **D03–D05** report the anomaly, trend and volatility signals
([signals](signals.md)).

## Revisions

Phase 2 never overwrites a value: a revision is a new row, and the old one is kept as
superseded. `revisions()` reads, for each series, the latest 50 pairs of a superseded value
and the value that replaced it, with both revision numbers, when the revision arrived, and
its size (relative or in points, as for changes). **D06** reports up to five per series:
*"The provider revised … for 2024 from 83.7 INR per USD to 84.2 INR per USD (+0.60 %).
Both values are kept."* It suggests `review_revision`: check whether analyses that used
the earlier value need redoing. A stored analysis that read the earlier value reports
itself stale ([stored analyses](stored-analyses.md)).

## Relationship changes

`graphchanges.py` compares the latest completed build with the one before it. Each edge
records the build that added it (`first_build_id`), last changed it (`changed_build_id`) and
retired it (`retired_build_id`), so no stored diff is needed. At most 500 changes per build
are read. **G01** reports those that matter for exposure (`affects_*`, `influences`,
`in_industry`, `supplies_to`, `lends_to`).

These are changes in **RUMIN's records**, such as a relationship added to the sample or a
price file imported, not observed changes in the economy. A build keeps only an edge's
current content, so a *changed* edge can be named but its earlier attributes cannot be
shown. The response says so.

## Execution changes

For each listed company, the latest completed execution is compared with the newest earlier
completed execution **of the same scenario**, which may be of another version, on the
headline line. The comparison looks at the company's latest 20 executions. The response gives
both executions (with their versions), both changes and the difference, labelled simulated
and not a forecast. **S05** reports it in the dossier. Executions of different scenarios are
never compared: their changes, figures or models differ, so the difference would not
isolate anything. Between two versions of one scenario, the difference is the effect of
whatever the new version changed; the Scenario Lab's comparison shows what that was.

## Model interpretation (S06)

*What would the stored scenario's models say about the change just observed?*

For a company with a stored execution, the latest observed change of each series recorded
as a related measure of a variable that the execution changes is applied **alone** to the
stored scenario version. It uses the same company, figures, timing, models and assumptions.
The Lab's planner and models run it as a **preview**: computed on request and **never
stored**. `interpretation.py` builds it and rule **S06** reports it.

It is an interpretation, never an observation, and the finding says so in its statement,
its limitations and its chain:

1. the two observations and the observed change (observed);
2. the `related_measure_of` edge, with the curator's stated difference between the series
   and the variable, for example *"an annual average of the official exchange rate, not the
   same measure: the variable is defined as a daily market rate"*;
3. how it was applied (an assumption step), rounded to the four decimals the Lab accepts,
   with the rounding shown;
4. the preview run and its models (a simulation step, *not stored*).

A change is applied only when its measure matches the scenario's change type: a relative
change to a percent change, points to a change in points. Otherwise it is listed under
`not_interpreted` with the reason. The possible reasons are that the scenario does not change
this variable, that the series is measured differently from the scenario's change, that the
change rounds to zero at four decimals, that the scenario's models cannot run it, or a
numerical refusal. The change is applied as a step for the scenario's timing, which assumes
it holds over the simulated months. The finding lists that as a limitation.

Example (SYNTHETIC values): the observed +9.38 % in INR per US$ (84.2 → 92.1), applied alone
as +9.38 % to USD/INR in "Oil, rupee and rates on Aerisca", gives *operating profit
−1,032,064 INR (−2.06 %) over 12 months* through `airline_fuel_cost` 1.1.0 and
`fx_exposure` 1.0.0. The headline is operating profit, not profit before tax, because no
interest model applies without a rate change.

In the interface, the dossier's History tab shows observed data first. The interpretation
sits apart, under its own heading: *Model interpretation, computed on request. Not stored,
not an observation, not a forecast.*
