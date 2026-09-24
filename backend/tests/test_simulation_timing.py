"""The timing of changes (Phase 5): shock windows, percentage-point shocks, the definition
rules that go with them, and the airline model's version 1.1.0.

Company figures are HYPOTHETICAL round numbers (``tests/simulation_support.py``): a fuel
bill of 5,000,000 INR a month, so each result can be worked out on paper.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from app.simulation.definitions import (
    PERCENTAGE_POINTS,
    InputCategory,
    InputDefinition,
    InputKind,
    definition_hash,
    to_json,
)
from app.simulation.engine import execute, shock_window
from app.simulation.registry import REGISTRY
from app.simulation.transmission import Link, Shock, propagate
from tests.simulation_support import MODEL, codes, inputs, prepare_pure

D = Decimal
V1 = REGISTRY.get("airline_fuel_cost", "1.0.0")
# Half the fuel hedged for three months; 40 % of changes passed on to fares after two.
TERMS = {
    "hedge_ratio": "50",
    "hedge_months": "3",
    "fare_pass_through": "40",
    "fare_pass_through_lag": "2",
}


def run(**changes: Any) -> Any:
    preparation = prepare_pure(inputs(**{**TERMS, **changes}))
    assert preparation.ok, preparation.issues
    return execute(preparation)


def value(execution: Any, name: str) -> Decimal:
    return D(execution.outputs[name]["value"])


# --- Transmission windows ----------------------------------------------------------------------


def test_a_change_lasts_from_its_start_to_its_end_month() -> None:
    propagation = propagate([Shock("x", "a", D("0.1"), start=3, end=5)], [], horizon=8, max_depth=2)

    assert propagation.series["a"] == tuple(
        D(value) for value in ["0", "0", "0.1", "0.1", "0.1", "0", "0", "0"]
    )
    [path] = propagation.paths
    assert (path.first_month, path.last_month) == (3, 5)


def test_a_lag_moves_both_ends_of_the_window() -> None:
    link = Link("ab", "e-ab", "a", "b", D("2"), lag=2)
    propagation = propagate(
        [Shock("x", "a", D("0.1"), start=1, end=3)], [link], horizon=8, max_depth=2
    )

    assert propagation.series["b"] == tuple(
        D(value) for value in ["0", "0", "0.2", "0.2", "0.2", "0", "0", "0"]
    )
    assert propagation.final("b") == D("0.2")  # the run rate while the change lasts


def test_a_window_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValueError, match="ends before it starts"):
        propagate([Shock("x", "a", D("0.1"), start=4, end=3)], [], horizon=6, max_depth=1)


def test_a_percentage_point_change_stays_at_its_own_node() -> None:
    link = Link("ab", "e-ab", "a", "b", D("1"), lag=0)
    propagation = propagate(
        [Shock("x", "a", D("0.5"), kind="level")], [link], horizon=3, max_depth=4
    )

    assert set(propagation.series) == {"a"}
    [path] = propagation.paths
    assert (path.kind, path.log_change, path.nodes) == ("level", D("0.5"), ("a",))


# --- Definition rules --------------------------------------------------------------------------


def test_unset_timing_fields_leave_earlier_definitions_unchanged() -> None:
    assert V1 is not None
    data = to_json(V1.definition)
    assert "shock_start_input" not in data and "shock_duration_input" not in data
    assert to_json(MODEL.definition)["shock_start_input"] == "shock_start_month"


def test_timing_inputs_must_be_integer_inputs() -> None:
    with pytest.raises(ValueError, match="Shock timing input"):
        replace(MODEL.definition, shock_start_input="crude_oil_change")
    with pytest.raises(ValueError, match="Shock timing input"):
        replace(MODEL.definition, shock_duration_input="no_such_input")


def test_a_shock_to_a_graph_variable_must_be_a_percent_or_a_rate_change() -> None:
    wrong = replace(MODEL.definition.input("crude_oil_change"), unit="ratio")
    with pytest.raises(ValueError, match="unit must be one of"):
        replace(
            MODEL.definition,
            inputs=tuple(
                wrong if item.id == "crude_oil_change" else item for item in MODEL.definition.inputs
            ),
        )


def test_a_rate_change_cannot_travel_along_a_log_linear_rule() -> None:
    rate = InputDefinition(
        id="rate_change",
        label="Rate",
        category=InputCategory.SCENARIO_INPUT,
        kind=InputKind.DECIMAL,
        description="A rate change.",
        unit=PERCENTAGE_POINTS,
        required=False,
        default=D(0),
        variable="variable:var_brent_crude",  # the source of rule T1
    )
    with pytest.raises(ValueError, match="percentage points"):
        replace(MODEL.definition, inputs=(*MODEL.definition.inputs, rate))


# --- The airline model, version 1.1.0 ----------------------------------------------------------


def test_version_1_1_0_gives_1_0_0_s_results_when_changes_are_permanent() -> None:
    assert V1 is not None
    old = prepare_pure(inputs(**TERMS), model=V1)
    assert old.ok, old.issues
    first, second = execute(old), run()

    assert first.outputs == second.outputs
    assert second.inputs_hash != first.inputs_hash  # a different definition
    assert definition_hash(MODEL.definition) != definition_hash(V1.definition)


def test_a_change_that_lasts_six_months() -> None:
    # Months 1–3 half hedged (+250,000), 4–6 unhedged (+500,000), then back to baseline.
    execution = run(shock_duration_months="6")

    assert value(execution, "fuel_cost_change") == D(2_250_000)
    # Fares follow two months later: 3 × 100,000 + 3 × 200,000.
    assert value(execution, "fare_recovery") == D(900_000)
    assert value(execution, "operating_profit_change") == D(-1_350_000)
    changes = [D(item) for item in execution.monthly["fuel_cost_change"]["values"]]
    assert changes[6:] == [D(0)] * 6
    values = prepare_pure(inputs(shock_duration_months="6")).values
    assert values is not None
    assert shock_window(MODEL, values) == (1, 6)


def test_a_change_that_starts_in_month_four() -> None:
    # The three months of hedges expire before the change: 9 unhedged months of +500,000.
    execution = run(shock_start_month="4")

    assert value(execution, "fuel_cost_change") == D(4_500_000)
    assert value(execution, "fare_recovery") == D(1_400_000)  # months 6–12 × 200,000
    assert value(execution, "operating_profit_change") == D(-3_100_000)
    assert "timing_within_horizon" in codes(execution.warnings)  # hedges end before month 4


def test_a_temporary_dollar_change_is_a_monthly_factor() -> None:
    # The dollar +10 % for two months only, no crude change: +500,000 in each of two months.
    execution = run(
        crude_oil_change="0",
        usd_change="10",
        shock_duration_months="2",
        hedge_ratio="0",
        hedge_months="0",
    )

    relative = [D(item) for item in execution.monthly["fx_relative"]["values"]]
    assert relative[:3] == [D("1.1"), D("1.1"), D(1)]
    assert value(execution, "fuel_cost_change") == D(1_000_000)
    # The run rate is the effect while the change lasts: 60,000,000 × 10 %.
    assert value(execution, "steady_state_fuel_cost_change") == D(6_000_000)


def test_a_change_must_start_inside_the_horizon() -> None:
    preparation = prepare_pure(inputs(shock_start_month="13"))

    assert not preparation.ok
    assert codes(preparation.errors) == ["start_within_horizon"]


def test_the_transmission_record_carries_the_window() -> None:
    execution = run(shock_start_month="2", shock_duration_months="3")
    crude = [path for path in execution.transmission if path["input"] == "crude_oil_change"]

    assert {(path["first_month"], path["last_month"], path["kind"]) for path in crude} == {
        (2, 4, "log")
    }
