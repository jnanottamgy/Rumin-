"""Joint sensitivity: two quantities varied together over a grid.

One-at-a-time analysis cannot see whether two quantities reinforce each other. Here every
combination of the values of *A* (rows) and *B* (columns) is evaluated — each axis holds the
requested points plus the execution's own value *a₀* or *b₀* — and each cell carries:

* the line or metric, *f(a, b)*, and its change from the execution, *f(a, b) − f(a₀, b₀)*;
* the **interaction**, *I(a, b) = f(a, b) − f(a, b₀) − f(a₀, b) + f(a₀, b₀)*: what moving
  both together adds to the sum of moving each alone. It is zero when the effects simply add
  (a crude-oil rise and a repo-rate rise act on different lines) and not zero when one
  changes the other's effect (a weaker rupee makes a crude-oil rise costlier in rupees).

Axis values outside an input's range are refused before anything runs; a cell whose
combination breaks a model's own rule is skipped with the reason, and the interactions that
need it are not computed. Deterministic: no probabilities are involved.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.scenario_lab.aggregate import LINE_EQUATIONS, METRIC_LABELS
from app.scenario_lab.evaluation import (
    DeadlineExceeded,
    Evaluator,
    Skipped,
    Target,
    conform,
    targets,
    value_problem,
)
from app.scenario_lab.executor import Member
from app.scenario_lab.profiles import LINE_LABELS
from app.scenario_lab.sensitivity import Item, LabSensitivityError, points
from app.scenario_lab.spec import ScenarioSpec
from app.simulation.decimal_math import arithmetic, text, to_output

MAX_AXIS_POINTS = 7
DEADLINE_SECONDS = 10.0
# Interactions smaller than this (in the metric's unit) are rounding, not interaction: every
# line is rounded to 10 decimal places before it is combined.
INTERACTION_TOLERANCE = Decimal("1e-6")
METRICS = (*LINE_EQUATIONS, *METRIC_LABELS)


class JointError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def _axis(available: dict[str, Target], item: Item, field: str) -> tuple[Target, list[Decimal]]:
    target = available.get(item.target)
    if target is None:
        raise JointError(f"'{item.target}' is not a quantity of this execution.", field=field)
    base = target.base
    try:
        wanted = points(target, item, base)
    except LabSensitivityError as error:
        raise JointError(error.message, field=field) from error
    values = sorted({conform(target.definition, value) for _, value in wanted} | {base})
    if len(values) > MAX_AXIS_POINTS:
        raise JointError(
            f"At most {MAX_AXIS_POINTS} values per axis, the execution's own value included.",
            field=field,
        )
    for value in values:
        problem = value_problem(target, value)
        if problem:
            raise JointError(f"{target.label}: {text(value)} {problem}.", field=field)
    return target, values


def _axis_json(target: Target, values: Sequence[Decimal]) -> dict[str, Any]:
    return {
        "target": target.id,
        "label": target.label,
        "kind": target.kind,
        "models": target.models,
        "unit": target.unit,
        "base_value": text(target.base),
        "values": [text(value) for value in values],
    }


def run(
    spec: ScenarioSpec,
    members: Sequence[Member],
    rows: Item,
    columns: Item,
    *,
    metric: str,
    deadline_seconds: float = DEADLINE_SECONDS,
) -> dict[str, Any]:
    if metric not in METRICS:
        raise JointError(f"'{metric}' is not a line or metric of the Lab.", field="metric")
    if rows.target == columns.target:
        raise JointError("Choose two different quantities.", field="columns")
    available = targets(spec, members)
    row_target, row_values = _axis(available, rows, "rows")
    column_target, column_values = _axis(available, columns, "columns")
    evaluator = Evaluator(spec, members, deadline_seconds=deadline_seconds)
    base = evaluator.base_totals.get(metric)
    if base is None:
        raise JointError(
            f"This execution has no {metric.replace('_', ' ')}: no included model produces it.",
            field="metric",
        )
    row_base, column_base = row_target.base, column_target.base

    values: list[list[Decimal | None]] = []
    skipped: list[list[str | None]] = []
    for a in row_values:
        row: list[Decimal | None] = []
        reasons: list[str | None] = []
        for b in column_values:
            if a == row_base and b == column_base:
                row.append(base)
                reasons.append(None)
                continue
            try:
                row.append(evaluator.evaluate([(row_target, a), (column_target, b)])[metric])
                reasons.append(None)
            except Skipped as reason:
                row.append(None)
                reasons.append(reason.message)
            except DeadlineExceeded as stopped:
                raise JointError(
                    f"The analysis stopped after {stopped.evaluations} evaluations: it exceeded "
                    f"{stopped.seconds:g} seconds."
                ) from None
        values.append(row)
        skipped.append(reasons)

    i0 = row_values.index(row_base)
    j0 = column_values.index(column_base)
    cells: list[list[dict[str, Any]]] = []
    largest: dict[str, Any] | None = None
    largest_change: dict[str, Any] | None = None
    computed = 0
    for i in range(len(row_values)):
        cells_row: list[dict[str, Any]] = []
        for j in range(len(column_values)):
            value = values[i][j]
            own_row, own_column, own = values[i][j0], values[i0][j], values[i0][j0]
            interaction = None
            delta = None
            with arithmetic():
                if value is not None:
                    delta = to_output(value - base)
                    if own_row is not None and own_column is not None and own is not None:
                        interaction = to_output(value - own_row - own_column + own)
                        computed += 1
            cells_row.append(
                {
                    "metric": text(value) if value is not None else None,
                    "delta": text(delta) if delta is not None else None,
                    "interaction": text(interaction) if interaction is not None else None,
                    "skipped": skipped[i][j],
                }
            )
            if interaction is not None and (
                largest is None or abs(interaction) > abs(Decimal(largest["value"]))
            ):
                largest = {"row": i, "column": j, "value": text(interaction)}
            if delta is not None and (
                largest_change is None or abs(delta) > abs(Decimal(largest_change["value"]))
            ):
                largest_change = {"row": i, "column": j, "value": text(delta)}
        cells.append(cells_row)
    additive = largest is not None and abs(Decimal(largest["value"])) <= INTERACTION_TOLERANCE
    return {
        "metric": metric,
        "metric_label": LINE_LABELS.get(metric) or METRIC_LABELS.get(metric, metric),
        "metric_kind": "line_change" if metric in LINE_EQUATIONS else "metric_value",
        "base": text(base),
        "rows": _axis_json(row_target, row_values),
        "columns": _axis_json(column_target, column_values),
        "cells": cells,
        "summary": {
            "largest_interaction": largest,
            "largest_change": largest_change,
            "interactions_computed": computed,
            "additive": additive,
            "tolerance": text(INTERACTION_TOLERANCE),
            "skipped": sum(1 for row in skipped for reason in row if reason),
        },
        "evaluations": evaluator.evaluations + 1,
        "duration_ms": evaluator.elapsed_ms,
    }
