"""Tools over RUMIN's records: finding records, what RUMIN knows about a company or industry,
exposure, a variable's reach, how two records are connected, one relationship, the models,
the templates, and what data RUMIN holds. Each reads through an existing service."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analyst.answer import (
    Block,
    Column,
    EntityRef,
    PathItem,
    PathLink,
    PathsBlock,
    PathStep,
    ScenarioBlock,
    ScenarioChange,
    ScenarioLine,
    TableBlock,
    TableRow,
)
from app.analyst.evidence import (
    Knowledge,
    SourceRef,
    exact,
    model_link,
    node_link,
    scenario_link,
    series_link,
    template_link,
)
from app.analyst.policy import data_text
from app.analyst.tools.common import (
    STATUS_LABEL,
    THRESHOLDS,
    compact_path,
    edge_evidence,
    node_evidence,
    path_item,
    path_names,
)
from app.analyst.tools.registry import RenderContext, Tool, ToolOutput
from app.analyst.vocabulary import KINDS, Vocabulary, normalise
from app.graph.algorithms import Direction
from app.graph.drafts import EDGE_KEY_PATTERN, NODE_KEY_PATTERN
from app.models import (
    Dataset,
    EconomicSeries,
    GraphNode,
    Instrument,
    Scenario,
    ScenarioExecution,
)
from app.schemas.common import InputModel
from app.schemas.graph import GraphEdgeDetail, PathsResponse
from app.schemas.intelligence import (
    EntityAnalysisRead,
    ExposureMapRead,
    ExposurePathRead,
    NodeRead,
    VariableExposureRead,
)
from app.schemas.scenario import TemplateList
from app.schemas.simulation import SimulationModelSummary
from app.services import graph as graph_service
from app.services import intelligence as intelligence_service
from app.services import scenario_lab as lab_service
from app.services import simulation as simulation_service
from app.services.intelligence import build_info

MAX_PATHS_SHOWN = 12
EntityKey = Field(pattern=r"^(company|industry):[a-z0-9][a-z0-9_.-]{0,95}$", max_length=128)


# --- search_records ----------------------------------------------------------------------------


class SearchInput(InputModel):
    query: str = Field(
        default="", max_length=120, description="A name or part of one; empty lists all."
    )
    kinds: list[Literal[KINDS]] = Field(  # type: ignore[valid-type]
        default_factory=list, max_length=8, description="Only these kinds of record."
    )
    country_key: str | None = Field(
        default=None,
        pattern=r"^country:[a-z0-9_]{2,60}$",
        description="Only records of this country (companies by domicile, series, variables).",
    )
    limit: int = Field(default=8, ge=1, le=20)


@dataclass
class Match:
    kind: str
    key: str
    record_id: str
    label: str
    by: str


def _search(session: Session, args: SearchInput, vocabulary: Vocabulary) -> list[Match]:
    text = normalise(args.query)
    wanted = set(args.kinds) or set(KINDS) | {"scenario"}
    country = args.country_key.partition(":")[2] if args.country_key else None

    def fits(term_country: str | None) -> bool:
        return country is None or (term_country or "").lower() == country

    found: dict[str, Match] = {}
    if text:
        for mention in vocabulary.find(text):
            term = mention.term
            if term.kind in wanted and fits(term.country):
                found.setdefault(
                    term.key, Match(term.kind, term.key, term.record_id, term.label, mention.by)
                )
    for term in vocabulary.terms:
        if (
            term.kind in wanted
            and term.key not in found
            and fits(term.country)
            and (not text or text in term.name or any(text in alias for alias in term.aliases))
        ):
            found[term.key] = Match(
                term.kind, term.key, term.record_id, term.label, "part" if text else "filter"
            )
    if "scenario" in wanted and text and country is None:
        pattern = f"%{args.query.lower()}%"
        for scenario in session.scalars(
            select(Scenario).where(func.lower(Scenario.name).like(pattern)).limit(args.limit)
        ):
            key = f"scenario:{scenario.id}"
            found.setdefault(key, Match("scenario", key, str(scenario.id), scenario.name, "name"))
    return list(found.values())[: args.limit]


def _search_render(
    ctx: RenderContext, args: SearchInput, matches: list[Match], read_at: datetime
) -> ToolOutput:
    def link(match: Match) -> str | None:
        if match.kind == "scenario":
            return scenario_link(match.record_id)
        if match.kind == "model":
            return model_link(match.record_id)
        if match.kind == "template":
            return template_link(match.record_id)
        if match.kind == "series":
            return series_link(match.record_id)
        return node_link(match.key)

    evidence = ctx.ledger.add(
        tool="search_records",
        call=ctx.call,
        kind=Knowledge.RECORD,
        title=f"Records matching '{data_text(args.query, 80)}'"
        + (f" in {args.country_key}" if args.country_key else "")
        + (f" ({', '.join(args.kinds)})" if args.kinds else ""),
        source=SourceRef(
            kind="catalogue",
            id=f"search:{args.query.lower()}:{args.country_key or ''}:{','.join(args.kinds)}",
            label="Search",
        ),
        retrieved_at=read_at,
        values={"matches": len(matches)},
    )
    rows = [
        TableRow(
            cells={"name": match.label, "kind": match.kind}, link=link(match), citations=[evidence]
        )
        for match in matches
    ]
    return ToolOutput(
        data={
            "evidence": evidence,
            "matches": [
                {"kind": m.kind, "key": m.key, "name": m.label, "matched_by": m.by} for m in matches
            ],
        },
        summary=f"{len(matches)} records match '{args.query}'",
        evidence=[evidence],
        display=[
            TableBlock(
                title=f"Records matching '{args.query}'",
                columns=[Column(key="name", label="Record"), Column(key="kind", label="Kind")],
                rows=rows,
                citations=[evidence],
            )
        ]
        if rows
        else [],
        facts=matches,
    )


SEARCH_RECORDS = Tool(
    name="search_records",
    description="Find RUMIN records (companies, industries, countries, economic variables, "
    "data series, instruments, simulation models, scenario templates, stored scenarios) by "
    "name. Use it to turn a name into a record key before calling another tool.",
    input_model=SearchInput,
    fetch=_search,
    render=_search_render,
    timeout_seconds=4,
)


# --- get_entity_dossier ------------------------------------------------------------------------


class EntityInput(InputModel):
    entity_key: str = EntityKey


@dataclass
class Dossier:
    analysis: EntityAnalysisRead
    description: str


def _dossier(session: Session, args: EntityInput, _vocabulary: Vocabulary) -> Dossier:
    analysis = intelligence_service.entity(session, args.entity_key, THRESHOLDS, "any")
    node = session.get(GraphNode, args.entity_key)
    return Dossier(analysis, node.description if node else "")


def simulation_block(
    ctx: RenderContext,
    tool: str,
    drivers: Any,
    entity: NodeRead,
    read_at: datetime,
) -> tuple[ScenarioBlock, list[str]]:
    """A stored execution (a ``DriverAnalysisRead``) as evidence and a scenario card."""
    execution = drivers.execution
    models = [f"{model.model_id} {model.version}" for model in drivers.models]
    link = scenario_link(execution.scenario_id, execution.id)
    line_values: dict[str, Any] = {}
    for line in drivers.lines:
        line_values[f"{line.id}.baseline"] = line.baseline
        line_values[f"{line.id}.change"] = line.change
        line_values[f"{line.id}.scenario"] = line.scenario
        line_values[f"{line.id}.percent_change"] = line.percent_change
    for change in drivers.changes:
        line_values[f"change.{change.variable_id}"] = change.value
    line_values["horizon_months"] = execution.horizon_months
    line_values["version"] = execution.version
    simulated = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.SIMULATED,
        title=f"Execution of '{data_text(execution.scenario_name, 120)}' (version "
        f"{execution.version}) for {entity.name}",
        detail=data_text(drivers.headline, 300) if drivers.headline else None,
        source=SourceRef(
            kind="execution", id=execution.id, label=execution.scenario_name, link=link
        ),
        retrieved_at=read_at,
        as_of=execution.finished_at.isoformat() if execution.finished_at else None,
        period=f"{execution.horizon_months} months simulated",
        currency=execution.currency,
        models=models,
        assumptions=[data_text(item, 300) for item in drivers.assumptions[:12]],
        provenance={
            "scenario": execution.scenario_id,
            "version": str(execution.version),
            "inputs_hash": execution.inputs_hash,
            "result_hash": execution.result_hash,
            "graph_build": str(execution.graph_build_id) if execution.graph_build_id else None,
        },
        values=line_values,
    )
    cited = [simulated]
    if drivers.figures:
        figures = ctx.ledger.add(
            tool=tool,
            call=ctx.call,
            kind=Knowledge.USER_INPUT,
            title=f"Figures entered in '{data_text(execution.scenario_name, 120)}'",
            detail="Entered by a person in the Scenario Lab; not RUMIN data.",
            source=SourceRef(
                kind="scenario",
                id=execution.scenario_id,
                label=execution.scenario_name,
                link=scenario_link(execution.scenario_id),
            ),
            retrieved_at=read_at,
            period=f"version {execution.version}",
            values={
                "version": execution.version,
                **{item.label: item.value for item in drivers.figures},
            },
        )
        cited.append(figures)
    block = ScenarioBlock(
        status="stored",
        title=execution.scenario_name,
        entity=EntityRef(key=entity.key, name=entity.name, link=node_link(entity.key)),
        changes=[
            ScenarioChange(
                variable_id=change.variable_id,
                name=change.name,
                change_type=change.change_type,
                value=exact(change.value) or "0",
                unit=change.unit,
                modelled=change.modelled,
            )
            for change in drivers.changes
        ],
        horizon_months=execution.horizon_months,
        lines=[
            ScenarioLine(
                id=line.id,
                label=line.label,
                currency=line.currency,
                baseline=exact(line.baseline),
                change=exact(line.change) or "0",
                scenario=exact(line.scenario),
                percent_change=exact(line.percent_change),
                citations=[simulated],
            )
            for line in drivers.lines
        ],
        models=models,
        headline=drivers.headline,
        scenario_id=execution.scenario_id,
        execution_id=execution.id,
        link=link,
        notes=[data_text(item, 300) for item in drivers.not_modelled[:6]],
        citations=cited,
    )
    return block, cited


def _dossier_render(
    ctx: RenderContext, args: EntityInput, found: Dossier, read_at: datetime
) -> ToolOutput:
    analysis = found.analysis
    entity = analysis.entity
    build_id = analysis.build.id
    tool = "get_entity_dossier"
    record = node_evidence(ctx, tool, entity, read_at, build_id, found.description or None)
    exposure = analysis.exposure
    summary = exposure.summary
    exposure_id = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RECORD,
        title=f"Exposure of {entity.name} stated in the knowledge graph",
        detail="Counts of validated relationship paths from economic variables. They say who "
        "is exposed and through what, never how much.",
        source=SourceRef(
            kind="exposure",
            id=entity.key,
            label=f"Exposure of {entity.name} (graph build {build_id})",
            link=node_link(entity.key),
        ),
        retrieved_at=read_at,
        as_of=f"graph build {build_id}" if build_id else None,
        values={
            "paths": summary.paths,
            "variables": summary.variables,
            **{f"channel.{key}": value for key, value in summary.by_channel.items()},
            **{f"how.{key}": value for key, value in summary.by_directness.items()},
        },
    )
    names = path_names(exposure.paths, entity)
    shown = exposure.paths[:MAX_PATHS_SHOWN]
    items = [path_item(ctx, tool, path, entity, names, read_at, build_id) for path in shown]
    display: list[Any] = []
    if items:
        display.append(
            PathsBlock(
                title=f"How economic variables reach {entity.name}",
                paths=items,
                total=len(exposure.paths),
                note="Relationships say who is exposed and through what, never how much.",
                citations=[exposure_id],
            )
        )
    counterparties = []
    for party in exposure.counterparties[:10]:
        names[party.counterparty.key] = party.counterparty.name
        cited = edge_evidence(ctx, tool, party.edge, names, read_at, build_id)
        counterparties.append(
            TableRow(
                cells={
                    "counterparty": party.counterparty.name,
                    "role": party.role,
                    "level": party.level,
                    "evidence": STATUS_LABEL.get(party.edge.evidence_status),
                },
                link=node_link(party.counterparty.key),
                citations=[cited],
            )
        )
    if counterparties:
        display.append(
            TableBlock(
                title="Counterparties stated in the graph",
                columns=[
                    Column(key="counterparty", label="Counterparty"),
                    Column(key="role", label="Role"),
                    Column(key="level", label="Stated for"),
                    Column(key="evidence", label="Evidence"),
                ],
                rows=counterparties,
            )
        )
    simulation: list[str] = []
    if analysis.drivers is not None:
        block, simulation = simulation_block(ctx, tool, analysis.drivers, entity, read_at)
        display.append(block)
    findings: list[TableRow] = []
    finding_ids: list[str] = []
    findings_total = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RECORD,
        title=f"Financial Intelligence findings for {entity.name}",
        detail="How many findings the documented rules produce for this entity now.",
        source=SourceRef(
            kind="catalogue",
            id=f"findings:{entity.key}",
            label="Financial Intelligence",
            link=node_link(entity.key),
        ),
        retrieved_at=read_at,
        values={
            "findings": len(analysis.insights),
            **{f"grade.{grade}": count for grade, count in analysis.grades.items()},
        },
    )
    for insight in analysis.insights[:6]:
        cited = ctx.ledger.add(
            tool=tool,
            call=ctx.call,
            kind=Knowledge.FINDING,
            title=data_text(insight.headline, 200),
            detail=data_text(insight.statement, 500),
            source=SourceRef(
                kind="insight", id=insight.id, label=insight.rule_title, link=node_link(entity.key)
            ),
            retrieved_at=read_at,
            period=insight.period.label,
            grade=insight.evidence.grade,
            assumptions=[data_text(item, 200) for item in insight.assumptions[:4]],
            values={
                fact.label: fact.value
                for fact in insight.facts
                if fact.value is not None and _is_number(fact.value)
            },
        )
        finding_ids.append(cited)
        findings.append(
            TableRow(
                cells={
                    "finding": insight.headline,
                    "kind": insight.kind,
                    "grade": insight.evidence.grade,
                },
                link=node_link(entity.key),
                citations=[cited],
            )
        )
    if findings:
        display.append(
            TableBlock(
                title="Financial Intelligence findings",
                columns=[
                    Column(key="finding", label="Finding"),
                    Column(key="kind", label="Kind"),
                    Column(key="grade", label="Evidence grade"),
                ],
                rows=findings,
                note="The grade is the weakest step of each finding's evidence chain; it is "
                "not a probability.",
            )
        )
    data = {
        "entity": {
            "key": entity.key,
            "name": entity.name,
            "kind": entity.node_type,
            "nature": entity.nature,
            "evidence": record,
        },
        "description": data_text(found.description, 400),
        "graph_build": build_id,
        "graph_freshness": analysis.build.freshness,
        "exposure": {
            "evidence": exposure_id,
            "paths": summary.paths,
            "variables": summary.variables,
            "by_channel": summary.by_channel,
            "by_directness": summary.by_directness,
            "shown": [compact_path(path) for path in shown[:8]],
        },
        "counterparties": [
            {"name": p.counterparty.name, "role": p.role, "level": p.level}
            for p in exposure.counterparties[:10]
        ],
        "latest_execution": _execution_data(analysis, simulation),
        "findings_total": {"evidence": findings_total, "count": len(analysis.insights)},
        "findings": [
            {"evidence": cited, "headline": insight.headline, "grade": insight.evidence.grade}
            for cited, insight in zip(finding_ids, analysis.insights[:6], strict=False)
        ],
        "stored_executions": len(analysis.executions),
    }
    return ToolOutput(
        data=data,
        summary=f"{entity.name}: {summary.paths} exposure paths, "
        f"{len(analysis.executions)} stored executions, {len(analysis.insights)} findings",
        evidence=[record, exposure_id, *simulation, findings_total, *finding_ids],
        display=display,
        facts=found,
    )


def _is_number(value: str) -> bool:
    try:
        float(value.replace(",", ""))
    except ValueError:
        return False
    return True


def _execution_data(analysis: EntityAnalysisRead, cited: list[str]) -> dict[str, Any] | None:
    drivers = analysis.drivers
    if drivers is None:
        return None
    return {
        "evidence": cited,
        "scenario": drivers.execution.scenario_name,
        "version": drivers.execution.version,
        "horizon_months": drivers.execution.horizon_months,
        "currency": drivers.execution.currency,
        "changes": [
            {"variable": c.name, "type": c.change_type, "value": exact(c.value), "unit": c.unit}
            for c in drivers.changes
        ],
        "lines": [
            {
                "line": line.label,
                "baseline": exact(line.baseline),
                "change": exact(line.change),
                "percent_change": exact(line.percent_change),
            }
            for line in drivers.lines
        ],
        "headline": drivers.headline,
    }


GET_ENTITY_DOSSIER = Tool(
    name="get_entity_dossier",
    description="What RUMIN holds about one company or industry: its record, the economic "
    "variables that reach it through validated knowledge-graph relationships (counts and "
    "paths), counterparties, its latest stored scenario execution (simulated) and its "
    "Financial Intelligence findings with evidence grades.",
    input_model=EntityInput,
    fetch=_dossier,
    render=_dossier_render,
    timeout_seconds=10,
)


# --- get_exposure ------------------------------------------------------------------------------


class ExposureInput(InputModel):
    entity_key: str = EntityKey
    channel: Literal["costs", "revenue", "financing"] | None = None
    variable_key: str | None = Field(
        default=None, pattern=r"^variable:[a-z0-9][a-z0-9_.-]{0,95}$", max_length=128
    )
    evidence: Literal["any", "evidence_backed"] = "any"


def _exposure(session: Session, args: ExposureInput, _vocabulary: Vocabulary) -> ExposureMapRead:
    return ExposureMapRead.model_validate(
        intelligence_service.entity_exposure_read(session, args.entity_key, args.evidence)
    )


def _exposure_render(
    ctx: RenderContext, args: ExposureInput, exposure: ExposureMapRead, read_at: datetime
) -> ToolOutput:
    entity = exposure.entity
    tool = "get_exposure"
    paths: list[ExposurePathRead] = [
        path
        for path in exposure.paths
        if (args.channel is None or path.channel == args.channel)
        and (
            args.variable_key is None
            or args.variable_key
            in {path.origin.key, path.variable.key, *(node.key for node in path.hops)}
        )
    ]
    variables = sorted({node.key for path in paths for node in path.hops})
    origins = sorted({path.origin.key for path in paths})
    channels = Counter(path.channel for path in paths)
    how = Counter(path.directness for path in paths)
    weakest = Counter(path.evidence_status for path in paths)
    scope = []
    if args.channel:
        scope.append(f"{args.channel}")
    if args.variable_key:
        scope.append(args.variable_key)
    summary_id = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RECORD,
        title=f"Exposure of {entity.name}" + (f" ({', '.join(scope)})" if scope else ""),
        detail="Validated relationship paths in the current knowledge graph. They say who is "
        "exposed and through what, never how much.",
        source=SourceRef(
            kind="exposure",
            id="|".join([entity.key, args.channel or "", args.variable_key or "", args.evidence]),
            label=f"Exposure of {entity.name} (graph build {exposure.build_id})",
            link=node_link(entity.key),
        ),
        retrieved_at=read_at,
        as_of=f"graph build {exposure.build_id}" if exposure.build_id else None,
        values={
            "paths": len(paths),
            "variables": len(variables),
            "origins": len(origins),
            **{f"channel.{key}": value for key, value in channels.items()},
            **{f"how.{key}": value for key, value in how.items()},
            **{f"weakest.{key}": value for key, value in weakest.items()},
            "flagged": len(exposure.flagged),
            "removed_by_filter": exposure.removed_by_filter,
            "all_paths": len(exposure.paths),
        },
    )
    names = path_names(paths, entity)
    items = [
        path_item(ctx, tool, path, entity, names, read_at, exposure.build_id)
        for path in paths[:MAX_PATHS_SHOWN]
    ]
    display: list[Any] = []
    if items:
        display.append(
            PathsBlock(
                title=f"How economic variables reach {entity.name}",
                paths=items,
                total=len(paths),
                note="Each path is a chain of validated relationships; its evidence is the "
                "weakest along it.",
                citations=[summary_id],
            )
        )
    by_path = [
        {**compact_path(path), "evidence": item.citations}
        for path, item in zip(paths, items, strict=False)
    ]
    return ToolOutput(
        data={
            "entity": {"key": entity.key, "name": entity.name, "nature": entity.nature},
            "evidence": summary_id,
            "paths": len(paths),
            "variables": [names.get(key, key) for key in variables],
            "by_channel": dict(channels),
            "by_how": dict(how),
            "by_weakest_evidence": dict(weakest),
            "shown": by_path,
            "flagged_relationships": len(exposure.flagged),
            "notes": [data_text(note, 300) for note in exposure.notes[:4]],
        },
        summary=f"{entity.name}: {len(paths)} paths from {len(variables)} variables",
        evidence=[summary_id, *(cited for item in items for cited in item.citations)],
        display=display,
        facts=(exposure, paths),
    )


GET_EXPOSURE = Tool(
    name="get_exposure",
    description="The economic variables that reach one company or industry through validated "
    "knowledge-graph relationships: each path with its channel (costs, revenue, financing), "
    "how it reaches (directly, via the industry, upstream through another variable), the "
    "weakest evidence along it and the models that can simulate it. Optionally one channel "
    "or one variable. Exposure is stated, never sized.",
    input_model=ExposureInput,
    fetch=_exposure,
    render=_exposure_render,
)


# --- get_variable_reach ------------------------------------------------------------------------


class VariableInput(InputModel):
    variable_key: str = Field(pattern=r"^variable:[a-z0-9][a-z0-9_.-]{0,95}$", max_length=128)


@dataclass
class Reach:
    read: VariableExposureRead
    description: str
    series: list[tuple[str, str, int]]  # related series: id, name, stored values


def _reach(session: Session, args: VariableInput, _vocabulary: Vocabulary) -> Reach:
    read = intelligence_service.variable_exposure_read(session, args.variable_key)
    node = session.get(GraphNode, args.variable_key)
    variable_id = args.variable_key.partition(":")[2]
    series = [
        (row.id, row.name, row.observation_count)
        for row in session.scalars(
            select(EconomicSeries)
            .where(func.lower(EconomicSeries.variable_id) == variable_id)
            .order_by(EconomicSeries.name)
        )
    ]
    return Reach(read, node.description if node else "", series)


def _reach_render(
    ctx: RenderContext, args: VariableInput, found: Reach, read_at: datetime
) -> ToolOutput:
    read = found.read
    variable = read.variable
    tool = "get_variable_reach"
    build_id = read.build.id
    record = node_evidence(ctx, tool, variable, read_at, build_id, found.description or None)
    by_channel = Counter(
        channel for reach in read.companies for channel in {path.channel for path in reach.paths}
    )
    by_how = Counter(
        how for reach in read.companies for how in {path.directness for path in reach.paths}
    )
    summary_id = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RECORD,
        title=f"Companies {variable.name} reaches in the knowledge graph",
        detail=data_text(read.note, 400),
        source=SourceRef(
            kind="reach",
            id=variable.key,
            label=f"Reach of {variable.name} (graph build {build_id})",
            link=node_link(variable.key),
        ),
        retrieved_at=read_at,
        as_of=f"graph build {build_id}" if build_id else None,
        values={
            "companies": read.total,
            "listed": len(read.companies),
            **{f"channel.{key}": value for key, value in by_channel.items()},
            **{f"how.{key}": value for key, value in by_how.items()},
        },
    )
    rows: list[TableRow] = []
    names: dict[str, str] = {variable.key: variable.name}
    for reach in read.companies:
        names[reach.company.key] = reach.company.name
        path_names_ = path_names(reach.paths, reach.company)
        names.update(path_names_)
        cited = [
            edge_evidence(ctx, tool, edge, names, read_at, build_id)
            for path in reach.paths[:3]
            for edge in path.edges
        ]
        rows.append(
            TableRow(
                cells={
                    "company": reach.company.name,
                    "channels": ", ".join(sorted({path.channel for path in reach.paths})),
                    "how": ", ".join(
                        sorted({path.directness.replace("_", " ") for path in reach.paths})
                    ),
                    "evidence": ", ".join(
                        sorted(
                            {
                                STATUS_LABEL.get(path.evidence_status, path.evidence_status)
                                for path in reach.paths
                            }
                        )
                    ),
                    "models": ", ".join(sorted({m for path in reach.paths for m in path.models}))
                    or "none",
                },
                link=node_link(reach.company.key),
                citations=list(dict.fromkeys(cited)),
            )
        )
    series_ids = []
    for series_id, name, count in found.series:
        series_ids.append(
            ctx.ledger.add(
                tool=tool,
                call=ctx.call,
                kind=Knowledge.RECORD,
                title=f"{data_text(name, 160)}: a related measure of {variable.name}",
                source=SourceRef(
                    kind="series", id=series_id, label=name, link=series_link(series_id)
                ),
                retrieved_at=read_at,
                values={"stored_values": count},
            )
        )
    display: list[Any] = []
    if rows:
        display.append(
            TableBlock(
                title=f"Companies {variable.name} reaches",
                columns=[
                    Column(key="company", label="Company"),
                    Column(key="channels", label="Channel"),
                    Column(key="how", label="How"),
                    Column(key="evidence", label="Weakest evidence"),
                    Column(key="models", label="Models that can simulate it"),
                ],
                rows=rows,
                total=read.total if read.truncated else None,
                note="Stated exposure: who is reached and through what, never how much.",
                citations=[summary_id],
            )
        )
    return ToolOutput(
        data={
            "variable": {
                "key": variable.key,
                "name": variable.name,
                "evidence": record,
                "unit": variable.attributes.get("unit"),
            },
            "evidence": summary_id,
            "companies_total": read.total,
            "truncated": read.truncated,
            "companies": [
                {
                    "name": row.cells["company"],
                    "channels": row.cells["channels"],
                    "how": row.cells["how"],
                    "weakest_evidence": row.cells["evidence"],
                    "models": row.cells["models"],
                    "evidence": row.citations,
                }
                for row in rows[:40]
            ],
            "related_series": [
                {"series_id": sid, "name": name, "stored_values": count, "evidence": cited}
                for (sid, name, count), cited in zip(found.series, series_ids, strict=True)
            ],
        },
        summary=f"{variable.name} reaches {read.total} companies",
        evidence=[record, summary_id, *series_ids],
        display=display,
        facts=found,
    )


GET_VARIABLE_REACH = Tool(
    name="get_variable_reach",
    description="Which companies one economic variable reaches through validated "
    "knowledge-graph relationships (directly, via their industry, or upstream through "
    "another variable), with the channel, the weakest evidence and the models that can "
    "simulate each; also the stored series recorded as related measures of the variable.",
    input_model=VariableInput,
    fetch=_reach,
    render=_reach_render,
)


# --- find_paths --------------------------------------------------------------------------------


class PathsInput(InputModel):
    from_key: str = Field(pattern=NODE_KEY_PATTERN, max_length=128)
    to_key: str = Field(pattern=NODE_KEY_PATTERN, max_length=128)
    max_depth: int = Field(default=4, ge=1, le=6)


def _paths(session: Session, args: PathsInput, _vocabulary: Vocabulary) -> PathsResponse:
    return graph_service.paths(
        session,
        args.from_key,
        args.to_key,
        max_depth=args.max_depth,
        limit=3,
        direction=Direction.ANY,
        edge_types=(),
        evidence_statuses=(),
        include_illustrative=True,
    )


def _paths_render(
    ctx: RenderContext, args: PathsInput, found: PathsResponse, read_at: datetime
) -> ToolOutput:
    tool = "find_paths"
    names = {node.id: node.name for node in found.nodes}
    kinds = {node.id: str(node.type.value) for node in found.nodes}
    edges = {edge.id: edge for edge in found.edges}
    summary_id = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RECORD,
        title=f"Shortest connections between {found.source.name} and {found.target.name}",
        detail=data_text(found.note, 400),
        source=SourceRef(
            kind="catalogue",
            id=f"paths:{args.from_key}:{args.to_key}",
            label="Graph path search",
            link=f"/graph?from={args.from_key}&to={args.to_key}",
        ),
        retrieved_at=read_at,
        values={"paths": len(found.paths), "hops": found.length},
    )
    items = []
    for path in found.paths:
        cited = []
        for key in path.edges:
            edge = edges[key]
            cited.append(
                ctx.ledger.add(
                    tool=tool,
                    call=ctx.call,
                    kind=Knowledge.RELATIONSHIP,
                    title=f"{names.get(edge.source, edge.source)} — {edge.label} → "
                    f"{names.get(edge.target, edge.target)}",
                    detail=data_text(edge.description, 400),
                    source=SourceRef(
                        kind="graph_edge",
                        id=edge.id,
                        label=edge.label,
                        link=f"/graph?from={edge.source}&to={edge.target}",
                    ),
                    retrieved_at=read_at,
                    evidence_status=str(edge.evidence_status.value),
                )
            )
        items.append(
            PathItem(
                steps=[
                    PathStep(
                        key=key,
                        name=names.get(key, key),
                        kind=kinds.get(key, ""),
                        link=node_link(key),
                    )
                    for key in path.nodes
                ],
                links=[
                    PathLink(
                        key=key,
                        label=edges[key].label,
                        evidence_status=str(edges[key].evidence_status.value),
                        illustrative=edges[key].is_illustrative,
                    )
                    for key in path.edges
                ],
                citations=cited,
            )
        )
    display: list[Block] = (
        [
            PathsBlock(
                title=f"How {found.source.name} and {found.target.name} are connected",
                paths=items,
                total=len(items),
                note="A path shows how records are connected; it is not an influence or causal "
                "chain, and a shorter path is not a stronger relationship.",
                citations=[summary_id],
            )
        ]
        if items
        else []
    )
    return ToolOutput(
        data={
            "evidence": summary_id,
            "found": found.found,
            "hops": found.length,
            "paths": [
                {
                    "nodes": [names.get(key, key) for key in path.nodes],
                    "relationships": [edges[key].label for key in path.edges],
                    "evidence": item.citations,
                }
                for path, item in zip(found.paths, items, strict=True)
            ],
            "budget_exhausted": found.budget_exhausted,
        },
        summary=f"{len(found.paths)} paths of {found.length} hops"
        if found.found
        else "no path found",
        evidence=[summary_id, *(c for item in items for c in item.citations)],
        display=display,
        facts=found,
    )


FIND_PATHS = Tool(
    name="find_paths",
    description="The shortest chains of knowledge-graph relationships between two records "
    "(any kinds), up to 6 hops. A path shows how records are connected; it is not a causal "
    "chain.",
    input_model=PathsInput,
    fetch=_paths,
    render=_paths_render,
)


# --- get_relationship --------------------------------------------------------------------------


class RelationshipInput(InputModel):
    edge_key: str = Field(pattern=EDGE_KEY_PATTERN, max_length=24)


def _relationship(
    session: Session, args: RelationshipInput, _vocabulary: Vocabulary
) -> GraphEdgeDetail:
    return graph_service.get_edge(session, args.edge_key)


def _relationship_render(
    ctx: RenderContext, args: RelationshipInput, edge: GraphEdgeDetail, read_at: datetime
) -> ToolOutput:
    sources = [
        {
            "rule": item.rule,
            "source": f"{item.source_table}/{item.source_record_id}",
            "dataset": f"{item.dataset_id} {item.dataset_version}" if item.dataset_id else None,
            "statement": data_text(item.statement, 300),
            "citation": data_text(item.citation, 200) if item.citation else None,
        }
        for item in edge.evidence[:5]
    ]
    evidence = ctx.ledger.add(
        tool="get_relationship",
        call=ctx.call,
        kind=Knowledge.RELATIONSHIP,
        title=f"{edge.source_node.name} — {edge.label} → {edge.target_node.name}",
        detail=data_text(f"{edge.explanation} What it does not mean: {edge.caveat}", 900),
        source=SourceRef(
            kind="graph_edge",
            id=edge.id,
            label=edge.label,
            link=f"/graph?from={edge.source}&to={edge.target}",
        ),
        retrieved_at=read_at,
        evidence_status=str(edge.evidence_status.value),
        provenance={
            "rule": edge.evidence[0].rule if edge.evidence else None,
            "dataset": edge.evidence[0].dataset_id if edge.evidence else None,
            "dataset_version": edge.evidence[0].dataset_version if edge.evidence else None,
            "citation": data_text(edge.evidence[0].citation, 200)
            if edge.evidence and edge.evidence[0].citation
            else None,
        },
    )
    return ToolOutput(
        data={
            "evidence": evidence,
            "relationship": f"{edge.source_node.name} {edge.label} {edge.target_node.name}",
            "evidence_status": edge.evidence_status_label,
            "illustrative": edge.is_illustrative,
            "polarity": edge.qualifiers.polarity,
            "strength": edge.qualifiers.strength,
            "rationale": data_text(edge.qualifiers.rationale, 400)
            if edge.qualifiers.rationale
            else None,
            "caveat": data_text(edge.caveat, 300),
            "sources": sources,
        },
        summary=f"{edge.label} ({edge.evidence_status_label})",
        evidence=[evidence],
        facts=edge,
    )


GET_RELATIONSHIP = Tool(
    name="get_relationship",
    description="One knowledge-graph relationship by its key: what it states, the source "
    "records and rule that built it, its evidence status and what it does not mean.",
    input_model=RelationshipInput,
    fetch=_relationship,
    render=_relationship_render,
    timeout_seconds=4,
)


# --- list_models -------------------------------------------------------------------------------


class NoInput(InputModel):
    pass


@dataclass
class ModelFacts:
    models: list[SimulationModelSummary]
    responds_to: dict[str, list[str]]


def _models(session: Session, _args: NoInput, vocabulary: Vocabulary) -> ModelFacts:
    from app.scenario_lab.profiles import PROFILES

    responds: dict[str, list[str]] = {}
    for model_id, profile in PROFILES.items():
        labels = []
        for variable_id in sorted({binding.variable_id for binding in profile.shocks}):
            term = vocabulary.by_record(variable_id)
            labels.append(term.label if term is not None else variable_id)
        responds[model_id] = labels
    return ModelFacts(simulation_service.list_models(session), responds)


def _models_render(
    ctx: RenderContext, _args: NoInput, found: ModelFacts, read_at: datetime
) -> ToolOutput:
    rows = []
    ids = []
    summary = ctx.ledger.add(
        tool="list_models",
        call=ctx.call,
        kind=Knowledge.RECORD,
        title="Registered simulation models",
        source=SourceRef(kind="catalogue", id="models", label="Model registry", link="/simulation"),
        retrieved_at=read_at,
        values={"models": len(found.models)},
    )
    for model in found.models:
        evidence = ctx.ledger.add(
            tool="list_models",
            call=ctx.call,
            kind=Knowledge.RECORD,
            title=f"Model {model.name} {model.version}",
            detail=data_text(model.summary, 400),
            source=SourceRef(
                kind="model", id=model.id, label=model.name, link=model_link(model.id)
            ),
            retrieved_at=read_at,
            provenance={"status": model.status, "definition_hash": model.definition_hash},
            values={"runs": model.runs},
        )
        ids.append(evidence)
        rows.append(
            TableRow(
                cells={
                    "model": model.name,
                    "version": model.version,
                    "responds_to": ", ".join(found.responds_to.get(model.id, [])) or "—",
                    "status": model.status,
                    "runs": str(model.runs),
                },
                link=model_link(model.id),
                citations=[evidence],
            )
        )
    return ToolOutput(
        data={
            "evidence": summary,
            "models": [
                {
                    "id": m.id,
                    "version": m.version,
                    "name": m.name,
                    "summary": data_text(m.summary, 300),
                    "status": m.status,
                    "runs": m.runs,
                    "responds_to": found.responds_to.get(m.id, []),
                    "evidence": cited,
                }
                for m, cited in zip(found.models, ids, strict=True)
            ],
        },
        summary=f"{len(found.models)} registered models",
        evidence=[summary, *ids],
        display=[
            TableBlock(
                title="Registered simulation models",
                columns=[
                    Column(key="model", label="Model"),
                    Column(key="version", label="Version"),
                    Column(key="responds_to", label="Responds to"),
                    Column(key="status", label="Status"),
                    Column(key="runs", label="Stored runs", align="end"),
                ],
                rows=rows,
            )
        ],
        facts=found,
    )


LIST_MODELS = Tool(
    name="list_models",
    description="The registered simulation models: what each covers, its version and status, "
    "the variables it responds to and how many runs are stored.",
    input_model=NoInput,
    fetch=_models,
    render=_models_render,
    timeout_seconds=4,
)


# --- list_templates ----------------------------------------------------------------------------


def _templates(session: Session, _args: NoInput, _vocabulary: Vocabulary) -> TemplateList:
    return lab_service.list_templates(session)


def _templates_render(
    ctx: RenderContext, _args: NoInput, found: TemplateList, read_at: datetime
) -> ToolOutput:
    rows = []
    ids = []
    summary = ctx.ledger.add(
        tool="list_templates",
        call=ctx.call,
        kind=Knowledge.RECORD,
        title="Scenario Lab templates",
        source=SourceRef(
            kind="catalogue", id="templates", label="Scenario Lab", link="/scenarios/new"
        ),
        retrieved_at=read_at,
        values={"templates": len(found.items), "unavailable": len(found.unsupported)},
    )
    for template in found.items:
        evidence = ctx.ledger.add(
            tool="list_templates",
            call=ctx.call,
            kind=Knowledge.RECORD,
            title=f"Template: {template.title}",
            detail=data_text(template.question, 300),
            source=SourceRef(
                kind="template",
                id=template.id,
                label=template.title,
                link=template_link(template.id),
            ),
            retrieved_at=read_at,
            values={f"change.{c.variable_id}": c.value for c in template.changes},
        )
        ids.append(evidence)
        rows.append(
            TableRow(
                cells={
                    "template": template.title,
                    "question": template.question,
                    "models": ", ".join(m.title for m in template.models),
                    "companies": ", ".join(e.name for e in template.suggested_entities[:4]) or "—",
                },
                link=template_link(template.id),
                citations=[evidence],
            )
        )
    return ToolOutput(
        data={
            "evidence": summary,
            "templates": [
                {
                    "id": t.id,
                    "title": t.title,
                    "question": t.question,
                    "changes": [
                        {
                            "variable_id": c.variable_id,
                            "type": c.change_type,
                            "value": exact(c.value),
                        }
                        for c in t.changes
                    ],
                    "models": [m.model_id for m in t.models],
                    "suggested_companies": [e.name for e in t.suggested_entities[:6]],
                    "evidence": cited,
                }
                for t, cited in zip(found.items, ids, strict=True)
            ],
            "unavailable": [
                {"title": u.title, "reason": data_text(u.reason, 200)} for u in found.unsupported
            ],
        },
        summary=f"{len(found.items)} templates",
        evidence=[summary, *ids],
        display=[
            TableBlock(
                title="Scenario Lab templates",
                columns=[
                    Column(key="template", label="Template"),
                    Column(key="question", label="Question it answers"),
                    Column(key="models", label="Models"),
                    Column(key="companies", label="Companies the graph suggests"),
                ],
                rows=rows,
                note="Templates carry no company figures: a person enters those in the Lab.",
            )
        ],
        facts=found,
    )


LIST_TEMPLATES = Tool(
    name="list_templates",
    description="The Scenario Lab's ready-made templates: the changes each applies, the "
    "models it uses and the companies the knowledge graph suggests for it; also the kinds "
    "of scenario no model supports yet.",
    input_model=NoInput,
    fetch=_templates,
    render=_templates_render,
    timeout_seconds=6,
)


# --- get_data_coverage -------------------------------------------------------------------------


@dataclass
class SeriesRow:
    id: str
    name: str
    frequency: str
    count: int
    first: str | None
    last: str | None
    dataset: str
    illustrative: bool


@dataclass
class Coverage:
    series: list[SeriesRow]
    instruments: list[tuple[str, str, int]]
    datasets: list[tuple[str, str, str, bool, str]]
    graph: tuple[int | None, str, str | None]
    scenarios: int
    executions: int


def _coverage(session: Session, _args: NoInput, _vocabulary: Vocabulary) -> Coverage:
    datasets = {row.id: row for row in session.scalars(select(Dataset))}
    series = [
        SeriesRow(
            id=row.id,
            name=row.name,
            frequency=str(row.frequency.value),
            count=row.observation_count,
            first=row.first_period.isoformat() if row.first_period else None,
            last=row.last_period.isoformat() if row.last_period else None,
            dataset=row.dataset_id,
            illustrative=datasets[row.dataset_id].is_illustrative
            if row.dataset_id in datasets
            else False,
        )
        for row in session.scalars(select(EconomicSeries).order_by(EconomicSeries.name))
    ]
    instruments = [
        (row.id, row.name, row.bar_count)
        for row in session.scalars(select(Instrument).order_by(Instrument.name))
    ]
    info = build_info(session)
    return Coverage(
        series=series,
        instruments=instruments,
        datasets=[
            (row.id, row.name, row.version, row.is_illustrative, row.license)
            for row in datasets.values()
        ],
        graph=(info.id, info.freshness, info.finished_at.isoformat() if info.finished_at else None),
        scenarios=int(session.scalar(select(func.count()).select_from(Scenario)) or 0),
        executions=int(session.scalar(select(func.count()).select_from(ScenarioExecution)) or 0),
    )


def _coverage_render(
    ctx: RenderContext, _args: NoInput, found: Coverage, read_at: datetime
) -> ToolOutput:
    with_data = [row for row in found.series if row.count > 0]
    build_id, freshness, finished = found.graph
    summary = ctx.ledger.add(
        tool="get_data_coverage",
        call=ctx.call,
        kind=Knowledge.RECORD,
        title="What RUMIN holds",
        detail="Counts of stored records. RUMIN holds stored values, not live data.",
        source=SourceRef(kind="catalogue", id="coverage", label="RUMIN's catalogue", link="/data"),
        retrieved_at=read_at,
        as_of=finished,
        provenance={
            "graph_build": str(build_id) if build_id else None,
            "graph_freshness": freshness,
        },
        values={
            "series": len(found.series),
            "series_with_data": len(with_data),
            "observations": sum(row.count for row in found.series),
            "instruments": len(found.instruments),
            "instruments_with_data": sum(1 for _, _, bars in found.instruments if bars),
            "datasets": len(found.datasets),
            "scenarios": found.scenarios,
            "executions": found.executions,
        },
    )
    rows = []
    ids = []
    for row in found.series:
        evidence = ctx.ledger.add(
            tool="get_data_coverage",
            call=ctx.call,
            kind=Knowledge.RECORD,
            title=f"{data_text(row.name, 160)}: stored values",
            source=SourceRef(kind="series", id=row.id, label=row.name, link=series_link(row.id)),
            retrieved_at=read_at,
            period=f"{row.first[:4]}–{row.last[:4]}" if row.first and row.last else None,
            provenance={
                "dataset": row.dataset,
                "illustrative": "yes" if row.illustrative else None,
            },
            values={"stored_values": row.count},
        )
        ids.append(evidence)
        rows.append(
            TableRow(
                cells={
                    "series": row.name,
                    "frequency": row.frequency,
                    "values": str(row.count),
                    "first": row.first[:4] if row.first else "—",
                    "last": row.last[:4] if row.last else "—",
                },
                link=series_link(row.id),
                citations=[evidence],
            )
        )
    return ToolOutput(
        data={
            "evidence": summary,
            "series": [
                {
                    "series_id": r.id,
                    "name": r.name,
                    "frequency": r.frequency,
                    "stored_values": r.count,
                    "first": r.first,
                    "last": r.last,
                    "evidence": cited,
                }
                for r, cited in zip(found.series, ids, strict=True)
            ],
            "instruments": [{"id": i, "name": n, "price_bars": b} for i, n, b in found.instruments],
            "datasets": [
                {"id": d[0], "name": d[1], "version": d[2], "illustrative": d[3], "licence": d[4]}
                for d in found.datasets
            ],
            "graph": {"build": build_id, "freshness": freshness, "finished_at": finished},
            "scenarios": found.scenarios,
            "executions": found.executions,
        },
        summary=f"{len(with_data)} of {len(found.series)} series hold values",
        evidence=[summary, *ids],
        display=[
            TableBlock(
                title="Stored series",
                columns=[
                    Column(key="series", label="Series"),
                    Column(key="frequency", label="Frequency"),
                    Column(key="values", label="Values", align="end"),
                    Column(key="first", label="First", align="end"),
                    Column(key="last", label="Last", align="end"),
                ],
                rows=rows,
                citations=[summary],
            )
        ]
        if rows
        else [],
        facts=found,
    )


GET_DATA_COVERAGE = Tool(
    name="get_data_coverage",
    description="What data RUMIN holds: every catalogued series with how many values are "
    "stored and for which periods, instruments, datasets with their licences, the knowledge "
    "graph's build and freshness, and how many scenarios and executions are stored.",
    input_model=NoInput,
    fetch=_coverage,
    render=_coverage_render,
    timeout_seconds=4,
)
