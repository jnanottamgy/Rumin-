"""Pure domain rules — no database or HTTP involved."""

from __future__ import annotations

import math

import pytest

from app.domain.enums import ChangeType, RelationshipType, StructuralLinkType, ValueKind
from app.domain.relationship_types import RELATIONSHIP_TYPES
from app.domain.scenario_rules import change_rules_for, has_at_most_decimal_places, validate_change

PCT = ChangeType.PERCENT_CHANGE
ABS = ChangeType.ABSOLUTE_CHANGE


def test_every_edge_type_is_registered_with_a_meaning() -> None:
    expected = {*RelationshipType, *StructuralLinkType}

    assert set(RELATIONSHIP_TYPES) == expected
    for spec in RELATIONSHIP_TYPES.values():
        assert spec.label and spec.description and spec.allowed_pairs


def test_rates_only_accept_percentage_point_changes() -> None:
    rules = change_rules_for(ValueKind.RATE, "percent per annum")

    assert [rule.change_type for rule in rules] == [ABS]
    assert rules[0].unit_label == "percentage points"


@pytest.mark.parametrize("kind", [ValueKind.PRICE, ValueKind.EXCHANGE_RATE, ValueKind.INDEX])
def test_levels_accept_percent_and_absolute_changes(kind: ValueKind) -> None:
    rules = change_rules_for(kind, "unit")

    assert [rule.change_type for rule in rules] == [PCT, ABS]
    assert rules[1].unit_label == "unit"


@pytest.mark.parametrize(
    ("kind", "change", "value", "field"),
    [
        (ValueKind.PRICE, PCT, 30, None),
        (ValueKind.PRICE, PCT, -99.99, None),
        (ValueKind.PRICE, PCT, -100, "value"),
        (ValueKind.PRICE, PCT, 1000, None),
        (ValueKind.PRICE, PCT, 1000.0001, "value"),
        (ValueKind.PRICE, PCT, 0, "value"),
        (ValueKind.PRICE, PCT, 0.0001, None),
        (ValueKind.PRICE, PCT, 0.00001, "value"),
        (ValueKind.PRICE, ABS, -12.5, None),
        (ValueKind.RATE, ABS, 0.25, None),
        (ValueKind.RATE, ABS, -25, None),
        (ValueKind.RATE, ABS, 25.01, "value"),
        (ValueKind.RATE, PCT, 10, "change_type"),
        (ValueKind.PRICE, PCT, math.inf, "value"),
        (ValueKind.PRICE, PCT, math.nan, "value"),
    ],
)
def test_validate_change(
    kind: ValueKind, change: ChangeType, value: float, field: str | None
) -> None:
    violation = validate_change(kind, "unit", change, value)

    assert (violation.field if violation else None) == field


def test_decimal_place_check_tolerates_binary_floating_point() -> None:
    assert has_at_most_decimal_places(0.1)
    assert has_at_most_decimal_places(30.1234)
    assert not has_at_most_decimal_places(30.12345)
