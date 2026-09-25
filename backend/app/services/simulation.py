"""API logic for the simulation engine: models, validation, runs, explanations,
provenance, sensitivity analysis and verification.

Runs are created by ``POST /api/v1/simulations`` and never changed afterwards. Everything
a run is explained with — equations, steps, graph snapshot, inputs and their sources — is
read from what the run stored, so an explanation cannot drift from the calculation.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.db.base import utcnow
from app.graph.store import GraphReader
from app.models import (
    GraphEdge,
    SimulationModelVersion,
    SimulationRun,
    SimulationRunStep,
    SimulationSensitivityAnalysis,
)
from app.schemas.common import ErrorDetail
from app.schemas.simulation import (
    BridgeRead,
    ContributionRead,
    EntityRead,
    ExplanationRead,
    GraphSnapshotRead,
    InputDefinitionRead,
    ModelVerificationRead,
    ModelVersionRead,
    MonthlySeriesRead,
    ObservationSourceRead,
    OutputRead,
    ProvenanceRead,
    ResolvedInputRead,
    SensitivityAnalysisList,
    SensitivityAnalysisRead,
    SensitivityRequest,
    SimulationIssueRead,
    SimulationModelDetail,
    SimulationModelSummary,
    SimulationObservationRead,
    SimulationRequest,
    SimulationRunPage,
    SimulationRunRead,
    SimulationRunRequest,
    SimulationRunSummary,
    StatementRead,
    TransmissionPathRead,
    TransmissionRuleRead,
    UnitChoice,
    ValidationReport,
    VerificationRead,
)
from app.services import graph as graph_service
from app.simulation import verification as model_register
from app.simulation.data_sources import latest_observation
from app.simulation.decimal_math import NumericalError
from app.simulation.definitions import plain
from app.simulation.engine import Preparation, execute, inputs_hash, prepare
from app.simulation.explain import explanation
from app.simulation.graph_context import load_graph_context
from app.simulation.persistence import (
    ModelVersionConflict,
    rebuild,
    store_analysis,
    store_run,
)
from app.simulation.registry import REGISTRY, RegisteredModel
from app.simulation.runtime import Issue
from app.simulation.sensitivity import SensitivityError, SensitivityItem, analyse
from app.simulation.units import PRICE_UNITS, VOLUME_UNITS, unit_label
from app.simulation.validation import InputValue, parse_number

RUN_NOTE = (
    "A deterministic calculation from the inputs and assumptions shown, holding everything "
    "else constant. It is not a forecast and not investment advice."
)
SENSITIVITY_NOTE = (
    "Each input is moved on its own while every other input keeps the run's value. The "
    "spread shows how much the result depends on that input, not how likely any value is."
)


# --- Models -------------------------------------------------------------------------------------


def _model_or_404(model_id: str, version: str | None = None) -> RegisteredModel:
    model = REGISTRY.get(model_id, version)
    if model is None:
        suffix = f" version {version}" if version else ""
        raise NotFoundError(f"No simulation model '{model_id}'{suffix}.")
    return model


def _model_for(payload: SimulationRequest) -> RegisteredModel:
    model = REGISTRY.get(payload.model_id, payload.model_version)
    field = "model_version" if payload.model_version else "model_id"
    if model is None:
        raise DomainValidationError(
            "Unknown simulation model.",
            details=[
                ErrorDetail(
                    location="body",
                    field=field,
                    message=f"No runnable model '{payload.model_id}'"
                    + (f" version {payload.model_version}." if payload.model_version else "."),
                    type="unknown_model",
                )
            ],
        )
    if not model.runnable:
        raise DomainValidationError(
            "This model version is deprecated.",
            details=[
                ErrorDetail(
                    location="body",
                    field=field,
                    message=f"{model.definition.name} {model.definition.version} is deprecated: "
                    "its runs stay readable, but it no longer runs.",
                    type="deprecated_model",
                )
            ],
        )
    return model


def _freshness(session: Session) -> tuple[int | None, str]:
    build = GraphReader(session).latest_build()
    return (build.id if build else None), graph_service.freshness(session, build).status


def _run_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(SimulationRun.model_id, func.count()).group_by(SimulationRun.model_id)
    ).tuples()
    return {model_id: count for model_id, count in rows}


def _summary(model: RegisteredModel, runs: int) -> dict[str, Any]:
    definition = model.definition
    return {
        "id": definition.id,
        "version": definition.version,
        "name": definition.name,
        "summary": definition.summary,
        "domain": definition.domain,
        "status": definition.status.value,
        "definition_hash": model.definition_hash,
        "versions": [item.definition.version for item in REGISTRY.versions(definition.id)],
        "runs": runs,
    }


def list_models(session: Session) -> list[SimulationModelSummary]:
    counts = _run_counts(session)
    return [
        SimulationModelSummary(**_summary(model, counts.get(model.definition.id, 0)))
        for model in REGISTRY.latest()
    ]


def _unit_choices(units: tuple[str, ...]) -> list[UnitChoice]:
    choices = []
    for unit in units:
        if unit in PRICE_UNITS:
            choices.append(UnitChoice(id=unit, label=PRICE_UNITS[unit].label))
        elif unit in VOLUME_UNITS:
            choices.append(UnitChoice(id=unit, label=VOLUME_UNITS[unit].label))
    return choices


def get_model(session: Session, model_id: str, version: str | None = None) -> SimulationModelDetail:
    model = _model_or_404(model_id, version)
    definition = model.definition
    build_id, freshness = _freshness(session)
    context, _ = load_graph_context(session, definition, None, freshness)
    counts = _run_counts(session)

    inputs = []
    for item in definition.inputs:
        sources = []
        for source in item.sources:
            observation = latest_observation(session, source.series_id)
            sources.append(
                ObservationSourceRead(
                    series_id=source.series_id,
                    label=source.label,
                    unit=source.unit,
                    currency_pair=list(source.currency_pair),
                    caveat=source.caveat,
                    available=observation is not None,
                    latest_period=observation.period_label if observation else None,
                    latest_value=observation.value if observation else None,
                    last_confirmed_at=observation.last_confirmed_at if observation else None,
                )
            )
        inputs.append(
            InputDefinitionRead(
                id=item.id,
                label=item.label,
                category=item.category.value,
                kind=item.kind.value,
                description=item.description,
                unit=item.unit,
                unit_label=unit_label(item.unit) if item.unit else None,
                units=_unit_choices(item.units),
                minimum=item.minimum,
                maximum=item.maximum,
                minimum_exclusive=item.minimum_exclusive,
                maximum_exclusive=item.maximum_exclusive,
                max_decimals=item.max_decimals,
                required=item.required,
                default=plain(item.default),
                rationale=item.rationale,
                variable=item.variable,
                variable_name=context.names.get(item.variable) if item.variable else None,
                sources=sources,
                sensitivity=plain(item.sensitivity),
            )
        )
    rules = [
        TransmissionRuleRead(
            **plain(rule),
            source_name=context.names.get(rule.source),
            target_name=context.names.get(rule.target),
            graph_edge=plain(context.transmission.get(rule.id)),
        )
        for rule in definition.transmission_rules
    ]
    data = plain(definition)
    return SimulationModelDetail(
        **_summary(model, counts.get(definition.id, 0)),
        description=definition.description,
        inputs=inputs,
        equations=data["equations"],
        outputs=data["outputs"],
        monthly_outputs=data["monthly_outputs"],
        transmission_rules=rules,
        supporting_relationships=data["supporting_relationships"],
        assumptions=data["assumptions"],
        limitations=data["limitations"],
        validation_rules=data["validation_rules"],
        references=data["references"],
        pathway=data["pathway"],
        bridge=data["bridge"],
        bridge_total=definition.bridge_total,
        headline_outputs=list(definition.headline_outputs),
        sensitivity_defaults=list(definition.sensitivity_defaults),
        sensitivity_metric=definition.sensitivity_metric,
        time_step=definition.time_step,
        max_horizon_months=definition.max_horizon_months,
        max_propagation_depth=definition.max_propagation_depth,
        graph_build_id=build_id,
        graph_freshness=freshness,
    )


# --- Validation and runs ------------------------------------------------------------------------


def _raw_inputs(payload: SimulationRequest) -> dict[str, InputValue]:
    return {
        name: InputValue(
            value=item.value, unit=item.unit, source=item.source, series_id=item.series_id
        )
        for name, item in payload.inputs.items()
    }


def _issue_read(issue: Issue) -> SimulationIssueRead:
    return SimulationIssueRead(code=issue.code, message=issue.message, field=issue.field)


def _details(issues: list[Issue]) -> list[ErrorDetail]:
    return [
        ErrorDetail(
            location="body",
            field=f"inputs.{issue.field}" if issue.field else "inputs",
            message=issue.message,
            type=issue.code,
        )
        for issue in issues
        if issue.severity == "error"
    ]


def _prepare(session: Session, model: RegisteredModel, payload: SimulationRequest) -> Preparation:
    _, freshness = _freshness(session)
    return prepare(session, model, _raw_inputs(payload), freshness=freshness)


def validate(session: Session, payload: SimulationRequest) -> ValidationReport:
    model = _model_for(payload)
    preparation = _prepare(session, model, payload)
    return ValidationReport(
        valid=preparation.ok,
        model_id=model.definition.id,
        model_version=model.definition.version,
        definition_hash=model.definition_hash,
        errors=[_issue_read(issue) for issue in preparation.errors],
        warnings=[_issue_read(issue) for issue in preparation.warnings],
        inputs=[ResolvedInputRead(**entry.snapshot()) for entry in preparation.resolved.values()],
        graph=GraphSnapshotRead(**preparation.graph.snapshot()),
        inputs_hash=inputs_hash(model, preparation.resolved) if preparation.ok else None,
    )


def run_owner(session: Session, run_id: uuid.UUID) -> uuid.UUID | None:
    """Who owns a run (404 when there is no such run)."""
    return _run_or_404(session, run_id).owner_id


def create_run(
    session: Session, payload: SimulationRunRequest, *, owner_id: uuid.UUID | None = None
) -> SimulationRunRead:
    model = _model_for(payload)
    preparation = _prepare(session, model, payload)
    if not preparation.ok:
        raise DomainValidationError(
            "The simulation inputs are invalid.", details=_details(preparation.issues)
        )
    started = utcnow()
    try:
        execution = execute(preparation)
    except NumericalError as error:
        raise DomainValidationError(
            "The simulation could not be calculated.",
            details=[
                ErrorDetail(location="body", field="inputs", message=error.message, type=error.code)
            ],
        ) from error
    finished = utcnow()
    try:
        run = store_run(
            session,
            execution,
            label=payload.label,
            started_at=started,
            finished_at=finished,
            owner_id=owner_id,
        )
    except ModelVersionConflict as error:
        session.rollback()
        raise ConflictError(str(error)) from error
    session.commit()
    return get_run(session, run.id)


def _run_or_404(session: Session, run_id: uuid.UUID) -> SimulationRun:
    run = session.get(SimulationRun, run_id)
    if run is None:
        raise NotFoundError(f"No simulation run '{run_id}'.")
    return run


def _version_row(session: Session, run: SimulationRun) -> SimulationModelVersion:
    row = session.get(SimulationModelVersion, run.model_version_id)
    if row is None:  # pragma: no cover - the foreign key forbids it
        raise NotFoundError("The run's model version is missing.")
    return row


def _entity(run: SimulationRun) -> EntityRead | None:
    entity = run.graph_snapshot.get("entity")
    return EntityRead(**entity) if entity else None


def _outputs(run: SimulationRun, definition: Mapping[str, Any], ids: list[str]) -> list[OutputRead]:
    specs = {item["id"]: item for item in definition["outputs"]}
    return [
        OutputRead(
            id=name,
            label=specs[name]["label"],
            value=Decimal(run.outputs[name]["value"]),
            unit=run.outputs[name]["unit"],
            kind=run.outputs[name]["kind"],
            description=specs[name]["description"],
            equation=specs[name]["equation"],
        )
        for name in ids
        if name in run.outputs and name in specs
    ]


def _contributions(run: SimulationRun, definition: Mapping[str, Any]) -> list[ContributionRead]:
    labels = {entry["id"]: entry["label"] for entry in run.inputs}
    outputs = {item["id"]: item["label"] for item in definition["outputs"]}
    return [
        ContributionRead(
            output=output,
            label=outputs.get(output, output),
            items=[
                {
                    "input": item["input"],
                    "label": labels.get(item["input"], item["input"]),
                    "value": item["value"],
                }
                for item in items
            ],
        )
        for output, items in run.contributions.items()
    ]


def _run_read(session: Session, run: SimulationRun) -> SimulationRunRead:
    version = _version_row(session, run)
    definition = version.definition
    monthly_specs = {item["id"]: item for item in definition.get("monthly_outputs", [])}
    analyses = session.scalar(
        select(func.count()).where(SimulationSensitivityAnalysis.run_id == run.id)
    )
    return SimulationRunRead(
        id=run.id,
        model_id=run.model_id,
        model_name=version.name,
        model_version=run.model_version,
        definition_hash=version.definition_hash,
        status=run.status.value,
        label=run.label,
        entity=_entity(run),
        horizon_months=run.horizon_months,
        inputs=[ResolvedInputRead(**entry) for entry in run.inputs],
        outputs=_outputs(run, definition, [item["id"] for item in definition["outputs"]]),
        monthly=[
            MonthlySeriesRead(
                id=name,
                label=monthly_specs.get(name, {}).get("label", name),
                unit=series["unit"],
                kind=monthly_specs.get(name, {}).get("kind", "simulated"),
                equation=monthly_specs.get(name, {}).get("equation", ""),
                values=series["values"],
            )
            for name, series in run.monthly.items()
        ],
        contributions=_contributions(run, definition),
        bridge=BridgeRead(**run.bridge) if run.bridge else None,
        warnings=[SimulationIssueRead(**item) for item in run.warnings],
        limitations=[StatementRead(**item) for item in run.limitations],
        inputs_hash=run.inputs_hash,
        result_hash=run.result_hash,
        engine_version=run.engine_version,
        random_seed=run.random_seed,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=run.duration_ms,
        created_at=run.created_at,
        sensitivity_analyses=analyses or 0,
        note=RUN_NOTE,
    )


def get_run(session: Session, run_id: uuid.UUID) -> SimulationRunRead:
    return _run_read(session, _run_or_404(session, run_id))


def list_runs(
    session: Session, *, model_id: str | None, limit: int, offset: int
) -> SimulationRunPage:
    statement = select(SimulationRun)
    count = select(func.count()).select_from(SimulationRun)
    if model_id:
        statement = statement.where(SimulationRun.model_id == model_id)
        count = count.where(SimulationRun.model_id == model_id)
    rows = session.scalars(
        statement.order_by(SimulationRun.created_at.desc(), SimulationRun.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = session.scalar(count) or 0
    items = []
    for run in rows:
        definition = _version_row(session, run).definition
        items.append(
            SimulationRunSummary(
                id=run.id,
                model_id=run.model_id,
                model_version=run.model_version,
                label=run.label,
                entity=_entity(run),
                horizon_months=run.horizon_months,
                created_at=run.created_at,
                headline=_outputs(run, definition, list(definition.get("headline_outputs", []))),
                result_hash=run.result_hash,
            )
        )
    return SimulationRunPage(items=items, total=total, limit=limit, offset=offset)


def get_explanation(session: Session, run_id: uuid.UUID) -> ExplanationRead:
    run = _run_or_404(session, run_id)
    definition = _version_row(session, run).definition
    steps = session.scalars(
        select(SimulationRunStep)
        .where(SimulationRunStep.run_id == run.id)
        .order_by(SimulationRunStep.sequence)
    ).all()
    data = explanation(run, definition, list(steps))
    return ExplanationRead(
        run_id=run.id,
        equations=data["equations"],
        steps=data["steps"],
        pathway=data["pathway"],
        contributions=_contributions(run, definition),
        bridge=BridgeRead(**run.bridge) if run.bridge else None,
        parameters=data["parameters"],
        assumptions=data["assumptions"],
        limitations=data["limitations"],
        warnings=data["warnings"],
        method=data["method"],
    )


def get_provenance(session: Session, run_id: uuid.UUID) -> ProvenanceRead:
    run = _run_or_404(session, run_id)
    version = _version_row(session, run)
    return ProvenanceRead(
        run_id=run.id,
        model=ModelVersionRead(
            model_id=version.model_id,
            version=version.version,
            name=version.name,
            status=version.status.value,
            definition_hash=version.definition_hash,
            registered_at=version.registered_at,
        ),
        engine_version=run.engine_version,
        inputs_hash=run.inputs_hash,
        result_hash=run.result_hash,
        random_seed=run.random_seed,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        inputs=[ResolvedInputRead(**entry) for entry in run.inputs],
        observations=[
            SimulationObservationRead(
                **{key: value for key, value in item.items() if key != "input"}
            )
            for item in run.data_snapshot
        ],
        graph=GraphSnapshotRead(**run.graph_snapshot),
        transmission=[TransmissionPathRead(**path) for path in run.transmission],
        reproducibility="The inputs hash covers the model, its version and definition hash, the "
        "engine version and every input value with its source. The result hash covers every "
        "output, monthly value and contribution. Re-executing the stored inputs "
        "(POST …/verify) must give the same result hash.",
    )


# --- Verification -------------------------------------------------------------------------------


def verify(session: Session, run_id: uuid.UUID) -> VerificationRead:
    run = _run_or_404(session, run_id)
    version = _version_row(session, run)
    model = REGISTRY.get(run.model_id, run.model_version)
    edges = []
    for rule, edge in sorted(run.graph_snapshot.get("transmission", {}).items()):
        if edge is None:
            continue
        current = session.get(GraphEdge, edge["edge_key"])
        edges.append(
            {
                "rule": rule,
                "edge_key": edge["edge_key"],
                "still_current": current is not None and current.retired_build_id is None,
            }
        )
    if model is None or model.definition_hash != version.definition_hash:
        return VerificationRead(
            run_id=run.id,
            reproduced=False,
            inputs_hash_matches=False,
            result_hash_matches=False,
            stored_result_hash=run.result_hash,
            recomputed_result_hash=None,
            model_registered=model is not None,
            definition_matches=False,
            graph_edges=edges,
            message="This model version is no longer registered with the same definition, so "
            "the run cannot be re-executed. Its stored explanation remains valid.",
        )
    preparation = rebuild(model, run)
    execution = execute(preparation)
    same_inputs = execution.inputs_hash == run.inputs_hash
    same_result = execution.result_hash == run.result_hash
    return VerificationRead(
        run_id=run.id,
        reproduced=same_inputs and same_result,
        inputs_hash_matches=same_inputs,
        result_hash_matches=same_result,
        stored_result_hash=run.result_hash,
        recomputed_result_hash=execution.result_hash,
        model_registered=True,
        definition_matches=True,
        graph_edges=edges,
        message="Re-executed from the stored inputs: identical result."
        if same_inputs and same_result
        else "Re-executing the stored inputs gave a different result: the run is not "
        "reproducible and should be investigated.",
    )


# --- Sensitivity --------------------------------------------------------------------------------


def _number(value: str | int | float | None, field: str) -> Decimal | None:
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


def _analysis_read(
    row: SimulationSensitivityAnalysis, definition: Mapping[str, Any]
) -> SensitivityAnalysisRead:
    labels = {item["id"]: item["label"] for item in definition["outputs"]}
    results = row.results
    return SensitivityAnalysisRead(
        id=row.id,
        run_id=row.run_id,
        metric=row.metric,
        metric_label=labels.get(row.metric, row.metric),
        base=results["base"],
        items=results["items"],
        ranking=results["ranking"],
        evaluations=row.evaluations,
        duration_ms=row.duration_ms,
        result_hash=row.result_hash,
        created_at=row.created_at,
        note=SENSITIVITY_NOTE,
    )


def run_sensitivity(
    session: Session,
    run_id: uuid.UUID,
    payload: SensitivityRequest,
    *,
    created_by: uuid.UUID | None = None,
) -> SensitivityAnalysisRead:
    run = _run_or_404(session, run_id)
    version = _version_row(session, run)
    model = REGISTRY.get(run.model_id, run.model_version)
    if model is None or model.definition_hash != version.definition_hash:
        raise ConflictError(
            "This run's model version is no longer registered with the same definition, so "
            "it cannot be re-evaluated."
        )
    definition = model.definition
    requests = [
        SensitivityItem(
            input=item.input,
            mode=item.mode,
            step=_number(item.step, f"inputs[{index}].step"),
            values=tuple(
                value
                for position, raw in enumerate(item.values)
                if (value := _number(raw, f"inputs[{index}].values[{position}]")) is not None
            ),
        )
        for index, item in enumerate(payload.inputs)
    ] or [SensitivityItem(input=name) for name in definition.sensitivity_defaults]
    metric = payload.metric or definition.sensitivity_metric or definition.outputs[0].id
    try:
        analysis = analyse(rebuild(model, run), requests, metric=metric)
    except SensitivityError as error:
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
    row = store_analysis(session, run, requests, analysis, created_by=created_by)
    session.commit()
    return _analysis_read(row, version.definition)


def list_sensitivity(session: Session, run_id: uuid.UUID) -> SensitivityAnalysisList:
    run = _run_or_404(session, run_id)
    definition = _version_row(session, run).definition
    rows = session.scalars(
        select(SimulationSensitivityAnalysis)
        .where(SimulationSensitivityAnalysis.run_id == run.id)
        .order_by(SimulationSensitivityAnalysis.created_at.desc())
    ).all()
    return SensitivityAnalysisList(items=[_analysis_read(row, definition) for row in rows])


def get_sensitivity(
    session: Session, run_id: uuid.UUID, analysis_id: uuid.UUID
) -> SensitivityAnalysisRead:
    run = _run_or_404(session, run_id)
    row = session.get(SimulationSensitivityAnalysis, analysis_id)
    if row is None or row.run_id != run.id:
        raise NotFoundError(f"No sensitivity analysis '{analysis_id}' for this run.")
    return _analysis_read(row, _version_row(session, run).definition)


__all__ = [
    "create_run",
    "get_explanation",
    "get_model",
    "get_provenance",
    "get_run",
    "get_sensitivity",
    "list_models",
    "list_runs",
    "list_sensitivity",
    "run_sensitivity",
    "validate",
    "verify",
]


# --- Verification register ----------------------------------------------------------------------


def model_verification(model_id: str, version: str | None = None) -> ModelVerificationRead:
    """Run the model's verification checks now (pure, a few tens of milliseconds)."""
    model = _model_or_404(model_id, version)
    return ModelVerificationRead.model_validate(
        model_register.register_json(model_register.verify(model))
    )
