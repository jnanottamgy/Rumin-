"""Tools over stored data and findings: a series' stored values, the exact change between two
stored periods, what changed, and Financial Intelligence findings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from app.analyst.answer import Block, Column, SeriesBlock, SeriesPoint, TableBlock, TableRow
from app.analyst.evidence import Knowledge, SourceRef, exact, node_link, series_link
from app.analyst.policy import data_text
from app.analyst.tools.common import THRESHOLDS, counted
from app.analyst.tools.registry import RenderContext, Tool, ToolOutput, ToolProblem
from app.analyst.vocabulary import Vocabulary
from app.intelligence import fmt, stats
from app.intelligence.series import History, Point, load_series
from app.schemas.common import InputModel
from app.schemas.data import SeriesDetail
from app.schemas.intelligence import ChangesRead, InsightListRead, SeriesIntelligenceRead
from app.services import data as data_service
from app.services import intelligence as intelligence_service

SERIES_ID = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,95}$", max_length=96)
MAX_POINTS_SHOWN = 80


def _provenance(detail: SeriesDetail | None, history: History) -> dict[str, str | None]:
    dataset = history.subject.dataset
    return {
        "dataset": dataset.name,
        "dataset_version": dataset.version,
        "licence": dataset.license,
        "attribution": dataset.attribution,
        "provider": detail.provider_name if detail else None,
        "illustrative": "yes" if dataset.is_illustrative else None,
        "variable_relation": data_text(history.subject.variable_relation, 300)
        if history.subject.variable_relation
        else None,
    }


# --- get_series --------------------------------------------------------------------------------


class SeriesInput(InputModel):
    series_id: str = SERIES_ID
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_year: int | None = Field(default=None, ge=1900, le=2100)
    last: int | None = Field(default=None, ge=1, le=200, description="Only the last N values.")


@dataclass
class SeriesFacts:
    history: History
    analysis: SeriesIntelligenceRead
    detail: SeriesDetail


def _series(session: Session, args: SeriesInput, _vocabulary: Vocabulary) -> SeriesFacts:
    history = load_series(session, args.series_id)
    if history is None:
        raise ToolProblem(f"RUMIN has no series '{args.series_id}'.", status="not_found")
    analysis = intelligence_service.series_read(session, args.series_id, THRESHOLDS)
    detail = data_service.get_series(session, args.series_id)
    return SeriesFacts(history, analysis, detail)


def in_range(points: tuple[Point, ...], args: SeriesInput) -> list[Point]:
    chosen = [
        point
        for point in points
        if (args.start_year is None or point.start.year >= args.start_year)
        and (args.end_year is None or point.start.year <= args.end_year)
    ]
    if args.last is not None:
        chosen = chosen[-args.last :]
    return chosen[-MAX_POINTS_SHOWN:]


def _series_render(
    ctx: RenderContext, args: SeriesInput, found: SeriesFacts, read_at: datetime
) -> ToolOutput:
    history = found.history
    subject = history.subject
    analysis = found.analysis.analysis
    points = in_range(history.points, args)
    tool = "get_series"
    if not history.points:
        evidence = ctx.ledger.add(
            tool=tool,
            call=ctx.call,
            kind=Knowledge.RECORD,
            title=f"{data_text(subject.name, 160)}: no stored values",
            detail="The series is catalogued, but no values are stored for it yet.",
            source=SourceRef(
                kind="series", id=subject.id, label=subject.name, link=series_link(subject.id)
            ),
            retrieved_at=read_at,
            unit=subject.unit,
            provenance=_provenance(found.detail, history),
            values={"stored_values": 0},
        )
        return ToolOutput(
            data={
                "series_id": subject.id,
                "name": subject.name,
                "stored_values": 0,
                "evidence": evidence,
            },
            summary="no stored values",
            evidence=[evidence],
            facts=found,
        )
    values: dict[str, Any] = {point.label: point.value for point in points}
    shown = points or list(history.points[-1:])
    lowest = min(shown, key=lambda point: point.value)
    highest = max(shown, key=lambda point: point.value)
    first_point, last_point = history.points[0], history.points[-1]
    values.update(
        {
            "count": len(history.points),
            "shown": len(shown),
            "min": lowest.value,
            "max": highest.value,
            f"first.{first_point.label}": first_point.value,
            f"latest.{last_point.label}": last_point.value,
        }
    )
    latest = analysis.latest
    if latest is not None:
        values["latest_change"] = latest.value
        values["latest_change.earlier"] = latest.earlier.value
        values["latest_change.later"] = latest.later.value
    trend = analysis.trend
    if trend is not None:
        values["trend.slope"] = trend.slope
        values["trend.values"] = trend.n
        values["trend.significance"] = trend.significance
        if trend.relative_slope is not None:
            values["trend.relative_slope"] = trend.relative_slope
    if analysis.volatility is not None:
        values["volatility.latest"] = analysis.volatility.latest
    notes = []
    if trend is not None:
        notes.append(
            f"Trend over the last {trend.n} values ({trend.first}–{trend.last}): "
            f"{trend.direction.replace('_', ' ')} (significance {trend.significance})."
        )
    if analysis.volatility is not None:
        notes.append(f"Volatility: {analysis.volatility.level.replace('_', ' ')}.")
    if analysis.anomaly is not None:
        notes.append(f"Latest change: {analysis.anomaly.level.replace('_', ' ')}.")
    first, last = history.points[0], history.points[-1]
    evidence = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.OBSERVED,
        title=f"{data_text(subject.name, 160)}: stored values",
        detail=" ".join(notes) or None,
        source=SourceRef(
            kind="series", id=subject.id, label=subject.name, link=series_link(subject.id)
        ),
        retrieved_at=read_at,
        period=f"{shown[0].label}–{shown[-1].label}",
        as_of=last.label,
        unit=subject.unit,
        provenance={
            **_provenance(found.detail, history),
            "retrieved_from_provider": last.retrieved_at.isoformat(),
            "last_confirmed": last.last_confirmed_at.isoformat(),
        },
        values=values,
    )
    ids = [evidence]
    revisions = analysis.revisions[:5]
    if revisions:
        ids.append(
            ctx.ledger.add(
                tool=tool,
                call=ctx.call,
                kind=Knowledge.OBSERVED,
                title=f"Revisions of {data_text(subject.name, 160)}",
                detail="Values the provider changed after they were first stored; both are kept.",
                source=SourceRef(
                    kind="series", id=subject.id, label=subject.name, link=series_link(subject.id)
                ),
                retrieved_at=read_at,
                period="revisions",
                unit=subject.unit,
                values={
                    **{f"{item.label}.previous": item.previous for item in revisions},
                    **{f"{item.label}.revised": item.revised for item in revisions},
                    **{f"{item.label}.change": item.change for item in revisions},
                },
            )
        )
    block = SeriesBlock(
        title=subject.name,
        series_id=subject.id,
        unit=subject.unit,
        frequency=subject.frequency,
        points=[
            SeriesPoint(
                period=point.label, start=point.start.isoformat(), value=exact(point.value) or "0"
            )
            for point in shown
        ],
        highlight=[shown[-1].label],
        link=series_link(subject.id),
        note=data_text(subject.variable_relation, 300) if subject.variable_relation else None,
        citations=[evidence],
    )
    return ToolOutput(
        data={
            "series_id": subject.id,
            "name": subject.name,
            "unit": subject.unit,
            "frequency": subject.frequency,
            "evidence": ids,
            "stored_values": len(history.points),
            "first": {"period": first.label, "value": exact(first.value)},
            "latest": {"period": last.label, "value": exact(last.value)},
            "shown": [{"period": p.label, "value": exact(p.value)} for p in shown[-40:]],
            "latest_change": {
                "from": latest.earlier.label,
                "to": latest.later.label,
                "value": exact(latest.value),
                "unit": subject.change_unit,
            }
            if latest
            else None,
            "trend": notes[0] if trend is not None else None,
            "revisions": len(analysis.revisions),
            "dataset": subject.dataset.name,
            "illustrative": subject.dataset.is_illustrative,
            "relation_to_variable": data_text(subject.variable_relation, 300)
            if subject.variable_relation
            else None,
        },
        summary=f"{len(shown)} of {counted(len(history.points), 'value')}, "
        f"{shown[0].label}–{shown[-1].label}",
        evidence=ids,
        display=[block],
        facts=found,
    )


GET_SERIES = Tool(
    name="get_series",
    description="A stored data series: its values (optionally a year range or the last N), "
    "unit, frequency, dataset, licence and provider, when it was retrieved, its latest "
    "change, trend, volatility and revisions. Values are stored observations, not live data.",
    input_model=SeriesInput,
    fetch=_series,
    render=_series_render,
)


# --- compare_periods ---------------------------------------------------------------------------


class CompareInput(InputModel):
    series_id: str = SERIES_ID
    from_period: str = Field(pattern=r"^\d{4}(-\d{2}){0,2}$", description="e.g. 2020")
    to_period: str = Field(pattern=r"^\d{4}(-\d{2}){0,2}$", description="e.g. 2025")

    @model_validator(mode="after")
    def _different(self) -> CompareInput:
        if self.from_period == self.to_period:
            raise ValueError("from_period and to_period must differ.")
        return self


@dataclass
class Comparison:
    history: History
    earlier: Point
    later: Point
    change: Decimal | None  # percent or percentage points
    difference: Decimal


def _compare(session: Session, args: CompareInput, _vocabulary: Vocabulary) -> Comparison:
    history = load_series(session, args.series_id)
    if history is None:
        raise ToolProblem(f"RUMIN has no series '{args.series_id}'.", status="not_found")
    by_label = {point.label: point for point in history.points}
    missing = [label for label in (args.from_period, args.to_period) if label not in by_label]
    if missing:
        stored = (
            f"stored values run from {history.points[0].label} to {history.points[-1].label}"
            if history.points
            else "no values are stored"
        )
        raise ToolProblem(
            f"No stored value of {history.subject.name} for {', '.join(missing)}; {stored}.",
            status="not_found",
        )
    earlier, later = sorted(
        (by_label[args.from_period], by_label[args.to_period]), key=lambda point: point.start
    )
    if history.subject.measure == "relative":
        change = stats.relative_change(earlier.value, later.value)
    else:
        change = stats.point_change(earlier.value, later.value)
    return Comparison(
        history, earlier, later, change, stats.point_change(earlier.value, later.value)
    )


def _compare_render(
    ctx: RenderContext, args: CompareInput, found: Comparison, read_at: datetime
) -> ToolOutput:
    subject = found.history.subject
    unit = "percent" if subject.measure == "relative" else "percentage points"
    values: dict[str, Any] = {
        found.earlier.label: found.earlier.value,
        found.later.label: found.later.value,
        "difference": found.difference,
    }
    if found.change is not None:
        values["change"] = found.change
    period = f"{found.earlier.label}–{found.later.label}"
    method = (
        "the difference as a percentage of the earlier value"
        if subject.measure == "relative"
        else "the difference, in percentage points"
    )
    evidence = ctx.ledger.add(
        tool="compare_periods",
        call=ctx.call,
        kind=Knowledge.OBSERVED,
        title=f"{data_text(subject.name, 160)}: {period}",
        detail=f"Exact change between two stored values: {method}. Computed by RUMIN in exact "
        "decimals.",
        source=SourceRef(
            kind="series", id=subject.id, label=subject.name, link=series_link(subject.id)
        ),
        retrieved_at=read_at,
        period=period,
        as_of=found.later.label,
        unit=subject.unit,
        provenance={
            "observations": f"{found.earlier.record_id}, {found.later.record_id}",
            "dataset": subject.dataset.name,
            "dataset_version": subject.dataset.version,
            "licence": subject.dataset.license,
            "illustrative": "yes" if subject.dataset.is_illustrative else None,
        },
        values=values,
    )
    display: list[Block] = [
        TableBlock(
            title=f"{subject.name}: {period}",
            columns=[
                Column(key="period", label="Period"),
                Column(key="value", label=f"Value ({subject.unit})", align="end"),
            ],
            rows=[
                TableRow(
                    cells={"period": found.earlier.label, "value": exact(found.earlier.value)},
                    citations=[evidence],
                ),
                TableRow(
                    cells={"period": found.later.label, "value": exact(found.later.value)},
                    citations=[evidence],
                ),
            ],
            note=f"Change: {exact(found.change) if found.change is not None else 'undefined'} "
            f"{unit}.",
            citations=[evidence],
        )
    ]
    return ToolOutput(
        data={
            "evidence": evidence,
            "series": subject.name,
            "unit": subject.unit,
            "earlier": {"period": found.earlier.label, "value": exact(found.earlier.value)},
            "later": {"period": found.later.label, "value": exact(found.later.value)},
            "difference": exact(found.difference),
            "change": exact(found.change),
            "change_unit": unit,
            "method": method,
        },
        summary=f"{found.earlier.label} → {found.later.label}: "
        f"{fmt.number(found.change) if found.change is not None else 'undefined'} {unit}",
        evidence=[evidence],
        display=display,
        facts=found,
    )


COMPARE_PERIODS = Tool(
    name="compare_periods",
    description="The exact change of a stored series between two stored periods (percent "
    "for levels, prices and exchange rates; percentage points for series already in percent), "
    "computed in exact decimals, with the two observations it rests on.",
    input_model=CompareInput,
    fetch=_compare,
    render=_compare_render,
    timeout_seconds=4,
)


# --- list_changes ------------------------------------------------------------------------------


class NoInput(InputModel):
    pass


def _changes(session: Session, _args: NoInput, _vocabulary: Vocabulary) -> ChangesRead:
    return intelligence_service.changes(session, THRESHOLDS)


def _changes_render(
    ctx: RenderContext, _args: NoInput, found: ChangesRead, read_at: datetime
) -> ToolOutput:
    tool = "list_changes"
    rows: list[TableRow] = []
    ids: list[str] = []
    totals = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RECORD,
        title="What changed: totals",
        detail="Observed changes that meet the default thresholds, revised values, and "
        "headline changes between two executions of the same scenario.",
        source=SourceRef(
            kind="catalogue", id="changes", label="Financial Intelligence", link="/intelligence"
        ),
        retrieved_at=read_at,
        values={
            "observed": len(found.observed),
            "revisions": len(found.revisions),
            "executions": len(found.executions),
        },
    )
    ids.append(totals)
    observed: list[dict[str, Any]] = []
    for item in found.observed[:10]:
        change = item.change
        unit = "%" if item.subject.change_unit == "percent" else "pp"
        cited = ctx.ledger.add(
            tool=tool,
            call=ctx.call,
            kind=Knowledge.OBSERVED,
            title=f"{data_text(item.subject.name, 160)}: {change.earlier.label}–"
            f"{change.later.label}",
            detail=f"A change that meets the threshold ({item.threshold_name} "
            f"{exact(item.threshold)}).",
            source=SourceRef(
                kind=item.subject.kind,
                id=item.subject.id,
                label=item.subject.name,
                link=series_link(item.subject.id) if item.subject.kind == "series" else None,
            ),
            retrieved_at=read_at,
            period=f"{change.earlier.label}–{change.later.label}",
            unit=item.subject.unit,
            values={
                change.earlier.label: change.earlier.value,
                change.later.label: change.later.value,
                "change": change.value,
            },
        )
        ids.append(cited)
        observed.append(
            {
                "what": item.subject.name,
                "from": change.earlier.label,
                "to": change.later.label,
                "change": exact(change.value),
                "unit": item.subject.change_unit,
                "evidence": [cited],
            }
        )
        rows.append(
            TableRow(
                cells={
                    "what": item.subject.name,
                    "kind": "Observed",
                    "period": f"{change.earlier.label}–{change.later.label}",
                    "change": f"{fmt.signed(change.value)} {unit}",
                },
                link=series_link(item.subject.id) if item.subject.kind == "series" else None,
                citations=[cited],
            )
        )
    for revised in found.revisions[:5]:
        revision = revised.revision
        cited = ctx.ledger.add(
            tool=tool,
            call=ctx.call,
            kind=Knowledge.OBSERVED,
            title=f"Revision of {data_text(revised.subject.name, 160)} for {revision.label}",
            source=SourceRef(
                kind=revised.subject.kind,
                id=revised.subject.id,
                label=revised.subject.name,
                link=series_link(revised.subject.id),
            ),
            retrieved_at=read_at,
            period=revision.label,
            unit=revised.subject.unit,
            values={
                "previous": revision.previous,
                "revised": revision.revised,
                "change": revision.change,
            },
        )
        ids.append(cited)
        rows.append(
            TableRow(
                cells={
                    "what": revised.subject.name,
                    "kind": "Revision",
                    "period": revision.label,
                    "change": f"{exact(revision.previous)} → {exact(revision.revised)}",
                },
                link=series_link(revised.subject.id),
                citations=[cited],
            )
        )
    relationships = found.relationships
    relationship_id = ctx.ledger.add(
        tool=tool,
        call=ctx.call,
        kind=Knowledge.RECORD,
        title="Relationship changes between the last two graph builds",
        detail=data_text(relationships.note, 300),
        source=SourceRef(
            kind="graph_build",
            id=str(relationships.build.id if relationships.build else "none"),
            label="Knowledge graph",
            link="/graph",
        ),
        retrieved_at=read_at,
        values={f"relationships.{key}": value for key, value in relationships.counts.items()},
    )
    ids.append(relationship_id)
    for executed in found.executions[:6]:
        cited = ctx.ledger.add(
            tool=tool,
            call=ctx.call,
            kind=Knowledge.SIMULATED,
            title=f"{executed.entity.name}: {executed.label} between two executions of "
            f"'{data_text(executed.latest.scenario_name, 120)}'",
            detail="Simulated results, not observations; each holds only under its scenario's "
            "inputs and assumptions.",
            source=SourceRef(
                kind="execution",
                id=executed.latest.id,
                label=executed.latest.scenario_name,
                link=f"/scenarios/{executed.latest.scenario_id}?execution={executed.latest.id}",
            ),
            retrieved_at=read_at,
            currency=executed.currency,
            values={
                "previous_change": executed.previous_change,
                "latest_change": executed.latest_change,
                "difference": executed.difference,
            },
        )
        ids.append(cited)
        rows.append(
            TableRow(
                cells={
                    "what": f"{executed.entity.name}: {executed.label}",
                    "kind": "Simulated",
                    "period": f"v{executed.previous.version} → v{executed.latest.version}",
                    "change": f"{exact(executed.difference)} {executed.currency}",
                },
                link=node_link(executed.entity.key),
                citations=[cited],
            )
        )
    display: list[Block] = []
    if rows:
        display.append(
            TableBlock(
                title="What changed",
                columns=[
                    Column(key="what", label="What"),
                    Column(key="kind", label="Kind"),
                    Column(key="period", label="Between"),
                    Column(key="change", label="Change", align="end"),
                ],
                rows=rows,
                note="Observed changes meet the default thresholds; simulated changes are "
                "between two executions of the same scenario.",
            )
        )
    return ToolOutput(
        data={
            "observed": observed,
            "revisions": [
                row.cells | {"evidence": row.citations}
                for row in rows
                if row.cells["kind"] == "Revision"
            ],
            "relationships": {"evidence": relationship_id, **relationships.counts},
            "executions": [
                row.cells | {"evidence": row.citations}
                for row in rows
                if row.cells["kind"] == "Simulated"
            ],
            "totals": {
                "evidence": totals,
                "observed": len(found.observed),
                "revisions": len(found.revisions),
                "executions": len(found.executions),
            },
            "notes": [data_text(note, 300) for note in found.notes],
        },
        summary=f"{len(found.observed)} observed, {counted(len(found.revisions), 'revision')}, "
        f"{len(found.executions)} simulated",
        evidence=ids,
        display=display,
        facts=found,
    )


LIST_CHANGES = Tool(
    name="list_changes",
    description="What changed in RUMIN: stored values whose latest change meets the default "
    "thresholds (observed), revised values, relationships added or retired between graph "
    "builds, and headline changes between two executions of the same scenario (simulated).",
    input_model=NoInput,
    fetch=_changes,
    render=_changes_render,
    timeout_seconds=10,
)


# --- get_findings ------------------------------------------------------------------------------


class FindingsInput(InputModel):
    entity_key: str | None = Field(
        default=None, pattern=r"^(company|industry):[a-z0-9][a-z0-9_.-]{0,95}$", max_length=128
    )
    kind: str | None = Field(default=None, pattern=r"^[a-z_]{2,40}$")
    limit: int = Field(default=8, ge=1, le=20)


def _findings(session: Session, args: FindingsInput, _vocabulary: Vocabulary) -> InsightListRead:
    return intelligence_service.insight_list(
        session, THRESHOLDS, entity=args.entity_key, kind=args.kind, rule=None, grade=None
    )


def _findings_render(
    ctx: RenderContext, args: FindingsInput, found: InsightListRead, read_at: datetime
) -> ToolOutput:
    rows = []
    ids = []
    link = node_link(args.entity_key) if args.entity_key else "/intelligence"
    where = f" for {found.subject.label}" if found.subject else " across the workspace"
    summary = ctx.ledger.add(
        tool="get_findings",
        call=ctx.call,
        kind=Knowledge.RECORD,
        title=f"Financial Intelligence findings{where}",
        detail="How many findings the documented rules produce now, at the default thresholds.",
        source=SourceRef(
            kind="catalogue",
            id=f"findings:{args.entity_key or 'workspace'}",
            label="Financial Intelligence",
            link=link,
        ),
        retrieved_at=read_at,
        values={"findings": found.total},
    )
    for insight in found.items[: args.limit]:
        cited = ctx.ledger.add(
            tool="get_findings",
            call=ctx.call,
            kind=Knowledge.FINDING,
            title=data_text(insight.headline, 200),
            detail=data_text(insight.statement, 600),
            source=SourceRef(kind="insight", id=insight.id, label=insight.rule_title, link=link),
            retrieved_at=read_at,
            period=insight.period.label,
            grade=insight.evidence.grade,
            models=[model for ref in insight.models for model in ref.models],
            assumptions=[data_text(item, 200) for item in insight.assumptions[:4]],
            values={
                fact.label: fact.value
                for fact in insight.facts
                if fact.value is not None and _number(fact.value)
            },
        )
        ids.append(cited)
        rows.append(
            TableRow(
                cells={
                    "finding": insight.headline,
                    "kind": insight.kind.replace("_", " "),
                    "grade": insight.evidence.grade,
                    "simulated": "yes" if insight.evidence.conditional_on_simulation else "no",
                },
                link=link,
                citations=[cited],
            )
        )
    display: list[Block] = []
    if rows:
        display.append(
            TableBlock(
                title="Findings" + (f" for {found.subject.label}" if found.subject else ""),
                columns=[
                    Column(key="finding", label="Finding"),
                    Column(key="kind", label="Kind"),
                    Column(key="grade", label="Evidence grade"),
                    Column(key="simulated", label="Rests on a simulation"),
                ],
                rows=rows,
                total=found.total if found.total > len(rows) else None,
                note="Each grade is the weakest step of the finding's evidence chain; it is not "
                "a probability.",
            )
        )
    return ToolOutput(
        data={
            "evidence": summary,
            "scope": found.scope,
            "subject": found.subject.label if found.subject else None,
            "total": found.total,
            "findings": [
                {
                    "evidence": cited,
                    "headline": insight.headline,
                    "statement": data_text(insight.statement, 400),
                    "kind": insight.kind,
                    "grade": insight.evidence.grade,
                    "conditional_on_simulation": insight.evidence.conditional_on_simulation,
                    "limitations": [data_text(item, 200) for item in insight.limitations[:3]],
                }
                for cited, insight in zip(ids, found.items, strict=False)
            ],
        },
        summary=counted(found.total, "finding"),
        evidence=[summary, *ids],
        display=display,
        facts=found,
    )


def _number(value: str) -> bool:
    try:
        Decimal(value.replace(",", ""))
    except ArithmeticError:
        return False
    return True


GET_FINDINGS = Tool(
    name="get_findings",
    description="Financial Intelligence findings for the whole workspace or one company or "
    "industry: each with its headline, statement, kind, evidence grade (the weakest step of "
    "its chain, not a probability), whether it rests on a simulation, and its limitations.",
    input_model=FindingsInput,
    fetch=_findings,
    render=_findings_render,
    timeout_seconds=10,
)
