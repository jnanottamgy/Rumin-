"""Scenarios and their versions: create, read, save a new version, duplicate, restore,
delete; the plan and the preview of a scenario.

Saving never overwrites. Every save that changes anything adds a version; a save that
changes nothing adds none; a save based on an older version than the latest is refused
(409) when the request says which version it started from. A scenario that has been
executed cannot be deleted: its executions must stay reproducible.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.db.base import utcnow
from app.domain.enums import ScenarioStatus
from app.graph.store import GraphReader
from app.models import Scenario, ScenarioExecution, ScenarioShock, ScenarioVersion
from app.scenario_lab.executor import (
    combine,
    evaluate_stress,
    members_of,
    results_json,
    simulate,
)
from app.scenario_lab.executor import spec_of as version_spec
from app.scenario_lab.pathways import complete, trace
from app.scenario_lab.planner import Plan, build_plan, plan_json
from app.scenario_lab.spec import (
    ModelSettings,
    ScenarioSpec,
    ShockSpec,
    StressCaseSpec,
    ValueSpec,
    decimal_text,
    spec_hash,
    spec_json,
)
from app.scenario_lab.validation import load_variables, validate_spec
from app.schemas.common import ErrorDetail
from app.schemas.scenario import (
    ExecutionSummaryRead,
    HeadlineRead,
    PlanRead,
    PreviewRead,
    ResultsRead,
    ScenarioDuplicateRequest,
    ScenarioInput,
    ScenarioPage,
    ScenarioRead,
    ScenarioSpecRead,
    ScenarioSummaryRead,
    ScenarioUpdate,
    ShockRead,
    VersionRead,
    VersionSummaryRead,
)
from app.schemas.simulation import SimulationInputValue
from app.services import graph as graph_service
from app.simulation.decimal_math import NumericalError
from app.simulation.validation import parse_number

PREVIEW_NOTE = (
    "Computed from the scenario as it stands and not stored. Execute the scenario to keep "
    "a reproducible record."
)


# --- Request → typed scenario -------------------------------------------------------------------


def _text(raw: str | int | float | None) -> str | None:
    """A number's canonical text ("0300.50" → "300.5"), or the raw text when it is not a
    plain number (validation then reports it)."""
    if raw is None:
        return None
    number = parse_number(raw)
    return decimal_text(number) if number is not None else str(raw)


def _value(item: SimulationInputValue | None) -> ValueSpec | None:
    if item is None:
        return None
    return ValueSpec(
        value=_text(item.value), unit=item.unit, source=item.source, series_id=item.series_id
    )


def _invalid_number(field: str) -> ErrorDetail:
    return ErrorDetail(
        location="body",
        field=field,
        message="Use a plain number such as 20 or 2.5 (no separators, symbols or exponents).",
        type="invalid_number",
    )


def to_spec(payload: ScenarioInput) -> ScenarioSpec:
    """The typed scenario a request describes; 422 if a change or stress value is not a
    plain number (other values are checked by ``validate_spec``)."""
    details: list[ErrorDetail] = []
    shocks: list[ShockSpec] = []
    for index, shock in enumerate(payload.shocks):
        value = parse_number(shock.value)
        if value is None:
            details.append(_invalid_number(f"shocks[{index}].value"))
            continue
        shocks.append(ShockSpec(shock.variable_id, shock.change_type, value, shock.note))
    cases: list[StressCaseSpec] = []
    for index, case in enumerate(payload.stress_cases):
        scale = parse_number(case.scale) if case.scale is not None else None
        if case.scale is not None and scale is None:
            details.append(_invalid_number(f"stress_cases[{index}].scale"))
        changes: dict[str, Decimal] = {}
        for variable, raw in case.changes.items():
            number = parse_number(raw)
            if number is None:
                details.append(_invalid_number(f"stress_cases[{index}].changes.{variable}"))
            else:
                changes[variable] = number
        cases.append(StressCaseSpec(name=case.name, scale=scale, changes=changes))
    if details:
        raise DomainValidationError("The scenario inputs are invalid.", details=details)
    return ScenarioSpec(
        name=payload.name,
        description=payload.description,
        template_id=payload.template_id,
        shocks=tuple(shocks),
        entity=payload.entity,
        start_month=payload.timing.start_month,
        duration_months=payload.timing.duration_months,
        horizon_months=payload.timing.horizon_months,
        reporting_currency=payload.company.reporting_currency,
        annual_revenue=_text(payload.company.annual_revenue),
        annual_operating_costs=_text(payload.company.annual_operating_costs),
        fx_rate=_value(payload.markets.fx_rate),
        models={
            model_id: ModelSettings(
                mode=settings.mode,
                inputs={
                    name: spec_value
                    for name, raw in settings.inputs.items()
                    if (spec_value := _value(raw)) is not None
                },
                assumptions={
                    name: text
                    for name, raw in settings.assumptions.items()
                    if (text := _text(raw)) is not None
                },
            )
            for model_id, settings in payload.models.items()
        },
        evidence=payload.constraints.evidence,
        stored_market_data=payload.constraints.stored_market_data,
        stress_cases=tuple(cases),
    )


def _validated(session: Session, payload: ScenarioInput) -> ScenarioSpec:
    spec = to_spec(payload)
    issues = validate_spec(session, spec, load_variables(session))
    if issues:
        raise DomainValidationError(
            "The scenario inputs are invalid.",
            details=[
                ErrorDetail(
                    location="body", field=issue.field, message=issue.message, type=issue.code
                )
                for issue in issues
            ],
        )
    return spec


# --- Reading ------------------------------------------------------------------------------------


def scenario_or_404(session: Session, scenario_id: uuid.UUID) -> Scenario:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        raise NotFoundError(f"No scenario with ID '{scenario_id}'.")
    return scenario


def version_of(scenario: Scenario, number: int | None = None) -> ScenarioVersion:
    wanted = number if number is not None else scenario.current_version
    version = next((item for item in scenario.versions if item.version == wanted), None)
    if version is None:
        raise NotFoundError(f"Scenario '{scenario.id}' has no version {wanted}.")
    return version


def _shocks(version: ScenarioVersion) -> list[ShockRead]:
    return [
        ShockRead(
            variable_id=shock.variable_id,
            change_type=shock.change_type,
            value=Decimal(shock.value),
            note=shock.note,
        )
        for shock in version.shocks
    ]


def _execution_counts(session: Session, scenario_ids: Sequence[uuid.UUID]) -> dict[int, int]:
    """Executions per version id."""
    if not scenario_ids:
        return {}
    rows = session.execute(
        select(ScenarioExecution.scenario_version_id, func.count())
        .where(ScenarioExecution.scenario_id.in_(list(scenario_ids)))
        .group_by(ScenarioExecution.scenario_version_id)
    ).tuples()
    return {version_id: count for version_id, count in rows}


def execution_summary(row: ScenarioExecution) -> ExecutionSummaryRead:
    results = row.results or {}
    currency = results.get("currency", "")
    headline_ids = ("operating_profit", "profit_before_tax", "operating_costs", "interest_expense")
    lines = {line["id"]: line for line in results.get("lines", [])}
    headline = [
        HeadlineRead(
            id=line_id,
            label=lines[line_id]["label"],
            change=Decimal(lines[line_id]["change"]),
            percent_change=Decimal(lines[line_id]["percent_change"])
            if lines[line_id]["percent_change"] is not None
            else None,
            currency=currency,
        )
        for line_id in headline_ids
        if line_id in lines
    ][:2]
    return ExecutionSummaryRead(
        id=row.id,
        scenario_id=row.scenario_id,
        version=row.version,
        status=row.status,
        requested_at=row.requested_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        inputs_hash=row.inputs_hash,
        result_hash=row.result_hash,
        headline=headline,
        models=[item.model_id for item in row.runs],
        error=row.error,
    )


def _latest_execution(session: Session, scenario_id: uuid.UUID) -> ScenarioExecution | None:
    return session.scalars(
        select(ScenarioExecution)
        .where(ScenarioExecution.scenario_id == scenario_id)
        .order_by(ScenarioExecution.requested_at.desc(), ScenarioExecution.id)
        .limit(1)
    ).first()


def _version_summary(version: ScenarioVersion, executions: int) -> VersionSummaryRead:
    return VersionSummaryRead(
        version=version.version,
        name=version.name,
        spec_hash=version.spec_hash,
        note=version.note,
        derived_from=version.derived_from,
        created_at=version.created_at,
        executions=executions,
    )


def _spec_read(version: ScenarioVersion) -> ScenarioSpecRead:
    return ScenarioSpecRead.model_validate(spec_json(version_spec(version)))


def scenario_read(session: Session, scenario: Scenario) -> ScenarioRead:
    current = version_of(scenario)
    counts = _execution_counts(session, [scenario.id])
    latest = _latest_execution(session, scenario.id)
    return ScenarioRead(
        id=scenario.id,
        name=scenario.name,
        description=scenario.description,
        status=scenario.status,
        template_id=scenario.template_id,
        current_version=scenario.current_version,
        shocks=_shocks(current),
        spec=_spec_read(current),
        versions=[
            _version_summary(version, counts.get(version.id, 0))
            for version in sorted(scenario.versions, key=lambda item: -item.version)
        ],
        latest_execution=execution_summary(latest) if latest else None,
        executions=sum(counts.values()),
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


def list_scenarios(session: Session, *, limit: int, offset: int) -> ScenarioPage:
    total = session.scalar(select(func.count()).select_from(Scenario)) or 0
    rows = session.scalars(
        select(Scenario)
        .order_by(Scenario.updated_at.desc(), Scenario.id)
        .limit(limit)
        .offset(offset)
    ).all()
    counts = _execution_counts(session, [row.id for row in rows])
    items = []
    for row in rows:
        current = version_of(row)
        latest = _latest_execution(session, row.id)
        items.append(
            ScenarioSummaryRead(
                id=row.id,
                name=row.name,
                description=row.description,
                template_id=row.template_id,
                current_version=row.current_version,
                shocks=_shocks(current),
                entity=current.spec.get("entity"),
                latest_execution=execution_summary(latest) if latest else None,
                executions=sum(counts.get(version.id, 0) for version in row.versions),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return ScenarioPage(items=items, total=total, limit=limit, offset=offset)


def get_scenario(session: Session, scenario_id: uuid.UUID) -> ScenarioRead:
    return scenario_read(session, scenario_or_404(session, scenario_id))


def list_versions(session: Session, scenario_id: uuid.UUID) -> list[VersionSummaryRead]:
    scenario = scenario_or_404(session, scenario_id)
    counts = _execution_counts(session, [scenario.id])
    return [
        _version_summary(version, counts.get(version.id, 0))
        for version in sorted(scenario.versions, key=lambda item: -item.version)
    ]


def get_version(session: Session, scenario_id: uuid.UUID, number: int) -> VersionRead:
    scenario = scenario_or_404(session, scenario_id)
    version = version_of(scenario, number)
    counts = _execution_counts(session, [scenario.id])
    return VersionRead(
        **_version_summary(version, counts.get(version.id, 0)).model_dump(),
        scenario_id=scenario.id,
        description=version.description,
        template_id=version.template_id,
        shocks=_shocks(version),
        spec=_spec_read(version),
    )


# --- Writing ------------------------------------------------------------------------------------


def _new_version(
    scenario: Scenario,
    spec: ScenarioSpec,
    *,
    number: int,
    note: str,
    derived_from: dict[str, Any] | None,
) -> ScenarioVersion:
    version = ScenarioVersion(
        version=number,
        name=spec.name,
        description=spec.description,
        template_id=spec.template_id,
        spec=spec_json(spec),
        spec_hash=spec_hash(spec),
        derived_from=derived_from,
        note=note,
    )
    version.shocks = [
        ScenarioShock(
            position=position,
            variable_id=shock.variable_id,
            change_type=shock.change_type,
            value=shock.value,
            note=shock.note,
        )
        for position, shock in enumerate(spec.shocks)
    ]
    scenario.versions.append(version)
    scenario.current_version = number
    scenario.name = spec.name
    scenario.description = spec.description
    scenario.template_id = spec.template_id
    return version


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ConflictError(
            "Another version of this scenario was saved at the same time. Reload it and save again."
        ) from error


def create_scenario(session: Session, payload: ScenarioInput) -> ScenarioRead:
    spec = _validated(session, payload)
    scenario = Scenario(
        name=spec.name,
        description=spec.description,
        status=ScenarioStatus.DRAFT,
        current_version=1,
        template_id=spec.template_id,
    )
    session.add(scenario)
    _new_version(scenario, spec, number=1, note=payload.note, derived_from=None)
    _commit(session)
    return scenario_read(session, scenario)


def save_version(session: Session, scenario_id: uuid.UUID, payload: ScenarioUpdate) -> ScenarioRead:
    scenario = scenario_or_404(session, scenario_id)
    if payload.base_version is not None and payload.base_version != scenario.current_version:
        raise ConflictError(
            f"Version {scenario.current_version} was saved after the version you edited "
            f"({payload.base_version}). Reload the scenario before saving, so no change is lost."
        )
    spec = _validated(session, payload)
    if spec_hash(spec) == version_of(scenario).spec_hash:
        return scenario_read(session, scenario)  # nothing changed: no new version
    _new_version(
        scenario, spec, number=scenario.current_version + 1, note=payload.note, derived_from=None
    )
    scenario.updated_at = utcnow()
    _commit(session)
    return scenario_read(session, scenario)


def restore_version(session: Session, scenario_id: uuid.UUID, number: int) -> ScenarioRead:
    """Save an earlier version's content as the newest version (nothing is deleted)."""
    scenario = scenario_or_404(session, scenario_id)
    source = version_of(scenario, number)
    if source.spec_hash == version_of(scenario).spec_hash:
        return scenario_read(session, scenario)
    _new_version(
        scenario,
        version_spec(source),
        number=scenario.current_version + 1,
        note=f"Restored from version {number}.",
        derived_from={"kind": "restore", "scenario_id": str(scenario.id), "version": number},
    )
    scenario.updated_at = utcnow()
    _commit(session)
    return scenario_read(session, scenario)


def duplicate_scenario(
    session: Session, scenario_id: uuid.UUID, payload: ScenarioDuplicateRequest
) -> ScenarioRead:
    original = scenario_or_404(session, scenario_id)
    source = version_of(original, payload.version)
    spec = version_spec(source)
    name = payload.name or f"{spec.name} (copy)"[:120]
    copy = ScenarioSpec(**{**spec.__dict__, "name": name})
    scenario = Scenario(
        name=name,
        description=copy.description,
        status=ScenarioStatus.DRAFT,
        current_version=1,
        template_id=copy.template_id,
    )
    session.add(scenario)
    _new_version(
        scenario,
        copy,
        number=1,
        note=f"Duplicated from '{original.name}', version {source.version}.",
        derived_from={
            "kind": "duplicate",
            "scenario_id": str(original.id),
            "version": source.version,
        },
    )
    _commit(session)
    return scenario_read(session, scenario)


def delete_scenario(session: Session, scenario_id: uuid.UUID) -> None:
    scenario = scenario_or_404(session, scenario_id)
    executed = session.scalar(
        select(func.count()).where(ScenarioExecution.scenario_id == scenario.id)
    )
    if executed:
        raise ConflictError(
            "This scenario has been executed, so it is kept: its executions must stay "
            "reproducible. Duplicate it to start a new line of work."
        )
    session.delete(scenario)
    session.commit()


# --- Plan and preview ---------------------------------------------------------------------------


def freshness(session: Session) -> str:
    return graph_service.freshness(session, GraphReader(session).latest_build()).status


def plan_for(session: Session, spec: ScenarioSpec, *, preview: bool = True) -> Plan:
    return build_plan(
        session,
        spec,
        freshness=freshness(session),
        variables=load_variables(session),
        preview=preview,
    )


def plan_draft(session: Session, payload: ScenarioInput) -> PlanRead:
    return PlanRead.model_validate(plan_json(plan_for(session, to_spec(payload))))


def plan_version(session: Session, scenario_id: uuid.UUID, number: int | None) -> PlanRead:
    scenario = scenario_or_404(session, scenario_id)
    return PlanRead.model_validate(
        plan_json(plan_for(session, version_spec(version_of(scenario, number))))
    )


def preview(session: Session, payload: ScenarioInput) -> PreviewRead:
    """Plan a draft and, if it can be executed, compute its results without storing them."""
    plan = plan_for(session, to_spec(payload))
    data = plan_json(plan)
    if not plan.executable:
        return PreviewRead(
            plan=PlanRead.model_validate(data), results=None, pathway=None, note=PREVIEW_NOTE
        )
    members = members_of(plan)
    try:
        executions = simulate(members)
        combined = combine(plan.spec, members, executions, evaluate_stress(plan.spec, members))
    except NumericalError as error:
        raise DomainValidationError(
            "The scenario could not be calculated.",
            details=[ErrorDetail(location="body", message=error.message, type=error.code)],
        ) from error
    pathway = complete(trace(plan, executions), plan, combined.main)
    results = results_json(plan, members, executions, combined, pathway, {})
    return PreviewRead(
        plan=PlanRead.model_validate(data),
        results=ResultsRead.model_validate({**results, "execution_id": None}),
        pathway=pathway,
        note=PREVIEW_NOTE,
    )
