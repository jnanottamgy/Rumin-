"""Turning provider values into RUMIN's types — strictly, and never by guessing.

Every function either returns a normalised value or raises ``NormalizationError`` naming
the rule that failed. Nothing is coerced silently: a comma in a number, an unexpected
date format or a period of the wrong frequency is refused, not "fixed".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.db.types import decimal_fits
from app.domain.enums import Frequency


class NormalizationError(ValueError):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule
        self.message = message


# --- Periods ------------------------------------------------------------------------------

_ANNUAL = re.compile(r"^(\d{4})$")
_QUARTERLY = re.compile(r"^(\d{4})Q([1-4])$")
_MONTHLY = re.compile(r"^(\d{4})M(\d{2})$")
MIN_YEAR, MAX_YEAR = 1800, 2200


@dataclass(frozen=True, order=True)
class Period:
    start: date
    frequency: Frequency
    label: str  # "2023", "2023-Q1", "2023-03"

    @property
    def end(self) -> date:
        """The last day of the period."""
        return next_period(self).start - timedelta(days=1)


def _period(year: int, frequency: Frequency, index: int = 1) -> Period:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise NormalizationError(
            "invalid_period", f"The year {year} is outside {MIN_YEAR} to {MAX_YEAR}."
        )
    if frequency is Frequency.ANNUAL:
        return Period(date(year, 1, 1), frequency, f"{year}")
    if frequency is Frequency.QUARTERLY:
        return Period(date(year, 3 * (index - 1) + 1, 1), frequency, f"{year}-Q{index}")
    if frequency is Frequency.MONTHLY:
        return Period(date(year, index, 1), frequency, f"{year}-{index:02d}")
    raise NormalizationError("unsupported_frequency", f"{frequency} periods are not supported.")


def parse_provider_period(value: object, expected: Frequency) -> Period:
    """Parse ``2023``, ``2023Q1`` or ``2023M03`` and check it has the expected frequency."""
    if not isinstance(value, str):
        raise NormalizationError("invalid_period", "The period is missing or not text.")
    text = value.strip()
    if match := _ANNUAL.match(text):
        found, year, index = Frequency.ANNUAL, int(match.group(1)), 1
    elif match := _QUARTERLY.match(text):
        found, year, index = Frequency.QUARTERLY, int(match.group(1)), int(match.group(2))
    elif match := _MONTHLY.match(text):
        found, year, index = Frequency.MONTHLY, int(match.group(1)), int(match.group(2))
        if not 1 <= index <= 12:
            raise NormalizationError("invalid_period", f"'{text}' has no month {index}.")
    else:
        raise NormalizationError("invalid_period", f"'{text}' is not a recognised period.")
    if found is not expected:
        raise NormalizationError(
            "frequency_mismatch", f"'{text}' is a {found} period; the series is {expected}."
        )
    return _period(year, found, index)


def next_period(period: Period) -> Period:
    year = period.start.year
    if period.frequency is Frequency.ANNUAL:
        return _period(year + 1, Frequency.ANNUAL)
    if period.frequency is Frequency.QUARTERLY:
        quarter = (period.start.month - 1) // 3 + 1
        return _period(year + quarter // 4, Frequency.QUARTERLY, quarter % 4 + 1)
    month = period.start.month
    return _period(year + month // 12, Frequency.MONTHLY, month % 12 + 1)


def periods_between(first: Period, last: Period) -> list[Period]:
    """Every period from ``first`` to ``last`` inclusive (same frequency)."""
    periods: list[Period] = []
    current = first
    while current.start <= last.start:
        periods.append(current)
        current = next_period(current)
    return periods


def provider_period_label(period: Period) -> str:
    """The provider notation (World Bank style) for a period: 2023, 2023Q1, 2023M03."""
    if period.frequency is Frequency.ANNUAL:
        return f"{period.start.year}"
    if period.frequency is Frequency.QUARTERLY:
        return f"{period.start.year}Q{(period.start.month - 1) // 3 + 1}"
    return f"{period.start.year}M{period.start.month:02d}"


def current_period(frequency: Frequency, today: date) -> Period:
    if frequency is Frequency.ANNUAL:
        return _period(today.year, frequency)
    if frequency is Frequency.QUARTERLY:
        return _period(today.year, frequency, (today.month - 1) // 3 + 1)
    return _period(today.year, frequency, today.month)


# --- Dates --------------------------------------------------------------------------------

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(text: str) -> date:
    """Strict ISO 8601 calendar date (YYYY-MM-DD). Other formats are ambiguous: 03/04/2024
    is March in one country and April in another, so they are refused."""
    if not _ISO_DATE.match(text):
        raise NormalizationError("invalid_date", f"'{text}' is not a YYYY-MM-DD date.")
    try:
        value = date.fromisoformat(text)
    except ValueError as error:
        raise NormalizationError(
            "invalid_date", f"'{text}' is not a real calendar date."
        ) from error
    if not MIN_YEAR <= value.year <= MAX_YEAR:
        raise NormalizationError("invalid_date", f"'{text}' is outside {MIN_YEAR} to {MAX_YEAR}.")
    return value


# --- Numbers ------------------------------------------------------------------------------

_DECIMAL_TEXT = re.compile(r"^[+-]?\d+(\.\d+)?$")
_INTEGER_TEXT = re.compile(r"^\d+$")


def _checked(value: Decimal, label: str) -> Decimal:
    if not value.is_finite():
        raise NormalizationError("invalid_number", f"{label} is not a finite number.")
    if not decimal_fits(value):
        raise NormalizationError(
            "precision_exceeded",
            f"{label} ({value}) has more digits than RUMIN stores exactly (NUMERIC(38, 18)); "
            "it is refused rather than rounded.",
        )
    return value


def parse_provider_number(value: object, label: str = "The value") -> Decimal:
    """A number from a provider's JSON, already parsed as ``Decimal`` (never a float)."""
    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        kind = type(value).__name__
        raise NormalizationError("invalid_number", f"{label} is a {kind}, not a number.")
    return _checked(Decimal(value), label)


def parse_decimal_text(text: str, label: str) -> Decimal:
    """A number from a file: plain digits with an optional sign and decimal point. Thousands
    separators, currency symbols and exponents are refused — their meaning varies."""
    if not _DECIMAL_TEXT.match(text):
        raise NormalizationError(
            "invalid_number",
            f"{label} '{text}' is not a plain decimal number (no separators or symbols).",
        )
    try:
        value = Decimal(text)
    except InvalidOperation as error:  # pragma: no cover - the pattern already guarantees it
        raise NormalizationError("invalid_number", f"{label} '{text}' is not a number.") from error
    return _checked(value, label)


def parse_volume(text: str) -> int:
    if not _INTEGER_TEXT.match(text):
        raise NormalizationError(
            "invalid_volume", f"Volume '{text}' is not a whole, non-negative number."
        )
    volume = int(text)
    if volume >= 2**63:
        raise NormalizationError("invalid_volume", f"Volume '{text}' is too large.")
    return volume


# --- Identifiers --------------------------------------------------------------------------

_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
_MIC = re.compile(r"^[A-Z0-9]{4}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


def isin_is_valid(isin: str) -> bool:
    """ISO 6166 format and check digit (letters become numbers, then the Luhn algorithm)."""
    if not _ISIN.match(isin):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin[:-1])
    total = 0
    for position, char in enumerate(reversed(digits)):
        number = int(char)
        if position % 2 == 0:  # double every second digit, starting from the right
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return (10 - total % 10) % 10 == int(isin[-1])


def mic_is_valid(mic: str) -> bool:
    return bool(_MIC.match(mic))


def currency_is_valid(code: str) -> bool:
    return bool(_CURRENCY.match(code))
