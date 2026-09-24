"""The models added in Phase 5, without a database: currency exposure, floating-rate
interest and commodity-linked costs — each checked against hand calculations — and the
inputs every model shares.

All company figures are HYPOTHETICAL round numbers chosen to be worked out on paper: a
company with revenue of 500,000,000 INR a year and operating costs of 400,000,000.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any

import pytest

from app.simulation.engine import execute
from app.simulation.graph_context import GraphContext
from app.simulation.models.common import SHARED_INPUTS
from app.simulation.registry import REGISTRY, RegisteredModel
from tests.simulation_support import codes, prepare_pure

D = Decimal
COMPANY = {
    "reporting_currency": {"value": "INR"},
    "annual_revenue": {"value": "500000000"},
    "annual_operating_costs": {"value": "400000000"},
}


def no_graph() -> GraphContext:
    """These models follow no graph relationship: a built graph with nothing confirmed."""
    return GraphContext(
        build_id=1,
        build_finished_at=None,
        source_fingerprint=None,
        freshness="current",
        transmission={},
        supporting={},
        entity=None,
        unused=(),
        unused_total=0,
        names={},
    )


def model(model_id: str) -> RegisteredModel:
    found = REGISTRY.get(model_id)
    assert found is not None
    return found


def prepare(model_id: str, **values: str) -> Any:
    given = {**COMPANY, **{name: {"value": item} for name, item in values.items()}}
    return prepare_pure(given, context=no_graph(), model=model(model_id))


def run(model_id: str, **values: str) -> Any:
    preparation = prepare(model_id, **values)
    assert preparation.ok, preparation.issues
    return execute(preparation)


def out(execution: Any, name: str) -> Decimal:
    return D(execution.outputs[name]["value"])


# --- Shared inputs -----------------------------------------------------------------------------

KEYS = (
    "unit",
    "units",
    "kind",
    "category",
    "minimum",
    "maximum",
    "minimum_exclusive",
    "maximum_exclusive",
    "max_decimals",
    "required",
    "default",
    "variable",
)


def test_every_model_defines_the_shared_inputs_identically() -> None:
    """A scenario hands one value to every model; the value must mean the same everywhere."""
    for registered in REGISTRY.latest() + REGISTRY.versions("airline_fuel_cost"):
        for item in registered.definition.inputs:
            if item.id not in SHARED_INPUTS:
                continue
            ours, theirs = asdict(SHARED_INPUTS[item.id]), asdict(item)
            assert {key: ours[key] for key in KEYS} == {key: theirs[key] for key in KEYS}, (
                f"{registered.definition.key} redefines the shared input {item.id}."
            )


def test_every_model_is_timed_and_labels_each_output() -> None:
    for registered in REGISTRY.latest():
        definition = registered.definition
        assert definition.shock_start_input == "shock_start_month"
        assert definition.shock_duration_input == "shock_duration_months"
        for output in (*definition.outputs, *definition.monthly_outputs):
            assert output.kind in ("derived", "simulated")


# --- Foreign-currency revenue and costs --------------------------------------------------------

FX = {
    "fx_rate": "80",
    "annual_usd_revenue": "2000000",
    "annual_usd_costs": "500000",
}


def test_currency_exposure_matches_the_hand_calculation() -> None:
    # 2,000,000 USD of revenue and 500,000 USD of costs at 80: 13,333,333.33 and
    # 3,333,333.33 a month. The dollar +5 %; half the revenue hedged for six months.
    execution = run("fx_exposure", fx_change="5", revenue_hedge_ratio="50", hedge_months="6", **FX)

    assert out(execution, "revenue_change") == D(6_000_000)  # 6 × 333,333.33 + 6 × 666,666.67
    assert out(execution, "cost_change") == D(2_000_000)  # 12 × 166,666.67
    assert out(execution, "operating_profit_change") == D(4_000_000)
    assert out(execution, "gross_revenue_change") == D(8_000_000)
    assert out(execution, "revenue_hedging_effect") == D(-2_000_000)
    assert out(execution, "net_usd_exposure") == D(1_500_000)
    assert out(execution, "run_rate_operating_profit_change") == D(6_000_000)  # 1.5M × 80 × 5 %
    assert out(execution, "baseline_operating_margin") == D("0.2")
    assert out(execution, "scenario_operating_margin") == D("0.2055335968")  # 104 ÷ 506
    assert execution.bridge["total"]["value"] == D(4_000_000)


def test_a_stronger_currency_reverses_the_signs() -> None:
    execution = run("fx_exposure", fx_change="-5", **FX)

    assert out(execution, "revenue_change") == D(-8_000_000)
    assert out(execution, "operating_profit_change") == D(-6_000_000)


def test_a_company_with_more_dollar_costs_than_revenue_loses() -> None:
    execution = run(
        "fx_exposure",
        fx_change="10",
        fx_rate="80",
        annual_usd_revenue="0",
        annual_usd_costs="1000000",
    )

    assert out(execution, "operating_profit_change") == D(-8_000_000)
    assert out(execution, "net_usd_exposure") == D(-1_000_000)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"reporting_currency": "USD"}, "not_usd_reporter"),
        ({"annual_usd_revenue": "0", "annual_usd_costs": "0"}, "has_exposure"),
        ({"annual_usd_revenue": "7000000"}, "usd_revenue_within_revenue"),  # 560M > 500M
        ({"annual_usd_costs": "6000000"}, "usd_costs_within_costs"),  # 480M > 400M
        ({"shock_start_month": "13"}, "start_within_horizon"),
    ],
)
def test_currency_exposure_refuses_inconsistent_figures(changes: dict[str, str], code: str) -> None:
    preparation = prepare("fx_exposure", fx_change="5", **{**FX, **changes})

    assert code in codes(preparation.errors)


def test_a_three_month_currency_change_reverts() -> None:
    execution = run("fx_exposure", fx_change="5", shock_duration_months="3", **FX)
    monthly = [D(item) for item in execution.monthly["operating_profit_change"]["values"]]

    # Net 1,500,000 USD × 80 ÷ 12 × 5 % = 500,000 a month while it lasts.
    assert monthly[:3] == [D(500_000)] * 3
    assert monthly[3:] == [D(0)] * 9


# --- Floating-rate interest --------------------------------------------------------------------

DEBT = {
    "annual_interest_expense": "80000000",
    "repo_linked_debt": "1000000000",
    "us_rate_linked_debt": "0",
}


def test_interest_matches_the_hand_calculation() -> None:
    # 1,000,000,000 of repo-linked debt; the repo rate +0.50 points, passed on in full after
    # three months: 1e9 × 0.5 % ÷ 12 = 416,666.67 a month for nine months.
    execution = run(
        "floating_rate_interest", repo_rate_change="0.5", repo_repricing_lag="3", **DEBT
    )

    assert out(execution, "interest_expense_change") == D(3_750_000)
    assert out(execution, "profit_before_tax_change") == D(-3_750_000)
    assert out(execution, "run_rate_interest_change") == D(5_000_000)
    assert out(execution, "baseline_profit_before_tax") == D(20_000_000)  # 500 − 400 − 80 (M)
    assert out(execution, "baseline_interest_coverage") == D("1.25")
    assert out(execution, "scenario_interest_coverage") == D("1.1940298507")  # 100 ÷ 83.75
    monthly = [D(item) for item in execution.monthly["interest_expense_change"]["values"]]
    assert monthly[:3] == [D(0)] * 3
    assert execution.bridge["total"]["value"] == D(-3_750_000)


def test_pass_through_and_both_benchmarks_add_up() -> None:
    execution = run(
        "floating_rate_interest",
        repo_rate_change="1",
        us_rate_change="-0.5",
        repo_pass_through="50",
        annual_interest_expense="80000000",
        repo_linked_debt="600000000",
        us_rate_linked_debt="240000000",
    )

    # Repo: 600M × 50 % × 1 point = 3,000,000 a year; US: 240M × −0.5 point = −1,200,000.
    assert out(execution, "repo_interest_change") == D(3_000_000)
    assert out(execution, "us_interest_change") == D(-1_200_000)
    assert out(execution, "interest_expense_change") == D(1_800_000)
    assert out(execution, "run_rate_interest_change") == D(1_800_000)


def test_a_rate_change_is_recorded_as_percentage_points() -> None:
    execution = run("floating_rate_interest", repo_rate_change="0.25", **DEBT)
    [path] = execution.transmission

    assert (path["kind"], path["log_change"], path["nodes"]) == (
        "level",
        D("0.25"),
        ["variable:var_rbi_repo_rate"],
    )
    in_effect = execution.monthly["repo_rate_change_in_effect"]["values"]
    assert {D(item) for item in in_effect} == {D("0.25")}


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"repo_rate_change": "25.5"}, "input_range"),
        ({"repo_rate_change": "0.12345"}, "input_range"),
        ({"repo_linked_debt": "0"}, "has_floating_debt"),
        ({"annual_interest_expense": "0"}, "interest_positive"),
    ],
)
def test_interest_refuses_invalid_figures(changes: dict[str, str], code: str) -> None:
    preparation = prepare(
        "floating_rate_interest", **{**DEBT, "repo_rate_change": "0.5", **changes}
    )

    assert code in codes(preparation.errors)


def test_repricing_after_the_horizon_is_flagged() -> None:
    preparation = prepare(
        "floating_rate_interest",
        repo_rate_change="0.5",
        repo_repricing_lag="12",
        **DEBT,
    )

    assert preparation.ok
    assert "timing_within_horizon" in codes(preparation.warnings)


# --- Commodity-linked costs --------------------------------------------------------------------


def test_crude_linked_costs_match_the_hand_calculation() -> None:
    # 120,000,000 a year priced off crude (10,000,000 a month); crude +20 %; a quarter hedged
    # for six months; half the change recovered through prices a month later.
    execution = run(
        "crude_linked_costs",
        crude_oil_change="20",
        linked_annual_cost="120000000",
        hedge_ratio="25",
        hedge_months="6",
        price_recovery="50",
        price_recovery_lag="1",
    )

    assert out(execution, "linked_cost_change") == D(21_000_000)  # 6 × 1.5M + 6 × 2M
    assert out(execution, "price_recovery") == D(9_500_000)  # 6 × 0.75M + 5 × 1M
    assert out(execution, "operating_profit_change") == D(-11_500_000)
    assert out(execution, "gross_linked_cost_change") == D(24_000_000)
    assert out(execution, "hedging_effect") == D(-3_000_000)
    assert out(execution, "run_rate_cost_change") == D(24_000_000)
    assert out(execution, "run_rate_operating_profit_change") == D(-12_000_000)
    assert out(execution, "scenario_operating_margin") == D("0.1736997056")  # 88.5 ÷ 509.5
    assert execution.bridge["total"]["value"] == D(-11_500_000)


def test_the_elasticity_and_the_delay_act_on_the_input_price() -> None:
    execution = run(
        "crude_linked_costs",
        crude_oil_change="20",
        linked_annual_cost="120000000",
        cost_pass_through="0.5",
        cost_pass_through_lag="2",
    )
    relative = [D(item) for item in execution.monthly["input_price_relative"]["values"]]

    assert relative[:2] == [D(1), D(1)]
    assert relative[2] == D("1.0954451150")  # √1.2 = exp(0.5 · ln 1.2)
    assert out(execution, "input_price_change") == D("0.0954451150")


def test_gas_linked_costs_follow_henry_hub() -> None:
    gas = model("gas_linked_costs")
    execution = run("gas_linked_costs", gas_price_change="30", linked_annual_cost="60000000")

    assert gas.definition.input("gas_price_change").variable == "variable:var_henry_hub_gas"
    assert out(execution, "linked_cost_change") == D(18_000_000)
    assert gas.definition_hash != model("crude_linked_costs").definition_hash


def test_linked_costs_cannot_exceed_operating_costs() -> None:
    preparation = prepare(
        "crude_linked_costs", crude_oil_change="20", linked_annual_cost="500000000"
    )

    assert codes(preparation.errors) == ["linked_cost_within_costs"]
