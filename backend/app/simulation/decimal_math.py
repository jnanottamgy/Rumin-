"""Exact decimal arithmetic for the simulation engine.

Every calculation runs in one decimal context: 34 significant digits (the precision of
IEEE 754 decimal128), rounding half to even, and traps on invalid operations, division by
zero and overflow — an impossible calculation raises instead of quietly producing NaN or
Infinity. ``Decimal.ln`` and ``Decimal.exp`` are correctly rounded, so every machine gets
the same digits and a run can be reproduced exactly.

Outputs are rounded half to even to ``OUTPUT_PLACES`` decimal places and bounded by
``MAGNITUDE_LIMIT``; inputs are bounded more tightly by each model's validation rules, so
the bound is a safety net, not the first line of defence.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

from app.db.types import canonical_decimal

PRECISION = 34
OUTPUT_PLACES = 10
OUTPUT_QUANTUM = Decimal(1).scaleb(-OUTPUT_PLACES)
# No output of a model may reach this magnitude (in its own unit). Below 10²⁰, every value
# rounded to OUTPUT_PLACES fits the database's exact NUMERIC(38, 18) columns.
MAGNITUDE_LIMIT = Decimal("1e20")

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)
MONTHS_PER_YEAR = Decimal(12)


def _context() -> Context:
    return Context(
        prec=PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=-999_999,
        Emax=999_999,
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )


class NumericalError(ValueError):
    """A calculation left the range the engine accepts (overflow, invalid operation)."""

    def __init__(self, message: str, *, code: str = "numerical_limit") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@contextmanager
def arithmetic() -> Iterator[Context]:
    """Run a block of calculations in the engine's decimal context.

    Decimal traps become ``NumericalError`` so callers can report them as validation
    problems rather than crashes.
    """
    with localcontext(_context()) as context:
        try:
            yield context
        except (InvalidOperation, DivisionByZero, Overflow) as error:
            raise NumericalError(
                "A calculation left the numerical range the engine accepts "
                f"({type(error).__name__}). Check the magnitudes of the inputs."
            ) from error


def ln(value: Decimal) -> Decimal:
    """Natural logarithm (correctly rounded). ``value`` must be positive."""
    if value <= ZERO:
        raise NumericalError(f"The logarithm of {value} is undefined (it must be positive).")
    return value.ln()


def exp(value: Decimal) -> Decimal:
    """Exponential (correctly rounded)."""
    return value.exp()


def check_finite(value: Decimal, label: str) -> Decimal:
    """``value`` itself, if it is finite and below the magnitude limit."""
    if not value.is_finite():
        raise NumericalError(f"{label} is not a finite number.")
    if abs(value) >= MAGNITUDE_LIMIT:
        raise NumericalError(
            f"{label} ({value:.3E}) is beyond the engine's limit of {MAGNITUDE_LIMIT:.0E}. "
            "Check the magnitudes and units of the inputs."
        )
    return value


def to_output(value: Decimal, label: str = "A result") -> Decimal:
    """``value`` rounded half to even to ``OUTPUT_PLACES`` decimal places, canonical."""
    check_finite(value, label)
    with localcontext(_context()):
        rounded = value.quantize(OUTPUT_QUANTUM, rounding=ROUND_HALF_EVEN)
    return canonical_decimal(rounded)


def text(value: Decimal) -> str:
    """Plain decimal notation (never exponent form), as the API serves numbers."""
    return format(canonical_decimal(value), "f")


def percent_to_fraction(value: Decimal) -> Decimal:
    """30 (percent) → 0.3. Exact: dividing by 100 only moves the decimal point."""
    return value.scaleb(-2)
