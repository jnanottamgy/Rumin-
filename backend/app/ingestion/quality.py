"""Data-quality rules.

Principle: **structural problems reject; plausibility problems flag.** A record that cannot
be what it claims to be (an unparseable number, a period of the wrong frequency, a high
below the low) is rejected and kept only as an issue with its raw content. A record that
is well-formed but unusual (outside a review range, a possible corporate action) is stored
exactly as reported and flagged for review. RUMIN never corrects a value.

Every rule is listed in ``RULES`` with its severity and outcome; the API exposes the list
and ``docs/data-quality.md`` explains each one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Any, Literal

from app.domain.enums import (
    Frequency,
    IssueOutcome,
    IssueSeverity,
    MeasureType,
    ObservationStatus,
    QualityStatus,
)
from app.ingestion.normalize import (
    NormalizationError,
    Period,
    parse_decimal_text,
    parse_iso_date,
    parse_provider_number,
    parse_provider_period,
    parse_volume,
    periods_between,
)
from app.ingestion.providers.base import RawObservation, RawPriceRow

ERROR, WARNING, INFO = IssueSeverity.ERROR, IssueSeverity.WARNING, IssueSeverity.INFO
REJECTED, FLAGGED, NOTED = IssueOutcome.REJECTED, IssueOutcome.FLAGGED, IssueOutcome.NOTED


@dataclass(frozen=True)
class Rule:
    code: str
    applies_to: Literal["economic", "price", "both"]
    severity: IssueSeverity
    outcome: IssueOutcome
    description: str


RULES: dict[str, Rule] = {
    rule.code: rule
    for rule in [
        # Structural: the record is rejected.
        Rule(
            "series_mismatch",
            "economic",
            ERROR,
            REJECTED,
            "The record names a different series or country than the one requested.",
        ),
        Rule(
            "invalid_period",
            "economic",
            ERROR,
            REJECTED,
            "The period is missing or not a recognised period (e.g. 2023, 2023Q1, 2023M03).",
        ),
        Rule(
            "frequency_mismatch",
            "economic",
            ERROR,
            REJECTED,
            "The period's frequency differs from the series' declared frequency.",
        ),
        Rule(
            "future_period",
            "economic",
            ERROR,
            REJECTED,
            "The period has not started yet, so the value cannot be an observation.",
        ),
        Rule(
            "duplicate_period",
            "economic",
            ERROR,
            REJECTED,
            "The same period appears twice in one response; the first is kept.",
        ),
        Rule(
            "missing_field",
            "price",
            ERROR,
            REJECTED,
            "A required column (date, open, high, low, close) is empty.",
        ),
        Rule(
            "invalid_date",
            "price",
            ERROR,
            REJECTED,
            "The date is not a real YYYY-MM-DD calendar date.",
        ),
        Rule("future_date", "price", ERROR, REJECTED, "The trade date is in the future."),
        Rule(
            "duplicate_date",
            "price",
            ERROR,
            REJECTED,
            "The same trade date appears twice in one file; the first is kept.",
        ),
        Rule(
            "invalid_number",
            "both",
            ERROR,
            REJECTED,
            "A value is not a plain, finite number (no separators, symbols or text).",
        ),
        Rule(
            "precision_exceeded",
            "both",
            ERROR,
            REJECTED,
            "A value has more digits than RUMIN stores exactly; it is refused rather than rounded.",
        ),
        Rule("non_positive_price", "price", ERROR, REJECTED, "A price is zero or negative."),
        Rule("high_below_low", "price", ERROR, REJECTED, "The day's high is below its low."),
        Rule(
            "invalid_volume",
            "price",
            ERROR,
            REJECTED,
            "Volume is not a whole, non-negative number.",
        ),
        # Plausibility: the record is stored and flagged for review.
        Rule(
            "outside_review_range",
            "economic",
            WARNING,
            FLAGGED,
            "The value is outside RUMIN's review range for the series (an assumption, not a fact).",
        ),
        Rule(
            "non_positive_level",
            "economic",
            WARNING,
            FLAGGED,
            "A level or exchange rate is zero or negative.",
        ),
        Rule(
            "period_in_progress",
            "economic",
            WARNING,
            FLAGGED,
            "The period has not ended, so the value may be provisional or partial.",
        ),
        Rule(
            "outside_high_low",
            "price",
            WARNING,
            FLAGGED,
            "The open or close lies outside the day's high-low range.",
        ),
        Rule(
            "weekend_date",
            "price",
            WARNING,
            FLAGGED,
            "The trade date is a Saturday or Sunday (some exchanges hold special sessions).",
        ),
        Rule(
            "large_price_move",
            "price",
            WARNING,
            FLAGGED,
            "The close moved more than 40% from the previous close: possibly a corporate "
            "action (split, bonus) or an error. RUMIN does not adjust prices.",
        ),
        # Informational: noted, nothing is changed.
        Rule(
            "provider_flag",
            "economic",
            INFO,
            NOTED,
            "The provider attached a flag to the value (e.g. an estimate).",
        ),
        Rule(
            "provider_unit",
            "economic",
            INFO,
            NOTED,
            "The provider reports a unit in its records; compare it with the catalogue's unit.",
        ),
        Rule(
            "missing_values",
            "economic",
            INFO,
            NOTED,
            "The provider listed periods without a value inside the reported range. RUMIN "
            "records them as missing and never fills them in.",
        ),
        Rule(
            "recent_periods_without_values",
            "economic",
            INFO,
            NOTED,
            "The latest periods were listed without values (usually a publication lag).",
        ),
        Rule(
            "zero_volume", "price", INFO, NOTED, "Volume is zero: no trades were reported that day."
        ),
        # Whole series or file.
        Rule(
            "empty_response",
            "economic",
            WARNING,
            NOTED,
            "The provider returned no records for the requested period range.",
        ),
        Rule(
            "no_reported_values",
            "economic",
            WARNING,
            NOTED,
            "Every period returned was without a value.",
        ),
        Rule(
            "unexpected_gap",
            "economic",
            WARNING,
            NOTED,
            "Periods inside the returned range were not returned at all.",
        ),
        Rule("empty_file", "price", WARNING, NOTED, "The file has a header but no data rows."),
        Rule(
            "trading_gap",
            "price",
            WARNING,
            NOTED,
            "More than 7 calendar days pass between consecutive trade dates.",
        ),
    ]
}


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str
    record_key: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def severity(self) -> IssueSeverity:
        return RULES[self.rule].severity

    @property
    def outcome(self) -> IssueOutcome:
        return RULES[self.rule].outcome


def _quality(findings: Sequence[Finding]) -> QualityStatus:
    return (
        QualityStatus.WARNING
        if any(f.outcome is IssueOutcome.FLAGGED for f in findings)
        else QualityStatus.VALIDATED
    )


def _labels(periods: Sequence[Period], limit: int = 12) -> str:
    labels = [p.label for p in periods]
    shown = ", ".join(labels[:limit])
    return shown + (f" and {len(labels) - limit} more" if len(labels) > limit else "")


# --- Economic observations ----------------------------------------------------------------


@dataclass(frozen=True)
class SeriesExpectation:
    provider_code: str
    country_iso3: str | None
    frequency: Frequency
    measure_type: MeasureType
    unit: str
    plausible_min: Decimal | None = None
    plausible_max: Decimal | None = None


@dataclass
class CheckedObservation:
    period: Period
    value: Decimal | None
    raw_value: str | None
    status: ObservationStatus
    flags: str | None
    capture_index: int | None
    findings: list[Finding] = field(default_factory=list)

    @property
    def quality(self) -> QualityStatus:
        return _quality(self.findings)


@dataclass
class ObservationAssessment:
    accepted: list[CheckedObservation] = field(default_factory=list)
    rejected: list[Finding] = field(default_factory=list)
    series_findings: list[Finding] = field(default_factory=list)


def _check_observation(
    raw: RawObservation, expect: SeriesExpectation, today: date
) -> CheckedObservation | Finding:
    """One record: a stored observation (with any flags), or the reason it is rejected."""
    key = raw.period if isinstance(raw.period, str) else None
    original = dict(raw.original) or {"period": str(raw.period), "value": str(raw.value)}
    if raw.series_code != expect.provider_code or raw.country_iso3 != expect.country_iso3:
        return Finding(
            "series_mismatch",
            f"The record is for {raw.series_code}/{raw.country_iso3}, not "
            f"{expect.provider_code}/{expect.country_iso3}.",
            key,
            original,
        )
    try:
        period = parse_provider_period(raw.period, expect.frequency)
        value = None if raw.value is None else parse_provider_number(raw.value)
    except NormalizationError as error:
        return Finding(error.rule, error.message, key, original)
    if period.start > today:
        return Finding("future_period", f"{period.label} has not started yet.", key, original)

    findings: list[Finding] = []
    if value is not None:
        low, high = expect.plausible_min, expect.plausible_max
        if (low is not None and value < low) or (high is not None and value > high):
            findings.append(
                Finding(
                    "outside_review_range",
                    f"{value} is outside RUMIN's review range [{low}, {high}] for this "
                    "series. It is stored as reported and flagged for review.",
                    period.label,
                )
            )
        if expect.measure_type in (MeasureType.LEVEL, MeasureType.EXCHANGE_RATE) and value <= 0:
            findings.append(
                Finding("non_positive_level", f"{value} is not a positive level.", period.label)
            )
        if period.end >= today:
            findings.append(
                Finding(
                    "period_in_progress",
                    f"{period.label} ends on {period.end.isoformat()}; the value may be "
                    "provisional.",
                    period.label,
                )
            )
    flags = str(raw.flags).strip() if raw.flags not in (None, "") else None
    if flags:
        findings.append(
            Finding("provider_flag", f"The provider flagged this value: '{flags}'.", period.label)
        )
    return CheckedObservation(
        period=period,
        value=value,
        raw_value=None if value is None else str(raw.value),
        status=ObservationStatus.MISSING if value is None else ObservationStatus.REPORTED,
        flags=flags,
        capture_index=raw.capture_index,
        findings=findings,
    )


def assess_observations(
    expect: SeriesExpectation, raws: Sequence[RawObservation], today: date
) -> ObservationAssessment:
    result = ObservationAssessment()
    by_period: dict[date, CheckedObservation] = {}
    provider_units: set[str] = set()
    for raw in raws:
        checked = _check_observation(raw, expect, today)
        if isinstance(checked, Finding):
            result.rejected.append(checked)
            continue
        if checked.period.start in by_period:
            result.rejected.append(
                Finding(
                    "duplicate_period",
                    f"{checked.period.label} appears more than once; the first is kept.",
                    checked.period.label,
                    dict(raw.original) or None,
                )
            )
            continue
        if isinstance(raw.unit, str) and raw.unit.strip():
            provider_units.add(raw.unit.strip())
        by_period[checked.period.start] = checked

    result.accepted = [by_period[start] for start in sorted(by_period)]
    result.series_findings = _series_findings(expect, raws, result.accepted, provider_units)
    return result


def _series_findings(
    expect: SeriesExpectation,
    raws: Sequence[RawObservation],
    accepted: list[CheckedObservation],
    provider_units: set[str],
) -> list[Finding]:
    findings: list[Finding] = []
    if not raws:
        return [Finding("empty_response", "The provider returned no records.")]
    if not accepted:
        return findings
    reported = [o for o in accepted if o.status is ObservationStatus.REPORTED]
    if not reported:
        findings.append(Finding("no_reported_values", "No period in the response had a value."))
    else:
        first, last = reported[0].period.start, reported[-1].period.start
        inside = [o.period for o in accepted if o.value is None and first < o.period.start < last]
        trailing = [o.period for o in accepted if o.value is None and o.period.start > last]
        if inside:
            findings.append(
                Finding(
                    "missing_values",
                    f"{len(inside)} period(s) listed without a value: {_labels(inside)}.",
                    raw={"periods": [p.label for p in inside]},
                )
            )
        if trailing:
            findings.append(
                Finding(
                    "recent_periods_without_values",
                    f"The latest value is for {reported[-1].period.label}; "
                    f"{_labels(trailing)} were listed without values.",
                    raw={"periods": [p.label for p in trailing]},
                )
            )
    received = {o.period.start for o in accepted}
    expected = periods_between(accepted[0].period, accepted[-1].period)
    absent = [p for p in expected if p.start not in received]
    if absent:
        findings.append(
            Finding(
                "unexpected_gap",
                f"{len(absent)} period(s) inside the range were not returned: {_labels(absent)}.",
                raw={"periods": [p.label for p in absent]},
            )
        )
    for unit in sorted(provider_units):
        findings.append(
            Finding(
                "provider_unit",
                f"The provider reports the unit '{unit}'; the catalogue unit is '{expect.unit}'.",
            )
        )
    return findings


# --- Price bars ---------------------------------------------------------------------------

PRICE_FIELDS = ("open", "high", "low", "close")
LARGE_MOVE = Decimal("0.40")
MAX_TRADING_GAP = timedelta(days=7)


@dataclass
class CheckedPriceBar:
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None
    volume: int | None
    line: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def quality(self) -> QualityStatus:
        return _quality(self.findings)


@dataclass
class PriceAssessment:
    accepted: list[CheckedPriceBar] = field(default_factory=list)
    rejected: list[Finding] = field(default_factory=list)
    file_findings: list[Finding] = field(default_factory=list)


def _check_price_row(row: RawPriceRow, today: date) -> CheckedPriceBar | Finding:
    fields = row.fields
    key = fields.get("date") or None
    raw = {"line": row.line, **fields}
    empty = [name for name in ("date", *PRICE_FIELDS) if not fields.get(name)]
    if empty:
        return Finding("missing_field", f"Line {row.line}: {', '.join(empty)} empty.", key, raw)
    try:
        trade_date = parse_iso_date(fields["date"])
        prices = {name: parse_decimal_text(fields[name], name) for name in PRICE_FIELDS}
        adjusted_text = fields.get("adjusted_close", "")
        adjusted = parse_decimal_text(adjusted_text, "adjusted_close") if adjusted_text else None
        volume_text = fields.get("volume", "")
        volume = parse_volume(volume_text) if volume_text else None
    except NormalizationError as error:
        return Finding(error.rule, f"Line {row.line}: {error.message}", key, raw)
    if trade_date > today:
        return Finding("future_date", f"Line {row.line}: {trade_date} is in the future.", key, raw)
    non_positive = [n for n, v in prices.items() if v <= 0]
    if adjusted is not None and adjusted <= 0:
        non_positive.append("adjusted_close")
    if non_positive:
        return Finding(
            "non_positive_price", f"Line {row.line}: {', '.join(non_positive)} ≤ 0.", key, raw
        )
    if prices["high"] < prices["low"]:
        return Finding(
            "high_below_low",
            f"Line {row.line}: high {prices['high']} is below low {prices['low']}.",
            key,
            raw,
        )

    label = trade_date.isoformat()
    findings: list[Finding] = []
    outside = [n for n in ("open", "close") if not prices["low"] <= prices[n] <= prices["high"]]
    if outside:
        findings.append(
            Finding(
                "outside_high_low",
                f"{' and '.join(outside)} outside the high-low range "
                f"[{prices['low']}, {prices['high']}].",
                label,
            )
        )
    if trade_date.weekday() >= 5:
        findings.append(Finding("weekend_date", f"{label} is a {trade_date:%A}.", label))
    if volume == 0:
        findings.append(Finding("zero_volume", "No trades were reported.", label))
    return CheckedPriceBar(
        trade_date=trade_date,
        open=prices["open"],
        high=prices["high"],
        low=prices["low"],
        close=prices["close"],
        adjusted_close=adjusted,
        volume=volume,
        line=row.line,
        findings=findings,
    )


def assess_price_rows(rows: Sequence[RawPriceRow], today: date) -> PriceAssessment:
    result = PriceAssessment()
    by_date: dict[date, CheckedPriceBar] = {}
    for row in rows:
        checked = _check_price_row(row, today)
        if isinstance(checked, Finding):
            result.rejected.append(checked)
            continue
        if checked.trade_date in by_date:
            result.rejected.append(
                Finding(
                    "duplicate_date",
                    f"Line {row.line}: {checked.trade_date} already appears on line "
                    f"{by_date[checked.trade_date].line}; the first is kept.",
                    checked.trade_date.isoformat(),
                    {"line": row.line, **row.fields},
                )
            )
            continue
        by_date[checked.trade_date] = checked

    bars = [by_date[d] for d in sorted(by_date)]
    for previous, bar in pairwise(bars):
        if bar.trade_date - previous.trade_date > MAX_TRADING_GAP:
            result.file_findings.append(
                Finding(
                    "trading_gap",
                    f"No prices between {previous.trade_date} and {bar.trade_date}.",
                    bar.trade_date.isoformat(),
                )
            )
        change = abs(bar.close / previous.close - 1)
        if change > LARGE_MOVE:
            bar.findings.append(
                Finding(
                    "large_price_move",
                    f"Close moved {change:.1%} from {previous.close} to {bar.close}: possibly a "
                    "corporate action (split, bonus) or an error. Stored as reported.",
                    bar.trade_date.isoformat(),
                )
            )
    if not rows:
        result.file_findings.append(Finding("empty_file", "The file has no data rows."))
    result.accepted = bars
    return result
