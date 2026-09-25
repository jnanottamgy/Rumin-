"""Model versions, runs and analyses in the database — append-only.

* ``ensure_model_version`` stores a model version's definition the first time it is used
  and refuses to run a version whose code no longer matches its stored definition: a
  changed equation needs a new version number, so old runs stay explainable.
* ``store_run`` and ``store_analysis`` only ever insert.
* ``rebuild`` turns a stored run back into a preparation from its snapshot alone — the
  stored values, the stored observation, the stored graph snapshot — never a fresh
  database lookup, so re-executing it tests the arithmetic, not whether data has moved.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import SimulationRunStatus
from app.models import (
    SimulationModelVersion,
    SimulationRun,
    SimulationRunStep,
    SimulationSensitivityAnalysis,
)
from app.simulation.data_sources import StoredObservation
from app.simulation.definitions import (
    InputCategory,
    InputKind,
    Knowledge,
    ValueSource,
    plain,
    sha256,
    to_json,
)
from app.simulation.engine import Execution, Preparation
from app.simulation.graph_context import EntityRef, GraphContext, GraphEdgeRef, UnusedEdge
from app.simulation.registry import ENGINE_VERSION, RegisteredModel
from app.simulation.runtime import Issue, ResolvedValues
from app.simulation.sensitivity import SensitivityItem
from app.simulation.validation import ResolvedInput


class ModelVersionConflict(RuntimeError):
    """The code of a registered model version differs from its stored definition."""


def ensure_model_version(session: Session, model: RegisteredModel) -> SimulationModelVersion:
    definition = model.definition
    row = session.scalars(
        select(SimulationModelVersion).where(
            SimulationModelVersion.model_id == definition.id,
            SimulationModelVersion.version == definition.version,
        )
    ).first()
    if row is None:
        row = SimulationModelVersion(
            model_id=definition.id,
            version=definition.version,
            name=definition.name,
            status=definition.status,
            definition=to_json(definition),
            definition_hash=model.definition_hash,
        )
        session.add(row)
        session.flush()
        return row
    if row.definition_hash != model.definition_hash:
        raise ModelVersionConflict(
            f"Model {definition.id} {definition.version} is stored with a different definition "
            f"({row.definition_hash[:12]}…) than the code now registers "
            f"({model.definition_hash[:12]}…). A changed model needs a new version number."
        )
    return row


def _issue(issue: Issue) -> dict[str, Any]:
    return {"code": issue.code, "message": issue.message, "field": issue.field}


def store_run(
    session: Session,
    execution: Execution,
    *,
    label: str | None,
    started_at: datetime,
    finished_at: datetime,
    owner_id: uuid.UUID | None = None,
) -> SimulationRun:
    """Insert a completed run and its steps. Never updates an existing run."""
    preparation = execution.preparation
    model = preparation.model
    definition = model.definition
    version = ensure_model_version(session, model)
    resolved = [preparation.resolved[item.id] for item in definition.inputs]
    run = SimulationRun(
        id=uuid.uuid4(),
        model_version_id=version.id,
        model_id=definition.id,
        model_version=definition.version,
        status=SimulationRunStatus.COMPLETED,
        label=label,
        entity_id=preparation.graph.entity.key if preparation.graph.entity else None,
        horizon_months=execution.horizon,
        inputs=[entry.snapshot() for entry in resolved],
        inputs_hash=execution.inputs_hash,
        assumptions=[plain(item) for item in definition.assumptions],
        limitations=[plain(item) for item in definition.limitations],
        graph_snapshot=preparation.graph.snapshot(),
        data_snapshot=[
            {"input": entry.id, **entry.observation.snapshot()}
            for entry in resolved
            if entry.observation is not None
        ],
        outputs=plain(execution.outputs),
        monthly=plain(execution.monthly),
        contributions=plain(execution.contributions),
        bridge=plain(execution.bridge),
        transmission=plain(execution.transmission),
        warnings=[_issue(issue) for issue in execution.warnings],
        result_hash=execution.result_hash,
        engine_version=ENGINE_VERSION,
        random_seed=None,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=max(0, round((finished_at - started_at).total_seconds() * 1000)),
        owner_id=owner_id,
    )
    session.add(run)
    session.flush()
    session.add_all(
        SimulationRunStep(
            run_id=run.id,
            sequence=index,
            equation_id=step.equation,
            label=step.label,
            month=step.month,
            output_symbol=step.output.symbol,
            output_value=step.output.value,
            output_unit=step.output.unit,
            inputs=[
                {"symbol": item.symbol, "value": plain(item.value), "unit": item.unit}
                for item in step.inputs
            ],
        )
        for index, step in enumerate(execution.steps, start=1)
    )
    session.flush()
    return run


def store_analysis(
    session: Session,
    run: SimulationRun,
    requests: list[SensitivityItem],
    analysis: dict[str, Any],
    *,
    created_by: uuid.UUID | None = None,
) -> SimulationSensitivityAnalysis:
    results = plain({key: value for key, value in analysis.items() if key != "duration_ms"})
    row = SimulationSensitivityAnalysis(
        id=uuid.uuid4(),
        run_id=run.id,
        metric=analysis["metric"],
        request=[plain(item) for item in requests],
        results=results,
        evaluations=analysis["evaluations"],
        duration_ms=analysis["duration_ms"],
        result_hash=sha256(results),
        created_by=created_by,
    )
    session.add(row)
    session.flush()
    return row


# --- Rebuilding a run from its snapshot ---------------------------------------------------------


def _observation(data: dict[str, Any] | None) -> StoredObservation | None:
    if data is None:
        return None
    fields = {**data, "value": Decimal(data["value"])}
    fields.pop("input", None)
    return StoredObservation(**fields)


def rebuild(model: RegisteredModel, run: SimulationRun) -> Preparation:
    """A preparation equal to the one the run was executed from, built from its snapshot."""
    definition = model.definition
    stored = {entry["id"]: entry for entry in run.inputs}
    numbers: dict[str, Decimal] = {}
    integers: dict[str, int] = {}
    texts: dict[str, str | None] = {}
    units: dict[str, str] = {}
    resolved: dict[str, ResolvedInput] = {}
    for item in definition.inputs:
        entry = stored.get(item.id)
        if entry is None:
            raise ModelVersionConflict(f"The stored run has no value for '{item.id}'.")
        value = entry["value"]
        if item.kind is InputKind.INTEGER:
            integers[item.id] = int(Decimal(value))
        elif item.kind in (InputKind.DECIMAL, InputKind.QUANTITY):
            numbers[item.id] = Decimal(value)
            if item.kind is InputKind.QUANTITY:
                units[item.id] = entry["unit"]
        else:
            texts[item.id] = value
        resolved[item.id] = ResolvedInput(
            id=item.id,
            label=entry["label"],
            category=InputCategory(entry["category"]),
            knowledge=Knowledge(entry["knowledge"]),
            source=ValueSource(entry["source"]),
            value=value,
            unit=entry["unit"],
            unit_label=entry["unit_label"],
            default=entry["default"],
            rationale=entry["rationale"],
            variable=entry["variable"],
            observation=_observation(entry.get("observation")),
        )
    graph = run.graph_snapshot
    context = GraphContext(
        build_id=graph["build_id"],
        build_finished_at=graph["build_finished_at"],
        source_fingerprint=graph["source_fingerprint"],
        freshness=graph["freshness"],
        transmission={
            rule: GraphEdgeRef(**edge) if edge else None
            for rule, edge in graph["transmission"].items()
        },
        supporting={
            rule: GraphEdgeRef(**edge) if edge else None
            for rule, edge in graph["supporting"].items()
        },
        entity=EntityRef(**graph["entity"]) if graph["entity"] else None,
        unused=tuple(UnusedEdge(**edge) for edge in graph["unused"]),
        unused_total=graph["unused_total"],
        names=dict(graph.get("names", {})),
    )
    warnings = [
        Issue(item["code"], item["message"], "warning", item.get("field")) for item in run.warnings
    ]
    return Preparation(
        model=model,
        resolved=resolved,
        values=ResolvedValues(numbers, integers, texts, units),
        graph=context,
        issues=warnings,
    )
