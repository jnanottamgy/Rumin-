"""Propagation of shocks along accepted relationships. Pure: no database, no clock.

A *link* is a knowledge-graph relationship that one of a model's transmission rules
accepts and that the latest graph build confirms, carrying the coefficient and lag the
model's parameters give it. A *shock* is a step change in a node's level that takes effect
in a given month and lasts until the end of the horizon or for a stated number of months.
A shock to a price or an exchange rate is a log-change (kind ``log``); a shock to a rate is
a change in percentage points (kind ``level``), which is applied at its own node and never
carried along a log-linear link.

The form is log-linear. A shock reaches a node along every simple path of links from the
shocked node, scaled by the product of the path's coefficients and delayed by the sum of
its lags:

    ℓₙ(m) = Σ over paths p from a shock s to n, with startₛ + lagₚ ≤ m ≤ endₛ + lagₚ,
            of (Π βₑ for e in p) · ℓₛ

The shocked node itself is the zero-length path (coefficient 1, lag 0). Safeguards:

* only **simple** paths count — no node appears twice — so a cycle of relationships
  cannot feed a shock back into itself;
* paths are at most ``max_depth`` links long;
* at most ``max_paths`` paths are followed; more raises ``TransmissionLimitError``
  instead of silently dropping some.

Every path is returned with its contribution, so each number can be traced back to the
shock and the relationships that carried it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.simulation.decimal_math import ONE, ZERO, arithmetic

HARD_MAX_DEPTH = 6
HARD_MAX_PATHS = 5_000


ShockKind = Literal["log", "level"]


class TransmissionLimitError(ValueError):
    """The propagation would exceed its depth or path budget."""


@dataclass(frozen=True)
class Link:
    rule_id: str
    edge_key: str | None
    source: str
    target: str
    coefficient: Decimal
    lag: int


@dataclass(frozen=True)
class Shock:
    input_id: str
    node: str
    # The change: a log-change for kind "log", percentage points for kind "level".
    log_change: Decimal
    start: int = 1
    # The last month the change lasts (inclusive); None: until the end of the horizon.
    end: int | None = None
    kind: ShockKind = "log"


@dataclass(frozen=True)
class PathContribution:
    input_id: str
    nodes: tuple[str, ...]
    rules: tuple[str, ...]
    edge_keys: tuple[str | None, ...]
    coefficient: Decimal
    lag: int
    # The first month the contribution applies (start of the shock + the path's lags).
    first_month: int
    # coefficient × the shock's change: the path's full effect on its last node.
    log_change: Decimal
    # The last month it applies (end of the shock + the path's lags); None: to the horizon.
    last_month: int | None = None
    kind: ShockKind = "log"

    @property
    def target(self) -> str:
        return self.nodes[-1]


@dataclass(frozen=True)
class Propagation:
    horizon: int
    series: Mapping[str, tuple[Decimal, ...]]
    paths: tuple[PathContribution, ...]

    def at(self, node: str, month: int) -> Decimal:
        """The node's log-change in ``month`` (1-based); zero for untouched nodes."""
        values = self.series.get(node)
        if values is None:
            return ZERO
        return values[month - 1]

    def final(self, node: str) -> Decimal:
        """The node's change once every lag has elapsed, while the shocks last (the run
        rate): the sum of every path's full effect on it."""
        with arithmetic():
            return sum((path.log_change for path in self.paths if path.target == node), ZERO)

    def paths_to(self, node: str) -> tuple[PathContribution, ...]:
        return tuple(path for path in self.paths if path.target == node)


def propagate(
    shocks: Iterable[Shock],
    links: Iterable[Link],
    *,
    horizon: int,
    max_depth: int,
    max_paths: int = 500,
) -> Propagation:
    """Propagate ``shocks`` along ``links`` over months 1…``horizon``."""
    if horizon < 1:
        raise ValueError("The horizon must be at least one month.")
    if not 0 <= max_depth <= HARD_MAX_DEPTH:
        raise TransmissionLimitError(f"The propagation depth must be 0–{HARD_MAX_DEPTH}.")
    if not 1 <= max_paths <= HARD_MAX_PATHS:
        raise TransmissionLimitError(f"The path budget must be 1–{HARD_MAX_PATHS}.")

    outgoing: dict[str, list[Link]] = defaultdict(list)
    for link in sorted(links, key=lambda item: (item.source, item.target, item.rule_id)):
        if link.lag < 0:
            raise ValueError(f"Link {link.rule_id} has a negative lag.")
        outgoing[link.source].append(link)

    found: list[PathContribution] = []
    with arithmetic():
        for shock in sorted(shocks, key=lambda item: (item.input_id, item.node)):
            if shock.start < 1:
                raise ValueError(f"Shock {shock.input_id} starts before month 1.")
            if shock.end is not None and shock.end < shock.start:
                raise ValueError(f"Shock {shock.input_id} ends before it starts.")
            if shock.log_change == ZERO:
                continue
            # Depth-first over simple paths; an explicit stack keeps deep graphs safe.
            stack: list[tuple[tuple[str, ...], tuple[Link, ...], Decimal, int]] = [
                ((shock.node,), (), ONE, 0)
            ]
            while stack:
                nodes, via, coefficient, lag = stack.pop()
                found.append(
                    PathContribution(
                        input_id=shock.input_id,
                        nodes=nodes,
                        rules=tuple(link.rule_id for link in via),
                        edge_keys=tuple(link.edge_key for link in via),
                        coefficient=coefficient,
                        lag=lag,
                        first_month=shock.start + lag,
                        log_change=coefficient * shock.log_change,
                        last_month=None if shock.end is None else shock.end + lag,
                        kind=shock.kind,
                    )
                )
                if len(found) > max_paths:
                    raise TransmissionLimitError(
                        f"More than {max_paths} transmission paths: the model's relationships "
                        "are too densely connected to trace every path."
                    )
                if len(via) >= max_depth or shock.kind == "level":
                    continue  # a level change is applied at its own node only
                # Reversed so that paths come out in (target, rule) order.
                for link in reversed(outgoing.get(nodes[-1], [])):
                    if link.target in nodes:
                        continue  # a cycle: never revisit a node on the same path
                    stack.append(
                        (
                            (*nodes, link.target),
                            (*via, link),
                            coefficient * link.coefficient,
                            lag + link.lag,
                        )
                    )

        series: dict[str, list[Decimal]] = {}
        for path in found:
            values = series.setdefault(path.target, [ZERO] * horizon)
            last = horizon if path.last_month is None else min(path.last_month, horizon)
            for month in range(max(path.first_month, 1), last + 1):
                values[month - 1] += path.log_change

    return Propagation(
        horizon=horizon,
        series={node: tuple(values) for node, values in sorted(series.items())},
        paths=tuple(found),
    )
