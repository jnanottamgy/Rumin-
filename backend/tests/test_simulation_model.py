"""The airline fuel-cost model, without a database: definition, validation, equations
(checked against hand calculations), contributions, reproducibility and sensitivity.

All company figures are HYPOTHETICAL round numbers (see ``tests/simulation_support.py``):
a fuel bill of 60,000,000 INR a year, 5,000,000 a month, so each result can be worked
out on paper.
"""

from __future__ import annotations

import time
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from app.simulation import sensitivity as sensitivity_module
from app.simulation.decimal_math import NumericalError, arithmetic, exp, ln, to_output
from app.simulation.definitions import InputCategory, Knowledge, ValueSource, definition_hash
from app.simulation.engine import Preparation, execute
from app.simulation.registry import REGISTRY, ModelRegistry, version_key
from app.simulation.sensitivity import SensitivityError, SensitivityItem, analyse
from tests.simulation_support import (
    MODEL,
    MONTHLY_FUEL,
    codes,
    fx_observation,
    graph,
    inputs,
    near,
    prepare_pure,
    with_model,
)

D = Decimal

# The definition as released. Any change to an equation, input, assumption or text changes
# this hash: release the change as a new model version instead of editing this one.
RELEASED = {
    (
        "airline_fuel_cost",
        "1.0.0",
    ): "5758b04209995f7c10e621443cc8c2275ef3bc00221df42423eda8d2c70c8090"
}


def run(**changes: Any) -> Any:
    preparation = prepare_pure(inputs(**changes))
    assert preparation.ok, preparation.issues
    return execute(preparation)


def output(execution: Any, name: str) -> Decimal:
    return D(execution.outputs[name]["value"])


# --- Definition and registry -------------------------------------------------------------------


def test_the_released_definition_has_not_changed() -> None:
    for (model_id, version), expected in RELEASED.items():
        model = REGISTRY.get(model_id, version)
        assert model is not None
        assert model.definition_hash == expected, (
            f"{model_id} {version} changed. Released versions are immutable: register the "
            "change as a new version (and keep this one for its stored runs)."
        )


def test_the_definition_hash_is_stable_and_sensitive_to_every_change() -> None:
    definition = MODEL.definition
    assert definition_hash(definition) == definition_hash(replace(definition))
    changed = replace(definition, summary=definition.summary + " ")
    assert definition_hash(changed) != definition_hash(definition)


def test_the_registry_serves_the_latest_runnable_version() -> None:
    assert REGISTRY.get("airline_fuel_cost") is MODEL
    assert REGISTRY.get("airline_fuel_cost", "9.9.9") is None
    assert REGISTRY.get("no_such_model") is None
    assert version_key("1.10.0") > version_key("1.9.0")

    newer = with_model(version="1.1.0")
    registry = ModelRegistry([MODEL, newer])
    assert registry.get("airline_fuel_cost") is newer
    assert [m.definition.version for m in registry.versions("airline_fuel_cost")] == [
        "1.1.0",
        "1.0.0",
    ]
    with pytest.raises(ValueError, match="registered twice"):
        ModelRegistry([MODEL, MODEL])


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"id": "Airline"}, "Invalid model id"),
        ({"version": "1.0"}, "MAJOR.MINOR.PATCH"),
        ({"headline_outputs": ("nope",)}, "Headline output"),
        ({"sensitivity_defaults": ("nope",)}, "Sensitivity default"),
        ({"sensitivity_metric": "nope"}, "sensitivity metric"),
        ({"horizon_input": "nope"}, "horizon input"),
        ({"bridge_total": "nope"}, "bridge total"),
    ],
)
def test_an_inconsistent_definition_is_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        replace(MODEL.definition, **changes)


def test_duplicate_inputs_are_refused() -> None:
    definition = MODEL.definition
    with pytest.raises(ValueError, match="Duplicate ids"):
        replace(definition, inputs=(*definition.inputs, definition.inputs[0]))


def test_every_equation_is_documented_and_every_statement_is_cited() -> None:
    definition = MODEL.definition
    cited = {key for eq in definition.equations for key in (*eq.assumptions, *eq.limitations)}
    for equation in definition.equations:
        assert equation.formula and equation.explanation
        assert equation.output.unit and all(term.unit for term in equation.terms)
    assert {item.id for item in definition.assumptions} <= cited | {"A8"}
    for item in definition.inputs:
        if item.category is InputCategory.ASSUMPTION:
            assert item.rationale, f"assumption {item.id} has no rationale"


# --- Validation --------------------------------------------------------------------------------


def test_inputs_are_labelled_by_the_kind_of_knowledge_they_are() -> None:
    preparation = prepare_pure(inputs(hedge_ratio="50", hedge_months="3"))
    knowledge = {key: entry.knowledge for key, entry in preparation.resolved.items()}
    sources = {key: entry.source for key, entry in preparation.resolved.items()}

    assert knowledge["crude_oil_change"] is Knowledge.SCENARIO_INPUT
    assert knowledge["annual_revenue"] is Knowledge.USER_INPUT
    assert knowledge["fx_rate"] is Knowledge.USER_INPUT
    assert knowledge["hedge_ratio"] is Knowledge.ASSUMPTION
    assert knowledge["horizon_months"] is Knowledge.SETTING
    assert sources["hedge_ratio"] is ValueSource.USER
    assert sources["crude_pass_through"] is ValueSource.DEFAULT  # stated, not hidden
    assert preparation.resolved["crude_pass_through"].value == "1"


@pytest.mark.parametrize(
    ("changes", "field", "code", "message"),
    [
        ({"annual_revenue": None}, "annual_revenue", "required", "is required"),
        ({"crude_oil_change": "-100"}, "crude_oil_change", "input_range", "greater than -100 %"),
        ({"crude_oil_change": "1000.5"}, "crude_oil_change", "input_range", "at most 1000 %"),
        ({"crude_oil_change": "2.12345"}, "crude_oil_change", "input_range", "4 decimal places"),
        ({"hedge_ratio": "100.5"}, "hedge_ratio", "input_range", "at most 100 %"),
        ({"horizon_months": "12.5"}, "horizon_months", "input_range", "whole number"),
        ({"horizon_months": "37"}, "horizon_months", "input_range", "at most 36"),
        ({"annual_revenue": "0"}, "annual_revenue", "input_range", "greater than 0"),
        ({"annual_revenue": "1e6"}, "annual_revenue", "input_range", "plain number"),
        ({"annual_revenue": "1,000,000"}, "annual_revenue", "input_range", "plain number"),
        ({"annual_revenue": True}, "annual_revenue", "input_range", "plain number"),
        (
            {"jet_fuel_price": {"value": "750"}},
            "jet_fuel_price",
            "unit_choice",
            "needs a unit",
        ),
        (
            {"jet_fuel_price": {"value": "750", "unit": "usd_per_litre"}},
            "jet_fuel_price",
            "unit_choice",
            "needs a unit",
        ),
        (
            {"fx_rate": {"value": "80", "unit": "percent"}},
            "fx_rate",
            "unit_choice",
            "is not converted",
        ),
        ({"reporting_currency": "inr"}, "reporting_currency", "input_range", "ISO 4217"),
        ({"entity": "Aerisca Airways"}, "entity", "input_range", "node key"),
        ({"surprise": "1"}, "surprise", "unknown_input", "not an input"),
    ],
)
def test_invalid_inputs_are_refused_with_the_reason(
    changes: dict[str, Any], field: str, code: str, message: str
) -> None:
    preparation = prepare_pure(inputs(**changes))

    assert not preparation.ok
    problem = next(issue for issue in preparation.errors if issue.field == field)
    assert problem.code == code
    assert message in problem.message


def test_a_float_is_read_through_its_shortest_form() -> None:
    preparation = prepare_pure(inputs(crude_oil_change=0.1))
    assert preparation.ok
    assert preparation.values is not None
    assert preparation.values.number("crude_oil_change") == D("0.1")


def test_usd_reporting_needs_a_rate_of_exactly_one() -> None:
    refused = prepare_pure(inputs(reporting_currency="USD"))
    accepted = prepare_pure(inputs(reporting_currency="USD", fx_rate="1"))

    assert codes(refused.errors) == ["usd_rate_is_one"]
    assert accepted.ok


def test_a_fuel_bill_larger_than_all_costs_is_an_error_and_a_tiny_one_a_warning() -> None:
    too_big = prepare_pure(inputs(annual_fuel_consumption={"value": "5000", "unit": "kilolitre"}))
    tiny = prepare_pure(inputs(annual_fuel_consumption={"value": "1", "unit": "kilolitre"}))

    assert codes(too_big.errors) == ["fuel_share_exceeds_costs"]
    assert tiny.ok and "fuel_share_low" in codes(tiny.warnings)


def test_timing_that_hides_an_effect_is_reported() -> None:
    preparation = prepare_pure(
        inputs(
            hedge_ratio="50", hedge_months="24", fare_pass_through="30", fare_pass_through_lag="12"
        )
    )
    messages = " ".join(issue.message for issue in preparation.warnings)

    assert preparation.ok
    assert "beyond the 12-month horizon" in messages
    assert "Fares respond only after the horizon" in messages


def test_a_scenario_with_no_change_is_valid_but_says_so() -> None:
    preparation = prepare_pure(inputs(crude_oil_change="0"))
    assert preparation.ok and "no_shock" in codes(preparation.warnings)


def test_a_stored_observation_is_used_exactly_with_its_provenance() -> None:
    choice = {"value": None, "source": "stored_observation"}
    preparation = prepare_pure(inputs(fx_rate=choice), observation=fx_observation())
    entry = preparation.resolved["fx_rate"]

    assert preparation.ok
    assert entry.value == "80.123456789"  # the published digits, not rounded to 6 places
    assert entry.source is ValueSource.STORED_OBSERVATION
    assert entry.knowledge is Knowledge.HISTORICAL_DATA
    assert entry.observation is not None and entry.observation.period_label == "2025"


def test_a_missing_or_mismatched_observation_is_never_filled_in() -> None:
    choice = {"value": None, "source": "stored_observation"}

    missing = prepare_pure(inputs(fx_rate=choice), observation=None)
    wrong_unit = prepare_pure(inputs(fx_rate=choice), observation=fx_observation(unit="USD"))
    wrong_currency = prepare_pure(
        inputs(fx_rate=choice, reporting_currency="EUR"), observation=fx_observation()
    )
    wrong_series = prepare_pure(
        inputs(fx_rate={**choice, "series_id": "wb-ind-fp-cpi-totl-zg"}),
        observation=fx_observation(),
    )

    assert codes(missing.errors) == ["no_stored_observation"]
    assert codes(wrong_unit.errors) == ["observation_matches"]
    assert codes(wrong_currency.errors) == ["observation_matches"]
    assert "does not convert between currencies" in wrong_currency.errors[0].message
    assert codes(wrong_series.errors) == ["observation_matches"]


# --- Graph relationships ------------------------------------------------------------------------


def test_a_crude_shock_needs_the_relationship_confirmed_by_the_graph() -> None:
    preparation = prepare_pure(inputs(), context=graph(confirmed=False))

    assert codes(preparation.errors) == ["channel_confirmed"]
    assert "never propagates" in preparation.errors[0].message
    assert preparation.errors[0].field == "crude_oil_change"


def test_changes_that_act_on_jet_fuel_or_the_currency_directly_need_no_relationship() -> None:
    unconfirmed = graph(confirmed=False)
    fx_only = prepare_pure(inputs(crude_oil_change="0", usd_change="5"), context=unconfirmed)
    margin = prepare_pure(
        inputs(crude_oil_change="0", jet_fuel_margin_change="5"), context=unconfirmed
    )

    assert fx_only.ok and margin.ok


def test_an_assumption_based_relationship_is_flagged_and_evidence_is_not() -> None:
    assumed = prepare_pure(inputs(), context=graph(evidence="model_assumption"))
    evidenced = prepare_pure(inputs(), context=graph(evidence="evidence_backed"))

    assert "assumption_based_channel" in codes(assumed.warnings)
    assert "assumption_based_channel" not in codes(evidenced.warnings)


# --- Equations (hand-calculated) ----------------------------------------------------------------


def test_the_baseline_fuel_bill_converts_units_explicitly() -> None:
    execution = run(
        jet_fuel_price={"value": "2", "unit": "usd_per_us_gallon"},
        annual_fuel_consumption={"value": "10000", "unit": "us_barrel"},
    )
    # 10,000 barrels × 42 gallons = 420,000 gallons × 2 USD = 840,000 USD × 80 = 67,200,000.
    assert output(execution, "annual_consumption_in_price_unit") == D(420_000)
    assert output(execution, "baseline_fuel_cost_usd") == D(840_000)
    assert output(execution, "baseline_fuel_cost") == D(67_200_000)
    conversion = next(step for step in execution.steps if step.equation == "E1")
    assert [(item.symbol, item.value) for item in conversion.inputs] == [
        ("Q", D(10_000)),
        ("λ(u_Q)/λ(u_P)", D(42)),
    ]


def test_a_crude_shock_raises_every_month_of_the_fuel_bill() -> None:
    execution = run()  # crude +10 %, β = 1, no lag, no hedges, no fare pass-through

    assert output(execution, "monthly_baseline_fuel_cost") == MONTHLY_FUEL
    assert output(execution, "jet_fuel_price_change") == D("0.1")
    assert execution.monthly["fuel_cost_change"]["values"] == [D(500_000)] * 12
    assert output(execution, "fuel_cost_change") == D(6_000_000)
    assert output(execution, "operating_profit_change") == D(-6_000_000)
    assert output(execution, "baseline_operating_profit") == D(50_000_000)
    # Margin: (300 − 250) / 300 → (300 − 256) / 300.
    assert near(output(execution, "baseline_operating_margin"), D(1) / 6)
    assert near(output(execution, "scenario_operating_margin"), D(44) / 300)
    assert output(execution, "offsetting_revenue_change") == D("0.02")


def test_the_crude_lag_delays_the_effect() -> None:
    execution = run(crude_pass_through_lag="3")

    values = execution.monthly["fuel_cost_change"]["values"]
    assert values == [D(0)] * 3 + [D(500_000)] * 9
    assert output(execution, "fuel_cost_change") == D(4_500_000)
    assert output(execution, "steady_state_fuel_cost_change") == D(6_000_000)


def test_the_elasticity_scales_the_log_change() -> None:
    execution = run(crude_pass_through="0.5")
    with arithmetic():
        relative = exp(D("0.5") * ln(D("1.1")))  # √1.1
        expected = to_output(12 * MONTHLY_FUEL * (relative - 1))

    assert near(output(execution, "fuel_cost_change"), expected)
    assert near(output(execution, "jet_fuel_price_change"), to_output(relative - 1))


def test_a_refining_margin_change_combines_with_crude_multiplicatively() -> None:
    execution = run(jet_fuel_margin_change="10")  # (1.1)(1.1) − 1 = 0.21

    assert near(output(execution, "jet_fuel_price_change"), D("0.21"))
    assert near(output(execution, "fuel_cost_change"), D(12_600_000))


def test_hedges_fix_the_dollar_price_of_the_hedged_share_while_they_last() -> None:
    execution = run(hedge_ratio="50", hedge_months="3")
    values = execution.monthly["fuel_cost_change"]["values"]

    assert values == [D(250_000)] * 3 + [D(500_000)] * 9
    assert output(execution, "gross_fuel_cost_change") == D(6_000_000)
    assert output(execution, "hedging_effect") == D(-750_000)
    assert output(execution, "fuel_cost_change") == D(5_250_000)


def test_hedges_do_not_cover_the_exchange_rate() -> None:
    # Months 1–3: 1.1 × (0.5 + 0.5 × 1.1) − 1 = 0.155; months 4–12: 1.1 × 1.1 − 1 = 0.21.
    execution = run(usd_change="10", hedge_ratio="50", hedge_months="3")
    values = execution.monthly["fuel_cost_change"]["values"]

    assert [near(v, D(775_000)) for v in values[:3]] == [True] * 3
    assert [near(v, D(1_050_000)) for v in values[3:]] == [True] * 9


@pytest.mark.parametrize(("lag", "recovered"), [(0, 2_400_000), (2, 2_000_000), (12, 0)])
def test_fares_recover_part_of_the_change_after_their_lag(lag: int, recovered: int) -> None:
    execution = run(fare_pass_through="40", fare_pass_through_lag=str(lag))

    assert output(execution, "fare_recovery") == D(recovered)
    assert output(execution, "operating_profit_change") == D(recovered - 6_000_000)


def test_the_steady_state_ignores_hedges_and_lags() -> None:
    execution = run(fare_pass_through="40", hedge_ratio="50", hedge_months="3")

    assert output(execution, "steady_state_fuel_cost_change") == D(6_000_000)
    assert output(execution, "steady_state_operating_profit_change") == D(-3_600_000)


def test_the_accounting_bridge_closes() -> None:
    execution = run(
        usd_change="5",
        hedge_ratio="50",
        hedge_months="3",
        fare_pass_through="40",
        fare_pass_through_lag="2",
    )
    bridge = execution.bridge

    assert [step["output"] for step in bridge["steps"]] == [
        "gross_fuel_cost_change",
        "hedging_effect",
        "fare_recovery",
    ]
    total = sum((D(step["value"]) for step in bridge["steps"]), D(0))
    assert near(total, D(bridge["total"]["value"]), quanta=3)
    assert bridge["total"]["value"] == output(execution, "operating_profit_change")


def test_a_margin_that_would_be_undefined_is_refused() -> None:
    """A loss-making airline, a crude collapse and full fare pass-through: revenue over the
    horizon would turn negative, so there is no margin to report."""
    preparation = prepare_pure(
        inputs(
            annual_revenue="10000000",
            annual_operating_costs="70000000",
            crude_oil_change="-99",
            fare_pass_through="100",
        )
    )
    assert preparation.ok
    with pytest.raises(NumericalError, match="margin is undefined"):
        execute(preparation)


# --- Contributions ------------------------------------------------------------------------------


def test_contributions_split_an_interaction_evenly_and_add_up_to_the_total() -> None:
    execution = run(usd_change="10")  # crude +10 % and the dollar +10 %
    credits = {
        item["input"]: D(item["value"]) for item in execution.contributions["fuel_cost_change"]
    }

    # v(crude) = v(usd) = 6,000,000; v(both) = 12,600,000: each gets 6,300,000.
    assert credits == {"crude_oil_change": D(6_300_000), "usd_change": D(6_300_000)}
    for name, items in execution.contributions.items():
        total = sum((D(item["value"]) for item in items), D(0))
        assert near(total, output(execution, name), quanta=len(items)), name


def test_three_changes_are_attributed_exactly_too() -> None:
    execution = run(
        usd_change="-5",
        jet_fuel_margin_change="3",
        fare_pass_through="25",
        hedge_ratio="30",
        hedge_months="6",
    )
    for name, items in execution.contributions.items():
        assert len(items) == 3
        total = sum((D(item["value"]) for item in items), D(0))
        assert near(total, output(execution, name), quanta=3), name


# --- Reproducibility and the record of a run ----------------------------------------------------


def test_identical_inputs_give_identical_results_and_hashes() -> None:
    first, second = run(usd_change="3.5"), run(usd_change="3.5")

    assert first.inputs_hash == second.inputs_hash
    assert first.result_hash == second.result_hash
    assert first.outputs == second.outputs


def test_any_input_change_changes_the_hashes() -> None:
    base, other = run(), run(hedge_ratio="0.0001", hedge_months="1")

    assert base.inputs_hash != other.inputs_hash
    assert base.result_hash != other.result_hash


def test_equal_numbers_written_differently_hash_the_same() -> None:
    assert run(crude_oil_change="10").inputs_hash == run(crude_oil_change="10.00").inputs_hash


def test_every_step_is_recorded_with_its_inputs() -> None:
    execution = run(horizon_months="6")
    equations = {step.equation for step in execution.steps}
    monthly = [step for step in execution.steps if step.month is not None]

    assert equations == {eq.id for eq in MODEL.definition.equations}
    assert {step.month for step in monthly} == set(range(1, 7))
    assert all(len(item["values"]) == 6 for item in execution.monthly.values())
    assert all(step.inputs for step in execution.steps if step.equation != "E8")
    assert execution.transmission[1]["nodes"] == [
        "variable:var_brent_crude",
        "variable:var_jet_fuel",
    ]
    assert execution.transmission[1]["edge_keys"] == ["e-test-t1"]


def test_only_a_valid_preparation_runs() -> None:
    preparation = prepare_pure(inputs(hedge_ratio="200"))
    with pytest.raises(ValueError, match="Only a valid preparation"):
        execute(preparation)


# --- Sensitivity --------------------------------------------------------------------------------


def base_preparation(**changes: Any) -> Preparation:
    preparation = prepare_pure(inputs(**changes))
    assert preparation.ok
    return preparation


def test_the_default_analysis_ranks_inputs_by_their_effect() -> None:
    analysis = analyse(
        base_preparation(fare_pass_through="40"),
        [SensitivityItem(name) for name in MODEL.definition.sensitivity_defaults],
        metric="operating_profit_change",
    )
    spreads = [D(entry["spread"]) for entry in analysis["ranking"]]

    assert analysis["base"]["operating_profit_change"] == D(-3_600_000)
    assert spreads == sorted(spreads, reverse=True)
    points = [point for item in analysis["items"] for point in item["points"]]
    skipped = [point for point in points if point["skipped"]]
    assert analysis["evaluations"] == 1 + len(points) - len(skipped)
    # The hedge ratio is 0 %: its low point (−20 %) is impossible and is skipped.
    assert [point["value"] for point in skipped] == ["-20"]


def test_a_relative_variation_moves_one_input_and_keeps_the_rest() -> None:
    analysis = analyse(
        base_preparation(),
        [SensitivityItem("jet_fuel_price", "relative", D(10))],
        metric="operating_profit_change",
    )
    item = analysis["items"][0]
    low, high = item["points"]

    assert (low["value"], high["value"]) == ("675", "825")
    # The fuel bill is linear in the price: ±10 % of the 6,000,000 change.
    assert low["deltas"]["operating_profit_change"] == D(600_000)
    assert high["deltas"]["operating_profit_change"] == D(-600_000)
    assert item["range"]["spread"] == D(1_200_000)


def test_points_outside_the_allowed_range_are_skipped_not_clipped() -> None:
    analysis = analyse(
        base_preparation(),
        [SensitivityItem("hedge_ratio", "values", values=(D(50), D(150)))],
        metric="fuel_cost_change",
    )
    ok, skipped = analysis["items"][0]["points"]

    assert ok["skipped"] is None and ok["outputs"] is not None
    assert skipped["outputs"] is None and "at most 100 %" in skipped["skipped"]


def test_a_point_that_needs_an_unconfirmed_relationship_is_skipped() -> None:
    preparation = prepare_pure(
        inputs(crude_oil_change="0", usd_change="5"), context=graph(confirmed=False)
    )
    analysis = analyse(
        preparation,
        [SensitivityItem("crude_oil_change", "values", values=(D(10),))],
        metric="fuel_cost_change",
    )
    assert "never propagates" in analysis["items"][0]["points"][0]["skipped"]


@pytest.mark.parametrize(
    ("requests", "message"),
    [
        ([], "at least one input"),
        ([SensitivityItem(f"i{n}") for n in range(9)], "At most 8 inputs"),
        ([SensitivityItem("hedge_ratio")] * 2, "only once"),
        ([SensitivityItem("nope")], "not an input"),
        ([SensitivityItem("reporting_currency", "values", values=(D(1),))], "not a number"),
        ([SensitivityItem("horizon_months", "absolute", D(1))], "is a setting"),
        ([SensitivityItem("hedge_months", "relative", D(10))], "counts months"),
        ([SensitivityItem("hedge_ratio", "relative", D(100))], "below 100 %"),
        ([SensitivityItem("hedge_ratio", "absolute", D(0))], "must be positive"),
        ([SensitivityItem("hedge_ratio", "values")], "at least one value"),
        (
            [SensitivityItem("hedge_ratio", "values", values=tuple(D(n) for n in range(8)))],
            "At most 7 values",
        ),
    ],
)
def test_requests_beyond_the_limits_are_refused(
    requests: list[SensitivityItem], message: str
) -> None:
    with pytest.raises(SensitivityError, match=message):
        analyse(base_preparation(), requests, metric="fuel_cost_change")


def test_an_unknown_metric_is_refused() -> None:
    with pytest.raises(SensitivityError, match="not an output"):
        analyse(base_preparation(), [SensitivityItem("hedge_ratio")], metric="profit")


def test_the_number_of_evaluations_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sensitivity_module, "MAX_EVALUATIONS", 3)
    with pytest.raises(SensitivityError, match="the limit is 3"):
        analyse(
            base_preparation(),
            [SensitivityItem("hedge_ratio"), SensitivityItem("fx_rate")],
            metric="fuel_cost_change",
        )


def test_an_analysis_that_runs_too_long_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter(range(0, 1000, 5))
    monkeypatch.setattr(time, "monotonic", lambda: float(next(clock)))
    with pytest.raises(SensitivityError, match="exceeded 1 seconds"):
        analyse(
            base_preparation(),
            [SensitivityItem("hedge_ratio")],
            metric="fuel_cost_change",
            deadline_seconds=1,
        )
