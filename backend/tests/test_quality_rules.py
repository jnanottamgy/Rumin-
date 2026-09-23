"""Quality rules: structural problems reject, plausibility problems flag, values are never
changed. All records here are SYNTHETIC."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.enums import (
    Frequency,
    IssueOutcome,
    IssueSeverity,
    MeasureType,
    ObservationStatus,
    QualityStatus,
)
from app.ingestion.providers.base import RawObservation, RawPriceRow
from app.ingestion.quality import (
    RULES,
    CheckedPriceBar,
    SeriesExpectation,
    assess_observations,
    assess_price_rows,
)

TODAY = date(2026, 9, 23)
LEVEL = SeriesExpectation(
    provider_code="PA.NUS.FCRF",
    country_iso3="IND",
    frequency=Frequency.ANNUAL,
    measure_type=MeasureType.EXCHANGE_RATE,
    unit="INR per USD",
    plausible_min=Decimal("1"),
    plausible_max=Decimal("500"),
)


def obs(period: object, value: object, **kwargs: object) -> RawObservation:
    values: dict[str, object] = {"series_code": "PA.NUS.FCRF", "country_iso3": "IND"}
    values.update(kwargs)
    return RawObservation(period=period, value=value, **values)  # type: ignore[arg-type]


def test_every_rule_is_documented_with_a_consistent_outcome() -> None:
    for rule in RULES.values():
        assert rule.description.endswith(".")
        if rule.outcome is IssueOutcome.REJECTED:
            assert rule.severity is IssueSeverity.ERROR
        else:
            assert rule.severity is not IssueSeverity.ERROR


def test_plausibility_problems_are_flagged_not_changed() -> None:
    result = assess_observations(
        LEVEL, [obs("2021", Decimal("0")), obs("2022", Decimal("900.25"))], TODAY
    )
    zero, high = result.accepted
    assert zero.value == Decimal("0") and high.value == Decimal("900.25")
    assert {f.rule for f in zero.findings} == {"outside_review_range", "non_positive_level"}
    assert [f.rule for f in high.findings] == ["outside_review_range"]
    assert zero.quality is QualityStatus.WARNING
    assert result.rejected == []


def test_a_period_still_in_progress_is_flagged() -> None:
    result = assess_observations(LEVEL, [obs("2026", Decimal("83.1"))], TODAY)
    (current,) = result.accepted
    assert [f.rule for f in current.findings] == ["period_in_progress"]


def test_duplicates_keep_the_first_record() -> None:
    result = assess_observations(
        LEVEL, [obs("2021", Decimal("74.1")), obs("2021", Decimal("80.0"))], TODAY
    )
    assert [o.value for o in result.accepted] == [Decimal("74.1")]
    assert [f.rule for f in result.rejected] == ["duplicate_period"]


def test_provider_flags_and_units_are_noted() -> None:
    result = assess_observations(
        LEVEL, [obs("2021", Decimal("74.1"), flags="E", unit="LCU per US$")], TODAY
    )
    (checked,) = result.accepted
    assert checked.flags == "E"
    assert [f.rule for f in checked.findings] == ["provider_flag"]
    assert checked.quality is QualityStatus.VALIDATED  # a note is not a warning
    assert [f.rule for f in result.series_findings] == ["provider_unit"]


def test_series_level_findings() -> None:
    assert [f.rule for f in assess_observations(LEVEL, [], TODAY).series_findings] == [
        "empty_response"
    ]
    all_missing = assess_observations(LEVEL, [obs("2020", None), obs("2021", None)], TODAY)
    assert [o.status for o in all_missing.accepted] == [ObservationStatus.MISSING] * 2
    assert [f.rule for f in all_missing.series_findings] == ["no_reported_values"]
    gap = assess_observations(
        LEVEL, [obs("2018", Decimal("70")), obs("2021", Decimal("74"))], TODAY
    )
    (finding,) = gap.series_findings
    assert finding.rule == "unexpected_gap"
    assert finding.raw == {"periods": ["2019", "2020"]}


# --- Price rows ------------------------------------------------------------------------------


def row(line: int, day: str, o: str, h: str, low: str, c: str, **extra: str) -> RawPriceRow:
    return RawPriceRow(
        line=line, fields={"date": day, "open": o, "high": h, "low": low, "close": c, **extra}
    )


def test_consistent_rows_are_accepted_exactly() -> None:
    result = assess_price_rows(
        [
            row(2, "2026-09-21", "100.10", "101.00", "99.50", "100.75", volume="1500"),
            row(3, "2026-09-22", "100.75", "102.25", "100.00", "101.90", volume="1700"),
        ],
        TODAY,
    )
    assert result.rejected == [] and result.file_findings == []
    first = result.accepted[0]
    assert isinstance(first, CheckedPriceBar)
    assert (first.close, first.volume, first.quality) == (
        Decimal("100.75"),
        1500,
        QualityStatus.VALIDATED,
    )


def test_structurally_impossible_rows_are_rejected() -> None:
    result = assess_price_rows(
        [
            row(2, "2026-09-21", "100", "99", "101", "100"),  # high below low
            row(3, "2026-09-22", "0", "1", "0", "1"),  # zero price
            row(4, "22/09/2026", "1", "1", "1", "1"),  # ambiguous date
            row(5, "2026-09-30", "1", "1", "1", "1"),  # future date
            row(6, "2026-09-18", "1", "", "1", "1"),  # empty field
            row(7, "2026-09-17", "1,000", "1", "1", "1"),  # thousands separator
            row(8, "2026-09-16", "1", "1", "1", "1", volume="-5"),
        ],
        TODAY,
    )
    assert result.accepted == []
    assert [f.rule for f in result.rejected] == [
        "high_below_low",
        "non_positive_price",
        "invalid_date",
        "future_date",
        "missing_field",
        "invalid_number",
        "invalid_volume",
    ]
    assert result.rejected[0].raw == {
        "line": 2,
        "date": "2026-09-21",
        "open": "100",
        "high": "99",
        "low": "101",
        "close": "100",
    }


def test_unusual_rows_are_flagged() -> None:
    result = assess_price_rows(
        [
            row(2, "2026-08-31", "100", "101", "99", "100", volume="10"),
            row(3, "2026-09-12", "100", "102", "98", "150", volume="0"),  # Saturday, +50%
            row(4, "2026-09-14", "150", "151", "149", "152.5"),
        ],
        TODAY,
    )
    saturday = result.accepted[1]
    assert {f.rule for f in saturday.findings} == {
        "outside_high_low",
        "weekend_date",
        "zero_volume",
        "large_price_move",
    }
    assert saturday.close == Decimal("150")  # stored as reported, never adjusted
    assert [f.rule for f in result.file_findings] == ["trading_gap"]


def test_duplicate_dates_keep_the_first_row() -> None:
    result = assess_price_rows(
        [row(2, "2026-09-21", "1", "2", "1", "2"), row(3, "2026-09-21", "5", "6", "5", "6")],
        TODAY,
    )
    assert [bar.line for bar in result.accepted] == [2]
    assert [f.rule for f in result.rejected] == ["duplicate_date"]
    assert assess_price_rows([], TODAY).file_findings[0].rule == "empty_file"
