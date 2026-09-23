"""The simulation engine's numbers: exact decimals, rounding, limits, units and parsing."""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app.simulation import decimal_math
from app.simulation.decimal_math import (
    MAGNITUDE_LIMIT,
    NumericalError,
    arithmetic,
    exp,
    ln,
    percent_to_fraction,
    text,
    to_output,
)
from app.simulation.units import (
    PRICE_UNITS,
    VOLUME_UNITS,
    unit_label,
    volume_conversion_factor,
)
from app.simulation.validation import decimal_places, parse_number

D = Decimal


# --- Decimal arithmetic ------------------------------------------------------------------------


def test_logarithms_and_exponentials_are_correctly_rounded_to_34_digits() -> None:
    with arithmetic():
        assert ln(D("1.1")) == D("0.09531017980432486004395212328076509")
        assert exp(ln(D("1.1"))) == D("1.100000000000000000000000000000000")
        assert exp(ln(D(2)) / 2) == D("1.414213562373095048801688724209698")  # √2


def test_an_impossible_calculation_raises_instead_of_returning_nan_or_infinity() -> None:
    with pytest.raises(NumericalError), arithmetic():
        _ = D(1) / D(0)
    with pytest.raises(NumericalError), arithmetic():
        _ = D("1e999999") * D(10)
    with pytest.raises(NumericalError, match="undefined"):
        ln(D(0))


def test_outputs_are_rounded_half_to_even_to_ten_places() -> None:
    assert to_output(D("0.00000000005")) == D(0)  # half, to the even digit 0
    assert to_output(D("0.00000000015")) == D("0.0000000002")  # half, to the even digit 2
    assert to_output(D("-2.123456789049")) == D("-2.123456789")
    assert text(to_output(D("5.0000000000"))) == "5"  # canonical: no trailing zeros


def test_outputs_beyond_the_magnitude_limit_are_refused() -> None:
    with pytest.raises(NumericalError, match="beyond the engine's limit"):
        to_output(MAGNITUDE_LIMIT, "Fuel cost")
    with pytest.raises(NumericalError, match="not a finite number"):
        to_output(D("NaN"))
    assert to_output(MAGNITUDE_LIMIT - 1) == MAGNITUDE_LIMIT - 1


def test_numbers_are_served_in_plain_notation() -> None:
    assert text(D("1E+3")) == "1000"
    assert text(D("1.50")) == "1.5"
    assert text(D("-0.000001")) == "-0.000001"


def test_percent_to_fraction_is_exact() -> None:
    assert percent_to_fraction(D("12.5")) == D("0.125")
    assert percent_to_fraction(D("-99.9999")) == D("-0.999999")


def test_the_decimal_context_is_the_documented_one() -> None:
    with arithmetic() as context:
        assert context.prec == decimal_math.PRECISION == 34
        assert context.rounding == "ROUND_HALF_EVEN"


# --- Units -------------------------------------------------------------------------------------


def test_volume_factors_are_exact_legal_definitions() -> None:
    assert VOLUME_UNITS["us_gallon"].litres == D("3.785411784")
    assert VOLUME_UNITS["us_barrel"].litres == D("158.987294928")
    assert volume_conversion_factor(VOLUME_UNITS["us_barrel"], VOLUME_UNITS["us_gallon"]) == 42
    assert volume_conversion_factor(VOLUME_UNITS["kilolitre"], VOLUME_UNITS["litre"]) == 1000
    with arithmetic():
        round_trip = volume_conversion_factor(
            VOLUME_UNITS["kilolitre"], VOLUME_UNITS["us_gallon"]
        ) * volume_conversion_factor(VOLUME_UNITS["us_gallon"], VOLUME_UNITS["kilolitre"])
    assert abs(round_trip - 1) < D("1e-32")


def test_prices_are_quoted_per_volume_in_us_dollars() -> None:
    assert {unit.volume.id for unit in PRICE_UNITS.values()} == {
        "us_gallon",
        "us_barrel",
        "kilolitre",
    }
    assert unit_label("usd_per_us_gallon") == PRICE_UNITS["usd_per_us_gallon"].label
    assert unit_label("currency_per_year", currency="INR") == "INR per year"


# --- Parsing request values --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2.35", D("2.35")),
        (" 10 ", D(10)),
        ("-0.5", D("-0.5")),
        (30, D(30)),
        (0.1, D("0.1")),  # the float's shortest form, not 0.1000000000000000055…
        (2.35, D("2.35")),
    ],
)
def test_plain_numbers_are_read_exactly(raw: str | int | float, expected: Decimal) -> None:
    assert parse_number(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "1e3",
        "1E3",
        "1,000",
        "₹100",
        "10%",
        "",
        "NaN",
        "Infinity",
        "0x10",
        "--1",
        True,
        1e300,
        float("nan"),
        float("inf"),
    ],
)
def test_anything_but_a_plain_number_is_refused(raw: str | int | float) -> None:
    assert parse_number(raw) is None


def test_decimal_places_ignore_trailing_zeros() -> None:
    assert decimal_places(D("2.3500")) == 2
    assert decimal_places(D("100")) == 0
    assert decimal_places(D("1E+2")) == 0


# --- Safeguards --------------------------------------------------------------------------------


def test_the_engine_never_evaluates_code() -> None:
    """No formula is ever executed from text: the package calls no eval, exec or compile."""
    package = Path(decimal_math.__file__).parent
    forbidden = {"eval", "exec", "compile", "__import__"}
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, f"{path.name} calls {node.func.id}()"
