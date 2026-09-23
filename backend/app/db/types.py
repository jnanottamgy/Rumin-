"""Custom column types."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on every database.

    PostgreSQL stores ``timestamptz`` natively, but SQLite has no timezone support and
    returns naive values. This type normalises writes to UTC and always returns
    timezone-aware UTC datetimes, so application code behaves identically on both.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use timezone-aware UTC values.")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


# --- Exact decimals ------------------------------------------------------------------------

DECIMAL_PRECISION = 38  # total significant digits
DECIMAL_SCALE = 18  # digits after the decimal point
_MAX_INTEGER_DIGITS = DECIMAL_PRECISION - DECIMAL_SCALE


def decimal_fits(value: Decimal) -> bool:
    """Whether ``value`` can be stored in ``NUMERIC(38, 18)`` without rounding."""
    if not value.is_finite():
        return False
    _, digits, raw_exponent = value.as_tuple()
    exponent = cast(int, raw_exponent)  # finite values always have an integer exponent
    decimals = max(0, -exponent)
    integer_digits = max(0, len(digits) + exponent)
    return decimals <= DECIMAL_SCALE and integer_digits <= _MAX_INTEGER_DIGITS


def canonical_decimal(value: Decimal) -> Decimal:
    """The same number without insignificant trailing zeros and never in exponent form,
    so ``Decimal("5.6490")`` and ``Decimal("5.649000000000000000")`` compare and print alike."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return Decimal(text)


class ExactDecimal(TypeDecorator[Decimal]):
    """Decimals stored exactly on every database.

    PostgreSQL stores ``NUMERIC(38, 18)``, which is exact. SQLite's ``NUMERIC`` affinity
    would silently turn values into binary floating point, so on SQLite the value is kept
    as its canonical decimal string instead. Values that do not fit are refused with an
    error — they are never rounded — and callers validate them before persisting.
    """

    impl = Numeric(DECIMAL_PRECISION, DECIMAL_SCALE)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(64))
        return dialect.type_descriptor(Numeric(DECIMAL_PRECISION, DECIMAL_SCALE, asdecimal=True))

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, Decimal):
            kind = type(value).__name__
            raise TypeError(f"ExactDecimal accepts Decimal values only, not {kind}.")
        if not decimal_fits(value):
            raise ValueError(f"{value} does not fit NUMERIC({DECIMAL_PRECISION}, {DECIMAL_SCALE}).")
        canonical = canonical_decimal(value)
        return format(canonical, "f") if dialect.name == "sqlite" else canonical

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return canonical_decimal(Decimal(str(value)))
