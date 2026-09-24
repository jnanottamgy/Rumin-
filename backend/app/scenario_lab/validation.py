"""The rules a scenario version must satisfy to be saved.

Saving checks form and domain rules that do not depend on which models will run: the
Phase 1 change rules on every change, known variables, models, model inputs and
assumptions, a company node in the knowledge graph, the timing, plain decimal numbers and
stress cases. Every problem is reported at once, each with the field it concerns.

Whether a saved version can be *executed* — every figure its models need, the knowledge
graph's relationships, the constraints — is the plan's job (``planner``). A draft may be
incomplete; it may not be malformed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ChangeType, GraphNodeType, ValueKind
from app.domain.scenario_rules import MAX_DECIMAL_PLACES, validate_change
from app.graph.store import GraphReader
from app.models import EconomicVariable
from app.scenario_lab.inputs import SHARED_PATHS, assumptions, own_inputs
from app.scenario_lab.profiles import PROFILES, lab_model
from app.scenario_lab.spec import ScenarioSpec, decimal_text
from app.simulation.definitions import InputKind
from app.simulation.runtime import Issue
from app.simulation.validation import decimal_places, parse_number

MAX_STRESS_CASES = 5
MAX_STRESS_SCALE = Decimal(10)
MAX_FIGURE = Decimal("1e15")


@dataclass(frozen=True)
class VariableInfo:
    id: str
    name: str
    unit: str
    value_kind: ValueKind


def load_variables(session: Session) -> dict[str, VariableInfo]:
    return {
        row.id: VariableInfo(row.id, row.name, row.unit, row.value_kind)
        for row in session.scalars(select(EconomicVariable))
    }


def change_unit(variable: VariableInfo | None, change_type: ChangeType) -> str:
    """How a change's value reads: '%', 'percentage points' or the variable's unit."""
    if change_type is ChangeType.PERCENT_CHANGE:
        return "%"
    if variable is not None and variable.value_kind is ValueKind.RATE:
        return "percentage points"
    return variable.unit if variable is not None else ""


def _issue(code: str, message: str, field: str) -> Issue:
    return Issue(code, message, field=field)


def _check_figure(value: str | None, field: str, label: str, issues: list[Issue]) -> None:
    if value is None:
        return
    number = parse_number(value)
    if number is None:
        issues.append(
            _issue(
                "invalid_number",
                f"{label} must be a plain number such as 250000000 (no separators, symbols or "
                "exponents).",
                field,
            )
        )
    elif number < 0 or number >= MAX_FIGURE:
        issues.append(_issue("input_range", f"{label} must be at least 0 and below 10¹⁵.", field))


def validate_spec(
    session: Session, spec: ScenarioSpec, variables: Mapping[str, VariableInfo]
) -> list[Issue]:
    """Every problem that stops ``spec`` from being saved (empty when it can be)."""
    issues: list[Issue] = []

    seen: dict[str, int] = {}
    for index, shock in enumerate(spec.shocks):
        prefix = f"shocks[{index}]"
        if shock.variable_id in seen:
            issues.append(
                _issue(
                    "duplicate_variable",
                    f"This variable is already changed by input {seen[shock.variable_id] + 1}; "
                    "combine them into one change.",
                    f"{prefix}.variable_id",
                )
            )
            continue
        seen[shock.variable_id] = index
        variable = variables.get(shock.variable_id)
        if variable is None:
            issues.append(
                _issue(
                    "unknown_variable",
                    f"Unknown economic variable '{shock.variable_id}'.",
                    f"{prefix}.variable_id",
                )
            )
            continue
        violation = validate_change(
            variable.value_kind, variable.unit, shock.change_type, shock.value
        )
        if violation is not None:
            issues.append(
                _issue("invalid_change", violation.message, f"{prefix}.{violation.field}")
            )

    if spec.template_id is not None:
        from app.scenario_lab.templates import get as get_template

        if get_template(spec.template_id) is None:
            issues.append(
                _issue("unknown_template", f"Unknown template '{spec.template_id}'.", "template_id")
            )

    if spec.entity is not None:
        reader = GraphReader(session)
        if reader.latest_build() is None:
            issues.append(
                _issue(
                    "entity_unavailable",
                    "The knowledge graph has not been built, so a company cannot be chosen. "
                    "Build it (make graph) or leave the company empty.",
                    "entity",
                )
            )
        else:
            node = reader.node(spec.entity)
            if node is None:
                issues.append(
                    _issue(
                        "entity_unavailable",
                        f"'{spec.entity}' is not a node in the current knowledge graph.",
                        "entity",
                    )
                )
            elif node.node_type is not GraphNodeType.COMPANY:
                issues.append(
                    _issue(
                        "entity_unavailable",
                        f"{node.name} is a {node.node_type.value.replace('_', ' ')}, not a "
                        "company.",
                        "entity",
                    )
                )

    if spec.start_month > spec.horizon_months:
        issues.append(
            _issue(
                "timing",
                f"The changes must start within the horizon (month {spec.horizon_months} at the "
                "latest).",
                "timing.start_month",
            )
        )

    _check_figure(spec.annual_revenue, "company.annual_revenue", "Annual revenue", issues)
    _check_figure(
        spec.annual_operating_costs,
        "company.annual_operating_costs",
        "Annual operating costs",
        issues,
    )
    if spec.fx_rate is not None and spec.fx_rate.source != "stored_observation":
        _check_figure(spec.fx_rate.value, "markets.fx_rate", "The exchange rate", issues)

    for model_id, settings in spec.models.items():
        prefix = f"models.{model_id}"
        model = lab_model(model_id) if model_id in PROFILES else None
        if model is None:
            issues.append(
                _issue("unknown_model", f"'{model_id}' is not a Scenario Lab model.", prefix)
            )
            continue
        own = set(own_inputs(model))
        for name, item in settings.inputs.items():
            field = f"{prefix}.inputs.{name}"
            if name not in own:
                where = (
                    f"it is stated once for the scenario ({SHARED_PATHS[name]})"
                    if name in SHARED_PATHS
                    else "it is not one of this model's own inputs"
                )
                issues.append(
                    _issue("unknown_input", f"'{name}' cannot be set here: {where}.", field)
                )
                continue
            kind = model.definition.input(name).kind
            if item.source != "stored_observation" and kind in (
                InputKind.DECIMAL,
                InputKind.QUANTITY,
                InputKind.INTEGER,
            ):
                _check_figure(item.value, field, model.definition.input(name).label, issues)
        known = set(assumptions(model))
        for name, value in settings.assumptions.items():
            field = f"{prefix}.assumptions.{name}"
            if name not in known:
                issues.append(
                    _issue("unknown_input", f"'{name}' is not an assumption of this model.", field)
                )
            elif parse_number(value) is None:
                issues.append(
                    _issue("invalid_number", "Use a plain number such as 0.8 or 25.", field)
                )

    _validate_stress_cases(spec, variables, issues)
    return issues


def _validate_stress_cases(
    spec: ScenarioSpec, variables: Mapping[str, VariableInfo], issues: list[Issue]
) -> None:
    invalid = {
        spec.shocks[int(issue.field.split("]")[0].removeprefix("shocks["))].variable_id
        for issue in issues
        if issue.field is not None and issue.field.startswith("shocks[")
    }
    if len(spec.stress_cases) > MAX_STRESS_CASES:
        issues.append(
            _issue(
                "stress_limit",
                f"At most {MAX_STRESS_CASES} stress cases per scenario.",
                "stress_cases",
            )
        )
        return
    names: set[str] = set()
    for index, case in enumerate(spec.stress_cases):
        prefix = f"stress_cases[{index}]"
        key = case.name.strip().casefold()
        if key in names:
            issues.append(
                _issue("duplicate_name", "Each stress case needs its own name.", f"{prefix}.name")
            )
        names.add(key)
        if (case.scale is None) == (not case.changes):
            issues.append(
                _issue(
                    "stress_case",
                    "Give either a multiple of the scenario's changes or explicit values for "
                    "some of them, not both.",
                    prefix,
                )
            )
            continue
        if case.scale is not None:
            if not Decimal(0) < case.scale <= MAX_STRESS_SCALE:
                issues.append(
                    _issue(
                        "stress_case",
                        f"The multiple must be above 0 and at most {MAX_STRESS_SCALE}.",
                        f"{prefix}.scale",
                    )
                )
                continue
            if decimal_places(case.scale) > MAX_DECIMAL_PLACES:
                issues.append(
                    _issue(
                        "stress_case",
                        f"Use at most {MAX_DECIMAL_PLACES} decimal places.",
                        f"{prefix}.scale",
                    )
                )
                continue
        for variable_id in case.changes:
            if spec.shock(variable_id) is None:
                issues.append(
                    _issue(
                        "stress_case",
                        f"'{variable_id}' is not one of the scenario's changes: a stress case "
                        "changes the magnitude of the same changes, not what changes.",
                        f"{prefix}.changes.{variable_id}",
                    )
                )
        for variable_id, value in stress_changes(spec, index).items():
            shock = spec.shock(variable_id)
            variable = variables.get(variable_id)
            if shock is None or variable is None or variable_id in invalid:
                continue  # an invalid change is reported once, at the change
            violation = validate_change(
                variable.value_kind, variable.unit, shock.change_type, value
            )
            if violation is not None:
                where = (
                    f"{prefix}.changes.{variable_id}"
                    if variable_id in case.changes
                    else f"{prefix}.scale"
                )
                issues.append(
                    _issue(
                        "stress_case",
                        f"{case.name}: {variable.name} would change by "
                        f"{decimal_text(value)} {change_unit(variable, shock.change_type)}. "
                        f"{violation.message}",
                        where,
                    )
                )


def stress_changes(spec: ScenarioSpec, index: int) -> dict[str, Decimal]:
    """The values of the scenario's changes in stress case ``index``, by variable."""
    case = spec.stress_cases[index]
    values: dict[str, Decimal] = {}
    for shock in spec.shocks:
        if shock.variable_id in case.changes:
            values[shock.variable_id] = case.changes[shock.variable_id]
        elif case.scale is not None:
            values[shock.variable_id] = shock.value * case.scale
        else:
            values[shock.variable_id] = shock.value
    return values
