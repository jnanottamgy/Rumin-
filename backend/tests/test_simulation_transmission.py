"""Shock propagation along accepted relationships: paths, lags, cycles and limits.

The graphs here are abstract (nodes a, b, c…): the engine is tested on its own, with no
knowledge graph and no model.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import permutations

import pytest

from app.simulation.transmission import (
    HARD_MAX_DEPTH,
    Link,
    Shock,
    TransmissionLimitError,
    propagate,
)

D = Decimal
Z = D(0)


def link(source: str, target: str, coefficient: str = "1", lag: int = 0) -> Link:
    return Link(
        rule_id=f"{source}{target}",
        edge_key=f"e-{source}{target}",
        source=source,
        target=target,
        coefficient=D(coefficient),
        lag=lag,
    )


SHOCK = Shock("x", "a", D("0.1"))


def test_a_shock_reaches_its_own_node_at_once_and_is_the_zero_length_path() -> None:
    result = propagate([SHOCK], [], horizon=3, max_depth=4)

    assert [path.nodes for path in result.paths] == [("a",)]
    assert result.series["a"] == (D("0.1"), D("0.1"), D("0.1"))
    assert result.at("unrelated", 2) == 0


def test_coefficients_multiply_and_lags_add_along_a_chain() -> None:
    links = [link("a", "b", "0.5", lag=1), link("b", "c", "2", lag=2)]
    result = propagate([SHOCK], links, horizon=5, max_depth=4)

    assert [(p.nodes, p.coefficient, p.lag, p.first_month) for p in result.paths] == [
        (("a",), D(1), 0, 1),
        (("a", "b"), D("0.5"), 1, 2),
        (("a", "b", "c"), D("1.0"), 3, 4),
    ]
    assert result.series["b"] == (Z, D("0.05"), D("0.05"), D("0.05"), D("0.05"))
    assert result.series["c"] == (Z, Z, Z, D("0.1"), D("0.1"))
    # Every contribution names the relationships that carried it.
    assert result.paths_to("c")[0].edge_keys == ("e-ab", "e-bc")


def test_contributions_from_every_path_add_up() -> None:
    """a → b → d and a → c → d both reach d; d gets the sum."""
    links = [link("a", "b", "0.5"), link("a", "c", "0.2"), link("b", "d"), link("c", "d")]
    result = propagate([SHOCK], links, horizon=1, max_depth=4)

    assert sorted(p.nodes for p in result.paths_to("d")) == [("a", "b", "d"), ("a", "c", "d")]
    assert result.final("d") == D("0.07")


def test_a_cycle_never_feeds_a_shock_back_into_itself() -> None:
    links = [link("a", "b"), link("b", "c"), link("c", "a"), link("b", "a")]
    result = propagate([SHOCK], links, horizon=1, max_depth=6)

    assert [p.nodes for p in result.paths] == [("a",), ("a", "b"), ("a", "b", "c")]
    assert result.final("a") == D("0.1")  # only the shock itself


def test_paths_longer_than_the_maximum_depth_are_not_followed() -> None:
    links = [link("a", "b"), link("b", "c"), link("c", "d")]

    shallow = propagate([SHOCK], links, horizon=1, max_depth=1)
    deep = propagate([SHOCK], links, horizon=1, max_depth=3)

    assert [p.nodes[-1] for p in shallow.paths] == ["a", "b"]
    assert [p.nodes[-1] for p in deep.paths] == ["a", "b", "c", "d"]


def test_a_densely_connected_graph_exceeds_the_path_budget_instead_of_being_truncated() -> None:
    nodes = "abcdef"
    links = [link(s, t) for s, t in permutations(nodes, 2)]

    with pytest.raises(TransmissionLimitError, match="More than 50 transmission paths"):
        propagate([SHOCK], links, horizon=1, max_depth=5, max_paths=50)


def test_limits_themselves_are_bounded() -> None:
    with pytest.raises(TransmissionLimitError):
        propagate([SHOCK], [], horizon=1, max_depth=HARD_MAX_DEPTH + 1)
    with pytest.raises(TransmissionLimitError):
        propagate([SHOCK], [], horizon=1, max_depth=2, max_paths=0)
    with pytest.raises(ValueError, match="horizon"):
        propagate([SHOCK], [], horizon=0, max_depth=2)
    with pytest.raises(ValueError, match="negative lag"):
        propagate([SHOCK], [link("a", "b", lag=-1)], horizon=1, max_depth=2)
    with pytest.raises(ValueError, match="before month 1"):
        propagate([Shock("x", "a", D("0.1"), start=0)], [], horizon=1, max_depth=2)


def test_an_effect_that_arrives_after_the_horizon_is_listed_but_not_in_the_series() -> None:
    result = propagate([SHOCK], [link("a", "b", lag=6)], horizon=3, max_depth=2)

    assert result.series["b"] == (Z, Z, Z)
    assert result.paths_to("b")[0].first_month == 7
    assert result.final("b") == D("0.1")  # the steady state still counts it


def test_a_zero_shock_propagates_nothing() -> None:
    result = propagate([Shock("x", "a", D(0))], [link("a", "b")], horizon=2, max_depth=2)

    assert result.paths == ()
    assert result.series == {}


def test_the_result_does_not_depend_on_the_order_of_links_or_shocks() -> None:
    links = [link("a", "b", "0.3", 1), link("a", "c", "0.7"), link("c", "b", "2", 2)]
    shocks = [SHOCK, Shock("y", "c", D("-0.05"), start=2)]

    first = propagate(shocks, links, horizon=6, max_depth=3)
    second = propagate(list(reversed(shocks)), list(reversed(links)), horizon=6, max_depth=3)

    assert first == second
