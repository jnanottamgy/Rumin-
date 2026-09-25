"""Monte Carlo and joint sensitivity analyses of a planned scenario (the same members an
execution stores), checked against hand calculations and exact properties.

The scenario is the HYPOTHETICAL reference scenario of ``scenario_support``; the
distributions are chosen for the tests and describe nothing real.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.scenario_lab import joint, montecarlo
from app.scenario_lab.executor import Member, members_of
from app.scenario_lab.montecarlo import Assumption, MonteCarloError
from app.scenario_lab.sampling import Discrete, Triangular, Uniform
from app.scenario_lab.sensitivity import Item
from app.scenario_lab.spec import ScenarioSpec
from app.schemas.scenario import ScenarioInput
from app.services import scenarios as scenario_service
from tests.scenario_support import D, brent_only, reference

REPO = "change:var_rbi_repo_rate"
CRUDE = "change:var_brent_crude"
USD = "change:var_usd_inr"


def planned(session: Session, body: dict[str, Any]) -> tuple[ScenarioSpec, list[Member]]:
    """What an execution of ``body`` would run (the members it stores), without storing it."""
    plan = scenario_service.plan_for(
        session, scenario_service.to_spec(ScenarioInput.model_validate(body))
    )
    return plan.spec, members_of(plan)


def without_timing(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "duration_ms"}


# --- Monte Carlo ------------------------------------------------------------------------------


def test_monte_carlo_matches_the_exact_answer_for_a_linear_line(built_graph: Session) -> None:
    # Interest on 100,000,000 of repo-linked debt, repriced after 3 months of 12: a change of
    # Δ points costs 100,000,000 × Δ % × 9/12 = 750,000 × Δ. With Δ uniform on [0, 1] the
    # line's mean is 375,000 and its standard deviation 750,000 / √12 = 216,506.35.
    spec, members = planned(built_graph, reference())

    result = montecarlo.run(
        spec,
        members,
        [Assumption(REPO, Uniform(D(0), D(1)))],
        metric="interest_expense",
        draws=2_000,
        seed=12345,
    )

    summary = result["summary"]
    assert (result["accepted"], result["rejected"]) == (2_000, 0)
    assert abs(D(summary["mean"]) - D(375_000)) < 4 * D(summary["standard_error"])
    assert abs(float(summary["standard_deviation"]) / (750_000 / math.sqrt(12)) - 1) < 0.05
    # A linear, increasing line: its ranks are the change's ranks.
    assert result["quantities"][0]["rank_correlation"] == "1"
    values = [D(entry["value"]) for entry in summary["percentiles"]]
    assert values == sorted(values)
    assert D("0") <= D(summary["minimum"]) and D(summary["maximum"]) <= D(750_000)
    assert sum(item["count"] for item in result["histogram"]) == 2_000
    assert result["convergence"]["checkpoints"][-1]["mean"] == summary["mean"]
    assert result["notes"] == [montecarlo.CONDITIONAL_NOTE]
    assert summary["share_below_zero"] == "0"


def test_a_seed_reproduces_a_monte_carlo_analysis_exactly(built_graph: Session) -> None:
    spec, members = planned(built_graph, reference())
    quantities = [
        Assumption(CRUDE, Triangular(D(-10), D(20), D(60))),
        Assumption(USD, Uniform(D(0), D(10))),
        Assumption(
            "model:floating_rate_interest:repo_repricing_lag",
            Discrete((D(0), D(3), D(6)), (D(1), D(2), D(1))),
        ),
    ]

    def analysis(seed: int) -> dict[str, Any]:
        return montecarlo.run(
            spec, members, quantities, metric="profit_before_tax", draws=300, seed=seed
        )

    first, again, other = analysis(7), analysis(7), analysis(8)

    assert without_timing(first) == without_timing(again)
    assert first["summary"]["mean"] != other["summary"]["mean"]
    assert montecarlo.INDEPENDENCE_NOTE in first["notes"]
    # Crude oil drives profit before tax far more than the others, and against it; a weaker
    # rupee costs more in fuel than it adds in net dollar revenue; the repricing lag only
    # moves a few months of interest.
    rho = {item["target"]: D(item["rank_correlation"]) for item in first["quantities"]}
    lag = rho["model:floating_rate_interest:repo_repricing_lag"]
    assert rho[CRUDE] < D("-0.9")
    assert D("-0.9") < rho[USD] < D(0)
    assert abs(lag) < D("0.1")
    ids = [item["id"] for item in first["outputs"]]
    assert ids[:5] == [
        "revenue",
        "operating_costs",
        "operating_profit",
        "interest_expense",
        "profit_before_tax",
    ]


def test_draws_that_break_a_model_rule_are_rejected_and_counted(built_graph: Session) -> None:
    # Dollar revenue × 80 cannot exceed annual revenue of 300,000,000: above 3,750,000 USD a
    # year (a quarter of this range) a draw is rejected, never clipped.
    spec, members = planned(built_graph, reference())

    result = montecarlo.run(
        spec,
        members,
        [Assumption("model:fx_exposure:annual_usd_revenue", Uniform(D(0), D(5_000_000)))],
        metric="operating_profit",
        draws=400,
        seed=3,
        threshold=D(-6_000_000),
    )

    assert result["accepted"] + result["rejected"] == 400
    assert 60 < result["rejected"] < 140
    [rejection] = result["rejections"]
    assert rejection["code"] == "usd_revenue_within_revenue"
    assert rejection["count"] == result["rejected"]
    assert "exceeds annual revenue" in rejection["example"]
    assert any("were rejected" in note for note in result["notes"])
    assert D(result["quantities"][0]["accepted_mean"]) < D(3_750_000)
    assert result["summary"]["share_at_or_below_threshold"] is not None
    assert result["summary"]["threshold"] == "-6000000"


def test_too_few_valid_draws_give_no_summary(built_graph: Session) -> None:
    spec, members = planned(built_graph, reference())

    with pytest.raises(MonteCarloError, match="Only 0 of 200 draws were valid"):
        montecarlo.run(
            spec,
            members,
            [
                Assumption(
                    "model:fx_exposure:annual_usd_revenue", Uniform(D(4_000_000), D(5_000_000))
                )
            ],
            metric="operating_profit",
            draws=200,
            seed=1,
        )


@pytest.mark.parametrize(
    ("quantities", "message"),
    [
        ([], "at least one quantity"),
        ([Assumption("change:var_nothing", Uniform(D(0), D(1)))], "not a quantity"),
        (
            [Assumption(REPO, Uniform(D(0), D(1))), Assumption(REPO, Uniform(D(0), D(2)))],
            "only one distribution",
        ),
        ([Assumption(REPO, Uniform(D(1), D(0)))], "low below its high"),
        (
            [Assumption("model:airline_fuel_cost:hedge_ratio", Uniform(D(0), D(120)))],
            "must be at most 100 %",
        ),
        (
            [Assumption("model:airline_fuel_cost:hedge_ratio", Uniform(D(0), D("10.12345")))],
            "at most 4 decimal places",
        ),
        (
            [Assumption("model:airline_fuel_cost:hedge_months", Uniform(D(0), D(6)))],
            "discrete distribution",
        ),
        (
            [Assumption(f"change:var_{index}", Uniform(D(0), D(1))) for index in range(9)],
            "At most 8",
        ),
    ],
)
def test_distributions_are_checked_before_any_draw(
    built_graph: Session, quantities: list[Assumption], message: str
) -> None:
    spec, members = planned(built_graph, reference())

    with pytest.raises(MonteCarloError, match=message):
        montecarlo.run(spec, members, quantities, metric="operating_profit", draws=100, seed=1)


def test_monte_carlo_limits(built_graph: Session) -> None:
    spec, members = planned(built_graph, brent_only())
    crude = [Assumption(CRUDE, Uniform(D(0), D(40)))]

    with pytest.raises(MonteCarloError, match="between 100 and 2,000 draws"):
        montecarlo.run(spec, members, crude, metric="operating_profit", draws=99, seed=1)
    with pytest.raises(MonteCarloError, match="no interest coverage"):
        montecarlo.run(spec, members, crude, metric="interest_coverage", draws=100, seed=1)
    with pytest.raises(MonteCarloError, match="stopped after"):
        montecarlo.run(
            spec,
            members,
            crude,
            metric="operating_profit",
            draws=100,
            seed=1,
            deadline_seconds=0,
        )


def test_whole_month_inputs_draw_whole_months(built_graph: Session) -> None:
    spec, members = planned(built_graph, reference())

    result = montecarlo.run(
        spec,
        members,
        [
            Assumption(
                "model:floating_rate_interest:repo_repricing_lag",
                Discrete((D(0), D(3), D(6)), (D(1), D(2), D(1))),
            )
        ],
        metric="interest_expense",
        draws=400,
        seed=2,
    )

    # 750,000 × 0.5 × (12 − lag) / 9 ... only three values are possible: lags 0, 3 and 6.
    distinct = {bin_["count"] > 0 for bin_ in result["histogram"]}
    assert distinct == {True, False}
    p = {entry["p"]: D(entry["value"]) for entry in result["summary"]["percentiles"]}
    assert {p[5], p[50], p[95]} <= {D(500_000), D(375_000), D(250_000)}


# --- Joint sensitivity ------------------------------------------------------------------------


def test_the_crude_and_rupee_interaction_matches_a_hand_calculation(built_graph: Session) -> None:
    # Fuel costs 5,000,000 a month. Crude acts from month 2 (a one-month lag); 40 % is hedged
    # for 6 months: 5 × 0.6 + 6 × 1 = 9 month-equivalents carry both changes. Crude ±10 points
    # and the dollar ±5 points interact by 5,000,000 × 9 × 0.10 × 0.05 = 225,000 on costs;
    # half of the cost change reaches fares two months later (months 2–10: 5 × 0.6 + 4 = 7
    # month-equivalents): 87,500 back in revenue. On operating profit: ∓137,500.
    spec, members = planned(built_graph, reference())

    result = joint.run(spec, members, Item(CRUDE), Item(USD), metric="operating_profit")

    assert (result["rows"]["values"], result["columns"]["values"]) == (
        ["10", "20", "30"],
        ["0", "5", "10"],
    )
    interactions = [[cell["interaction"] for cell in row] for row in result["cells"]]
    assert interactions == [
        ["-137500", "0", "137500"],
        ["0", "0", "0"],
        ["137500", "0", "-137500"],
    ]
    assert result["cells"][1][1] == {
        "metric": result["base"],
        "delta": "0",
        "interaction": "0",
        "skipped": None,
    }
    assert result["summary"]["additive"] is False
    assert result["evaluations"] == 9  # eight cells and the execution itself


def test_quantities_acting_on_different_lines_add_up(built_graph: Session) -> None:
    spec, members = planned(built_graph, reference())

    result = joint.run(spec, members, Item(CRUDE), Item(REPO), metric="profit_before_tax")

    assert {cell["interaction"] for row in result["cells"] for cell in row} == {"0"}
    assert result["summary"]["additive"] is True


def test_a_joint_cell_that_breaks_a_rule_is_skipped(built_graph: Session) -> None:
    # Revenue of 30,000,000 is below the dollar revenue's 40,000,000 at 80: the fx model
    # refuses it, so that row is skipped and its interactions are not computed.
    spec, members = planned(built_graph, reference())

    result = joint.run(
        spec,
        members,
        Item("shared:annual_revenue", mode="values", values=(D(30_000_000),)),
        Item(USD),
        metric="operating_margin",
    )

    low = result["cells"][0]
    assert all(cell["skipped"] and cell["interaction"] is None for cell in low)
    assert result["summary"]["skipped"] == 3
    assert result["cells"][1][1]["delta"] == "0"


@pytest.mark.parametrize(
    ("rows", "columns", "message"),
    [
        (Item(CRUDE), Item(CRUDE), "two different quantities"),
        (Item("change:var_nothing"), Item(USD), "not a quantity"),
        (
            Item("model:airline_fuel_cost:hedge_ratio", mode="values", values=(D(150),)),
            Item(USD),
            "must be at most 100 %",
        ),
        (
            Item(CRUDE, mode="values", values=tuple(D(value) for value in range(1, 8))),
            Item(USD),
            "At most 7 values",
        ),
    ],
)
def test_joint_axes_are_checked_first(
    built_graph: Session, rows: Item, columns: Item, message: str
) -> None:
    spec, members = planned(built_graph, reference())

    with pytest.raises(joint.JointError, match=message):
        joint.run(spec, members, rows, columns, metric="operating_profit")
