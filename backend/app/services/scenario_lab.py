"""API logic for executions, their results and analyses, comparisons and templates.

An execution is requested with ``POST /scenarios/{id}/executions``: the plan is checked
first (a scenario that cannot run is refused with every reason, and nothing is stored),
a place in the worker pool is reserved (429 when there is none), and the queued execution
is stored and handed to the runner. Everything afterwards — results, pathways,
explanations, verification, sensitivity, comparisons — is read from what the execution
and its Phase 4 runs stored.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, DomainValidationError, NotFoundError
from app.domain.enums import ScenarioExecutionStatus
from app.models import (
    Scenario,
    ScenarioExecution,
    ScenarioSensitivityAnalysis,
    SimulationModelVersion,
    SimulationRun,
    SimulationRunStep,
)
from app.scenario_lab import LAB_VERSION
from app.scenario_lab import templates as lab_templates
from app.scenario_lab.comparison import MAX_EXECUTIONS, MIN_EXECUTIONS, compare
from app.scenario_lab.executor import TERMINAL, Member, reproduce, spec_of
from app.scenario_lab.explain import TARGETS, explain
from app.scenario_lab.graph import affected_entities
from app.scenario_lab.profiles import PROFILES, lab_model
from app.scenario_lab.runner import ExecutionRunner, RunnerBusy
from app.scenario_lab.sensitivity import Item, LabSensitivityError, analyse, default_items
from app.scenario_lab.spec import spec_json
from app.schemas.common import ErrorDetail
from app.schemas.scenario import (
    ComparisonRead,
    ExecutionPage,
    ExecutionRead,
    ExecutionRequest,
    ExecutionVerificationRead,
    LabExplanationRead,
    LabPathwayRead,
    LabSensitivityList,
    LabSensitivityRead,
    LabSensitivityRequest,
    ResultsRead,
    RunCheckRead,
    ScenarioInput,
    TemplateList,
    TemplateRead,
)
from app.services.scenarios import execution_summary, plan_for, scenario_or_404, version_of
from app.simulation.definitions import plain, sha256
from app.simulation.persistence import rebuild
from app.simulation.registry import REGISTRY
from app.simulation.validation import parse_number

S = ScenarioExecutionStatus
POLL_MS = 400
SENSITIVITY_NOTE = (
    "One quantity is moved at a time while everything else keeps the execution's value. The "
    "spread shows how much the result depends on it, not how likely any value is. This is "
    "sensitivity analysis, not a stochastic (Monte Carlo) simulation."
)


class TooManyExecutions(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many scenario executions are running or waiting."


# --- Executions ---------------------------------------------------------------------------------


def _execution_or_404(session: Session, execution_id: uuid.UUID) -> ScenarioExecution:
    row = session.get(ScenarioExecution, execution_id)
    if row is None:
        raise NotFoundError(f"No scenario execution '{execution_id}'.")
    return row


def execution_read(session: Session, row: ScenarioExecution) -> ExecutionRead:
    scenario = session.get(Scenario, row.scenario_id)
    summary = execution_summary(row)
    return ExecutionRead(
        **summary.model_dump(),
        scenario_name=scenario.name if scenario else "",
        lab_version=row.lab_version,
        cancel_requested=row.cancel_requested,
        stages=row.stages or [],
        plan=row.plan,
        runs=[
            {
                "position": item.position,
                "model_id": item.model_id,
                "model_version": item.model_version,
                "run_id": item.simulation_run_id,
            }
            for item in row.runs
        ],
        results_available=row.status is S.COMPLETED and row.results is not None,
        poll_after_ms=None if row.status in TERMINAL else POLL_MS,
    )


def create_execution(
    session: Session,
    runner: ExecutionRunner,
    scenario_id: uuid.UUID,
    payload: ExecutionRequest,
) -> ExecutionRead:
    scenario = scenario_or_404(session, scenario_id)
    version = version_of(scenario, payload.version)
    plan = plan_for(session, spec_of(version), preview=False)
    if not plan.executable:
        raise DomainValidationError(
            "The scenario cannot be executed as it stands; nothing was stored.",
            details=[
                ErrorDetail(
                    location="body",
                    field=issue.field,
                    message=issue.message,
                    type=issue.code,
                )
                for issue in plan.errors
            ]
            or [ErrorDetail(location="body", message="No model is included.", type="no_model")],
        )
    try:
        runner.reserve()
    except RunnerBusy as busy:
        raise TooManyExecutions(str(busy)) from busy
    try:
        row = ScenarioExecution(
            id=uuid.uuid4(),
            scenario_id=scenario.id,
            scenario_version_id=version.id,
            version=version.version,
            status=S.QUEUED,
            stages=[],
            lab_version=LAB_VERSION,
        )
        session.add(row)
        session.commit()
    except Exception:
        runner.release()
        raise
    runner.submit(row.id)
    session.refresh(row)
    return execution_read(session, row)


def list_executions(
    session: Session, scenario_id: uuid.UUID, *, limit: int, offset: int
) -> ExecutionPage:
    scenario = scenario_or_404(session, scenario_id)
    total = (
        session.scalar(select(func.count()).where(ScenarioExecution.scenario_id == scenario.id))
        or 0
    )
    rows = session.scalars(
        select(ScenarioExecution)
        .where(ScenarioExecution.scenario_id == scenario.id)
        .order_by(ScenarioExecution.requested_at.desc(), ScenarioExecution.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return ExecutionPage(
        items=[execution_summary(row) for row in rows], total=total, limit=limit, offset=offset
    )


def get_execution(session: Session, execution_id: uuid.UUID) -> ExecutionRead:
    return execution_read(session, _execution_or_404(session, execution_id))


def _completed(session: Session, execution_id: uuid.UUID) -> ScenarioExecution:
    row = _execution_or_404(session, execution_id)
    if row.status is not S.COMPLETED or row.results is None:
        raise ConflictError(
            f"The execution is {row.status.value}: results exist only for a completed execution."
        )
    return row


def get_results(session: Session, execution_id: uuid.UUID) -> ResultsRead:
    row = _completed(session, execution_id)
    return ResultsRead.model_validate({**row.results, "execution_id": row.id})  # type: ignore[dict-item]


def get_pathways(session: Session, execution_id: uuid.UUID) -> LabPathwayRead:
    row = _completed(session, execution_id)
    return LabPathwayRead.model_validate(row.results["pathway"])  # type: ignore[index]


def cancel_execution(session: Session, execution_id: uuid.UUID) -> ExecutionRead:
    row = _execution_or_404(session, execution_id)
    if row.status in TERMINAL:
        raise ConflictError(f"The execution is already {row.status.value}; it cannot change.")
    row.cancel_requested = True
    session.commit()
    return execution_read(session, row)


# --- Stored runs --------------------------------------------------------------------------------


def _runs(session: Session, row: ScenarioExecution) -> list[SimulationRun]:
    runs = []
    for item in row.runs:
        run = session.get(SimulationRun, item.simulation_run_id)
        if run is None:  # pragma: no cover - RESTRICT forbids it
            raise NotFoundError("A model run of this execution is missing.")
        runs.append(run)
    return runs


def _definition(session: Session, run: SimulationRun) -> SimulationModelVersion:
    version = session.get(SimulationModelVersion, run.model_version_id)
    if version is None:  # pragma: no cover - the foreign key forbids it
        raise NotFoundError("A run's model version is missing.")
    return version


def _members(
    session: Session, runs: Sequence[SimulationRun]
) -> list[tuple[Member | None, SimulationRun]]:
    stored: list[tuple[Member | None, SimulationRun]] = []
    for run in runs:
        model = REGISTRY.get(run.model_id, run.model_version)
        version = _definition(session, run)
        profile = PROFILES.get(run.model_id)
        if model is None or profile is None or model.definition_hash != version.definition_hash:
            stored.append((None, run))
            continue
        stored.append((Member(profile, model, rebuild(model, run)), run))
    return stored


def verify_execution(session: Session, execution_id: uuid.UUID) -> ExecutionVerificationRead:
    row = _completed(session, execution_id)
    scenario = scenario_or_404(session, row.scenario_id)
    spec = spec_of(version_of(scenario, row.version))
    outcome = reproduce(spec, _members(session, _runs(session, row)))
    same_inputs = outcome.inputs_hash == row.inputs_hash
    same_result = outcome.result_hash == row.result_hash
    reproduced = outcome.reproducible and same_inputs and same_result
    message = outcome.message or (
        "Re-executed from the stored runs and recombined: identical results."
        if reproduced
        else "Re-executing the stored inputs gave a different result: the execution is not "
        "reproducible and should be investigated."
    )
    return ExecutionVerificationRead(
        execution_id=row.id,
        reproduced=reproduced,
        inputs_hash_matches=same_inputs,
        result_hash_matches=same_result,
        stored_result_hash=row.result_hash,
        recomputed_result_hash=outcome.result_hash,
        runs=[
            RunCheckRead(
                model_id=check.model_id,
                run_id=check.run_id,
                inputs_hash_matches=check.inputs_hash_matches,
                result_hash_matches=check.result_hash_matches,
            )
            for check in outcome.runs
        ],
        message=message,
    )


def get_explanation(session: Session, execution_id: uuid.UUID, target: str) -> LabExplanationRead:
    row = _completed(session, execution_id)
    if target not in TARGETS:
        raise NotFoundError(f"'{target}' is not a line or metric of the Scenario Lab.")
    runs = {run.model_id: run for run in _runs(session, row)}
    definitions = {model_id: _definition(session, run).definition for model_id, run in runs.items()}
    steps = {
        model_id: list(
            session.scalars(
                select(SimulationRunStep)
                .where(SimulationRunStep.run_id == run.id)
                .order_by(SimulationRunStep.sequence)
            )
        )
        for model_id, run in runs.items()
    }
    data = explain(row, target, runs, definitions, steps)
    if data is None:
        raise NotFoundError(
            f"This execution has no {target.replace('_', ' ')}: no included model produces it."
        )
    return LabExplanationRead.model_validate(data)


# --- Sensitivity --------------------------------------------------------------------------------


def _number(value: str | int | float | None, field: str) -> Any:
    if value is None:
        return None
    number = parse_number(value)
    if number is None:
        raise DomainValidationError(
            "The sensitivity request is invalid.",
            details=[
                ErrorDetail(
                    location="body",
                    field=field,
                    message="Use a plain number such as 10 or 2.5.",
                    type="invalid_number",
                )
            ],
        )
    return number


def _analysis_read(row: ScenarioSensitivityAnalysis) -> LabSensitivityRead:
    return LabSensitivityRead.model_validate(
        {
            **row.results,
            "id": row.id,
            "execution_id": row.execution_id,
            "evaluations": row.evaluations,
            "duration_ms": row.duration_ms,
            "result_hash": row.result_hash,
            "created_at": row.created_at,
            "note": SENSITIVITY_NOTE,
        }
    )


def run_sensitivity(
    session: Session, execution_id: uuid.UUID, payload: LabSensitivityRequest
) -> LabSensitivityRead:
    row = _completed(session, execution_id)
    scenario = scenario_or_404(session, row.scenario_id)
    spec = spec_of(version_of(scenario, row.version))
    stored = _members(session, _runs(session, row))
    if any(member is None for member, _ in stored):
        raise ConflictError(
            "A model version this execution used is no longer registered with the same "
            "definition, so it cannot be re-evaluated."
        )
    members = [member for member, _ in stored if member is not None]
    items = [
        Item(
            target=item.target,
            mode=item.mode,
            step=_number(item.step, f"inputs[{index}].step"),
            values=tuple(
                _number(raw, f"inputs[{index}].values[{position}]")
                for position, raw in enumerate(item.values)
            ),
        )
        for index, item in enumerate(payload.inputs)
    ] or default_items(spec, members)
    lines = {line["id"] for line in (row.results or {}).get("lines", [])}
    metric = payload.metric or (
        "profit_before_tax" if "profit_before_tax" in lines else "operating_profit"
    )
    try:
        analysis = analyse(spec, members, items, metric=metric)
    except LabSensitivityError as error:
        raise DomainValidationError(
            "The sensitivity request is invalid.",
            details=[
                ErrorDetail(
                    location="body",
                    field=error.field,
                    message=error.message,
                    type="sensitivity_limit",
                )
            ],
        ) from error
    results = {
        key: value for key, value in analysis.items() if key not in ("evaluations", "duration_ms")
    }
    record = ScenarioSensitivityAnalysis(
        id=uuid.uuid4(),
        execution_id=row.id,
        metric=metric,
        request=[plain(item) for item in items],
        results=results,
        evaluations=analysis["evaluations"],
        duration_ms=analysis["duration_ms"],
        result_hash=sha256(results),
    )
    session.add(record)
    session.commit()
    return _analysis_read(record)


def list_sensitivity(session: Session, execution_id: uuid.UUID) -> LabSensitivityList:
    row = _execution_or_404(session, execution_id)
    records = session.scalars(
        select(ScenarioSensitivityAnalysis)
        .where(ScenarioSensitivityAnalysis.execution_id == row.id)
        .order_by(ScenarioSensitivityAnalysis.created_at.desc())
    ).all()
    return LabSensitivityList(items=[_analysis_read(record) for record in records])


def get_sensitivity(
    session: Session, execution_id: uuid.UUID, analysis_id: uuid.UUID
) -> LabSensitivityRead:
    row = _execution_or_404(session, execution_id)
    record = session.get(ScenarioSensitivityAnalysis, analysis_id)
    if record is None or record.execution_id != row.id:
        raise NotFoundError(f"No sensitivity analysis '{analysis_id}' for this execution.")
    return _analysis_read(record)


# --- Comparison ---------------------------------------------------------------------------------


def compare_executions(
    session: Session, execution_ids: Sequence[uuid.UUID], reference: uuid.UUID | None
) -> ComparisonRead:
    unique = list(dict.fromkeys(execution_ids))
    if not MIN_EXECUTIONS <= len(unique) <= MAX_EXECUTIONS:
        raise DomainValidationError(
            "Choose executions to compare.",
            details=[
                ErrorDetail(
                    location="query",
                    field="execution_id",
                    message=f"Compare {MIN_EXECUTIONS} to {MAX_EXECUTIONS} different executions.",
                    type="comparison_size",
                )
            ],
        )
    rows = [_completed(session, execution_id) for execution_id in unique]
    reference_id = reference or unique[0]
    if reference_id not in unique:
        raise DomainValidationError(
            "The reference must be one of the compared executions.",
            details=[
                ErrorDetail(
                    location="query",
                    field="reference",
                    message="Choose one of the compared executions as the reference.",
                    type="comparison_reference",
                )
            ],
        )
    names = {
        str(row.id): (scenario.name if (scenario := session.get(Scenario, row.scenario_id)) else "")
        for row in rows
    }
    runs = {str(row.id): _runs(session, row) for row in rows}
    analyses = {
        str(row.id): session.scalars(
            select(ScenarioSensitivityAnalysis)
            .where(ScenarioSensitivityAnalysis.execution_id == row.id)
            .order_by(ScenarioSensitivityAnalysis.created_at.desc())
            .limit(1)
        ).first()
        for row in rows
    }
    return ComparisonRead.model_validate(compare(rows, names, runs, analyses, str(reference_id)))


# --- Templates ----------------------------------------------------------------------------------


def _suggested(session: Session, template: lab_templates.Template) -> list[dict[str, Any]]:
    """Companies the template fits, by what the graph states: every template model that
    requires a stated exposure has one, and at least one template model applies."""
    variables = [shock.variable_id for shock in template.shocks]
    found = affected_entities(session, variables, PROFILES, limit=50)
    required = {model_id for model_id in template.models if PROFILES[model_id].exposure_required}
    chosen = []
    for entry in found["entities"]:
        covered = {model for exposure in entry["exposures"] for model in exposure["models"]}
        if covered & set(template.models) and required <= covered:
            chosen.append(entry["entity"])
    return chosen


def _template_summary(session: Session, template: lab_templates.Template) -> dict[str, Any]:
    return {
        "id": template.id,
        "title": template.title,
        "category": template.category,
        "question": template.question,
        "summary": template.summary,
        "changes": lab_templates.requirements(template)["changes"],
        "models": [
            {
                "model_id": model_id,
                "title": PROFILES[model_id].title,
                "version": model.definition.version if (model := lab_model(model_id)) else "",
            }
            for model_id in template.models
        ],
        "stress_cases": spec_json(lab_templates.spec_for(template))["stress_cases"],
        "suggested_entities": _suggested(session, template),
    }


def list_templates(session: Session) -> TemplateList:
    return TemplateList.model_validate(
        {
            "items": [_template_summary(session, item) for item in lab_templates.TEMPLATES],
            "unsupported": list(lab_templates.UNSUPPORTED),
        }
    )


def get_template(session: Session, template_id: str) -> TemplateRead:
    template = lab_templates.get(template_id)
    if template is None:
        raise NotFoundError(f"No scenario template '{template_id}'.")
    spec = lab_templates.spec_for(template)
    data = spec_json(spec)
    scenario = ScenarioInput.model_validate(
        {
            "name": spec.name,
            "description": spec.description,
            "template_id": spec.template_id,
            "shocks": [
                {
                    "variable_id": shock.variable_id,
                    "change_type": shock.change_type.value,
                    "value": change["value"],
                }
                for shock, change in zip(
                    spec.shocks, lab_templates.requirements(template)["changes"], strict=True
                )
            ],
            "timing": data["timing"],
            "models": {model_id: {"mode": "include"} for model_id in template.models},
            "stress_cases": [
                {key: value for key, value in case.items() if value not in (None, {})}
                for case in data["stress_cases"]
            ],
        }
    )
    requirements = lab_templates.requirements(template)
    return TemplateRead.model_validate(
        {
            **_template_summary(session, template),
            "required_inputs": requirements["required_inputs"],
            "optional_inputs": requirements["optional_inputs"],
            "validation_rules": requirements["validation_rules"],
            "expected_outputs": requirements["expected_outputs"],
            "scenario": scenario,
        }
    )
