"""Units and currencies the simulation engine understands, with exact conversion factors.

Volumes convert through litres, using their legal definitions:

* 1 US gallon = 231 cubic inches = 3.785411784 litres (exact);
* 1 US barrel of petroleum = 42 US gallons = 158.987294928 litres (exact);
* 1 kilolitre = 1,000 litres.

Nothing converts silently. A conversion is a calculation step with its factor recorded,
and quantities of different dimensions (a volume and a price, one currency and another)
are never converted into each other: a currency conversion needs an exchange rate, which
is always an input.

RUMIN holds no copy of the ISO 4217 list, so a currency code is checked for its format
(three capital letters) only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.simulation.decimal_math import arithmetic

CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")
BENCHMARK_CURRENCY = "USD"


def currency_is_valid(code: str) -> bool:
    return bool(CURRENCY_CODE.match(code))


@dataclass(frozen=True)
class VolumeUnit:
    id: str
    label: str
    symbol: str
    litres: Decimal
    definition: str


VOLUME_UNITS: dict[str, VolumeUnit] = {
    unit.id: unit
    for unit in (
        VolumeUnit("litre", "litre", "L", Decimal(1), "The SI litre (1 cubic decimetre)."),
        VolumeUnit("kilolitre", "kilolitre", "kL", Decimal(1000), "1 kilolitre = 1,000 litres."),
        VolumeUnit(
            "us_gallon",
            "US gallon",
            "US gal",
            Decimal("3.785411784"),
            "1 US gallon = 231 cubic inches = 3.785411784 litres exactly.",
        ),
        VolumeUnit(
            "us_barrel",
            "US barrel",
            "bbl",
            Decimal("158.987294928"),
            "1 US barrel of petroleum = 42 US gallons = 158.987294928 litres exactly.",
        ),
    )
}


@dataclass(frozen=True)
class PriceUnit:
    """A price in one currency per unit of volume, e.g. USD per US gallon."""

    id: str
    currency: str
    volume: VolumeUnit

    @property
    def label(self) -> str:
        return f"{self.currency} per {self.volume.label}"


PRICE_UNITS: dict[str, PriceUnit] = {
    price.id: price
    for price in (
        PriceUnit("usd_per_us_gallon", BENCHMARK_CURRENCY, VOLUME_UNITS["us_gallon"]),
        PriceUnit("usd_per_us_barrel", BENCHMARK_CURRENCY, VOLUME_UNITS["us_barrel"]),
        PriceUnit("usd_per_kilolitre", BENCHMARK_CURRENCY, VOLUME_UNITS["kilolitre"]),
    )
}


def volume_conversion_factor(from_unit: VolumeUnit, to_unit: VolumeUnit) -> Decimal:
    """How many ``to_unit`` make one ``from_unit`` (litres(from) / litres(to)).

    Exact when the ratio terminates (e.g. barrel → gallon = 42); otherwise correctly
    rounded to the engine's 34 significant digits (e.g. kilolitre → US gallon).
    """
    with arithmetic():
        return from_unit.litres / to_unit.litres


# Human labels for the unit identifiers used in model definitions. Units that depend on
# the reporting currency use "{currency}", filled in when a run is described.
UNIT_LABELS: dict[str, str] = {
    "percent": "%",
    "percent_change": "% change",
    "ratio": "ratio",
    # A difference of two ratios, e.g. of margins: 0.01 is one percentage point.
    "ratio_points": "ratio points (0.01 = one percentage point)",
    "elasticity": "elasticity (dimensionless)",
    "months": "months",
    "currency_code": "ISO 4217 code",
    "graph_node": "knowledge-graph node",
    "currency_per_year": "{currency} per year",
    "currency_per_month": "{currency} per month",
    "currency": "{currency}",
    "currency_per_usd": "{currency} per USD",
    "usd_per_year": "USD per year",
    "volume_per_year": "{volume} per year",
    "price_per_volume": "USD per {volume}",
    "price_relative": "ratio to baseline",
    "log_change": "log change",
}


def unit_label(unit: str, *, currency: str | None = None, volume: str | None = None) -> str:
    if unit in PRICE_UNITS:
        return PRICE_UNITS[unit].label
    if unit in VOLUME_UNITS:
        return VOLUME_UNITS[unit].label
    label = UNIT_LABELS.get(unit, unit)
    return label.replace("{currency}", currency or "reporting currency").replace(
        "{volume}", volume or "unit of volume"
    )
