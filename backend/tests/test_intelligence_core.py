"""The intelligence engine's building blocks, without a database: exact statistics,
thresholds, the evidence model, change detection on a history, and exposure over a
hand-built graph (validated edges only). Values are SYNTHETIC and worked out by hand.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.intelligence import fmt, serialize
from app.intelligence.exposure import analyse
from app.intelligence.graphview import EdgeInfo, GraphSlice, NodeInfo
from app.intelligence.model import (
    Basis,
    ChainError,
    Grade,
    InsightDraft,
    Period,
    Ref,
    Step,
    evidence_of,
    insight_id,
)
from app.intelligence.series import (
    DatasetInfo,
    History,
    Point,
    Subject,
    anomaly,
    changes,
    meets,
    threshold_for,
    trend,
    volatility,
)
from app.intelligence.stats import (
    least_squares,
    mad,
    median,
    modified_z,
    percentile_rank,
    point_change,
    relative_change,
    sample_std,
    t_critical,
)
from app.intelligence.thresholds import DEFAULTS, ThresholdError, resolve

D = Decimal
WHEN = datetime(2026, 9, 1, tzinfo=UTC)
SYNTHETIC = DatasetInfo("synthetic", "Synthetic test values", "1", True, "none", None)


def history(
    values: list[str],
    *,
    measure: str = "relative",
    first_year: int = 2010,
    years: list[int] | None = None,
) -> History:
    """A SYNTHETIC annual series."""
    periods = years or list(range(first_year, first_year + len(values)))
    subject = Subject(
        kind="series",
        id="synthetic-series",
        name="Synthetic series",
        unit="units",
        frequency="annual",
        measure=measure,
        variable_id=None,
        variable_relation=None,
        country=None,
        dataset=SYNTHETIC,
    )
    points = tuple(
        Point(
            label=str(year),
            start=date(year, 1, 1),
            value=D(value),
            record_id=index + 1,
            revision=1,
            quality_status="validated",
            flags=None,
            retrieved_at=WHEN,
            last_confirmed_at=WHEN,
        )
        for index, (year, value) in enumerate(zip(periods, values, strict=True))
    )
    return History(subject, points)


# --- Statistics ------------------------------------------------------------------------------


def test_least_squares_is_exact() -> None:
    fit = least_squares([D("73.9"), D("78.6"), D("82.6"), D("84.2"), D("92.1")])

    assert fit.slope == D("4.2")  # Σ(x−x̄)(y−ȳ) = 42, Σ(x−x̄)² = 10
    assert fit.intercept == D("73.88")
    assert fit.t is not None and fit.t.quantize(D("0.0001")) == D("8.3511")
    assert not fit.exact_fit


def test_a_straight_line_has_no_t_statistic() -> None:
    fit = least_squares([D(1), D(3), D(5), D(7)])

    assert fit.slope == D(2) and fit.exact_fit and fit.t is None
    with pytest.raises(ValueError, match="at least two"):
        least_squares([D(1)])


def test_student_t_critical_values_come_from_the_table() -> None:
    assert t_critical(3, "0.05") == D("3.182")
    assert t_critical(10, "0.01") == D("3.169")
    # Between rows and beyond the table the larger (stricter) value is used.
    assert t_critical(35, "0.05") == D("2.042")
    assert t_critical(1000, "0.05") == D("1.980")


def test_robust_statistics() -> None:
    values = [D(1), D(2), D(3), D(4), D(100)]

    assert median(values) == D(3)
    assert mad(values) == D(1)
    assert modified_z(D(100), values) == D("0.6745") * D(97)
    assert modified_z(D(5), [D(2), D(2), D(2)]) is None  # MAD 0: undefined, never infinite
    assert sample_std([D(2), D(4), D(4), D(4), D(5), D(5), D(7), D(9)]).quantize(D("0.0001")) == D(
        "2.1381"
    )
    assert percentile_rank(D(3), [D(1), D(2), D(3), D(4)]) == D(75)


def test_relative_changes_need_a_positive_base() -> None:
    change = relative_change(D("84.2"), D("92.1"))
    assert change is not None and change.quantize(D("1e-10")) == D("9.3824228029")
    assert relative_change(D(0), D(5)) is None
    assert relative_change(D(-2), D(5)) is None
    assert point_change(D("4.9"), D("3.1")) == D("-1.8")


# --- Thresholds ------------------------------------------------------------------------------


def test_thresholds_default_and_override() -> None:
    assert resolve(None) is DEFAULTS
    used = resolve({"relative_change_percent": "2.5", "window": 7, "trend_significance": "0.01"})

    assert used.relative_change_percent == D("2.5")
    assert used.window == 7 and used.window_for("monthly") == 7
    assert DEFAULTS.window_for("annual") == 5 and DEFAULTS.window_for("daily") == 20
    assert used.to_json()["relative_change_percent"] == "2.5"


def test_every_invalid_threshold_is_reported_at_once() -> None:
    with pytest.raises(ThresholdError) as caught:
        resolve(
            {
                "relative_change_percent": "0",
                "point_change": "abc",
                "trend_significance": "0.2",
                "min_history": "4.5",
                "anomaly_score": True,
                "unknown": "1",
            }
        )

    fields = [problem.field for problem in caught.value.problems]
    assert fields == [
        "relative_change_percent",
        "point_change",
        "trend_significance",
        "min_history",
        "anomaly_score",
        "unknown",
    ]


# --- Evidence ----------------------------------------------------------------------------------


def test_the_grade_is_the_weakest_step() -> None:
    chain = [
        Step(Basis.OBSERVATION, "a stored value"),
        Step(Basis.RELATIONSHIP, "an edge", evidence_status="analyst_created"),
        Step(Basis.RELATIONSHIP, "an assumed edge", evidence_status="model_assumption"),
        Step(Basis.SIMULATION, "a stored run"),
    ]

    evidence = evidence_of(chain)

    assert evidence.grade is Grade.ASSUMED and evidence.weakest_step == 2
    assert evidence.conditional_on_simulation and evidence.includes_observations
    assert "only under the scenario's inputs" in evidence.statement
    assert evidence_of(chain[:2]).grade is Grade.CURATED
    assert evidence_of([Step(Basis.SIMULATION, "run")]).grade is Grade.SIMULATED


def test_an_insight_without_a_chain_cannot_exist() -> None:
    with pytest.raises(ChainError):
        evidence_of([])
    with pytest.raises(ChainError):  # thresholds and assumptions are not evidence
        evidence_of([Step(Basis.THRESHOLD, "5 %"), Step(Basis.ASSUMPTION, "figures")])
    with pytest.raises(ChainError):
        evidence_of([Step(Basis.RELATIONSHIP, "an edge", evidence_status=None)])

    draft = InsightDraft("D01", "change", "h", "s", Ref("series", "x"), {}, Period("analysis", "p"))
    with pytest.raises(ChainError):
        draft.build()


def test_insight_ids_are_stable_and_chains_hold_each_link_once() -> None:
    step = Step(Basis.OBSERVATION, "a stored value", (Ref("observation", "1"),))
    draft = InsightDraft(
        "D01", "change", "h", "s", Ref("series", "x"), {"to": 2}, Period("analysis", "p")
    )
    draft.chain.extend([step, step])

    built = draft.build()

    assert built.chain == (step,)
    assert built.id == insight_id("D01", Ref("series", "x"), {"to": 2})
    assert built.id != insight_id("D01", Ref("series", "x"), {"to": 3})


# --- Change detection on a history -------------------------------------------------------------


def test_changes_are_relative_for_levels_and_points_for_rates() -> None:
    levels = changes(history(["80", "84", "0", "5"]))
    rates = changes(history(["4.9", "3.1"], measure="points"))

    assert [c.value for c in levels] == [D(5), D(-100)]  # 0 → 5 has no relative change
    assert levels[0].direction == "up" and levels[1].direction == "down"
    assert [c.value for c in rates] == [D("-1.8")]
    assert threshold_for(history(["1"], measure="points").subject, DEFAULTS) == (
        "point_change",
        D(1),
    )


def test_a_gap_in_the_periods_breaks_the_chain() -> None:
    found = changes(history(["100", "110", "121"], years=[2019, 2020, 2022]))

    assert [(c.earlier.label, c.later.label) for c in found] == [("2019", "2020")]


def test_thresholds_select_changes() -> None:
    found = changes(history(["100", "104", "110"]))

    assert [meets(c, DEFAULTS.relative_change_percent) for c in found] == [False, True]


def test_a_trend_is_called_only_beyond_the_critical_value() -> None:
    # 2011–2015: 12, 13, 15, 16, 18 → slope 1.5, standard error 0.1, t = 15 > 3.182
    rising = trend(history(["10", "12", "13", "15", "16", "18"]), DEFAULTS)
    # 111, 112, 113, 114, 160 → slope 10, t = 1.92 < 3.182: no clear direction
    jump = trend(history(["111", "112", "113", "114", "160"]), DEFAULTS)

    assert rising is not None and rising.direction == "rising" and rising.slope == D("1.5")
    assert rising.t == D(15) and rising.critical == D("3.182")
    assert (rising.first, rising.last, rising.window) == ("2011", "2015", 5)
    assert jump is not None and jump.direction == "no_clear_direction" and jump.slope == D(10)


def test_volatility_and_unusual_changes_follow_their_definitions() -> None:
    found = changes(history([str(100 + i) for i in range(15)] + ["160"]))

    unusual = anomaly(found, DEFAULTS)
    assert unusual is not None and unusual.level == "unusual" and unusual.reference == 14

    high = volatility(found, DEFAULTS, "annual")
    assert high is not None and high.level == "high" and high.percentile == D(100)


def test_short_histories_say_so() -> None:
    found = changes(history(["100", "101", "103", "104"]))

    assert anomaly(found, DEFAULTS).level == "insufficient_history"  # type: ignore[union-attr]
    assert volatility(found, DEFAULTS, "annual") is None
    assert trend(history(["1", "2"]), DEFAULTS) is None


# --- Exposure over validated edges only --------------------------------------------------------


def node(key: str, name: str, node_type: str) -> NodeInfo:
    return NodeInfo(key, name, node_type, "fictional", {})


def edge(
    key: str, edge_type: str, source: str, target: str, quality: str = "validated"
) -> EdgeInfo:
    return EdgeInfo(
        key=key,
        edge_type=edge_type,
        label=edge_type.replace("_", " "),
        source=source,
        target=target,
        evidence_status="model_assumption",
        is_illustrative=True,
        quality_status=quality,
        description="",
        caveat="",
        polarity=None,
        strength=None,
        rationale="An assumed effect.",
        evidence_level=None,
        stated_difference=None,
    )


def test_only_validated_exposure_edges_make_paths() -> None:
    graph = GraphSlice(build_id=1)
    for item in (
        node("company:co_a", "Company A", "company"),
        node("company:co_b", "Company B", "company"),
        node("variable:var_x", "Variable X", "economic_variable"),
        node("variable:var_y", "Variable Y", "economic_variable"),
    ):
        graph.nodes[item.key] = item
    graph.add(
        [
            edge("e-0000000000000001", "affects_costs", "variable:var_x", "company:co_a"),
            edge("e-0000000000000002", "competes_with", "company:co_a", "company:co_b"),
        ]
    )
    graph.flagged["e-0000000000000003"] = edge(
        "e-0000000000000003", "affects_revenue", "variable:var_y", "company:co_a", "warning"
    )

    found = analyse(graph, "company:co_a")

    assert [(p.origin.key, p.channel, p.directness) for p in found.paths] == [
        ("variable:var_x", "costs", "direct")
    ]
    assert [e.key for e in found.flagged] == ["e-0000000000000003"]
    assert [link.kind for link in found.context] == ["competitor"]
    assert analyse(graph, "company:co_a", evidence="evidence_backed").paths == ()


# --- Presentation --------------------------------------------------------------------------------


def test_numbers_are_formatted_for_reading_and_kept_exact_as_data() -> None:
    assert fmt.money(D("-6700000"), "INR", sign=True) == "−6,700,000 INR"
    assert fmt.percent(D("-17.6315789474")) == "−17.63 %"
    assert fmt.points(D("0.5")) == "+0.50 percentage points"
    assert fmt.stored(D("84.2000")) == "84.2"
    assert fmt.listing(["a", "b", "c"]) == "a, b and c"
    assert serialize.data({"v": D("1E+3"), "d": date(2024, 1, 1), "t": (D("0.10"),)}) == {
        "v": "1000",
        "d": "2024-01-01",
        "t": ["0.1"],
    }
