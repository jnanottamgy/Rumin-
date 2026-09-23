"""Normalisation refuses anything ambiguous instead of guessing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import Frequency
from app.ingestion.normalize import (
    NormalizationError,
    currency_is_valid,
    current_period,
    isin_is_valid,
    mic_is_valid,
    next_period,
    parse_decimal_text,
    parse_iso_date,
    parse_provider_number,
    parse_provider_period,
    parse_volume,
    periods_between,
    provider_period_label,
)


def _rule(call: object) -> str:
    assert callable(call)
    with pytest.raises(NormalizationError) as caught:
        call()
    return caught.value.rule


@pytest.mark.parametrize(
    ("text", "frequency", "start", "label"),
    [
        ("2023", Frequency.ANNUAL, date(2023, 1, 1), "2023"),
        ("2023Q3", Frequency.QUARTERLY, date(2023, 7, 1), "2023-Q3"),
        ("2023M03", Frequency.MONTHLY, date(2023, 3, 1), "2023-03"),
        (" 2023 ", Frequency.ANNUAL, date(2023, 1, 1), "2023"),
    ],
)
def test_provider_periods(text: str, frequency: Frequency, start: date, label: str) -> None:
    period = parse_provider_period(text, frequency)
    assert (period.start, period.label, period.frequency) == (start, label, frequency)
    assert provider_period_label(period) == text.strip()


def test_period_ends() -> None:
    assert parse_provider_period("2024", Frequency.ANNUAL).end == date(2024, 12, 31)
    assert parse_provider_period("2024Q1", Frequency.QUARTERLY).end == date(2024, 3, 31)
    assert parse_provider_period("2024M02", Frequency.MONTHLY).end == date(2024, 2, 29)


def test_invalid_periods_are_refused() -> None:
    assert _rule(lambda: parse_provider_period("2023Q1", Frequency.ANNUAL)) == "frequency_mismatch"
    assert _rule(lambda: parse_provider_period("2023M13", Frequency.MONTHLY)) == "invalid_period"
    assert _rule(lambda: parse_provider_period("FY2023", Frequency.ANNUAL)) == "invalid_period"
    assert _rule(lambda: parse_provider_period(2023, Frequency.ANNUAL)) == "invalid_period"
    assert _rule(lambda: parse_provider_period(None, Frequency.ANNUAL)) == "invalid_period"
    assert _rule(lambda: parse_provider_period("1066", Frequency.ANNUAL)) == "invalid_period"


def test_period_arithmetic_crosses_year_ends() -> None:
    q4 = parse_provider_period("2023Q4", Frequency.QUARTERLY)
    assert next_period(q4).label == "2024-Q1"
    december = parse_provider_period("2023M12", Frequency.MONTHLY)
    assert next_period(december).label == "2024-01"
    first = parse_provider_period("2023M11", Frequency.MONTHLY)
    last = parse_provider_period("2024M02", Frequency.MONTHLY)
    assert [p.label for p in periods_between(first, last)] == [
        "2023-11",
        "2023-12",
        "2024-01",
        "2024-02",
    ]
    assert current_period(Frequency.QUARTERLY, date(2026, 9, 23)).label == "2026-Q3"


def test_dates_must_be_unambiguous_iso_dates() -> None:
    assert parse_iso_date("2024-02-29") == date(2024, 2, 29)
    for text in ("2023-02-29", "03/04/2024", "2024-3-4", "20240304", "2024-03-04T00:00"):
        assert _rule(lambda text=text: parse_iso_date(text)) == "invalid_date"


def test_provider_numbers_must_already_be_decimals() -> None:
    assert parse_provider_number(Decimal("5.649")) == Decimal("5.649")
    assert parse_provider_number(3) == Decimal(3)
    for value in (5.649, "5.649", True, None, [1]):
        assert _rule(lambda value=value: parse_provider_number(value)) == "invalid_number"
    assert _rule(lambda: parse_provider_number(Decimal("NaN"))) == "invalid_number"
    too_precise = Decimal("0.1234567890123456789")
    assert _rule(lambda: parse_provider_number(too_precise)) == "precision_exceeded"


def test_file_numbers_are_plain_decimals_only() -> None:
    assert parse_decimal_text("2934.55", "close") == Decimal("2934.55")
    assert parse_decimal_text("-0.5", "close") == Decimal("-0.5")
    # Separators, symbols and exponents mean different things in different places.
    for text in ("2,934.55", "₹2934", "2934,55", "2.93e3", "", " ", "1.", ".5", "NaN"):
        assert _rule(lambda text=text: parse_decimal_text(text, "close")) == "invalid_number"


def test_volumes_are_whole_non_negative_numbers() -> None:
    assert parse_volume("1200345") == 1200345
    for text in ("-1", "1.5", "1,000", "9" * 20):
        assert _rule(lambda text=text: parse_volume(text)) == "invalid_volume"


def test_identifiers() -> None:
    assert isin_is_valid("US0378331005")  # Apple Inc.
    assert isin_is_valid("INE002A01018")  # Reliance Industries
    assert not isin_is_valid("INE002A01019")  # wrong check digit
    assert not isin_is_valid("ine002a01018")
    assert mic_is_valid("XNSE") and not mic_is_valid("NSE")
    assert currency_is_valid("INR") and not currency_is_valid("inr")
