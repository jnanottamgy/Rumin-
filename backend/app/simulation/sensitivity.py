"""One-at-a-time sensitivity analysis of a completed run.

Each selected input is moved on its own — to a low and a high value, to relative
variations, or to explicit values — while every other input keeps its value from the
run. The model is re-evaluated at each point and the outputs are compared with the run
(the *base*). The summary ranks inputs by how far they move the chosen metric (the spread
between their lowest and highest result), which is what a tornado chart shows.

Every point is validated like a run's inputs: a point outside the input's range, one
that breaks a model check (e.g. a fuel bill above operating costs) or one that would need
a relationship the knowledge graph does not confirm is skipped and reported — never
clipped silently. Resource limits keep an analysis small: at most ``MAX_INPUTS`` inputs,
``MAX_POINTS`` points per input, ``MAX_EVALUATIONS`` evaluations and ``DEADLINE_SECONDS``.

The same building block (re-evaluating the model on perturbed inputs) is what a future
Monte Carlo analysis would use, with a recorded random seed; none is implemented yet.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Literal

from app.simulation.decimal_math import (
    HUNDRED,
    ONE,
    ZERO,
    NumericalError,
    arithmetic,
    text,
    to_output,
)
from app.simulation.definitions import InputCategory, InputDefinition, InputKind
from app.simulation.engine import Preparation, channel_issues, evaluate_outputs, links_for
from app.simulation.runtime import ResolvedValues
from app.simulation.validation import check_range, decimal_places

MAX_INPUTS = 8
MAX_POINTS = 7
MAX_EVALUATIONS = 60
DEADLINE_SECONDS = 10.0

Mode = Literal["default", "absolute", "relative", "values"]


class SensitivityError(ValueError):
    """A request the analysis refuses (limits, unknown or unsuitable inputs)."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass(frozen=True)
class SensitivityItem:
    input: str
    mode: Mode = "default"
    step: Decimal | None = None
    values: tuple[Decimal, ...] = ()


def _base_value(values: ResolvedValues, item: InputDefinition) -> Decimal:
    if item.kind is InputKind.INTEGER:
        return Decimal(values.integer(item.id))
    return values.number(item.id)


def _points(
    item: InputDefinition, request: SensitivityItem, base: Decimal
) -> list[tuple[str, Decimal]]:
    """(role, value) pairs to evaluate, before validation."""
    mode = request.mode
    step = request.step
    if mode == "default":
        if item.sensitivity is None:
            raise SensitivityError(
                f"{item.label} has no default variation; give values.", field=item.id
            )
        mode, step = item.sensitivity.mode, item.sensitivity.step
    if mode == "values":
        if not request.values:
            raise SensitivityError(f"Give at least one value for {item.label}.", field=item.id)
        if len(request.values) > MAX_POINTS:
            raise SensitivityError(f"At most {MAX_POINTS} values per input.", field=item.id)
        return [(f"value {index + 1}", value) for index, value in enumerate(request.values)]
    if step is None or step <= ZERO:
        raise SensitivityError(f"The variation for {item.label} must be positive.", field=item.id)
    with arithmetic():
        if mode == "absolute":
            low, high = base - step, base + step
        else:
            if item.kind is InputKind.INTEGER:
                raise SensitivityError(
                    f"{item.label} counts months: vary it by months (absolute) or by values.",
                    field=item.id,
                )
            if step >= HUNDRED:
                raise SensitivityError("A relative variation must be below 100 %.", field=item.id)
            low = base * (ONE - step / HUNDRED)
            high = base * (ONE + step / HUNDRED)
    return [("low", low), ("high", high)]


def _conform(item: InputDefinition, value: Decimal) -> Decimal:
    """Round a generated point to the input's allowed decimals (half to even)."""
    places = 0 if item.kind is InputKind.INTEGER else item.max_decimals
    if decimal_places(value) <= places:
        return value
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def analyse(
    preparation: Preparation,
    requests: list[SensitivityItem],
    *,
    metric: str,
    deadline_seconds: float = DEADLINE_SECONDS,
) -> dict[str, Any]:
    """Run the analysis. ``preparation`` is the (valid) preparation of the base run."""
    if not preparation.ok or preparation.values is None:
        raise SensitivityError("The base run's inputs are not valid.")
    model = preparation.model
    definition = model.definition
    if metric not in {item.id for item in definition.outputs}:
        raise SensitivityError(f"'{metric}' is not an output of this model.", field="metric")
    if not requests:
        raise SensitivityError("Choose at least one input to vary.", field="inputs")
    if len(requests) > MAX_INPUTS:
        raise SensitivityError(f"At most {MAX_INPUTS} inputs per analysis.", field="inputs")
    names = [request.input for request in requests]
    if len(names) != len(set(names)):
        raise SensitivityError("Each input can be varied only once per analysis.", field="inputs")

    base_values = preparation.values
    horizon = base_values.integer(definition.horizon_input)
    links = links_for(model, base_values, preparation.graph)
    started = time.monotonic()
    base_outputs = evaluate_outputs(model, base_values, links, horizon)
    evaluations = 0
    planned: list[tuple[InputDefinition, SensitivityItem, Decimal, list[tuple[str, Decimal]]]] = []
    for request in requests:
        try:
            item = definition.input(request.input)
        except KeyError:
            raise SensitivityError(
                f"'{request.input}' is not an input of this model.", field="inputs"
            ) from None
        if item.kind not in (InputKind.DECIMAL, InputKind.INTEGER, InputKind.QUANTITY):
            raise SensitivityError(
                f"{item.label} is not a number and cannot be varied.", field=item.id
            )
        if item.category is InputCategory.SETTING:
            raise SensitivityError(
                f"{item.label} is a setting, not an input to vary.", field=item.id
            )
        base = _base_value(base_values, item)
        points = _points(item, request, base)
        planned.append((item, request, base, points))
    total_points = sum(len(points) for *_, points in planned)
    if total_points > MAX_EVALUATIONS:
        raise SensitivityError(
            f"The analysis would need {total_points} evaluations; the limit is {MAX_EVALUATIONS}.",
            field="inputs",
        )

    results: list[dict[str, Any]] = []
    for item, request, base, points in planned:
        evaluated: list[dict[str, Any]] = []
        for role, raw_point in points:
            point = _conform(item, raw_point)
            entry: dict[str, Any] = {
                "role": role,
                "value": text(point),
                "outputs": None,
                "deltas": None,
                "skipped": None,
            }
            problem = check_range(item, point)
            if item.kind is InputKind.INTEGER and point != point.to_integral_value():
                problem = "must be a whole number"
            if problem:
                entry["skipped"] = f"{item.label} {problem}."
                evaluated.append(entry)
                continue
            if item.kind is InputKind.INTEGER:
                varied = replace(
                    base_values, integers={**base_values.integers, item.id: int(point)}
                )
            else:
                varied = replace(base_values, numbers={**base_values.numbers, item.id: point})
            blocking = [issue for issue in model.check(varied) if issue.severity == "error"]
            blocking += [
                issue
                for issue in channel_issues(model, varied, preparation.graph)
                if issue.severity == "error"
            ]
            if blocking:
                entry["skipped"] = blocking[0].message
                evaluated.append(entry)
                continue
            if time.monotonic() - started > deadline_seconds:
                raise SensitivityError(
                    f"The analysis stopped after {evaluations} evaluations: it exceeded "
                    f"{deadline_seconds:g} seconds."
                )
            try:
                outputs = evaluate_outputs(
                    model, varied, links_for(model, varied, preparation.graph), horizon
                )
            except NumericalError as error:
                entry["skipped"] = error.message
                evaluated.append(entry)
                continue
            evaluations += 1
            with arithmetic():
                entry["outputs"] = {name: to_output(outputs[name]) for name in sorted(outputs)}
                entry["deltas"] = {
                    name: to_output(outputs[name] - base_outputs[name]) for name in sorted(outputs)
                }
            evaluated.append(entry)
        usable = [entry for entry in evaluated if entry["outputs"] is not None]
        spread = None
        if usable:
            metric_values = [entry["outputs"][metric] for entry in usable] + [
                to_output(base_outputs[metric])
            ]
            with arithmetic():
                spread = {
                    "low": min(metric_values),
                    "high": max(metric_values),
                    "spread": max(metric_values) - min(metric_values),
                }
        results.append(
            {
                "input": item.id,
                "label": item.label,
                "category": item.category.value,
                "unit": item.unit
                or (base_values.unit(item.id) if item.kind is InputKind.QUANTITY else None),
                "base_value": text(base),
                "mode": request.mode
                if request.mode != "default"
                else (item.sensitivity.mode if item.sensitivity else "values"),
                "step": text(request.step)
                if request.step is not None
                else (
                    text(item.sensitivity.step)
                    if request.mode == "default" and item.sensitivity
                    else None
                ),
                "points": evaluated,
                "range": spread,
            }
        )

    ranking = sorted(
        (
            {
                "input": result["input"],
                "label": result["label"],
                "spread": result["range"]["spread"],
            }
            for result in results
            if result["range"] is not None
        ),
        key=lambda entry: (-entry["spread"], entry["input"]),
    )
    return {
        "metric": metric,
        "base": {name: to_output(base_outputs[name]) for name in sorted(base_outputs)},
        "items": results,
        "ranking": ranking,
        "evaluations": evaluations + 1,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
