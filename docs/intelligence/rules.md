# Insight rules

An insight is produced by a numbered rule. The rule tests a condition on findings and
signals, fills a sentence template with the computed values, and attaches the evidence
chain, facts, entities, relationships, period, models, assumptions, limitations, sources
and next steps. Rules never add a causal claim, a forecast or a recommendation. The code is
in `backend/app/intelligence/insights.py`, and `GET /intelligence/methods` lists every rule
with its purpose.

## The 19 rules

**Observed data**: from stored values, graded *observed*, except D02.

| Rule | Kind | Produced when | Chain | Scope |
|---|---|---|---|---|
| **D01** Observed change | `change` | the **latest** change of a series or instrument meets its threshold | two observations → the change (calculation) → the threshold | both |
| **D02** Observed change on an exposure variable | `exposure_change` | a D01 change on a series recorded as a related measure of a variable that the graph states reaches companies | D01's steps → the series' `related_measure_of` edge → the exposure edges to each company | workspace |
| **D03** Unusual change | `anomaly` | the anomaly signal is *unusual* | the stored changes → the modified z-score → the threshold | both |
| **D04** Trend | `trend` | the trend signal is *rising* or *falling* | the window's values → slope and *t* → the critical value at the chosen level | both |
| **D05** High volatility | `volatility` | the volatility signal is *high* | the changes → the standard deviations of every window → the percentile threshold | both |
| **D06** Data revision | `revision` | the provider replaced a stored value (at most 5 per series) | both revisions → the size of the revision | both |

D02 names the companies and says that it *does not* say the change affected them. Its grade
is that of its weakest edge (*assumed* on the sample).

**Simulations**: from stored Scenario Lab executions. Every one is marked conditional on a
simulation and says it is not a forecast.

| Rule | Kind | Produced when | Chain | Scope |
|---|---|---|---|---|
| **S01** Simulated impact | `impact` | a company has a completed execution with a headline line | the exposure edges from the changed variables to the company → the entered figures (assumption) → the stored execution and its runs | both |
| **S02** Contributions to a line | `contribution` | a line changed and has stored contributions | the stored contributions → shares of the change and points of the baseline (calculation) → the entered figures | entity |
| **S03** Effect per unit of a change | `sensitivity` | each change with a contribution to the headline | the stored contribution → contribution ÷ size of the change → the entered figures | entity |
| **S04** Largest sensitivity | `sensitivity` | a stored sensitivity analysis exists for the latest execution | the stored analysis → the largest spread | entity |
| **S05** Change between executions | `scenario_change` | the latest and the previous execution of the same scenario share a headline line | both executions → the difference | entity |
| **S06** Observed change through the models | `interpretation` | a related series' latest change can be applied to a variable the latest execution changes | two observations → the change → the `related_measure_of` edge → how it was applied (assumption) → a preview run, **not stored** | entity |

The headline line is the first of profit before tax, operating profit, operating costs and
revenue that the execution reports. S01 includes the exposure edges because the models
apply through them (the Lab's rule), so on the sample network S01 is graded *assumed*, with
its figures marked simulated. S06 is a **model interpretation**, labelled as such wherever
it appears ([changes](changes.md#model-interpretation-s06)).

**Relationships and exposure**: from the knowledge graph. Each is graded by the weakest
evidence status on its paths.

| Rule | Kind | Produced when | Chain | Scope |
|---|---|---|---|---|
| **G01** Relationship change | `relationship_change` | the latest completed build added, changed or retired an exposure-relevant edge (`affects_*`, `influences`, `in_industry`, `supplies_to`, `lends_to`), compared with the build before | the build record → the edge | workspace |
| **X01** Shared driver | `cross_entity` | a variable reaches two or more listed companies | the build → every edge on every company's paths from the variable | workspace |
| **E01** Stated exposure | `exposure` | one per variable that starts a path to the entity | the build → the path's edges (direct, via the industry, upstream) | entity |
| **E02** Concentrated dependency | `dependency` | the dependency signal is *concentrated* (at least 50 % of paths through one variable by default) | the build → the paths → the share (calculation) → the threshold | entity |
| **E03** Supply and credit relationships | `counterparty` | the entity has `supplies_to` or `lends_to` edges | the build → each edge, with the registry's caveat | entity |

X01 is capped at the 12 variables that reach the most companies (ties by name). The
exposure matrix still shows every variable. On the sample, the seven variables that reach
two or more companies each give one finding. X01 and D02 count among the companies the
workspace lists. When the listing is truncated, their headlines say *of the listed
companies*, and a limitation says the graph holds more.

**Coverage**: what RUMIN can and cannot say. Graded *observed*: the chain consists of RUMIN's
own records.

| Rule | Kind | Produced when | Chain | Scope |
|---|---|---|---|---|
| **C01** What is and is not covered | `coverage` | the entity has at least one exposure path | the build → the latest execution's changes and models | entity |
| **C02** Stored data | `coverage` | always | the data catalogue | workspace |

C01 counts the variables reaching the entity, how many the latest execution simulated, how
many a registered model can simulate, and how many have stored observations of a related
series. It also names any variable an execution simulated **without** a stated exposure.
In that case the result rests on the entered figures alone. C02 says how many series and
instruments have enough values to analyse and what cannot be computed without them.

## Order

Findings are listed in a fixed order of kinds (`KIND_ORDER`), new information first:

1. observed data: `anomaly`, `change`, `exposure_change`, `revision`, `trend`, `volatility`;
2. simulations: `impact`, `interpretation`, `contribution`, `sensitivity`, `scenario_change`;
3. relationships and exposure: `relationship_change`, `cross_entity`, `exposure`,
   `dependency`, `counterparty`;
4. `coverage`.

Within a kind, findings are sorted by rule and then alphabetically by headline, so the order
is stable. Nothing is ordered by size or by grade: the order says what kind of knowledge a
finding is, not how important it is.

## Next steps

A rule may attach **next steps**: analytical checks, never advice. Each names an action and,
where there is one, its target.

| Action | Suggested by | Meaning |
|---|---|---|
| `run_template` | E01 | a Scenario Lab template changes this variable with a model that covers this exposure: *Simulate it: start the “…” template for …* |
| `model_gap` | E01 | no registered model simulates how the variable reaches the entity, so its size cannot be simulated yet |
| `find_evidence` | E01 | quotes every relationship on the exposure that is recorded as a model assumption, and targets the first: look for a cited source before relying on them |
| `ingest_series` | E01, C02 | a series recorded as a related measure has no stored values: retrieve it |
| `run_scenario` | C01 | no execution is stored for the entity: run a scenario to size its exposures |
| `run_sensitivity` | S01, C01 | the latest execution has no sensitivity analysis |
| `review_revision` | D06 | check whether analyses that used the earlier value need redoing |

The overview, the dossier and the brief gather the distinct next steps of their findings.
The same check on the same record is listed once: S01 and C01 share one sensitivity step.

## Adding a rule

A new rule needs an id and purpose in `RULES` and a kind in `KIND_ORDER`. It builds its
insight through `InsightDraft`, whose `build` refuses a missing chain. It needs a test
through the API: `assert_grounded` checks the grade, the conditional flag, the not-a-forecast
limitation and the forbidden words for every insight returned. It must also be documented
on this page.
