"""One-at-a-time sensitivity analysis across a whole scenario.

Each selected quantity is moved on its own — a scenario change, a shared figure (revenue,
operating costs, the exchange rate) or one model's input or assumption — while everything
else keeps the execution's value. Every model that uses the quantity is re-evaluated, the
Lab's aggregation is recomputed, and the chosen line or metric is compared with the
execution. Inputs are ranked by the spread they cause: what a tornado chart shows.

This is **sensitivity analysis**, not scenario analysis (which sets several changes
together) and not a stochastic simulation: no probabilities are involved, and the spread
says how much the result depends on a quantity, not how likely any value is.

Points outside an input's range, or that break a model's own rules, are skipped and
reported — never clipped. Bounded like the Phase 4 analysis: at most ``MAX_ITEMS``
quantities, ``MAX_POINTS`` points each, ``MAX_EVALUATIONS`` evaluations and a deadline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from app.scenario_lab.aggregate import LINE_EQUATIONS, METRIC_LABELS
from app.scenario_lab.evaluation import (
    DeadlineExceeded,
    Evaluator,
    Skipped,
    Target,
    conform,
    targets,
)
from app.scenario_lab.executor import Member
from app.scenario_lab.profiles import LINE_LABELS
from app.scenario_lab.spec import ScenarioSpec
from app.simulation.decimal_math import HUNDRED, ONE, ZERO, arithmetic, text, to_output
from app.simulation.definitions import InputKind

__all__ = [
    "DEADLINE_SECONDS",
    "MAX_EVALUATIONS",
    "MAX_ITEMS",
    "MAX_POINTS",
    "METHOD_VERSION",
    "METRICS",
    "Item",
    "LabSensitivityError",
    "Target",
    "analyse",
    "default_items",
    "points",
    "targets",
]

# 1.1.0 (Phase 9): the varied values also reach the aggregation, so margins and interest
# coverage move with revenue, operating costs and interest expense.
METHOD_VERSION = "1.1.0"
MAX_ITEMS = 8
MAX_POINTS = 7
MAX_EVALUATIONS = 60
DEADLINE_SECONDS = 10.0
METRICS = (*LINE_EQUATIONS, *METRIC_LABELS)

Mode = Literal["default", "absolute", "relative", "values"]


class LabSensitivityError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass(frozen=True)
class Item:
    target: str
    mode: Mode = "default"
    step: Decimal | None = None
    values: tuple[Decimal, ...] = ()


def default_items(spec: ScenarioSpec, members: Sequence[Member]) -> list[Item]:
    """The scenario's changes, then each model's default sensitivity assumptions, up to the
    limit."""
    available = targets(spec, members)
    chosen = [key for key in available if key.startswith("change:")]
    for member in members:
        for name in member.model.definition.sensitivity_defaults:
            key = f"model:{member.model_id}:{name}"
            if key in available and available[key].kind == "assumption":
                chosen.append(key)
    return [Item(target=key) for key in chosen[:MAX_ITEMS]]


def points(target: Target, item: Item, base: Decimal) -> list[tuple[str, Decimal]]:
    """The values an item asks for: its default variation, a step either side or listed
    values (not yet conformed to the input's decimals)."""
    definition = target.definition
    mode, step = item.mode, item.step
    if mode == "default":
        if definition.sensitivity is None:
            raise LabSensitivityError(
                f"{target.label} has no default variation; give values.", field=target.id
            )
        mode, step = definition.sensitivity.mode, definition.sensitivity.step
    if mode == "values":
        if not item.values:
            raise LabSensitivityError(
                f"Give at least one value for {target.label}.", field=target.id
            )
        if len(item.values) > MAX_POINTS:
            raise LabSensitivityError(f"At most {MAX_POINTS} values per quantity.", field=target.id)
        return [(f"value {index + 1}", value) for index, value in enumerate(item.values)]
    if step is None or step <= ZERO:
        raise LabSensitivityError(
            f"The variation for {target.label} must be positive.", field=target.id
        )
    with arithmetic():
        if mode == "absolute":
            return [("low", base - step), ("high", base + step)]
        if definition.kind is InputKind.INTEGER:
            raise LabSensitivityError(
                f"{target.label} counts months: vary it by months (absolute) or by values.",
                field=target.id,
            )
        if step >= HUNDRED:
            raise LabSensitivityError("A relative variation must be below 100 %.", field=target.id)
        return [("low", base * (ONE - step / HUNDRED)), ("high", base * (ONE + step / HUNDRED))]


def analyse(
    spec: ScenarioSpec,
    members: Sequence[Member],
    items: Sequence[Item],
    *,
    metric: str,
    deadline_seconds: float = DEADLINE_SECONDS,
) -> dict[str, Any]:
    if metric not in METRICS:
        raise LabSensitivityError(f"'{metric}' is not a line or metric of the Lab.", field="metric")
    if not items:
        raise LabSensitivityError("Choose at least one quantity to vary.", field="inputs")
    if len(items) > MAX_ITEMS:
        raise LabSensitivityError(f"At most {MAX_ITEMS} quantities per analysis.", field="inputs")
    names = [item.target for item in items]
    if len(names) != len(set(names)):
        raise LabSensitivityError(
            "Each quantity can be varied only once per analysis.", field="inputs"
        )
    available = targets(spec, members)
    evaluator = Evaluator(spec, members, deadline_seconds=deadline_seconds)
    base_metric = evaluator.base_totals.get(metric)
    if base_metric is None:
        raise LabSensitivityError(
            f"This execution has no {metric.replace('_', ' ')}: no included model produces it.",
            field="metric",
        )

    planned = []
    for item in items:
        target = available.get(item.target)
        if target is None:
            raise LabSensitivityError(
                f"'{item.target}' is not a quantity of this execution.", field="inputs"
            )
        base = target.base
        planned.append((target, item, base, points(target, item, base)))
    total_points = sum(len(values) for *_, values in planned)
    if total_points > MAX_EVALUATIONS:
        raise LabSensitivityError(
            f"The analysis would need {total_points} evaluations; the limit is {MAX_EVALUATIONS}.",
            field="inputs",
        )

    results: list[dict[str, Any]] = []
    for target, item, base, wanted in planned:
        definition = target.definition
        evaluated: list[dict[str, Any]] = []
        for role, raw_point in wanted:
            point = conform(definition, raw_point)
            entry: dict[str, Any] = {
                "role": role,
                "value": text(point),
                "metric": None,
                "delta": None,
                "skipped": None,
            }
            try:
                value = evaluator.evaluate([(target, point)]).get(metric)
            except Skipped as skipped:
                entry["skipped"] = skipped.message
                evaluated.append(entry)
                continue
            except DeadlineExceeded as stopped:
                raise LabSensitivityError(
                    f"The analysis stopped after {stopped.evaluations} evaluations: it exceeded "
                    f"{stopped.seconds:g} seconds."
                ) from None
            if value is not None:
                with arithmetic():
                    entry["metric"] = text(value)
                    entry["delta"] = text(to_output(value - base_metric))
            evaluated.append(entry)
        usable = [Decimal(entry["metric"]) for entry in evaluated if entry["metric"] is not None]
        spread = None
        if usable:
            with arithmetic():
                low = min([*usable, base_metric])
                high = max([*usable, base_metric])
                spread = {"low": text(low), "high": text(high), "spread": text(high - low)}
        results.append(
            {
                "target": target.id,
                "label": target.label,
                "kind": target.kind,
                "models": target.models,
                "unit": target.unit,
                "base_value": text(base),
                "mode": item.mode
                if item.mode != "default"
                else (definition.sensitivity.mode if definition.sensitivity else "values"),
                "step": text(item.step)
                if item.step is not None
                else (
                    text(definition.sensitivity.step)
                    if item.mode == "default" and definition.sensitivity
                    else None
                ),
                "points": evaluated,
                "range": spread,
            }
        )
    ranking = sorted(
        (
            {
                "target": result["target"],
                "label": result["label"],
                "spread": result["range"]["spread"],
            }
            for result in results
            if result["range"] is not None
        ),
        key=lambda entry: (-Decimal(entry["spread"]), entry["target"]),
    )
    return {
        "metric": metric,
        "metric_label": LINE_LABELS.get(metric) or METRIC_LABELS.get(metric, metric),
        "metric_kind": "line_change" if metric in LINE_EQUATIONS else "metric_value",
        "base": text(base_metric),
        "items": results,
        "ranking": ranking,
        "evaluations": evaluator.evaluations + 1,
        "duration_ms": evaluator.elapsed_ms,
    }
