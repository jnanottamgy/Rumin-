"""Numbers as they appear inside the templated sentences of findings.

Sentences are for reading; the exact values always travel beside them as facts (exact
decimal strings with units and references). Rounding here is for display only.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

MINUS = "−"


def _grouped(value: Decimal, places: int) -> str:
    quantum = Decimal(1).scaleb(-places)
    rounded = abs(value).quantize(quantum, rounding=ROUND_HALF_EVEN)
    text = f"{rounded:,.{places}f}"
    negative = value < 0 and rounded != 0
    return f"{MINUS}{text}" if negative else text


def number(value: Decimal, places: int = 2) -> str:
    return _grouped(value, places)


def stored(value: Decimal, max_places: int = 6) -> str:
    """A stored value at its own precision (``84.2``, not ``84.2000``), grouped."""
    exponent = value.normalize().as_tuple().exponent
    places = min(max(0, -exponent), max_places) if isinstance(exponent, int) else 0
    return _grouped(value, places)


def signed_stored(value: Decimal, max_places: int = 4) -> str:
    """Signed, rounded to at most ``max_places`` without trailing zeros (``+4.2``)."""
    rounded = value.quantize(Decimal(1).scaleb(-max_places), rounding=ROUND_HALF_EVEN)
    text = stored(rounded, max_places)
    return text if text.startswith(MINUS) or rounded == 0 else f"+{text}"


PER_PERIOD = {
    "annual": "per year",
    "quarterly": "per quarter",
    "monthly": "per month",
    "daily": "per trading day",
}


def signed(value: Decimal, places: int = 2) -> str:
    text = _grouped(value, places)
    return text if text.startswith(MINUS) or value == 0 else f"+{text}"


def money(value: Decimal, currency: str, *, sign: bool = False) -> str:
    places = 0 if value == value.to_integral_value() or abs(value) >= 1000 else 2
    text = signed(value, places) if sign else _grouped(value, places)
    return f"{text} {currency}".strip()


def percent(value: Decimal, *, sign: bool = True, places: int = 2) -> str:
    return f"{signed(value, places) if sign else number(value, places)} %"


def points(value: Decimal, *, sign: bool = True, places: int = 2) -> str:
    text = signed(value, places) if sign else number(value, places)
    return f"{text} percentage points"


def change(value: Decimal, unit: str) -> str:
    """A change in its unit: percent or percentage points."""
    return percent(value) if unit == "percent" else points(value)


def listing(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"
