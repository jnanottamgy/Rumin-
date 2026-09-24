# Signals, statistics and thresholds

A **signal** answers one question with a documented calculation and reports the quantities
it computed. It is not a score, and there is no composite score anywhere in RUMIN. Where a
signal names a level (*rising*, *high*, *unusual*, *concentrated*), a configurable threshold
decides it, and that threshold is recorded with the result. When the data are too short or
the calculation is undefined, the signal says so instead of guessing. The definitions are in
`backend/app/intelligence/signals.py`, the statistics in `stats.py` and `series.py`, and the
thresholds in `thresholds.py`. `GET /intelligence/methods` serves all three.

Every signal carries its definition, method, inputs (with references), period, evidence
(observed for data signals; the grade of the exposure paths or the stored execution for
entity signals), limitations and the thresholds it used.

## The six signals

| Signal | Subjects | Question | Levels |
|---|---|---|---|
| **Exposure breadth** | company, industry | How many economic variables reach this entity through validated relationships? | none: counts by channel (costs, revenue, financing), directness (direct, via the industry, upstream) and evidence status |
| **Dependency** | company, industry | Do the entity's stated exposures depend on one variable? | *concentrated* when the largest share of paths through one variable is at least `dependency_share_percent`; otherwise *spread* |
| **Trend** | series, instrument | Has the series been rising or falling over the latest window? | *rising*, *falling*, *no clear direction*, *on a straight line* |
| **Volatility** | series, instrument | Is the series moving more than it usually does? | *high*, *not high*, *too little history* |
| **Unusual change** | series, instrument | Is the latest change unusual against the series' earlier changes? | *unusual*, *not unusual*, *undefined*, *too little history* |
| **Scenario sensitivity** | company | In the latest stored execution, which change moves the result most, and by how much per unit? | none: contributions, shares and effects per unit ([drivers](drivers.md)) |

**Limitations.** Each signal states its own. Exposure breadth and dependency count
relationships, not money: two exposures with equal counts can differ by orders of magnitude,
and an exposure the graph does not record is invisible. A trend describes its window and is
not a forecast. Volatility compares a series with its own past only. An unusual change is not
a wrong one: a real event can produce it, and data quality is judged separately by the
ingestion rules. Effects per unit are averages over the scenario's change, not slopes.

## The statistics

All calculations are exact decimal arithmetic (34 significant digits, half-even), on the
**current** stored values: the latest revision of each period. Missing values are skipped,
never treated as zero.

**Changes.** A change is computed only between **consecutive** periods of a series, or
consecutive bars of one price dataset. A gap breaks the chain. How a change is measured
depends on what the series measures (`measure_type`, Phase 2):

| Series | Change | Unit |
|---|---|---|
| `level`, `exchange_rate`, and prices | (later − earlier) ÷ earlier × 100, only when the earlier value is positive | percent |
| `change`, `rate`, `ratio` (already in percent) | later − earlier | percentage points, never a percent of a percent |

**Least-squares trend.** Over the latest window of *n* ≥ 3 values, *y* against *x* = periods
since the window's first value (so a gap keeps its spacing):

- slope *b* = Σ(x − x̄)(y − ȳ) ÷ Σ(x − x̄)²;
- standard error of the slope = √((SSE ÷ (n − 2)) ÷ Σ(x − x̄)²), where SSE is the sum of
  squared residuals;
- *t* = *b* ÷ standard error.

A direction is called only when |t| exceeds the **two-sided critical value of Student's t**
with n − 2 degrees of freedom at the chosen level (0.10, 0.05 or 0.01). The critical values
come from the standard published table (three decimals, 1–30, 40, 60 and 120 degrees of
freedom). Between two rows the lower row is used, because its value is larger. Beyond 120
the 120 row is used. A test is therefore never less strict than stated. If every value lies
on the line, there is no *t*: a non-zero slope is reported *on a straight line*, and a flat
line has no clear direction. For relative series the slope is also given as a percentage of
the window's mean.

**Volatility.** The sample standard deviation (n − 1) of the changes in the latest window,
ranked among the standard deviations of every earlier window of the same length (overlapping,
each starting one change earlier) together with the latest one. The percentile is the share
of those windows at or below the latest. The level is *high* when the percentile is at least
`volatility_high_percentile`. With fewer than `min_history` earlier windows the level is
*too little history*.

**Unusual change.** The modified z-score of the latest change against all earlier changes
(Iglewicz and Hoaglin, 1993): M = 0.6745 × (x − median) ÷ MAD, where MAD is the median
absolute deviation of the earlier changes. The median and MAD are robust: one earlier
extreme change does not hide the next. The level is *unusual* when |M| is at least
`anomaly_score`. It is *undefined* when MAD is zero (for example, when every earlier change
was equal), and *too little history* with fewer than `min_history` earlier changes.

Hand-checked values in `test_intelligence_core.py` pin the least-squares slope, standard
error and *t*, the critical-value lookup, the median, MAD, modified z-score and percentile
rank, and both kinds of change.

## Thresholds

Thresholds are configuration, not claims. Each has a documented default and a reason, can be
overridden per request within bounds, and is recorded in every result that used it, so a
reader can see which test a finding passed and repeat it with another value.

| Name | Label | Unit | Default | Allowed | Why this default |
|---|---|---|---|---|---|
| `relative_change_percent` | Change in a level or exchange rate | percent | 5 | 0.1–100 | A round, deliberately high default for annual averages, so that only large movements are reported. It filters for attention and does not say that smaller changes do not matter. |
| `point_change` | Change in a rate or a percentage | percentage points | 1 | 0.01–50 | Series already in percent (inflation, growth, interest rates, shares of GDP) are compared in points, never in percent of themselves. One point is a round default for annual data. |
| `price_move_percent` | Move in a daily close | percent | 5 | 0.1–100 | Day-to-day moves of 5 % or more. Ingestion already flags moves above 40 % as possible data errors; this threshold is for attention, not quality. |
| `anomaly_score` | Unusual change (modified z-score) | score | 3.5 | 1–10 | Iglewicz and Hoaglin recommend treating modified z-scores above 3.5 as potential outliers. |
| `trend_significance` | Trend test level | probability | 0.05 | 0.10, 0.05 or 0.01 | The test assumes independent, normally distributed residuals. Economic series often violate this, so a called trend describes the window, not a law. |
| `volatility_high_percentile` | High volatility | percentile | 80 | 50–100 | Volatility is compared with the series' own history. |
| `dependency_share_percent` | Concentrated dependency | percent | 50 | 10–100 | It counts relationships, not money. |
| `min_history` | Changes needed for a baseline | count | 8 | 4–200 (integer) | With fewer earlier changes (or windows), anomaly and volatility are not computed, and the result says so. |
| `window` | Window (periods) | periods | by frequency | 3–250 (integer) | Left empty: 5 years, 8 quarters, 12 months or 20 trading days. |

**Overriding.** On reads, thresholds are query parameters (for example
`GET /intelligence/overview?relative_change_percent=3&trend_significance=0.10`). On a stored
analysis they go in the body's `thresholds` object, with at most 20 entries, and a problem is
reported with the location `body` and the field `thresholds.<name>`. Every problem is
reported at once, as a 422:

```json
{"error": {"code": "validation_error", "message": "Some thresholds are invalid.",
  "details": [{"location": "query", "field": "relative_change_percent",
               "message": "Change in a level or exchange rate must be between 0.1 and 100 (percent).",
               "type": "invalid_threshold"}]}}
```

In the web app the thresholds panel is built from the API's own specification (label, unit,
range, default and reason). The overrides live in the URL, so a view with its thresholds can
be linked, and a refusal is shown beside its field.
