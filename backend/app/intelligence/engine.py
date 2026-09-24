"""The analysis engine: every module over one read of the store.

Two scopes:

* **an entity** (a company or an industry): its exposure map, the stored executions and their
  drivers, the series related to its exposure variables, its signals, and every insight about
  it — the dossier, and the brief a language-model analyst may phrase;
* **the workspace**: the exposure of every company, the observed data and its signals,
  relationship changes, the latest simulated impact per company, shared drivers, and what
  RUMIN can and cannot say (coverage).

Nothing is written. Reads are bounded (companies, series, instruments, executions), and a
truncated read is reported.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import GraphEdgeType, GraphNodeType, ScenarioExecutionStatus
from app.intelligence import insights as rules
from app.intelligence.drivers import (
    DriverAnalysis,
    ExecutionRef,
    executions_for,
    previous_of_same_scenario,
)
from app.intelligence.drivers import (
    analyse as analyse_drivers,
)
from app.intelligence.exposure import (
    ExposureMap,
    WorkspaceExposure,
    entity_exposure,
    workspace_exposure,
)
from app.intelligence.graphchanges import RelationshipChanges, relationship_changes
from app.intelligence.graphview import EdgeInfo, NodeInfo, query_edges, query_nodes
from app.intelligence.interpretation import Interpretation, NotInterpreted, interpret
from app.intelligence.model import Insight, NextStep
from app.intelligence.series import (
    AnomalyResult,
    Change,
    History,
    Revision,
    TrendResult,
    VolatilityResult,
    anomaly,
    changes,
    instruments_with_data,
    load_instrument,
    load_series,
    meets,
    revisions,
    series_with_data,
    threshold_for,
    trend,
    volatility,
)
from app.intelligence.signals import Signal, entity_signals, series_signals
from app.intelligence.thresholds import Thresholds
from app.models import (
    EconomicSeries,
    GraphNode,
    Instrument,
    ScenarioExecution,
    ScenarioExecutionRun,
    SimulationRun,
)

ENTITY_TYPES = ("company", "industry")
MAX_REVISION_INSIGHTS = 5


class EntityNotFound(LookupError):
    pass


class NotAnEntity(ValueError):
    pass


@dataclass(frozen=True)
class BuildInfo:
    id: int | None
    finished_at: datetime | None
    freshness: str  # current | stale | not_built
    message: str | None


@dataclass(frozen=True)
class SeriesAnalysis:
    history: History
    changes: tuple[Change, ...]
    threshold_name: str
    threshold: Decimal
    detected: tuple[Change, ...]  # changes in the latest window that meet the threshold
    trend: TrendResult | None
    volatility: VolatilityResult | None
    anomaly: AnomalyResult | None
    revisions: tuple[Revision, ...]
    signals: tuple[Signal, ...]

    @property
    def latest(self) -> Change | None:
        return self.changes[-1] if self.changes else None


def analyse_history(
    session: Session, history: History, thresholds: Thresholds, *, with_revisions: bool = True
) -> SeriesAnalysis:
    found = changes(history)
    name, threshold = threshold_for(history.subject, thresholds)
    window = thresholds.window_for(history.subject.frequency)
    detected = tuple(change for change in found[-window:] if meets(change, threshold))
    trend_result = trend(history, thresholds)
    volatility_result = volatility(found, thresholds, history.subject.frequency)
    anomaly_result = anomaly(found, thresholds)
    return SeriesAnalysis(
        history=history,
        changes=tuple(found),
        threshold_name=name,
        threshold=threshold,
        detected=detected,
        trend=trend_result,
        volatility=volatility_result,
        anomaly=anomaly_result,
        revisions=tuple(revisions(session, history)) if with_revisions else (),
        signals=tuple(
            series_signals(history, trend_result, volatility_result, anomaly_result, thresholds)
        ),
    )


def data_insights(analysis: SeriesAnalysis) -> list[Insight]:
    """D01, D03–D06 for one series or instrument."""
    history = analysis.history
    found: list[Insight] = []
    latest = analysis.latest
    if latest is not None and meets(latest, analysis.threshold):
        found.append(
            rules.change_insight(history, latest, analysis.threshold_name, analysis.threshold)
        )
    for signal in analysis.signals:
        builder = {
            "anomaly": rules.anomaly_insight,
            "trend": rules.trend_insight,
            "volatility": rules.volatility_insight,
        }.get(signal.id)
        insight = builder(history, signal) if builder else None
        if insight is not None:
            found.append(insight)
    found.extend(
        rules.revision_insight(history, item) for item in analysis.revisions[:MAX_REVISION_INSIGHTS]
    )
    return found


def unique_steps(insights: Iterable[Insight]) -> tuple[NextStep, ...]:
    seen: list[NextStep] = []
    for insight in insights:
        for step in insight.next_steps:
            if step not in seen:
                seen.append(step)
    return tuple(seen)


# --- One entity ------------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityAnalysis:
    entity: NodeInfo
    build: BuildInfo
    thresholds: Thresholds
    exposure: ExposureMap
    executions: tuple[ExecutionRef, ...]
    drivers: DriverAnalysis | None
    previous: DriverAnalysis | None
    series: tuple[SeriesAnalysis, ...]
    interpretations: tuple[Interpretation, ...]
    not_interpreted: tuple[NotInterpreted, ...]
    signals: tuple[Signal, ...]
    insights: tuple[Insight, ...]
    next_steps: tuple[NextStep, ...]


def entity_node(session: Session, entity_key: str) -> NodeInfo:
    node = query_nodes(session, [entity_key]).get(entity_key)
    if node is None:
        raise EntityNotFound(f"No current knowledge-graph node has the key '{entity_key}'.")
    if node.node_type not in ENTITY_TYPES:
        raise NotAnEntity(
            f"'{entity_key}' is {kind_phrase(node.node_type)}: intelligence is computed for "
            "companies and industries."
        )
    return node


def kind_phrase(node_type: str) -> str:
    """'an economic variable', 'a country'."""
    words = node_type.replace("_", " ")
    return f"{'an' if words[:1] in 'aeiou' else 'a'} {words}"


def _execution_ref(session: Session, execution: ScenarioExecution) -> ExecutionRef:
    return analyse_drivers(session, execution, "").execution


def analyse_entity(
    session: Session,
    entity_key: str,
    thresholds: Thresholds,
    *,
    build: BuildInfo,
    evidence: str = "any",
) -> EntityAnalysis:
    entity = entity_node(session, entity_key)
    exposure = entity_exposure(session, entity_key, build.id, evidence=evidence)
    stored = executions_for(session, entity_key) if entity.node_type == "company" else []
    drivers = analyse_drivers(session, stored[0], entity_key) if stored else None
    before = previous_of_same_scenario(stored, stored[0]) if stored else None
    previous = analyse_drivers(session, before, entity_key) if before is not None else None

    series: list[SeriesAnalysis] = []
    related: dict[str, EdgeInfo] = {}
    for measured in exposure.series:
        if measured.info is None or measured.info.observation_count == 0:
            continue
        history = load_series(session, measured.info.series_id)
        if history is not None and history.points:
            series.append(analyse_history(session, history, thresholds))
            related[history.subject.id] = measured.edge

    names = rules.names_of(
        [entity],
        [node for path in exposure.paths for node in path.hops],
        [c.counterparty for c in exposure.counterparties],
        [link.node for link in exposure.context],
        [path.industry for path in exposure.paths if path.industry],
    )
    for analysis in series:
        names[f"series:{analysis.history.subject.id}"] = analysis.history.subject.name

    interpretations: list[Interpretation] = []
    refused: list[NotInterpreted] = []
    if drivers is not None:
        changed = {c.variable_id for c in drivers.changes}
        for analysis in series:
            latest = analysis.latest
            if latest is None or analysis.history.subject.variable_id not in changed:
                continue
            result = interpret(
                session, drivers, analysis.history, latest, freshness=build.freshness
            )
            (interpretations if isinstance(result, Interpretation) else refused).append(
                result  # type: ignore[arg-type]
            )

    signals = entity_signals(exposure, drivers, thresholds)
    found: list[Insight] = []
    for analysis in series:
        found.extend(data_insights(analysis))
    if drivers is not None:
        impact = rules.impact_insight(
            drivers, entity, exposure.paths, names, list(drivers.not_modelled)
        )
        if impact:
            found.append(impact)
        for line in drivers.lines:
            item = rules.contribution_insight(drivers, line, entity)
            if item:
                found.append(item)
        found.extend(rules.per_unit_insights(drivers, entity))
        ranking = rules.ranking_insight(drivers, entity)
        if ranking:
            found.append(ranking)
        if previous is not None:
            moved = rules.execution_change_insight(drivers, previous, entity)
            if moved:
                found.append(moved)
        for interp in interpretations:
            history = next(a.history for a in series if a.history.subject.id == interp.series_id)
            item = rules.interpretation_insight(
                interp,
                history,
                entity,
                related.get(interp.series_id),
                names,
                drivers.execution.horizon_months,
            )
            if item:
                found.append(item)
    found.extend(
        rules.exposure_insights(
            exposure, {c.variable_id for c in drivers.changes} if drivers else set(), names
        )
    )
    dependency = next((s for s in signals if s.id == "dependency"), None)
    if dependency is not None:
        item = rules.dependency_insight(exposure, dependency, names)
        if item:
            found.append(item)
    counterparties = rules.counterparty_insight(exposure, names)
    if counterparties:
        found.append(counterparties)
    coverage = rules.coverage_insight(exposure, drivers)
    if coverage:
        found.append(coverage)
    ordered = rules.order(found)
    return EntityAnalysis(
        entity=entity,
        build=build,
        thresholds=thresholds,
        exposure=exposure,
        executions=tuple(_execution_ref(session, item) for item in stored),
        drivers=drivers,
        previous=previous,
        series=tuple(series),
        interpretations=tuple(interpretations),
        not_interpreted=tuple(refused),
        signals=tuple(signals),
        insights=tuple(ordered),
        next_steps=unique_steps(ordered),
    )


# --- The workspace ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Coverage:
    companies: int  # in the current graph
    companies_listed: int  # analysed (the first WORKSPACE_LIMIT by name)
    companies_with_exposure: int  # among those listed
    exposure_paths: int
    variables: int
    series: int
    series_with_data: int
    observations: int
    instruments: int
    instruments_with_data: int
    related_series: int
    related_with_data: int
    executions: int
    companies_with_executions: int
    truncated: bool

    @property
    def data(self) -> rules.DataCoverage:
        return rules.DataCoverage(
            series=self.series,
            series_with_data=self.series_with_data,
            observations=self.observations,
            instruments=self.instruments,
            instruments_with_data=self.instruments_with_data,
            related_series=self.related_series,
            related_with_data=self.related_with_data,
        )


@dataclass(frozen=True)
class WorkspaceAnalysis:
    build: BuildInfo
    thresholds: Thresholds
    exposure: WorkspaceExposure
    series: tuple[SeriesAnalysis, ...]
    instruments: tuple[SeriesAnalysis, ...]
    relationships: RelationshipChanges
    drivers: dict[str, DriverAnalysis]
    coverage: Coverage
    insights: tuple[Insight, ...]
    next_steps: tuple[NextStep, ...]


def latest_executions(
    session: Session, companies: Iterable[str] | None = None
) -> dict[str, ScenarioExecution]:
    """The latest completed execution of each company (of ``companies``, when given), from
    one query. Exact: a company keeps its latest execution however many executions other
    companies have had since."""
    ranked = (
        select(
            SimulationRun.entity_id.label("entity_id"),
            ScenarioExecution.id.label("execution_id"),
            func.row_number()
            .over(
                partition_by=SimulationRun.entity_id,
                order_by=(ScenarioExecution.finished_at.desc(), ScenarioExecution.id),
            )
            .label("position"),
        )
        .join(ScenarioExecutionRun, ScenarioExecutionRun.simulation_run_id == SimulationRun.id)
        .join(ScenarioExecution, ScenarioExecution.id == ScenarioExecutionRun.execution_id)
        .where(
            ScenarioExecution.status == ScenarioExecutionStatus.COMPLETED,
            ScenarioExecution.results.is_not(None),
            ScenarioExecution.finished_at.is_not(None),
            SimulationRun.entity_id.is_not(None),
        )
    )
    if companies is not None:
        keys = list(companies)
        if not keys:
            return {}
        ranked = ranked.where(SimulationRun.entity_id.in_(keys))
    latest = ranked.subquery()
    rows = session.execute(
        select(latest.c.entity_id, ScenarioExecution)
        .join(ScenarioExecution, ScenarioExecution.id == latest.c.execution_id)
        .where(latest.c.position == 1)
        .order_by(latest.c.entity_id)
    ).all()
    return {str(entity_id): execution for entity_id, execution in rows}


def _related_edges(session: Session, variable_keys: Iterable[str]) -> dict[str, EdgeInfo]:
    """series key → its `related_measure_of` edge, for the given variables."""
    found: dict[str, EdgeInfo] = {}
    for edge in query_edges(
        session, types=(GraphEdgeType.RELATED_MEASURE_OF,), targets=variable_keys
    ):
        found[edge.source] = edge
    return found


def analyse_data(
    session: Session, thresholds: Thresholds
) -> tuple[list[SeriesAnalysis], list[SeriesAnalysis]]:
    """Every series and instrument with two or more stored values, analysed."""
    series: list[SeriesAnalysis] = []
    for series_id in series_with_data(session):
        history = load_series(session, series_id)
        if history is not None and history.points:
            series.append(analyse_history(session, history, thresholds))
    instruments = [
        analyse_history(session, history, thresholds, with_revisions=False)
        for instrument_id in instruments_with_data(session)
        for history in load_instrument(session, instrument_id)
        if history.points
    ]
    return series, instruments


def analyse_workspace(
    session: Session, thresholds: Thresholds, *, build: BuildInfo
) -> WorkspaceAnalysis:
    exposure = workspace_exposure(session, build.id)
    names = rules.names_of(
        exposure.companies,
        exposure.variables,
        [p.industry for paths in exposure.paths.values() for p in paths if p.industry],
    )
    series, instruments = analyse_data(session, thresholds)
    changes_in_graph = relationship_changes(session)
    companies = {company.key: company for company in exposure.companies}
    drivers = {
        key: analyse_drivers(session, execution, key)
        for key, execution in latest_executions(session, companies).items()
    }

    variable_keys = {
        f"variable:{a.history.subject.variable_id}" for a in series if a.history.subject.variable_id
    }
    related = _related_edges(session, variable_keys) if variable_keys else {}
    names.update({key: node.name for key, node in query_nodes(session, variable_keys).items()})
    found: list[Insight] = []
    for analysis in [*series, *instruments]:
        found.extend(data_insights(analysis))
        latest = analysis.latest
        if analysis.history.subject.variable_id and latest and meets(latest, analysis.threshold):
            edge = related.get(f"series:{analysis.history.subject.id}")
            item = rules.exposure_change_insight(
                analysis.history,
                latest,
                analysis.threshold_name,
                analysis.threshold,
                exposure,
                edge,
                names,
            )
            if item:
                found.append(item)
    found.extend(rules.relationship_change_insights(changes_in_graph))
    found.extend(rules.shared_driver_insights(exposure, names))
    for key, company_drivers in drivers.items():
        impact = rules.impact_insight(
            company_drivers,
            companies[key],
            exposure.paths.get(key, ()),
            names,
            list(company_drivers.not_modelled),
        )
        if impact:
            found.append(impact)

    catalogue = session.execute(
        select(
            func.count(EconomicSeries.id),
            func.coalesce(func.sum(EconomicSeries.observation_count), 0),
        )
    ).one()
    executions_total = (
        session.scalar(
            select(func.count(ScenarioExecution.id)).where(
                ScenarioExecution.status == ScenarioExecutionStatus.COMPLETED
            )
        )
        or 0
    )
    measured = {
        edge.source.partition(":")[2]
        for edge in query_edges(session, types=(GraphEdgeType.RELATED_MEASURE_OF,))
    }
    coverage = Coverage(
        companies=company_count(session),
        companies_listed=len(exposure.companies),
        companies_with_exposure=sum(1 for paths in exposure.paths.values() if paths),
        exposure_paths=sum(len(paths) for paths in exposure.paths.values()),
        variables=len(exposure.variables),
        series=int(catalogue[0]),
        series_with_data=len(series),
        observations=int(catalogue[1]),
        instruments=int(session.scalar(select(func.count(Instrument.id))) or 0),
        instruments_with_data=len({a.history.subject.id for a in instruments}),
        related_series=len(measured),
        related_with_data=len(measured & {a.history.subject.id for a in series}),
        executions=int(executions_total),
        companies_with_executions=len(drivers),
        truncated=exposure.truncated,
    )
    found.append(rules.data_coverage_insight(coverage.data))
    ordered = rules.order(found)
    return WorkspaceAnalysis(
        build=build,
        thresholds=thresholds,
        exposure=exposure,
        series=tuple(series),
        instruments=tuple(instruments),
        relationships=changes_in_graph,
        drivers=drivers,
        coverage=coverage,
        insights=tuple(ordered),
        next_steps=unique_steps(ordered),
    )


def company_count(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count(GraphNode.id)).where(
                GraphNode.retired_build_id.is_(None),
                GraphNode.node_type == GraphNodeType.COMPANY,
            )
        )
        or 0
    )
