"""Financial intelligence: the service behind ``/api/v1/intelligence``.

Every read runs the analysis engine over the current store (graph build, stored values,
executions) with the requested thresholds; nothing is written except a stored analysis,
which is created by ``POST /intelligence/analyses`` and never changed afterwards. A stored
analysis keeps a fingerprint of everything it read; reading it back compares that
fingerprint with the store and reports it as stale when the inputs have moved on.
"""

from __future__ import annotations

import time
import uuid
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainValidationError, NotFoundError
from app.domain.enums import GraphEdgeType, GraphNodeType, ScenarioExecutionStatus
from app.graph.store import GraphReader
from app.intelligence import INTELLIGENCE_VERSION, fmt, registry, serialize
from app.intelligence import engine as intelligence
from app.intelligence import insights as rules
from app.intelligence import signals as signal_specs
from app.intelligence import thresholds as threshold_specs
from app.intelligence.drivers import (
    analyse as analyse_drivers,
)
from app.intelligence.drivers import (
    executions_for,
    previous_of_same_scenario,
)
from app.intelligence.engine import BuildInfo, EntityNotFound, NotAnEntity
from app.intelligence.exposure import (
    ExposurePath,
    entity_exposure,
    variable_exposure,
    weakest,
    workspace_exposure,
)
from app.intelligence.graphview import NodeInfo, query_edges, query_nodes
from app.intelligence.model import EDGE_GRADE, GRADE_STATEMENT, GRADE_STRENGTH, Grade
from app.intelligence.series import load_instrument, load_series
from app.intelligence.thresholds import ThresholdError, Thresholds
from app.models import (
    EconomicObservation,
    GraphNode,
    IntelligenceAnalysis,
    PriceBar,
    ScenarioExecution,
    ScenarioSensitivityAnalysis,
)
from app.schemas.common import ErrorDetail, ErrorLocation
from app.schemas.intelligence import (
    AnalysisFreshnessRead,
    AnalysisPage,
    AnalysisRead,
    AnalysisRequest,
    AnalysisSummaryRead,
    BriefRead,
    ChangesRead,
    DriversRead,
    EntityAnalysisRead,
    EntityListRead,
    InsightListRead,
    InstrumentIntelligenceRead,
    MethodsRead,
    OverviewRead,
    SeriesIntelligenceRead,
    SignalListRead,
    VariableExposureRead,
)
from app.services import graph as graph_service
from app.simulation.definitions import sha256

MAX_ENTITIES = 200
NOT_A_FORECAST = (
    "Simulated values hold only under their scenario's inputs and assumptions; they are not "
    "forecasts."
)


# --- Shared ------------------------------------------------------------------------------------


def build_info(session: Session) -> BuildInfo:
    build = GraphReader(session).latest_build()
    fresh = graph_service.freshness(session, build)
    return BuildInfo(
        id=build.id if build else None,
        finished_at=build.finished_at if build else None,
        freshness=fresh.status,
        message=fresh.message,
    )


def resolve_thresholds(
    overrides: Mapping[str, Any] | None, *, location: ErrorLocation = "query"
) -> Thresholds:
    """The defaults with ``overrides``; every invalid value is reported with its field."""
    try:
        return threshold_specs.resolve(overrides)
    except ThresholdError as error:
        prefix = "thresholds." if location == "body" else ""
        raise DomainValidationError(
            "Some thresholds are invalid.",
            details=[
                ErrorDetail(
                    location=location,
                    field=f"{prefix}{problem.field}",
                    message=problem.message,
                    type="invalid_threshold",
                )
                for problem in error.problems
            ],
        ) from error


def _entity_analysis(
    session: Session, entity_key: str, used: Thresholds, *, evidence: str = "any"
) -> intelligence.EntityAnalysis:
    try:
        return intelligence.analyse_entity(
            session, entity_key, used, build=build_info(session), evidence=evidence
        )
    except EntityNotFound as error:
        raise NotFoundError(str(error)) from error
    except NotAnEntity as error:
        raise DomainValidationError(
            str(error),
            details=[
                ErrorDetail(
                    location="path", field="entity_key", message=str(error), type="not_an_entity"
                )
            ],
        ) from error


def _entity_node(session: Session, entity_key: str) -> NodeInfo:
    try:
        return intelligence.entity_node(session, entity_key)
    except EntityNotFound as error:
        raise NotFoundError(str(error)) from error
    except NotAnEntity as error:
        raise DomainValidationError(
            str(error),
            details=[
                ErrorDetail(
                    location="path", field="entity_key", message=str(error), type="not_an_entity"
                )
            ],
        ) from error


# --- Workspace ---------------------------------------------------------------------------------


def overview(session: Session, used: Thresholds) -> OverviewRead:
    found = intelligence.analyse_workspace(session, used, build=build_info(session))
    return OverviewRead.model_validate(serialize.workspace_analysis(found))


def _grade_at_least(grade: str | None) -> set[str] | None:
    if grade is None:
        return None
    floor = GRADE_STRENGTH[Grade(grade)]
    return {item.value for item in Grade if GRADE_STRENGTH[item] >= floor}


def insight_list(
    session: Session,
    used: Thresholds,
    *,
    entity: str | None,
    kind: str | None,
    rule: str | None,
    grade: str | None,
) -> InsightListRead:
    build = build_info(session)
    if entity is not None:
        analysis = _entity_analysis(session, entity, used)
        found = list(analysis.insights)
        subject = {"kind": "graph_node", "id": analysis.entity.key, "label": analysis.entity.name}
    else:
        found = list(intelligence.analyse_workspace(session, used, build=build).insights)
        subject = None
    allowed = _grade_at_least(grade)
    items = [
        item
        for item in found
        if (kind is None or item.kind == kind)
        and (rule is None or item.rule == rule)
        and (allowed is None or item.evidence.grade.value in allowed)
    ]
    return InsightListRead.model_validate(
        {
            "scope": "entity" if entity else "workspace",
            "subject": subject,
            "build": serialize.build(build),
            "thresholds": used.to_json(),
            "items": serialize.insights(items),
            "total": len(items),
        }
    )


def changes(session: Session, used: Thresholds) -> ChangesRead:
    """What changed: stored values (observed), revisions, relationships (graph builds) and
    executions of the same scenario (simulated) — each labelled by what it is."""
    build = build_info(session)
    found = intelligence.analyse_workspace(session, used, build=build)
    observed: list[dict[str, Any]] = []
    revised: list[dict[str, Any]] = []
    for analysis in [*found.series, *found.instruments]:
        latest = analysis.latest
        subject = serialize.data(analysis.history.subject)
        for change in analysis.detected:
            observed.append(
                {
                    "subject": subject,
                    "change": serialize.data(change),
                    "threshold_name": analysis.threshold_name,
                    "threshold": serialize.data(analysis.threshold),
                    "latest": change == latest,
                }
            )
        revised.extend(
            {"subject": subject, "revision": serialize.data(item)} for item in analysis.revisions
        )
    observed.sort(key=lambda item: (item["change"]["later"]["start"], item["subject"]["id"]))
    observed.reverse()
    executions: list[dict[str, Any]] = []
    companies = {company.key: company for company in found.exposure.companies}
    for key, latest_drivers in sorted(found.drivers.items()):
        stored = executions_for(session, key)
        latest_row = next(
            (row for row in stored if str(row.id) == latest_drivers.execution.id), None
        )
        if latest_row is None:
            continue
        before = previous_of_same_scenario(stored, latest_row)
        if before is None or latest_drivers.headline is None:
            continue
        previous = analyse_drivers(session, before, key)
        now_line = latest_drivers.line(latest_drivers.headline)
        then_line = previous.line(latest_drivers.headline)
        if now_line is None or then_line is None:
            continue
        executions.append(
            {
                "entity": serialize.data(companies[key]),
                "line": now_line.id,
                "label": now_line.label,
                "currency": now_line.currency,
                "previous": serialize.data(previous.execution),
                "latest": serialize.data(latest_drivers.execution),
                "previous_change": serialize.data(then_line.change),
                "latest_change": serialize.data(now_line.change),
                "difference": serialize.data(now_line.change - then_line.change),
            }
        )
    return ChangesRead.model_validate(
        {
            "build": serialize.build(build),
            "thresholds": used.to_json(),
            "observed": observed,
            "revisions": revised,
            "relationships": serialize.data(found.relationships),
            "executions": executions,
            "notes": [
                "Observed changes are between consecutive stored values of the latest window, "
                "tested against the thresholds shown; nothing is fetched or filled in.",
                "Execution changes are simulated results, not observations. " + NOT_A_FORECAST,
            ],
        }
    )


# --- Entities ----------------------------------------------------------------------------------


def _summary(
    entity: NodeInfo, paths: tuple[ExposurePath, ...] | list[ExposurePath]
) -> dict[str, Any]:
    edges = [edge for path in paths for edge in path.edges]
    return {
        "entity": serialize.data(entity),
        "paths": len(paths),
        "variables": len({key for path in paths for key in path.variable_keys}),
        "by_channel": dict(Counter(path.channel for path in paths)),
        "by_directness": dict(Counter(path.directness for path in paths)),
        "weakest_evidence": weakest(edges) if edges else None,
        "latest_impact": None,
    }


def entity_list(session: Session, kind: str | None) -> EntityListRead:
    build = build_info(session)
    items: list[dict[str, Any]] = []
    if kind in (None, "company"):
        workspace = workspace_exposure(session, build.id)
        latest = intelligence.latest_executions(session)
        for company in workspace.companies:
            item = _summary(company, workspace.paths.get(company.key, ()))
            execution = latest.get(company.key)
            if execution is not None:
                item["latest_impact"] = serialize.impact(
                    analyse_drivers(session, execution, company.key)
                )
            items.append(item)
    if kind in (None, "industry"):
        industries = session.scalars(
            select(GraphNode.id)
            .where(
                GraphNode.retired_build_id.is_(None),
                GraphNode.node_type == GraphNodeType.INDUSTRY,
            )
            .order_by(GraphNode.display_name)
            .limit(MAX_ENTITIES)
        ).all()
        for key in industries:
            exposure = entity_exposure(session, key, build.id)
            items.append(_summary(exposure.entity, exposure.paths))
    return EntityListRead.model_validate(
        {"build": serialize.build(build), "items": items, "total": len(items)}
    )


def entity(
    session: Session, entity_key: str, used: Thresholds, evidence: str
) -> EntityAnalysisRead:
    found = _entity_analysis(session, entity_key, used, evidence=evidence)
    return EntityAnalysisRead.model_validate(serialize.entity_analysis(found))


def entity_brief(session: Session, entity_key: str, used: Thresholds) -> BriefRead:
    found = _entity_analysis(session, entity_key, used)
    return BriefRead.model_validate(serialize.brief(found, datetime.now(UTC)))


def entity_exposure_read(session: Session, entity_key: str, evidence: str) -> dict[str, Any]:
    node = _entity_node(session, entity_key)
    exposure = entity_exposure(session, node.key, build_info(session).id, evidence=evidence)
    return serialize.exposure_map(exposure)


def entity_signal_list(session: Session, entity_key: str, used: Thresholds) -> SignalListRead:
    found = _entity_analysis(session, entity_key, used)
    return SignalListRead.model_validate(
        {
            "subject": {"kind": "graph_node", "id": found.entity.key, "label": found.entity.name},
            "build": serialize.build(found.build),
            "thresholds": used.to_json(),
            "items": serialize.data(found.signals),
        }
    )


def entity_drivers(session: Session, entity_key: str) -> DriversRead:
    node = _entity_node(session, entity_key)
    stored = executions_for(session, node.key) if node.node_type == "company" else []
    latest = analyse_drivers(session, stored[0], node.key) if stored else None
    before = previous_of_same_scenario(stored, stored[0]) if stored else None
    previous = analyse_drivers(session, before, node.key) if before is not None else None
    if node.node_type != "company":
        note = "Executions are run for companies; an industry has no drivers of its own."
    elif latest is None:
        note = f"No completed execution is stored for {node.name}: run a scenario to size it."
    else:
        note = (
            "Contributions are the models' stored Shapley credits per change; they add up to "
            "each line's change. " + NOT_A_FORECAST
        )
    return DriversRead.model_validate(
        {
            "entity": serialize.data(node),
            "executions": [
                serialize.data(analyse_drivers(session, row, node.key).execution) for row in stored
            ],
            "drivers": serialize.drivers(latest),
            "previous": serialize.drivers(previous),
            "note": note,
        }
    )


def variable_exposure_read(session: Session, variable_key: str) -> VariableExposureRead:
    node = query_nodes(session, [variable_key]).get(variable_key)
    if node is None:
        raise NotFoundError(f"No current knowledge-graph node has the key '{variable_key}'.")
    if node.node_type != GraphNodeType.ECONOMIC_VARIABLE:
        message = (
            f"'{variable_key}' is {intelligence.kind_phrase(node.node_type)}, not an economic "
            "variable."
        )
        raise DomainValidationError(
            message,
            details=[
                ErrorDetail(
                    location="path", field="variable_key", message=message, type="not_a_variable"
                )
            ],
        )
    build = build_info(session)
    workspace = workspace_exposure(session, build.id)
    reached = variable_exposure(workspace, variable_key)
    return VariableExposureRead.model_validate(
        {
            "variable": serialize.data(node),
            "build": serialize.build(build),
            "companies": [
                {"company": serialize.data(company), "paths": serialize.data(paths)}
                for company, paths in reached
            ],
            "note": "Companies the graph states the variable reaches (directly, through their "
            "industry, or upstream through at most two `influences` hops). This says who is "
            "exposed, never how much.",
        }
    )


# --- Series and instruments --------------------------------------------------------------------


def series_read(session: Session, series_id: str, used: Thresholds) -> SeriesIntelligenceRead:
    history = load_series(session, series_id)
    if history is None:
        raise NotFoundError(f"No series '{series_id}'.")
    build = build_info(session)
    analysis = intelligence.analyse_history(session, history, used)
    found = intelligence.data_insights(analysis)
    variable = None
    reached: list[NodeInfo] = []
    if history.subject.variable_id:
        key = f"variable:{history.subject.variable_id}"
        variable = query_nodes(session, [key]).get(key)
        workspace = workspace_exposure(session, build.id)
        reach = variable_exposure(workspace, key)
        reached = [company for company, _ in reach]
        latest = analysis.latest
        if variable is not None and latest is not None and latest in analysis.detected:
            names = rules.names_of(workspace.companies, workspace.variables)
            related = next(
                (
                    edge
                    for edge in query_edges(
                        session,
                        types=(GraphEdgeType.RELATED_MEASURE_OF,),
                        sources=[f"series:{series_id}"],
                    )
                    if edge.target == key
                ),
                None,
            )
            names[f"series:{series_id}"] = history.subject.name
            item = rules.exposure_change_insight(
                history,
                latest,
                analysis.threshold_name,
                analysis.threshold,
                workspace,
                related,
                names,
            )
            if item is not None:
                found.append(item)
    return SeriesIntelligenceRead.model_validate(
        {
            "build": serialize.build(build),
            "thresholds": used.to_json(),
            "analysis": serialize.series_analysis(analysis),
            "variable": serialize.data(variable),
            "reached": serialize.data(reached),
            "insights": serialize.insights(rules.order(found)),
        }
    )


def instrument_read(
    session: Session, instrument_id: str, used: Thresholds
) -> InstrumentIntelligenceRead:
    histories = load_instrument(session, instrument_id)
    if not histories:
        raise NotFoundError(f"No instrument '{instrument_id}' with stored prices.")
    analyses = [
        intelligence.analyse_history(session, history, used, with_revisions=False)
        for history in histories
    ]
    found = [item for analysis in analyses for item in intelligence.data_insights(analysis)]
    return InstrumentIntelligenceRead.model_validate(
        {
            "thresholds": used.to_json(),
            "analyses": [serialize.series_analysis(item) for item in analyses],
            "insights": serialize.insights(rules.order(found)),
        }
    )


# --- Methods -----------------------------------------------------------------------------------


def methods() -> MethodsRead:
    return MethodsRead.model_validate(
        {
            "engine_version": INTELLIGENCE_VERSION,
            "modules": serialize.data(registry.MODULES),
            "signals": [
                {
                    **serialize.data(spec),
                    "levels": [{"id": key, "label": label} for key, label in spec.levels],
                }
                for spec in signal_specs.SPECS
            ],
            "rules": serialize.data(rules.RULES),
            "kinds": list(rules.KIND_ORDER),
            "thresholds": serialize.data(threshold_specs.SPECS),
            "defaults": threshold_specs.DEFAULTS.to_json(),
            "grades": [
                {"id": grade.value, "strength": GRADE_STRENGTH[grade], "statement": statement}
                for grade, statement in GRADE_STATEMENT.items()
            ],
            "edge_grades": {status: grade.value for status, grade in EDGE_GRADE.items()},
            "notes": [
                "Insights are produced by documented rules from stored data, validated graph "
                "relationships and stored simulations; no text is generated by a language model.",
                "The evidence grade is the weakest step of an insight's chain. It is not a "
                "probability.",
                "Observed changes and model interpretations are separate findings, labelled as "
                "such.",
                NOT_A_FORECAST,
            ],
        }
    )


# --- Stored analyses ---------------------------------------------------------------------------


def _fingerprint(rows: list[tuple[Any, Any, Any]]) -> list[list[Any]]:
    return sorted([str(key), int(count), int(last)] for key, count, last in rows)


def inputs_for(session: Session, scope: str, entity_key: str | None) -> dict[str, Any]:
    """Everything an analysis reads, as a comparable fingerprint (see the module docstring)."""
    build = GraphReader(session).latest_build()
    graph = (
        {
            "build_id": build.id,
            "finished_at": build.finished_at.isoformat() if build.finished_at else None,
            "source_fingerprint": build.source_fingerprint,
        }
        if build
        else None
    )
    observations = select(
        EconomicObservation.series_id,
        func.count(EconomicObservation.id),
        func.max(EconomicObservation.id),
    ).group_by(EconomicObservation.series_id)
    if scope == "entity" and entity_key is not None:
        exposure = entity_exposure(session, entity_key, build.id if build else None)
        series_ids = sorted({item.info.series_id for item in exposure.series if item.info})
        data = {
            "series": _fingerprint(
                [
                    tuple(row)
                    for row in session.execute(
                        observations.where(EconomicObservation.series_id.in_(series_ids))
                    )
                ]
                if series_ids
                else []
            ),
            "related_series": series_ids,
        }
        stored = executions_for(session, entity_key)
        latest_id = stored[0].id if stored else None
        sensitivity = (
            session.scalars(
                select(ScenarioSensitivityAnalysis.id)
                .where(ScenarioSensitivityAnalysis.execution_id == latest_id)
                .order_by(ScenarioSensitivityAnalysis.id)
            ).all()
            if latest_id
            else []
        )
        executions: dict[str, Any] = {
            "ids": [str(row.id) for row in stored],
            "sensitivity": [str(item) for item in sensitivity],
        }
    else:
        data = {
            "series": _fingerprint([tuple(row) for row in session.execute(observations)]),
            "instruments": _fingerprint(
                [
                    tuple(row)
                    for row in session.execute(
                        select(
                            PriceBar.instrument_id, func.count(PriceBar.id), func.max(PriceBar.id)
                        ).group_by(PriceBar.instrument_id)
                    )
                ]
            ),
        }
        executions = {
            "latest": {
                key: str(row.id) for key, row in intelligence.latest_executions(session).items()
            },
            "completed": int(
                session.scalar(
                    select(func.count()).where(
                        ScenarioExecution.status == ScenarioExecutionStatus.COMPLETED
                    )
                )
                or 0
            ),
        }
    return {
        "engine_version": INTELLIGENCE_VERSION,
        "scope": scope,
        "subject": entity_key,
        "graph": graph,
        "data": data,
        "executions": executions,
    }


SECTION_WORDS = {
    "graph": "the knowledge graph was rebuilt",
    "data": "stored values changed",
    "executions": "executions were added",
    "engine_version": "the intelligence engine changed",
    "subject": "the subject changed",
    "scope": "the scope changed",
}


def _freshness(session: Session, row: IntelligenceAnalysis) -> AnalysisFreshnessRead:
    now = datetime.now(UTC)
    if row.subject_key is not None and not query_nodes(session, [row.subject_key]):
        return AnalysisFreshnessRead(
            status="stale",
            changed=["subject"],
            checked_at=now,
            message="The entity is no longer in the current knowledge graph.",
        )
    current = inputs_for(session, row.scope, row.subject_key)
    changed = [key for key in SECTION_WORDS if (row.inputs or {}).get(key) != current.get(key)]
    if not changed:
        return AnalysisFreshnessRead(
            status="current",
            changed=[],
            checked_at=now,
            message="Nothing it read has changed: recomputing it would give the same analysis.",
        )
    return AnalysisFreshnessRead(
        status="stale",
        changed=changed,
        checked_at=now,
        message="Since it was stored, "
        + fmt.listing([SECTION_WORDS[key] for key in changed])
        + ". It shows the analysis as it was; run a new one to see the current state.",
    )


def _summary_read(row: IntelligenceAnalysis) -> AnalysisSummaryRead:
    return AnalysisSummaryRead.model_validate(row)


def analysis_read(session: Session, row: IntelligenceAnalysis) -> AnalysisRead:
    summary = _summary_read(row)
    return AnalysisRead.model_validate(
        {
            **summary.model_dump(),
            "thresholds": row.thresholds,
            "inputs": row.inputs,
            "entity": row.result if row.scope == "entity" else None,
            "workspace": row.result if row.scope == "workspace" else None,
            "freshness": _freshness(session, row),
        }
    )


def create_analysis(session: Session, payload: AnalysisRequest) -> AnalysisRead:
    used = resolve_thresholds(payload.thresholds, location="body")
    started = time.perf_counter()
    if payload.scope == "entity":
        assert payload.entity is not None  # noqa: S101 - the request model requires it
        found = _entity_analysis(session, payload.entity, used, evidence=payload.evidence)
        result = serialize.entity_analysis(found)
        subject_key: str | None = found.entity.key
        subject_name = found.entity.name
        count = len(found.insights)
        build_id = found.build.id
    else:
        workspace = intelligence.analyse_workspace(session, used, build=build_info(session))
        result = serialize.workspace_analysis(workspace)
        subject_key = None
        subject_name = "Workspace"
        count = len(workspace.insights)
        build_id = workspace.build.id
    inputs = inputs_for(session, payload.scope, subject_key)
    row = IntelligenceAnalysis(
        id=uuid.uuid4(),
        scope=payload.scope,
        subject_key=subject_key,
        subject_name=subject_name,
        label=payload.label,
        engine_version=INTELLIGENCE_VERSION,
        thresholds=used.to_json(),
        graph_build_id=build_id,
        inputs=inputs,
        inputs_hash=sha256(inputs),
        result=result,
        result_hash=sha256(result),
        insight_count=count,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    session.add(row)
    session.commit()
    return analysis_read(session, row)


def list_analyses(
    session: Session, *, scope: str | None, entity: str | None, limit: int, offset: int
) -> AnalysisPage:
    query = select(IntelligenceAnalysis)
    if scope is not None:
        query = query.where(IntelligenceAnalysis.scope == scope)
    if entity is not None:
        query = query.where(IntelligenceAnalysis.subject_key == entity)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(IntelligenceAnalysis.created_at.desc(), IntelligenceAnalysis.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return AnalysisPage(
        items=[_summary_read(row) for row in rows], total=total, limit=limit, offset=offset
    )


def get_analysis(session: Session, analysis_id: uuid.UUID) -> AnalysisRead:
    row = session.get(IntelligenceAnalysis, analysis_id)
    if row is None:
        raise NotFoundError(f"No stored analysis '{analysis_id}'.")
    return analysis_read(session, row)
