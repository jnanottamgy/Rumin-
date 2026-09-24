"""The plan of a scenario: which models apply, why, and whether it can be executed.

For a scenario the planner lists every Scenario Lab model with a status and its reasons:

* ``not_applicable`` — none of the scenario's changes reaches the model, or a company is
  chosen and the knowledge graph does not state the exposure the model requires;
* ``available`` — a change reaches it but it is not included by default (no company is
  chosen, or the graph does not state the company's exposure): the user may include it;
* ``excluded`` — applicable, and excluded by the user;
* ``included`` — it will run: its inputs are valid and every graph relationship it needs is
  confirmed (``engine.prepare``), and it satisfies the scenario's constraints;
* ``blocked`` — it would run, but an input is missing or invalid, a relationship is not
  confirmed or a constraint is not met. Each problem is listed with its field.

A model is included by default (``auto``) when a company is chosen and the graph states its
exposure — directly or through the company's industry. That statement is an assumption or a
curated fact about which way the company is exposed; it decides *whether* a model applies,
never *how much*: the amounts come from the user's figures and the model's equations.

The plan can be executed only if every change is modelled by an included model, no included
model is blocked, no two models claim the same item of the same line and every stress case
is valid. Nothing is filled in to make a plan executable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.domain.enums import ChangeType, GraphEdgeType
from app.domain.graph_types import EDGE_TYPES
from app.graph.store import GraphReader
from app.scenario_lab import graph as lab_graph
from app.scenario_lab.graph import EdgeView
from app.scenario_lab.inputs import model_inputs, spec_path
from app.scenario_lab.profiles import (
    CAUTIONS,
    ITEMS,
    LINE_LABELS,
    PROFILES,
    ScenarioProfile,
    lab_model,
    profile_hash,
)
from app.scenario_lab.spec import ModelMode, ScenarioSpec, ShockSpec, decimal_text, spec_hash
from app.scenario_lab.validation import VariableInfo, change_unit, stress_changes, validate_spec
from app.simulation.decimal_math import NumericalError
from app.simulation.engine import Preparation, channel_issues, prepare, shocked_nodes
from app.simulation.graph_context import needed_rules
from app.simulation.registry import RegisteredModel
from app.simulation.runtime import Issue
from app.simulation.validation import InputValue, check_range

PlanStatus = Literal["not_applicable", "available", "excluded", "included", "blocked"]
Severity = Literal["error", "warning"]

EVIDENCE_BACKED = "evidence_backed"
TIE_TYPES = (GraphEdgeType.INFLUENCES, *lab_graph.EXPOSURE_TYPES)


@dataclass(frozen=True)
class PlanIssue:
    code: str
    message: str
    severity: Severity = "error"
    field: str | None = None
    model_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "field": self.field,
            "model_id": self.model_id,
        }


@dataclass(frozen=True)
class EntityInfo:
    key: str
    name: str
    nature: str
    industries: tuple[tuple[str, str], ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "nature": self.nature,
            "industries": [{"key": key, "name": name} for key, name in self.industries],
        }


@dataclass
class ModelPlan:
    profile: ScenarioProfile
    model: RegisteredModel
    mode: ModelMode
    status: PlanStatus
    reasons: list[str]
    changes: list[str]  # variable ids of the scenario's changes it responds to
    exposure: list[list[EdgeView]]
    exposure_checked: bool  # a company is chosen, so the exposure was looked up
    preparation: Preparation | None = None
    raw: dict[str, InputValue] | None = None
    issues: list[PlanIssue] = field(default_factory=list)

    @property
    def model_id(self) -> str:
        return self.profile.model_id

    @property
    def included(self) -> bool:
        return self.status == "included"


@dataclass(frozen=True)
class ChangePlan:
    index: int
    shock: ShockSpec
    name: str
    unit: str  # how the value reads: '%', 'percentage points' or the variable's unit
    models: tuple[str, ...]  # included models that simulate it
    # Why no included model simulates it (None while the scenario has form errors, when
    # nothing is planned).
    reason: str | None

    @property
    def modelled(self) -> bool:
        return bool(self.models)


@dataclass(frozen=True)
class StressPlan:
    index: int
    name: str
    changes: dict[str, Decimal]
    issues: tuple[PlanIssue, ...]


@dataclass
class Plan:
    spec: ScenarioSpec
    spec_hash: str
    graph_build_id: int | None
    freshness: str
    entity: EntityInfo | None
    variables: dict[str, VariableInfo]
    changes: list[ChangePlan]
    models: list[ModelPlan]
    stress: list[StressPlan]
    cautions: list[PlanIssue]
    issues: list[PlanIssue]  # scenario-level
    # The graph's relationships from the changed variables (influences, affects …): the
    # pathway marks the ones no included model simulates as not modelled.
    ties: list[EdgeView] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)
    affected: dict[str, Any] | None = None

    @property
    def included(self) -> list[ModelPlan]:
        return [item for item in self.models if item.included]

    @property
    def all_issues(self) -> list[PlanIssue]:
        found = list(self.issues)
        for change in self.changes:
            if not change.modelled and change.reason is not None:
                found.append(
                    PlanIssue(
                        "unmodelled_change",
                        f"{change.name} {signed(change.shock.value)} {change.unit}: "
                        f"{change.reason}",
                        field=f"shocks[{change.index}]",
                    )
                )
        for item in self.models:
            found.extend(item.issues)
        for case in self.stress:
            found.extend(case.issues)
        found.extend(self.cautions)
        return found

    @property
    def errors(self) -> list[PlanIssue]:
        return [issue for issue in self.all_issues if issue.severity == "error"]

    @property
    def executable(self) -> bool:
        return bool(self.included) and not self.errors


def signed(value: Decimal) -> str:
    text = decimal_text(value)
    return text if text.startswith("-") else f"+{text}"


# --- Building the plan -------------------------------------------------------------------------


def _entity(session: Session, key: str | None) -> EntityInfo | None:
    if key is None:
        return None
    reader = GraphReader(session)
    node = reader.node(key)
    if node is None:
        return None
    memberships = lab_graph.industries_of(session, key)
    names = reader.nodes([edge.target for edge in memberships])
    return EntityInfo(
        key=node.key,
        name=node.name,
        nature=node.nature.value,
        industries=tuple(
            (edge.target, names[edge.target].name if edge.target in names else edge.target)
            for edge in memberships
        ),
    )


def _variable_name(variables: Mapping[str, VariableInfo], variable_id: str) -> str:
    variable = variables.get(variable_id)
    return variable.name if variable else variable_id


def _responds(profile: ScenarioProfile, spec: ScenarioSpec) -> tuple[list[str], list[str]]:
    """Variables of the scenario's changes the model takes, and those it binds with another
    kind of change (which it refuses)."""
    takes: list[str] = []
    other_kind: list[str] = []
    for shock in spec.shocks:
        binding = profile.binding(shock.variable_id)
        if binding is None:
            continue
        if binding.change_type is shock.change_type:
            takes.append(shock.variable_id)
        else:
            other_kind.append(shock.variable_id)
    return takes, other_kind


def _relation(edge_type: str) -> str:
    return EDGE_TYPES[GraphEdgeType(edge_type)].label


def _chain_text(chain: list[EdgeView], names: Mapping[str, str]) -> str:
    first = chain[0]
    source = names.get(first.source, first.source)
    target = names.get(first.target, first.target)
    text = f"{source} {_relation(first.edge_type)} {target}"
    if len(chain) > 1:
        text += f", the industry of {names.get(chain[1].source, chain[1].source)}"
    return text


def _exposure_names(session: Session, chains: list[list[EdgeView]]) -> dict[str, str]:
    keys = {end for chain in chains for edge in chain for end in (edge.source, edge.target)}
    return {key: node.name for key, node in lab_graph.nodes(session, keys).items()}


def _kind_text(change_type: ChangeType) -> str:
    return (
        "percent changes"
        if change_type is ChangeType.PERCENT_CHANGE
        else ("changes in percentage points")
    )


def _needs_text(profile: ScenarioProfile, variables: Mapping[str, VariableInfo]) -> str:
    parts = []
    for binding in profile.shocks:
        name = _variable_name(variables, binding.variable_id)
        kind = "%" if binding.change_type is ChangeType.PERCENT_CHANGE else "percentage points"
        parts.append(f"{name} ({kind})")
    return ", ".join(parts)


def _evidence_issues(
    item: ModelPlan, preparation: Preparation, spec: ScenarioSpec
) -> list[PlanIssue]:
    """The constraint 'evidence-backed relationships only' on the relationships the model's
    shocks would travel along."""
    if spec.evidence != EVIDENCE_BACKED or preparation.values is None:
        return []
    issues: list[PlanIssue] = []
    definition = item.model.definition
    for rule_id in needed_rules(definition, shocked_nodes(item.model, preparation.values)):
        edge = preparation.graph.transmission.get(rule_id)
        if edge is not None and edge.evidence_status != EVIDENCE_BACKED:
            names = preparation.graph.names
            issues.append(
                PlanIssue(
                    "constraint_evidence",
                    f"Rule {rule_id} follows '{names.get(edge.source, edge.source)} → "
                    f"{names.get(edge.target, edge.target)}', which the knowledge graph records "
                    f"as {edge.evidence_status.replace('_', ' ')}. The scenario requires "
                    "evidence-backed relationships only.",
                    field="constraints.evidence",
                    model_id=item.model_id,
                )
            )
    return issues


def _stored_data_issues(
    item: ModelPlan, preparation: Preparation, spec: ScenarioSpec
) -> list[PlanIssue]:
    """The constraint 'stored market data only': every market baseline must be a stored
    observation, never a typed value."""
    if not spec.stored_market_data:
        return []
    issues: list[PlanIssue] = []
    for entry in preparation.resolved.values():
        if entry.category.value != "market_baseline" or entry.source.value == "stored_observation":
            continue
        has_source = bool(item.model.definition.input(entry.id).sources)
        why = (
            "use the stored series instead of a typed value"
            if has_source
            else "RUMIN stores no values for it, so this model cannot meet the constraint"
        )
        issues.append(
            PlanIssue(
                "constraint_stored_data",
                f"{entry.label} is typed, but the scenario requires stored market data only: "
                f"{why}.",
                field=spec_path(spec, item.profile, item.model, entry.id),
                model_id=item.model_id,
            )
        )
    return issues


def _model_issues(item: ModelPlan, preparation: Preparation, spec: ScenarioSpec) -> list[PlanIssue]:
    # The scenario reports the graph's freshness and the fictional-company note once.
    shared_codes = {"graph_stale", "fictional_entity"}
    return [
        PlanIssue(
            issue.code,
            issue.message,
            issue.severity,
            spec_path(spec, item.profile, item.model, issue.field) if issue.field else None,
            item.model_id,
        )
        for issue in preparation.issues
        if issue.code not in shared_codes
    ]


def _plan_model(
    session: Session,
    spec: ScenarioSpec,
    profile: ScenarioProfile,
    model: RegisteredModel,
    entity: EntityInfo | None,
    variables: Mapping[str, VariableInfo],
    freshness: str,
) -> ModelPlan:
    settings = spec.settings(profile.model_id)
    mode = settings.mode
    takes, other_kind = _responds(profile, spec)
    chains: list[list[EdgeView]] = []
    if entity is not None:
        chains = lab_graph.profile_exposure(session, entity.key, profile)
        if spec.evidence == EVIDENCE_BACKED:
            chains = [
                chain
                for chain in chains
                if all(edge.evidence_status == EVIDENCE_BACKED for edge in chain)
            ]
    item = ModelPlan(
        profile=profile,
        model=model,
        mode=mode,
        status="not_applicable",
        reasons=[],
        changes=takes,
        exposure=chains,
        exposure_checked=entity is not None,
    )

    if not takes:
        if other_kind:
            for variable_id in other_kind:
                binding = profile.binding(variable_id)
                if binding is None:  # pragma: no cover - other_kind holds bound variables
                    continue
                item.reasons.append(
                    f"It takes {_kind_text(binding.change_type)} to "
                    f"{_variable_name(variables, variable_id)}; the scenario's change is of "
                    "another kind and is never converted."
                )
        else:
            item.reasons.append(
                f"None of the scenario's changes reaches it. It responds to "
                f"{_needs_text(profile, variables)}."
            )
        if mode == "include":
            item.issues.append(
                PlanIssue(
                    "model_not_reached",
                    f"{profile.title} is included, but none of the scenario's changes reaches it, "
                    "so it is not run.",
                    "warning",
                    f"models.{profile.model_id}.mode",
                    profile.model_id,
                )
            )
        return item

    names = _exposure_names(session, chains) if chains else {}
    stated = bool(chains)
    if entity is not None and not stated:
        exposure_text = " or ".join(
            f"{_variable_name(variables, exposure.variable_id)} "
            f"{' or '.join(_relation(name) for name in exposure.relationships)}"
            for exposure in profile.exposures
        )
        qualifier = " (evidence-backed)" if spec.evidence == EVIDENCE_BACKED else ""
        missing = (
            f"The knowledge graph does not state{qualifier} that {exposure_text} "
            f"{entity.name} or its industry."
        )
        if profile.exposure_required:
            item.reasons.append(f"{missing} This model only simulates companies it does.")
            if mode == "include":
                item.status = "blocked"
                item.issues.append(
                    PlanIssue(
                        "exposure_required",
                        f"{profile.title}: {missing} This model only simulates companies it "
                        "does; choose another company, none, or exclude the model.",
                        field="entity",
                        model_id=profile.model_id,
                    )
                )
            return item
        item.reasons.append(missing)
    elif stated:
        item.reasons.append(
            "The knowledge graph states that "
            + "; ".join(_chain_text(chain, names) for chain in chains)
            + ". This decides whether the model applies, not how much: the amounts come from "
            "your figures."
        )

    if mode == "exclude":
        item.status = "excluded"
        item.reasons.append("Excluded by you.")
        return item
    if mode == "auto" and not (entity is not None and stated):
        item.status = "available"
        item.reasons.append(
            "Not included by default: "
            + ("no company is chosen." if entity is None else "the exposure is not stated.")
            + " Include it to use it."
        )
        return item

    item.reasons.append("Included by you." if mode == "include" else "Included by default.")
    if mode == "include" and entity is not None and not stated:
        item.issues.append(
            PlanIssue(
                "exposure_not_stated",
                f"{profile.title}: the knowledge graph does not state this exposure of "
                f"{entity.name}; the result rests on your figures alone.",
                "warning",
                "entity",
                profile.model_id,
            )
        )
    item.raw = model_inputs(spec, profile, model)
    preparation = prepare(session, model, item.raw, freshness=freshness)
    item.preparation = preparation
    item.issues.extend(_model_issues(item, preparation, spec))
    item.issues.extend(_evidence_issues(item, preparation, spec))
    item.issues.extend(_stored_data_issues(item, preparation, spec))
    blocked = not preparation.ok or any(
        issue.severity == "error" for issue in item.issues if issue.model_id == profile.model_id
    )
    item.status = "blocked" if blocked else "included"
    return item


def _unmodelled_reason(
    shock: ShockSpec,
    models: list[ModelPlan],
    variables: Mapping[str, VariableInfo],
) -> str:
    candidates = [item for item in models if shock.variable_id in item.changes]
    if candidates:
        parts = []
        for item in candidates:
            if item.status == "available":
                parts.append(f"include {item.profile.title}")
            elif item.status == "excluded":
                parts.append(f"{item.profile.title} is excluded")
            elif item.status == "blocked":
                parts.append(f"{item.profile.title} is blocked (see its issues)")
            else:
                parts.append(f"{item.profile.title} does not apply to this company")
        return "No included model simulates it: " + "; ".join(parts) + "."
    kinds = [
        binding
        for item in models
        if (binding := item.profile.binding(shock.variable_id)) is not None
    ]
    if kinds:
        return (
            f"The models that respond to {_variable_name(variables, shock.variable_id)} take "
            f"{_kind_text(kinds[0].change_type)}; this change is of another kind and is never "
            "converted."
        )
    return (
        f"No registered model responds to a change in "
        f"{_variable_name(variables, shock.variable_id)}."
    )


def _stress_plans(spec: ScenarioSpec, models: list[ModelPlan]) -> list[StressPlan]:
    """Each stress case's changes, checked against every included model: the input ranges
    and the model's own consistency rules. Invalid cases are reported, never clipped."""
    plans: list[StressPlan] = []
    for index, case in enumerate(spec.stress_cases):
        changes = stress_changes(spec, index)
        issues: list[PlanIssue] = []
        for item in models:
            preparation = item.preparation
            if not item.included or preparation is None or preparation.values is None:
                continue
            numbers = dict(preparation.values.numbers)
            problem: str | None = None
            for binding in item.profile.shocks:
                if binding.variable_id not in changes or binding.variable_id not in item.changes:
                    continue
                definition = item.model.definition.input(binding.input_id)
                value = changes[binding.variable_id]
                problem = check_range(definition, value)
                if problem:
                    problem = f"{definition.label} {problem}"
                    break
                numbers[binding.input_id] = value
            if problem is None:
                varied = replace(preparation.values, numbers=numbers)
                try:
                    blocking = [
                        issue for issue in item.model.check(varied) if issue.severity == "error"
                    ]
                    blocking += [
                        issue
                        for issue in channel_issues(item.model, varied, preparation.graph)
                        if issue.severity == "error"
                    ]
                except NumericalError as error:
                    blocking = [Issue(error.code, error.message)]
                if blocking:
                    problem = blocking[0].message
            if problem:
                issues.append(
                    PlanIssue(
                        "stress_case_invalid",
                        f"{case.name} cannot be evaluated with {item.profile.title}: {problem} "
                        "It is refused, not adjusted.",
                        field=f"stress_cases[{index}]",
                        model_id=item.model_id,
                    )
                )
        plans.append(StressPlan(index, case.name, changes, tuple(issues)))
    return plans


def _scenario_issues(
    spec: ScenarioSpec, freshness: str, graph_build_id: int | None, entity: EntityInfo | None
) -> list[PlanIssue]:
    issues: list[PlanIssue] = []
    if freshness == "stale":
        issues.append(
            PlanIssue(
                "graph_stale",
                f"The knowledge graph (build #{graph_build_id}) is older than its sources; the "
                "relationships it confirms are those of that build.",
                "warning",
            )
        )
    elif freshness == "not_built":
        issues.append(
            PlanIssue(
                "graph_not_built",
                "The knowledge graph has not been built: no relationship can be confirmed, so "
                "only changes a model applies directly can run.",
                "warning",
            )
        )
    if entity is not None and entity.nature != "real":
        kind = "a fictional company" if entity.nature == "fictional" else "sample data"
        issues.append(
            PlanIssue(
                "fictional_entity",
                f"{entity.name} is {kind} in RUMIN's sample network: the results describe the "
                "figures you entered, not a real company.",
                "warning",
                "entity",
            )
        )
    if spec.duration_months > 0 and spec.end_month > spec.horizon_months:
        issues.append(
            PlanIssue(
                "timing_beyond_horizon",
                f"The changes last until month {spec.end_month}, beyond the {spec.horizon_months}-"
                "month horizon: only the months within it are simulated.",
                "warning",
                "timing.duration_months",
            )
        )
    return issues


def build_plan(
    session: Session,
    spec: ScenarioSpec,
    *,
    freshness: str,
    variables: Mapping[str, VariableInfo],
    preview: bool = True,
) -> Plan:
    """Plan ``spec``: validate it, decide each model's status and prepare the included
    models (inputs validated, stored data resolved, graph relationships confirmed).
    ``preview`` adds the companies the graph ties to the changed variables."""
    build = GraphReader(session).latest_build()
    build_id = build.id if build else None
    form = validate_spec(session, spec, variables)
    entity = _entity(session, spec.entity) if build is not None else None
    issues = [PlanIssue(issue.code, issue.message, issue.severity, issue.field) for issue in form]
    issues.extend(_scenario_issues(spec, freshness, build_id, entity))

    models: list[ModelPlan] = []
    if not form:
        for profile in PROFILES.values():
            model = lab_model(profile.model_id)
            if model is None:  # pragma: no cover - check_profiles guarantees it
                continue
            models.append(_plan_model(session, spec, profile, model, entity, variables, freshness))

    changes = []
    for index, shock in enumerate(spec.shocks):
        simulated = tuple(
            item.model_id for item in models if item.included and shock.variable_id in item.changes
        )
        changes.append(
            ChangePlan(
                index=index,
                shock=shock,
                name=_variable_name(variables, shock.variable_id),
                unit=change_unit(variables.get(shock.variable_id), shock.change_type),
                models=simulated,
                reason=None if simulated or form else _unmodelled_reason(shock, models, variables),
            )
        )
    included = [item for item in models if item.included]
    claimed: dict[tuple[str, str], str] = {}
    for item in included:
        for contribution in item.profile.lines:
            key = (contribution.line, contribution.item)
            if key in claimed:
                issues.append(
                    PlanIssue(
                        "double_counting",
                        f"{item.profile.title} and {claimed[key]} both cover "
                        f"'{ITEMS[contribution.item]}' in {LINE_LABELS[contribution.line]}: "
                        "exclude one of them.",
                        field=f"models.{item.model_id}.mode",
                        model_id=item.model_id,
                    )
                )
            claimed[key] = item.profile.title
    cautions = [
        PlanIssue("cross_effect", text, "warning", model_id=None)
        for pair, text in CAUTIONS.items()
        if pair <= {item.model_id for item in included}
    ]
    ties: list[EdgeView] = []
    names: dict[str, str] = {}
    affected: dict[str, Any] | None = None
    changed = [lab_graph.variable_key(shock.variable_id) for shock in spec.shocks]
    if build is not None and not form:
        ties = lab_graph.edges(session, types=TIE_TYPES, sources=changed)
        names = {
            key: node.name
            for key, node in lab_graph.nodes(
                session, {end for edge in ties for end in (edge.source, edge.target)}
            ).items()
        }
        if preview:
            affected = lab_graph.affected_entities(
                session, [shock.variable_id for shock in spec.shocks], PROFILES
            )
    return Plan(
        spec=spec,
        spec_hash=spec_hash(spec),
        graph_build_id=build_id,
        freshness=freshness,
        entity=entity,
        variables=dict(variables),
        changes=changes,
        models=models,
        stress=_stress_plans(spec, models) if not form else [],
        cautions=cautions,
        issues=issues,
        ties=ties,
        names=names,
        affected=affected,
    )


# --- JSON --------------------------------------------------------------------------------------


def model_plan_json(item: ModelPlan) -> dict[str, Any]:
    definition = item.model.definition
    return {
        "model_id": item.model_id,
        "version": definition.version,
        "name": definition.name,
        "title": item.profile.title,
        "covers": item.profile.covers,
        "definition_hash": item.model.definition_hash,
        "profile_hash": profile_hash(item.profile),
        "mode": item.mode,
        "status": item.status,
        "reasons": item.reasons,
        "changes": item.changes,
        "responds_to": [
            {
                "variable_id": binding.variable_id,
                "change_type": binding.change_type.value,
                "input": binding.input_id,
            }
            for binding in item.profile.shocks
        ],
        "lines": [
            {
                "line": contribution.line,
                "item": contribution.item,
                "label": contribution.label,
                "output": contribution.output,
            }
            for contribution in item.profile.lines
        ],
        "exposure": {
            "checked": item.exposure_checked,
            "required": item.profile.exposure_required,
            "stated": bool(item.exposure),
            "chains": [[edge.to_json() for edge in chain] for chain in item.exposure],
        },
        "issues": [issue.to_json() for issue in item.issues],
        "inputs": [entry.snapshot() for entry in item.preparation.resolved.values()]
        if item.preparation is not None
        else [],
        "graph": item.preparation.graph.snapshot() if item.preparation is not None else None,
    }


def plan_json(plan: Plan) -> dict[str, Any]:
    """The plan as stored with an execution and served by the API."""
    return {
        "spec_hash": plan.spec_hash,
        "executable": plan.executable,
        "graph": {"build_id": plan.graph_build_id, "freshness": plan.freshness},
        "entity": plan.entity.to_json() if plan.entity else None,
        "changes": [
            {
                "index": change.index,
                "variable_id": change.shock.variable_id,
                "name": change.name,
                "change_type": change.shock.change_type.value,
                "value": decimal_text(change.shock.value),
                "unit": change.unit,
                "modelled": change.modelled,
                "models": list(change.models),
                "reason": change.reason,
            }
            for change in plan.changes
        ],
        "models": [model_plan_json(item) for item in plan.models],
        "stress_cases": [
            {
                "index": case.index,
                "name": case.name,
                "changes": {key: decimal_text(value) for key, value in case.changes.items()},
                "valid": not case.issues,
                "issues": [issue.to_json() for issue in case.issues],
            }
            for case in plan.stress
        ],
        "issues": [issue.to_json() for issue in plan.all_issues],
        "errors": len(plan.errors),
        "ties": [edge.to_json() for edge in plan.ties],
        "names": dict(sorted(plan.names.items())),
        "affected": plan.affected,
    }
