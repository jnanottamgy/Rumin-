"""One simulation run: validate, confirm, propagate, compute, attribute, hash.

``prepare`` does everything that needs the database (stored observations, the knowledge
graph); ``execute`` is pure — the same preparation always gives the same result, down to
the last digit, which is what makes runs reproducible and verifiable.

Contribution analysis uses **Shapley values**: the model is evaluated with every subset
of the scenario's non-zero changes (the others held at zero), and each change is credited
with its average marginal effect over all orders. The credits add up exactly to the total
change, whatever the interactions between shocks (e.g. a weaker currency makes a crude
oil rise costlier) — no ordering of shocks is privileged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from itertools import combinations
from math import factorial
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import GraphEdgeType
from app.domain.graph_types import EDGE_TYPES
from app.simulation.data_sources import latest_observation
from app.simulation.decimal_math import (
    HUNDRED,
    ONE,
    ZERO,
    NumericalError,
    arithmetic,
    ln,
    text,
    to_output,
)
from app.simulation.definitions import PERCENTAGE_POINTS, InputCategory, sha256
from app.simulation.graph_context import GraphContext, load_graph_context, needed_rules
from app.simulation.registry import ENGINE_VERSION, RegisteredModel
from app.simulation.runtime import (
    ComputeContext,
    Issue,
    ModelResult,
    ResolvedValues,
    Step,
    StepRecorder,
)
from app.simulation.transmission import (
    Link,
    Propagation,
    Shock,
    TransmissionLimitError,
    propagate,
)
from app.simulation.validation import InputValue, ResolvedInput, validate_inputs

MAX_PATHS = 500
# Shapley analysis evaluates 2ⁿ subsets of the n non-zero shocks.
MAX_ATTRIBUTED_SHOCKS = 6


@dataclass
class Preparation:
    model: RegisteredModel
    resolved: dict[str, ResolvedInput]
    values: ResolvedValues | None
    graph: GraphContext
    issues: list[Issue]

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return self.values is not None and not self.errors


@dataclass
class Execution:
    preparation: Preparation
    horizon: int
    propagation: Propagation
    result: ModelResult
    steps: list[Step]
    outputs: dict[str, dict[str, Any]]
    monthly: dict[str, dict[str, Any]]
    contributions: dict[str, list[dict[str, Any]]]
    bridge: dict[str, Any] | None
    transmission: list[dict[str, Any]]
    inputs_hash: str
    result_hash: str
    warnings: list[Issue] = field(default_factory=list)


def _shock_inputs(model: RegisteredModel) -> list[str]:
    return [
        item.id
        for item in model.definition.inputs
        if item.category is InputCategory.SCENARIO_INPUT and item.variable
    ]


def shocked_nodes(model: RegisteredModel, values: ResolvedValues) -> set[str]:
    nodes: set[str] = set()
    for input_id in _shock_inputs(model):
        variable = model.definition.input(input_id).variable
        if variable and values.number(input_id) != ZERO:
            nodes.add(variable)
    return nodes


def channel_issues(
    model: RegisteredModel, values: ResolvedValues, graph: GraphContext
) -> list[Issue]:
    """Errors for every transmission rule a shock needs that the graph does not confirm,
    and notes on the evidence behind the ones it does."""
    issues: list[Issue] = []
    definition = model.definition
    shocks_by_node: dict[str, str] = {}
    for input_id in _shock_inputs(model):
        variable = definition.input(input_id).variable
        if variable and values.number(input_id) != ZERO:
            shocks_by_node[variable] = input_id
    for rule_id in needed_rules(definition, set(shocks_by_node)):
        rule = next(item for item in definition.transmission_rules if item.id == rule_id)
        edge = graph.transmission.get(rule_id)
        field_name = shocks_by_node.get(rule.source)
        if edge is None:
            where = (
                "the knowledge graph has not been built (make graph)"
                if graph.build_id is None
                else f"build #{graph.build_id} of the knowledge graph does not contain it as a "
                "validated relationship"
            )
            label = EDGE_TYPES[GraphEdgeType(rule.edge_type)].label
            source = graph.names.get(rule.source, rule.source)
            target = graph.names.get(rule.target, rule.target)
            issues.append(
                Issue(
                    "channel_confirmed",
                    f"This change needs the relationship '{source} — {label} → {target}' "
                    f"(rule {rule.id}), but {where}. The engine never propagates a shock "
                    "along a relationship the graph does not state.",
                    field=field_name,
                )
            )
        elif edge.evidence_status == "model_assumption":
            issues.append(
                Issue(
                    "assumption_based_channel",
                    f"Rule {rule.id} follows a relationship the knowledge graph records as a "
                    "model assumption, not an empirical finding: results that depend on it "
                    "are assumption-driven.",
                    severity="warning",
                    field=field_name,
                )
            )
    return issues


def prepare(
    session: Session,
    model: RegisteredModel,
    raw_inputs: Mapping[str, InputValue],
    *,
    freshness: str,
) -> Preparation:
    """Validate the inputs, resolve stored data and confirm the graph relationships."""
    definition = model.definition
    resolved, values, issues = validate_inputs(
        definition, raw_inputs, lookup=lambda series: latest_observation(session, series)
    )
    entity_raw = raw_inputs.get("entity")
    entity_key = (
        values.text("entity")
        if values is not None
        else (entity_raw.value if entity_raw and isinstance(entity_raw.value, str) else None)
    )
    graph, graph_issues = load_graph_context(session, definition, entity_key, freshness)
    issues.extend(graph_issues)
    if graph.entity is not None and graph.entity.nature != "real":
        kind = "a fictional company" if graph.entity.nature == "fictional" else "sample data"
        issues.append(
            Issue(
                "fictional_entity",
                f"{graph.entity.name} is {kind} in RUMIN's sample network: the results "
                "describe the figures you entered, not a real airline.",
                severity="warning",
                field="entity",
            )
        )
    for input_id, entry in resolved.items():
        if entry.observation is not None:
            spec = next(
                item
                for item in definition.input(input_id).sources
                if item.series_id == entry.observation.series_id
            )
            issues.append(
                Issue(
                    "historical_baseline",
                    f"{entry.label} is the {entry.observation.period_label} value of "
                    f"'{spec.label}': {spec.caveat}",
                    severity="warning",
                    field=input_id,
                )
            )
    if values is not None and not any(issue.severity == "error" for issue in issues):
        try:
            issues.extend(model.check(values))
        except NumericalError as error:
            issues.append(Issue(error.code, error.message))
        issues.extend(channel_issues(model, values, graph))
    has_errors = any(issue.severity == "error" for issue in issues)
    return Preparation(model, resolved, None if has_errors else values, graph, issues)


def links_for(model: RegisteredModel, values: ResolvedValues, graph: GraphContext) -> list[Link]:
    links: list[Link] = []
    for rule in model.definition.transmission_rules:
        edge = graph.transmission.get(rule.id)
        if edge is None:
            continue
        links.append(
            Link(
                rule_id=rule.id,
                edge_key=edge.edge_key,
                source=rule.source,
                target=rule.target,
                coefficient=values.number(rule.coefficient_input),
                lag=values.integer(rule.lag_input) if rule.lag_input else 0,
            )
        )
    return links


def shock_window(model: RegisteredModel, values: ResolvedValues) -> tuple[int, int | None]:
    """The first and last month (None: the end of the horizon) the run's changes last.

    Models that declare no timing inputs have permanent changes from month 1.
    """
    definition = model.definition
    start = values.integer(definition.shock_start_input) if definition.shock_start_input else 1
    duration = (
        values.integer(definition.shock_duration_input) if definition.shock_duration_input else 0
    )
    return start, (start + duration - 1 if duration > 0 else None)


def _shocks(model: RegisteredModel, values: ResolvedValues) -> list[Shock]:
    shocks: list[Shock] = []
    start, end = shock_window(model, values)
    with arithmetic():
        for input_id in _shock_inputs(model):
            item = model.definition.input(input_id)
            variable = item.variable
            change = values.number(input_id)
            if not variable or change == ZERO:
                continue
            if item.unit == PERCENTAGE_POINTS:
                shocks.append(Shock(input_id, variable, change, start, end, kind="level"))
            else:
                shocks.append(Shock(input_id, variable, ln(ONE + change / HUNDRED), start, end))
    return shocks


def _evaluate(
    model: RegisteredModel,
    values: ResolvedValues,
    links: list[Link],
    horizon: int,
    recorder: StepRecorder,
) -> tuple[Propagation, ModelResult]:
    definition = model.definition
    try:
        propagation = propagate(
            _shocks(model, values),
            links,
            horizon=horizon,
            max_depth=definition.max_propagation_depth,
            max_paths=MAX_PATHS,
        )
    except TransmissionLimitError as error:
        raise NumericalError(str(error), code="transmission_limit") from error
    result = model.compute(ComputeContext(values, horizon, propagation, recorder))
    return propagation, result


def evaluate_result(
    model: RegisteredModel, values: ResolvedValues, links: list[Link], horizon: int
) -> ModelResult:
    """The model's outputs and monthly series for ``values``, unrounded and without
    recording steps (used by the Scenario Lab's stress cases and sensitivity analysis)."""
    _, result = _evaluate(model, values, links, horizon, StepRecorder(enabled=False))
    return result


def evaluate_outputs(
    model: RegisteredModel, values: ResolvedValues, links: list[Link], horizon: int
) -> dict[str, Decimal]:
    """The model's scalar outputs for ``values``, without recording steps (used by
    contribution and sensitivity analysis)."""
    return evaluate_result(model, values, links, horizon).scalars


def shapley(
    model: RegisteredModel,
    values: ResolvedValues,
    links: list[Link],
    horizon: int,
    factors: list[str],
    outputs: list[str],
) -> dict[str, dict[str, Decimal]]:
    """Shapley attribution of ``outputs`` across ``factors`` (non-zero shock inputs).

    v(S) evaluates the model with the shocks in S and the others at zero; factor i gets
    Σ over S ⊆ F∖{i} of |S|!(n−|S|−1)!/n! × (v(S ∪ {i}) − v(S)).
    """
    count = len(factors)
    if count > MAX_ATTRIBUTED_SHOCKS:
        raise NumericalError(
            f"Contribution analysis supports at most {MAX_ATTRIBUTED_SHOCKS} changes at once."
        )
    cache: dict[frozenset[str], dict[str, Decimal]] = {}

    def value(subset: frozenset[str]) -> dict[str, Decimal]:
        if subset not in cache:
            numbers = {
                **values.numbers,
                **{name: ZERO for name in factors if name not in subset},
            }
            cache[subset] = evaluate_outputs(
                model, replace(values, numbers=numbers), links, horizon
            )
        return cache[subset]

    credits: dict[str, dict[str, Decimal]] = {name: {} for name in factors}
    with arithmetic():
        for factor in factors:
            others = [name for name in factors if name != factor]
            totals = {output: ZERO for output in outputs}
            for size in range(len(others) + 1):
                weight = Decimal(factorial(size) * factorial(count - size - 1)) / Decimal(
                    factorial(count)
                )
                for subset in combinations(others, size):
                    without = frozenset(subset)
                    with_factor = without | {factor}
                    for output in outputs:
                        totals[output] += weight * (
                            value(with_factor)[output] - value(without)[output]
                        )
            credits[factor] = totals
    return credits


def _snapshot_inputs(resolved: Mapping[str, ResolvedInput]) -> dict[str, Any]:
    """The part of each input that determines the result (hashed for reproducibility)."""
    snapshot: dict[str, Any] = {}
    for input_id, entry in sorted(resolved.items()):
        item: dict[str, Any] = {"value": entry.value, "unit": entry.unit, "source": entry.source}
        if entry.observation is not None:
            item["observation"] = {
                "series_id": entry.observation.series_id,
                "period": entry.observation.period_label,
                "value": text(entry.observation.value),
            }
        snapshot[input_id] = item
    return snapshot


def inputs_hash(model: RegisteredModel, resolved: Mapping[str, ResolvedInput]) -> str:
    return sha256(
        {
            "model": model.definition.id,
            "version": model.definition.version,
            "definition_hash": model.definition_hash,
            "engine": ENGINE_VERSION,
            "inputs": _snapshot_inputs(resolved),
        }
    )


def execute(preparation: Preparation) -> Execution:
    """Run a prepared, valid simulation. Pure: no database, no clock."""
    if not preparation.ok or preparation.values is None:
        raise ValueError("Only a valid preparation can be executed.")
    model = preparation.model
    definition = model.definition
    values = preparation.values
    horizon = values.integer(definition.horizon_input)
    links = links_for(model, values, preparation.graph)
    recorder = StepRecorder()
    propagation, result = _evaluate(model, values, links, horizon, recorder)

    outputs: dict[str, dict[str, Any]] = {}
    for item in definition.outputs:
        outputs[item.id] = {
            "value": to_output(result.scalars[item.id], item.label),
            "unit": result.units.get(item.id, item.unit),
            "kind": item.kind,
        }
    declared = [item.id for item in definition.monthly_outputs]
    if sorted(declared) != sorted(result.monthly):
        raise NumericalError(
            "The model returned monthly series that its definition does not declare.",
            code="model_inconsistent",
        )
    monthly: dict[str, dict[str, Any]] = {
        name: {
            "unit": result.monthly_units.get(name, ""),
            "values": [to_output(number, name) for number in result.monthly[name]],
        }
        for name in declared
    }

    factors = [name for name in _shock_inputs(model) if values.number(name) != ZERO]
    attributable = [item.id for item in definition.outputs if item.attributable]
    contributions: dict[str, list[dict[str, Any]]] = {}
    if factors:
        credits = shapley(model, values, links, horizon, factors, attributable)
        for output in attributable:
            contributions[output] = [
                {"input": factor, "value": to_output(credits[factor][output], output)}
                for factor in factors
            ]

    bridge: dict[str, Any] | None = None
    if definition.bridge and definition.bridge_total:
        # Signed inside the engine's context, so no value is rounded to fewer digits.
        with arithmetic():
            signed = [step.sign * result.scalars[step.output] for step in definition.bridge]
            residual = sum(signed, ZERO) - result.scalars[definition.bridge_total]
        if abs(residual) > Decimal("1e-12"):
            raise NumericalError(
                f"The accounting bridge does not close (residual {residual}); the model is "
                "inconsistent.",
                code="bridge_mismatch",
            )
        bridge = {
            "steps": [
                {
                    "output": step.output,
                    "label": step.label,
                    "sign": step.sign,
                    "value": to_output(value, step.label),
                }
                for step, value in zip(definition.bridge, signed, strict=True)
            ],
            "total": {
                "output": definition.bridge_total,
                "value": to_output(result.scalars[definition.bridge_total]),
            },
        }

    transmission = [
        {
            "input": path.input_id,
            "nodes": list(path.nodes),
            "rules": list(path.rules),
            "edge_keys": list(path.edge_keys),
            "coefficient": to_output(path.coefficient),
            "lag": path.lag,
            "first_month": path.first_month,
            "last_month": path.last_month,
            "kind": path.kind,
            "log_change": to_output(path.log_change),
        }
        for path in propagation.paths
    ]

    hashed_result = {
        "outputs": {name: text(item["value"]) for name, item in sorted(outputs.items())},
        "monthly": {
            name: [text(number) for number in item["values"]]
            for name, item in sorted(monthly.items())
        },
        "contributions": {
            output: [{"input": entry["input"], "value": text(entry["value"])} for entry in items]
            for output, items in sorted(contributions.items())
        },
    }
    return Execution(
        preparation=preparation,
        horizon=horizon,
        propagation=propagation,
        result=result,
        steps=recorder.steps,
        outputs=outputs,
        monthly=monthly,
        contributions=contributions,
        bridge=bridge,
        transmission=transmission,
        inputs_hash=inputs_hash(model, preparation.resolved),
        result_hash=sha256(hashed_result),
        warnings=preparation.warnings,
    )
