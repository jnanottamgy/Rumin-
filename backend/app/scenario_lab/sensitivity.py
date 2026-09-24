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

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Literal

from app.scenario_lab.aggregate import (
    LINE_EQUATIONS,
    METRIC_LABELS,
    Outcome,
    Part,
    aggregate,
    outcome_of_result,
    totals,
)
from app.scenario_lab.executor import Member
from app.scenario_lab.inputs import SHARED_PATHS
from app.scenario_lab.profiles import LINE_LABELS
from app.scenario_lab.spec import ScenarioSpec
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
from app.simulation.engine import channel_issues, evaluate_result, links_for
from app.simulation.validation import check_range, decimal_places

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
class Target:
    """What one item varies: a change, a shared figure or one model's input."""

    id: str  # "change:var_brent_crude", "shared:annual_revenue", "model:<model>:<input>"
    label: str
    kind: str  # change | shared | company | market | assumption
    uses: tuple[tuple[Member, str], ...]  # (model, its input id)

    @property
    def definition(self) -> InputDefinition:
        member, input_id = self.uses[0]
        return member.model.definition.input(input_id)


@dataclass(frozen=True)
class Item:
    target: str
    mode: Mode = "default"
    step: Decimal | None = None
    values: tuple[Decimal, ...] = ()


def targets(spec: ScenarioSpec, members: Sequence[Member]) -> dict[str, Target]:
    """Everything an analysis of this execution can vary."""
    found: dict[str, Target] = {}
    for shock in spec.shocks:
        uses = tuple(
            (member, binding.input_id)
            for member in members
            if (binding := member.profile.binding(shock.variable_id)) is not None
            and binding.change_type is shock.change_type
        )
        if uses:
            found[f"change:{shock.variable_id}"] = Target(
                f"change:{shock.variable_id}",
                uses[0][0].model.definition.input(uses[0][1]).label,
                "change",
                uses,
            )
    for name in SHARED_PATHS:
        uses = tuple(
            (member, name)
            for member in members
            if any(item.id == name for item in member.model.definition.inputs)
        )
        if uses and uses[0][0].model.definition.input(name).kind in (
            InputKind.DECIMAL,
            InputKind.QUANTITY,
        ):
            found[f"shared:{name}"] = Target(
                f"shared:{name}", uses[0][0].model.definition.input(name).label, "shared", uses
            )
    for member in members:
        for item in member.model.definition.inputs:
            if item.id in SHARED_PATHS or item.category in (
                InputCategory.SCENARIO_INPUT,
                InputCategory.SETTING,
            ):
                continue
            if item.kind not in (InputKind.DECIMAL, InputKind.QUANTITY, InputKind.INTEGER):
                continue
            kind = {
                InputCategory.ASSUMPTION: "assumption",
                InputCategory.COMPANY_INPUT: "company",
                InputCategory.MARKET_BASELINE: "market",
            }[item.category]
            key = f"model:{member.model_id}:{item.id}"
            found[key] = Target(
                key, f"{item.label} ({member.profile.title})", kind, ((member, item.id),)
            )
    return found


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


def _base_value(member: Member, input_id: str) -> Decimal:
    values = member.values
    definition = member.model.definition.input(input_id)
    if definition.kind is InputKind.INTEGER:
        return Decimal(values.integer(input_id))
    return values.number(input_id)


def _points(target: Target, item: Item, base: Decimal) -> list[tuple[str, Decimal]]:
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


def _conform(definition: InputDefinition, value: Decimal) -> Decimal:
    places = 0 if definition.kind is InputKind.INTEGER else definition.max_decimals
    if decimal_places(value) <= places:
        return value
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def _metric(result: Any, metric: str) -> Decimal | None:
    return totals(result).get(metric)


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
    started = time.monotonic()
    horizon = spec.horizon_months

    def evaluate(member: Member, values: Any) -> Outcome:
        links = links_for(member.model, values, member.preparation.graph)
        return outcome_of_result(
            member.model_id, evaluate_result(member.model, values, links, horizon)
        )

    base_outcomes = {member.model_id: evaluate(member, member.values) for member in members}

    def combined(outcomes: Mapping[str, Outcome]) -> Any:
        return aggregate(
            [Part(member.profile, member.values, outcomes[member.model_id]) for member in members],
            horizon=horizon,
        )

    base_result = combined(base_outcomes)
    base_metric = _metric(base_result, metric)
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
        member, input_id = target.uses[0]
        base = _base_value(member, input_id)
        planned.append((target, item, base, _points(target, item, base)))
    total_points = sum(len(points) for *_, points in planned)
    if total_points > MAX_EVALUATIONS:
        raise LabSensitivityError(
            f"The analysis would need {total_points} evaluations; the limit is {MAX_EVALUATIONS}.",
            field="inputs",
        )

    evaluations = 0
    results: list[dict[str, Any]] = []
    for target, item, base, points in planned:
        definition = target.definition
        evaluated: list[dict[str, Any]] = []
        for role, raw_point in points:
            point = _conform(definition, raw_point)
            entry: dict[str, Any] = {
                "role": role,
                "value": text(point),
                "metric": None,
                "delta": None,
                "skipped": None,
            }
            problem = None
            if definition.kind is InputKind.INTEGER and point != point.to_integral_value():
                problem = "must be a whole number"
            for member, input_id in target.uses:
                problem = problem or check_range(member.model.definition.input(input_id), point)
            if problem:
                entry["skipped"] = f"{target.label} {problem}."
                evaluated.append(entry)
                continue
            outcomes = dict(base_outcomes)
            try:
                for member, input_id in target.uses:
                    values = member.values
                    if member.model.definition.input(input_id).kind is InputKind.INTEGER:
                        varied = replace(values, integers={**values.integers, input_id: int(point)})
                    else:
                        varied = replace(values, numbers={**values.numbers, input_id: point})
                    blocking = [
                        issue for issue in member.model.check(varied) if issue.severity == "error"
                    ]
                    blocking += [
                        issue
                        for issue in channel_issues(member.model, varied, member.preparation.graph)
                        if issue.severity == "error"
                    ]
                    if blocking:
                        raise LabSensitivityError(blocking[0].message)
                    if time.monotonic() - started > deadline_seconds:
                        raise TimeoutError
                    outcomes[member.model_id] = evaluate(member, varied)
                value = _metric(combined(outcomes), metric)
            except LabSensitivityError as skipped:
                entry["skipped"] = skipped.message
                evaluated.append(entry)
                continue
            except NumericalError as error:
                entry["skipped"] = error.message
                evaluated.append(entry)
                continue
            except TimeoutError:
                raise LabSensitivityError(
                    f"The analysis stopped after {evaluations} evaluations: it exceeded "
                    f"{deadline_seconds:g} seconds."
                ) from None
            evaluations += 1
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
                "models": [member.model_id for member, _ in target.uses],
                "unit": definition.unit
                or (
                    member.values.unit(input_id) if definition.kind is InputKind.QUANTITY else None
                ),
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
        "evaluations": evaluations + 1,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
