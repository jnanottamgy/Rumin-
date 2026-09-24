"""Rules for scenario inputs ("shocks").

These rules are the single source of truth for scenario validation. The API exposes
them per variable (``scenario_rules`` on each economic variable) so the frontend can
guide users with the same limits the backend enforces.

The limits are *input sanity limits* — they catch typos and impossible values. They
are not judgements about economic plausibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.domain.enums import ChangeType, ValueKind

MAX_SHOCKS_PER_SCENARIO = 10
MAX_DECIMAL_PLACES = 4

# A level (price, exchange rate, index) cannot fall by 100 % or more.
PERCENT_CHANGE_MIN_EXCLUSIVE = -100.0
PERCENT_CHANGE_MAX = 1000.0
# Rates (policy rates, inflation) are shocked in percentage points.
RATE_CHANGE_LIMIT_PP = 25.0
ABSOLUTE_CHANGE_LIMIT = 1_000_000.0


@dataclass(frozen=True)
class ChangeRule:
    change_type: ChangeType
    minimum: float
    maximum: float
    minimum_exclusive: bool
    unit_label: str


def change_rules_for(value_kind: ValueKind, unit: str) -> list[ChangeRule]:
    """Which kinds of change a variable accepts, and within what limits.

    A *percentage* change of a rate is ambiguous (+10 % of a 6.5 % rate is 7.15 %, not
    16.5 %), so rates only accept absolute changes in percentage points.
    """
    if value_kind is ValueKind.RATE:
        return [
            ChangeRule(
                change_type=ChangeType.ABSOLUTE_CHANGE,
                minimum=-RATE_CHANGE_LIMIT_PP,
                maximum=RATE_CHANGE_LIMIT_PP,
                minimum_exclusive=False,
                unit_label="percentage points",
            )
        ]
    return [
        ChangeRule(
            change_type=ChangeType.PERCENT_CHANGE,
            minimum=PERCENT_CHANGE_MIN_EXCLUSIVE,
            maximum=PERCENT_CHANGE_MAX,
            minimum_exclusive=True,
            unit_label="%",
        ),
        ChangeRule(
            change_type=ChangeType.ABSOLUTE_CHANGE,
            minimum=-ABSOLUTE_CHANGE_LIMIT,
            maximum=ABSOLUTE_CHANGE_LIMIT,
            minimum_exclusive=False,
            unit_label=unit,
        ),
    ]


def _exact(value: float | Decimal) -> Decimal | None:
    """The exact decimal a value stands for (a float through its shortest form, so 0.1 is
    0.1), or None if it is not finite."""
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if not math.isfinite(value):
        return None
    return Decimal(repr(value))


def _places(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def has_at_most_decimal_places(value: float | Decimal, places: int = MAX_DECIMAL_PLACES) -> bool:
    exact = _exact(value)
    return exact is not None and _places(exact) <= places


@dataclass(frozen=True)
class ChangeViolation:
    field: Literal["change_type", "value"]
    message: str


def validate_change(
    value_kind: ValueKind, unit: str, change_type: ChangeType, value: float | Decimal
) -> ChangeViolation | None:
    """Check one scenario change against the variable's rules (``None`` means valid).

    Exact: a decimal is compared as it is, a float as the decimal it prints as."""
    rules = {rule.change_type: rule for rule in change_rules_for(value_kind, unit)}
    rule = rules.get(change_type)
    if rule is None:
        allowed = ", ".join(sorted(rules))
        return ChangeViolation(
            "change_type", f"'{change_type}' is not allowed for this variable. Allowed: {allowed}."
        )
    exact = _exact(value)
    if exact is None:
        return ChangeViolation("value", "The change must be a finite number.")
    if exact == 0:
        return ChangeViolation(
            "value", "A change of zero has no effect; remove this input instead."
        )
    minimum, maximum = Decimal(repr(rule.minimum)), Decimal(repr(rule.maximum))
    if rule.minimum_exclusive and exact <= minimum:
        return ChangeViolation(
            "value", f"The change must be greater than {rule.minimum:g} {rule.unit_label}."
        )
    if not rule.minimum_exclusive and exact < minimum:
        return ChangeViolation(
            "value", f"The change must be at least {rule.minimum:g} {rule.unit_label}."
        )
    if exact > maximum:
        return ChangeViolation(
            "value", f"The change must be at most {rule.maximum:g} {rule.unit_label}."
        )
    if _places(exact) > MAX_DECIMAL_PLACES:
        return ChangeViolation("value", f"Use at most {MAX_DECIMAL_PLACES} decimal places.")
    return None
