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


def has_at_most_decimal_places(value: float, places: int = MAX_DECIMAL_PLACES) -> bool:
    return math.isclose(round(value, places), value, rel_tol=0.0, abs_tol=1e-12)


@dataclass(frozen=True)
class ChangeViolation:
    field: Literal["change_type", "value"]
    message: str


def validate_change(
    value_kind: ValueKind, unit: str, change_type: ChangeType, value: float
) -> ChangeViolation | None:
    """Check one scenario change against the variable's rules (``None`` means valid)."""
    rules = {rule.change_type: rule for rule in change_rules_for(value_kind, unit)}
    rule = rules.get(change_type)
    if rule is None:
        allowed = ", ".join(sorted(rules))
        return ChangeViolation(
            "change_type", f"'{change_type}' is not allowed for this variable. Allowed: {allowed}."
        )
    if not math.isfinite(value):
        return ChangeViolation("value", "The change must be a finite number.")
    if value == 0:
        return ChangeViolation(
            "value", "A change of zero has no effect; remove this input instead."
        )
    if rule.minimum_exclusive and value <= rule.minimum:
        return ChangeViolation(
            "value", f"The change must be greater than {rule.minimum:g} {rule.unit_label}."
        )
    if not rule.minimum_exclusive and value < rule.minimum:
        return ChangeViolation(
            "value", f"The change must be at least {rule.minimum:g} {rule.unit_label}."
        )
    if value > rule.maximum:
        return ChangeViolation(
            "value", f"The change must be at most {rule.maximum:g} {rule.unit_label}."
        )
    if not has_at_most_decimal_places(value):
        return ChangeViolation("value", f"Use at most {MAX_DECIMAL_PLACES} decimal places.")
    return None
