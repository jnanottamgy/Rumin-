# Data-quality rules

Every record RUMIN ingests is checked. The rules are defined once, in
`backend/app/ingestion/quality.py` (`RULES`), served by the API
(`GET /api/v1/data-quality/rules`) and listed here.

## The principle

**Structural problems reject; plausibility problems flag; nothing is ever corrected.**

| Outcome | Severity | What happens to the record |
|---|---|---|
| **Rejected** | error | Not stored as data. The issue keeps the record exactly as the source sent it (`raw_record`), with the reason, so nothing disappears silently |
| **Flagged** | warning | Stored **exactly as reported**, with quality status `warning`, and linked to an issue for review |
| **Noted** | info (or warning, for whole-series findings) | Stored; the note is informational |

A flagged value is not "wrong": it is unusual by a rule RUMIN chose (for example, a review
range, which is an **assumption**). No workflow exists yet to review issues: every issue's
review status is `unreviewed`.

## The rules

| Rule | Applies to | Severity | Outcome | What it checks |
|---|---|---|---|---|
| `series_mismatch` | economic | error | rejected | The record names a different series or country than the one requested. |
| `invalid_period` | economic | error | rejected | The period is missing or not a recognised period (e.g. 2023, 2023Q1, 2023M03). |
| `frequency_mismatch` | economic | error | rejected | The period's frequency differs from the series' declared frequency. |
| `future_period` | economic | error | rejected | The period has not started yet, so the value cannot be an observation. |
| `duplicate_period` | economic | error | rejected | The same period appears twice in one response; the first is kept. |
| `missing_field` | price | error | rejected | A required column (date, open, high, low, close) is empty. |
| `invalid_date` | price | error | rejected | The date is not a real YYYY-MM-DD calendar date. |
| `future_date` | price | error | rejected | The trade date is in the future. |
| `duplicate_date` | price | error | rejected | The same trade date appears twice in one file; the first is kept. |
| `invalid_number` | both | error | rejected | A value is not a plain, finite number (no separators, symbols or text). |
| `precision_exceeded` | both | error | rejected | A value has more digits than RUMIN stores exactly; it is refused rather than rounded. |
| `non_positive_price` | price | error | rejected | A price is zero or negative. |
| `high_below_low` | price | error | rejected | The day's high is below its low. |
| `invalid_volume` | price | error | rejected | Volume is not a whole, non-negative number. |
| `outside_review_range` | economic | warning | flagged | The value is outside RUMIN's review range for the series (an assumption, not a fact). |
| `non_positive_level` | economic | warning | flagged | A level or exchange rate is zero or negative. |
| `period_in_progress` | economic | warning | flagged | The period has not ended, so the value may be provisional or partial. |
| `outside_high_low` | price | warning | flagged | The open or close lies outside the day's high-low range. |
| `weekend_date` | price | warning | flagged | The trade date is a Saturday or Sunday (some exchanges hold special sessions). |
| `large_price_move` | price | warning | flagged | The close moved more than 40% from the previous close: possibly a corporate action (split, bonus) or an error. RUMIN does not adjust prices. |
| `provider_flag` | economic | info | noted | The provider attached a flag to the value (e.g. an estimate). |
| `provider_unit` | economic | info | noted | The provider reports a unit in its records; compare it with the catalogue's unit. |
| `missing_values` | economic | info | noted | The provider listed periods without a value inside the reported range. RUMIN records them as missing and never fills them in. |
| `recent_periods_without_values` | economic | info | noted | The latest periods were listed without values (usually a publication lag). |
| `zero_volume` | price | info | noted | Volume is zero: no trades were reported that day. |
| `empty_response` | economic | warning | noted | The provider returned no records for the requested period range. |
| `no_reported_values` | economic | warning | noted | Every period returned was without a value. |
| `unexpected_gap` | economic | warning | noted | Periods inside the returned range were not returned at all. |
| `empty_file` | price | warning | noted | The file has a header but no data rows. |
| `trading_gap` | price | warning | noted | More than 7 calendar days pass between consecutive trade dates. |

## Parsing rules behind them

Normalisation (`app/ingestion/normalize.py`) refuses anything ambiguous instead of
guessing:

- **Numbers from JSON** must already be decimals (the parser reads them as `Decimal`); a
  string, boolean or float is `invalid_number`.
- **Numbers from files** must be plain decimals: `1234.5` or `-0.25`. Thousands separators
  (`1,234.5`), currency symbols (`₹100`), exponents (`1e5`) and decimal commas (`1234,5`)
  are refused — their meaning varies by locale.
- **Precision:** values must fit `NUMERIC(38, 18)` (20 digits before the point, 18 after).
  Trailing zeros are not counted (`5.100` is 5.1). A value that does not fit is refused,
  never rounded.
- **Dates** must be ISO `YYYY-MM-DD`; `03/04/2024` means March in one country and April in
  another, so it is refused.
- **Periods** must match the series' frequency: `2023` (annual), `2023Q1`, `2023M03`.
- **Identifiers:** ISINs are checked against their check digit; exchange codes must be ISO
  10383 MICs (four characters); currencies ISO 4217 codes.

## What quality status means on a stored value

| `quality_status` | Meaning |
|---|---|
| `validated` | Stored; passed every rule that can flag it |
| `warning` | Stored exactly as reported; at least one rule flagged it (see its issues) |

A value is re-assessed each time it is received again, with the rules in force then.
Issues are recorded per run, so re-running records them again for that run.
