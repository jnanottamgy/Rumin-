"""Tools over scenarios: stored scenarios, a stored execution's results and drivers, why a
line of it changed, and a **preview** of a what-if — computed by the registered models on
request and never stored. A preview reuses the figures a person entered in a stored
scenario for the same company (labelled as theirs); without them it returns the plan: which
models apply and which figures are missing. RUMIN never fills in company figures."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analyst.answer import (
    Block,
    Column,
    EntityRef,
    ScenarioBlock,
    ScenarioChange,
    ScenarioLine,
    TableBlock,
    TableRow,
)
from app.analyst.evidence import Knowledge, SourceRef, exact, node_link, scenario_link
from app.analyst.policy import data_text
from app.analyst.tools.records import simulation_block
from app.analyst.tools.registry import RenderContext, Tool, ToolOutput, ToolProblem
from app.analyst.vocabulary import Vocabulary
from app.domain.enums import ScenarioExecutionStatus
from app.intelligence import serialize
from app.intelligence.drivers import analyse as analyse_drivers
from app.intelligence.drivers import executions_for
from app.models import Scenario, ScenarioExecution
from app.scenario_lab.explain import TARGETS
from app.scenario_lab.templates import TEMPLATES
from app.schemas.common import InputModel
from app.schemas.intelligence import DriverAnalysisRead, NodeRead
from app.schemas.scenario import (
    LabExplanationRead,
    PlanRead,
    PreviewRead,
    ScenarioInput,
    ScenarioSummaryRead,
)
from app.services import scenario_lab as lab_service
from app.services import scenarios as scenario_service

COMPANY = r"^company:[a-z0-9_]{2,120}$"
MAX_SCENARIOS_READ = 200
Line = Literal[TARGETS]  # type: ignore[valid-type]


def _label(vocabulary: Vocabulary, key: str | None) -> str:
    term = vocabulary.get(key) if key else None
    return term.label if term is not None else (key or "—")


# --- list_scenarios ----------------------------------------------------------------------------


class ScenariosInput(InputModel):
    entity_key: str | None = Field(default=None, pattern=COMPANY, max_length=128)
    limit: int = Field(default=10, ge=1, le=20)


def _scenarios(
    session: Session, args: ScenariosInput, _vocabulary: Vocabulary
) -> tuple[list[ScenarioSummaryRead], int]:
    page = scenario_service.list_scenarios(session, limit=MAX_SCENARIOS_READ, offset=0)
    items = [
        item for item in page.items if args.entity_key is None or item.entity == args.entity_key
    ]
    return items, page.total


def _scenarios_render(
    ctx: RenderContext,
    args: ScenariosInput,
    found: tuple[list[ScenarioSummaryRead], int],
    read_at: datetime,
) -> ToolOutput:
    items, total = found
    rows = []
    ids = []
    for item in items[: args.limit]:
        latest = item.latest_execution
        cited = ctx.ledger.add(
            tool="list_scenarios",
            call=ctx.call,
            kind=Knowledge.RECORD,
            title=f"Scenario '{data_text(item.name, 120)}'",
            detail=data_text(item.description, 300) or None,
            source=SourceRef(
                kind="scenario", id=str(item.id), label=item.name, link=scenario_link(str(item.id))
            ),
            retrieved_at=read_at,
            as_of=item.updated_at.isoformat(),
            values={"versions": item.current_version, "executions": item.executions},
        )
        ids.append(cited)
        rows.append(
            TableRow(
                cells={
                    "scenario": item.name,
                    "company": _label(ctx.vocabulary, item.entity),
                    "version": str(item.current_version),
                    "executions": str(item.executions),
                    "latest": latest.status.value if latest else "never executed",
                },
                link=scenario_link(str(item.id), str(latest.id) if latest else None),
                citations=[cited],
            )
        )
    display: list[Block] = []
    if rows:
        display.append(
            TableBlock(
                title="Stored scenarios",
                columns=[
                    Column(key="scenario", label="Scenario"),
                    Column(key="company", label="Company"),
                    Column(key="version", label="Version", align="end"),
                    Column(key="executions", label="Executions", align="end"),
                    Column(key="latest", label="Latest execution"),
                ],
                rows=rows,
                total=len(items) if len(items) > len(rows) else None,
            )
        )
    return ToolOutput(
        data={
            "total_stored": total,
            "matching": len(items),
            "scenarios": [
                {
                    "evidence": cited,
                    "id": str(item.id),
                    "name": item.name,
                    "company": item.entity,
                    "version": item.current_version,
                    "executions": item.executions,
                    "latest_execution": str(item.latest_execution.id)
                    if item.latest_execution
                    else None,
                }
                for cited, item in zip(ids, items, strict=False)
            ],
        },
        summary=f"{len(items)} stored scenarios",
        evidence=ids,
        display=display,
        facts=items,
    )


LIST_SCENARIOS = Tool(
    name="list_scenarios",
    description="Stored scenarios (optionally only those for one company): name, company, "
    "version, how many times each was executed and its latest execution.",
    input_model=ScenariosInput,
    fetch=_scenarios,
    render=_scenarios_render,
    timeout_seconds=5,
)


# --- get_execution -----------------------------------------------------------------------------


class ExecutionInput(InputModel):
    execution_id: uuid.UUID | None = None
    entity_key: str | None = Field(default=None, pattern=COMPANY, max_length=128)

    @model_validator(mode="after")
    def _one(self) -> ExecutionInput:
        if (self.execution_id is None) == (self.entity_key is None):
            raise ValueError("Give either execution_id or entity_key (its latest execution).")
        return self


@dataclass
class ExecutionFacts:
    drivers: DriverAnalysisRead
    entity: NodeRead
    stored: int  # completed executions for the company


def _entity_of(row: ScenarioExecution) -> str | None:
    entity = (row.plan or {}).get("entity")
    return str(entity.get("key")) if isinstance(entity, dict) and entity.get("key") else None


def _execution(session: Session, args: ExecutionInput, vocabulary: Vocabulary) -> ExecutionFacts:
    if args.entity_key is not None:
        rows = executions_for(session, args.entity_key)
        if not rows:
            term = vocabulary.get(args.entity_key)
            name = term.label if term else args.entity_key
            raise ToolProblem(
                f"No completed scenario execution is stored for {name}.", status="not_found"
            )
        row, key, stored = rows[0], args.entity_key, len(rows)
    else:
        found = session.get(ScenarioExecution, args.execution_id)
        if found is None or found.status is not ScenarioExecutionStatus.COMPLETED:
            raise ToolProblem("No completed execution has that id.", status="not_found")
        entity_key = _entity_of(found)
        if entity_key is None:
            raise ToolProblem(
                "That execution was run without a company, so it has no drivers to read.",
                status="not_found",
            )
        row, key, stored = found, entity_key, len(executions_for(session, entity_key))
    drivers = DriverAnalysisRead.model_validate(
        serialize.drivers(analyse_drivers(session, row, key))
    )
    term = vocabulary.get(key)
    entity = NodeRead(
        key=key,
        name=term.label if term else key,
        node_type="company",
        nature="fictional" if term is not None and term.fictional else "real",
        attributes={},
    )
    return ExecutionFacts(drivers, entity, stored)


def _execution_render(
    ctx: RenderContext, _args: ExecutionInput, found: ExecutionFacts, read_at: datetime
) -> ToolOutput:
    drivers = found.drivers
    block, cited = simulation_block(ctx, "get_execution", drivers, found.entity, read_at)
    simulated = cited[0]
    contributions: dict[str, Any] = {}
    top: list[dict[str, Any]] = []
    for line in drivers.lines:
        for item in line.contributions:
            contributions[f"{line.id}.{item.variable_id}"] = item.value
            if item.share_of_change is not None:
                contributions[f"{line.id}.{item.variable_id}.share"] = item.share_of_change
        if line.contributions:
            leading = max(line.contributions, key=lambda item: abs(item.value))
            top.append(
                {
                    "line": line.label,
                    "largest_contribution": leading.name,
                    "value": exact(leading.value),
                    "share_of_change": exact(leading.share_of_change),
                }
            )
    if contributions:
        ctx.ledger.add(
            tool="get_execution",
            call=ctx.call,
            kind=Knowledge.SIMULATED,
            title=block.title,
            source=SourceRef(
                kind="execution",
                id=drivers.execution.id,
                label=drivers.execution.scenario_name,
                link=block.link,
            ),
            retrieved_at=read_at,
            period=f"{drivers.execution.horizon_months} months simulated",
            currency=drivers.execution.currency,
            values=contributions,
        )
    return ToolOutput(
        data={
            "evidence": cited,
            "company": found.entity.name,
            "scenario": drivers.execution.scenario_name,
            "scenario_id": drivers.execution.scenario_id,
            "execution_id": drivers.execution.id,
            "version": drivers.execution.version,
            "finished_at": drivers.execution.finished_at.isoformat()
            if drivers.execution.finished_at
            else None,
            "currency": drivers.execution.currency,
            "horizon_months": drivers.execution.horizon_months,
            "changes": [
                {
                    "variable": c.name,
                    "type": c.change_type,
                    "value": exact(c.value),
                    "unit": c.unit,
                    "modelled": c.modelled,
                }
                for c in drivers.changes
            ],
            "lines": [
                {
                    "id": line.id,
                    "label": line.label,
                    "baseline": exact(line.baseline),
                    "change": exact(line.change),
                    "scenario": exact(line.scenario),
                    "percent_change": exact(line.percent_change),
                }
                for line in drivers.lines
            ],
            "largest_contributions": top,
            "models": [f"{m.model_id} {m.version}" for m in drivers.models],
            "assumptions": [data_text(item, 200) for item in drivers.assumptions[:8]],
            "figures_entered": [
                {"label": f.label, "value": f.value, "unit": f.unit} for f in drivers.figures[:12]
            ],
            "not_modelled": [data_text(item, 200) for item in drivers.not_modelled[:6]],
            "stored_executions_for_company": found.stored,
        },
        summary=f"'{drivers.execution.scenario_name}' v{drivers.execution.version}: "
        f"{len(drivers.lines)} lines",
        evidence=[*cited, simulated],
        display=[block],
        facts=found,
    )


GET_EXECUTION = Tool(
    name="get_execution",
    description="A stored scenario execution (by id, or a company's latest): the changes it "
    "applied, each line's baseline, change and scenario value, the largest contributions "
    "(stored Shapley credits), the models and versions, their assumptions and the figures a "
    "person entered. Results are simulated under the scenario's inputs, not forecasts.",
    input_model=ExecutionInput,
    fetch=_execution,
    render=_execution_render,
    timeout_seconds=8,
)


# --- explain_line ------------------------------------------------------------------------------


class ExplainInput(InputModel):
    line: Line = Field(description="A line or metric id, e.g. operating_costs.")
    execution_id: uuid.UUID | None = None
    entity_key: str | None = Field(default=None, pattern=COMPANY, max_length=128)

    @model_validator(mode="after")
    def _one(self) -> ExplainInput:
        if (self.execution_id is None) == (self.entity_key is None):
            raise ValueError("Give either execution_id or entity_key (its latest execution).")
        return self


def _explain(session: Session, args: ExplainInput, vocabulary: Vocabulary) -> LabExplanationRead:
    execution_id = args.execution_id
    if execution_id is None and args.entity_key is not None:
        rows = executions_for(session, args.entity_key)
        if not rows:
            term = vocabulary.get(args.entity_key)
            raise ToolProblem(
                f"No completed scenario execution is stored for "
                f"{term.label if term else args.entity_key}.",
                status="not_found",
            )
        execution_id = rows[0].id
    if execution_id is None:  # pragma: no cover - the input model requires one of the two
        raise ToolProblem("Give an execution or a company.", status="invalid")
    return lab_service.get_explanation(session, execution_id, str(args.line))


def _explain_render(
    ctx: RenderContext, args: ExplainInput, found: LabExplanationRead, read_at: datetime
) -> ToolOutput:
    execution = str(found.execution_id)
    values: dict[str, Any] = {f"term.{term.id}": term.change for term in found.terms}
    values.update({f"by_change.{item.variable_id}": item.value for item in found.by_change})
    models = [f"{model.model_id} {model.version}" for model in found.models]
    assumptions = [
        data_text(statement.text, 200)
        for model in found.models
        for statement in model.assumptions[:4]
    ]
    evidence = ctx.ledger.add(
        tool="explain_line",
        call=ctx.call,
        kind=Knowledge.SIMULATED,
        title=f"Why {found.label.lower()} changed in execution {execution[:8]}",
        detail=data_text(" ".join(found.chain), 900),
        source=SourceRef(kind="execution", id=execution, label=found.label, link=None),
        retrieved_at=read_at,
        models=models,
        assumptions=assumptions,
        provenance={"equation": data_text(found.equation.formula, 200)},
        values=values,
    )
    rows = [
        TableRow(
            cells={
                "change": item.name,
                "credit": exact(item.value),
                "as_entered": f"{item.change} {item.unit or ''}".strip() if item.change else "—",
            },
            citations=[evidence],
        )
        for item in found.by_change
    ]
    display: list[Block] = []
    if rows:
        display.append(
            TableBlock(
                title=f"{found.label}: credit per change",
                columns=[
                    Column(key="change", label="Change"),
                    Column(key="as_entered", label="As entered"),
                    Column(key="credit", label="Credit", align="end"),
                ],
                rows=rows,
                note="Shapley credits: each change's share of the line's change; they add up "
                "to it.",
                citations=[evidence],
            )
        )
    return ToolOutput(
        data={
            "evidence": evidence,
            "line": found.label,
            "equation": data_text(found.equation.formula, 200),
            "terms": [{"term": t.label, "change": exact(t.change)} for t in found.terms],
            "credit_by_change": [
                {"change": item.name, "credit": exact(item.value)} for item in found.by_change
            ],
            "chain": [data_text(step, 300) for step in found.chain[:8]],
            "models": models,
            "assumptions": assumptions[:8],
        },
        summary=f"{found.label}: {len(found.by_change)} changes credited",
        evidence=[evidence],
        display=display,
        facts=found,
    )


EXPLAIN_LINE = Tool(
    name="explain_line",
    description="Why one line or metric of a stored execution changed (by execution id, or a "
    "company's latest): its equation, the change in each term, the credit of each scenario "
    "change, the chain from the changes to the line, and the models' assumptions.",
    input_model=ExplainInput,
    fetch=_explain,
    render=_explain_render,
    timeout_seconds=8,
)


# --- preview_scenario --------------------------------------------------------------------------


class ChangeArg(InputModel):
    variable_id: str = Field(pattern=r"^var_[a-z0-9_]{2,59}$")
    change_type: Literal["percent_change", "absolute_change"]
    value: str = Field(pattern=r"^[+-]?\d{1,6}(\.\d{1,4})?$")


class PreviewInput(InputModel):
    changes: list[ChangeArg] = Field(min_length=1, max_length=5)
    entity_key: str | None = Field(default=None, pattern=COMPANY, max_length=128)
    horizon_months: int | None = Field(default=None, ge=1, le=36)
    use_stored_figures: bool = Field(
        default=True,
        description="Reuse the figures entered in the company's latest stored scenario.",
    )


@dataclass
class PreviewFacts:
    payload: ScenarioInput
    preview: PreviewRead | None
    plan: PlanRead
    base: tuple[str, str, int] | None  # scenario id, name, version the figures came from
    template: str | None


def _base_scenario(session: Session, entity_key: str) -> tuple[Scenario, dict[str, Any]] | None:
    for scenario in session.scalars(
        select(Scenario).order_by(Scenario.updated_at.desc()).limit(MAX_SCENARIOS_READ)
    ):
        current = scenario_service.version_of(scenario)
        if current.spec.get("entity") == entity_key:
            return scenario, current.spec
    return None


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if item is not None}
    return value


def _preview(session: Session, args: PreviewInput, _vocabulary: Vocabulary) -> PreviewFacts:
    shocks = [
        {"variable_id": c.variable_id, "change_type": c.change_type, "value": c.value}
        for c in args.changes
    ]
    variables = {c.variable_id for c in args.changes}
    template = next(
        (t for t in TEMPLATES if {shock.variable_id for shock in t.shocks} & variables), None
    )
    base = (
        _base_scenario(session, args.entity_key)
        if (args.entity_key and args.use_stored_figures)
        else None
    )
    if base is not None:
        scenario, spec = base
        body = _clean(
            {
                "name": "Analyst preview",
                "description": f"Changes from the AI Analyst on the figures of '{scenario.name}'.",
                "template_id": scenario.template_id,
                "shocks": shocks,
                "entity": args.entity_key,
                "timing": {
                    **spec.get("timing", {}),
                    **({"horizon_months": args.horizon_months} if args.horizon_months else {}),
                },
                "company": spec.get("company", {}),
                "markets": spec.get("markets", {}),
                "models": spec.get("models", {}),
                "constraints": spec.get("constraints", {}),
                "stress_cases": [],
            }
        )
        payload = ScenarioInput.model_validate(body)
        preview = scenario_service.preview(session, payload)
        return PreviewFacts(
            payload,
            preview,
            preview.plan,
            (str(scenario.id), scenario.name, scenario.current_version),
            template.id if template else None,
        )
    body = {
        "name": template.title if template else "Analyst what-if",
        "template_id": template.id if template else None,
        "shocks": shocks,
        "entity": args.entity_key,
        "timing": {"horizon_months": args.horizon_months or 12},
        "models": {model: {"mode": "include"} for model in (template.models if template else ())},
    }
    payload = ScenarioInput.model_validate(_clean(body))
    plan = scenario_service.plan_draft(session, payload)
    if plan.executable:
        preview = scenario_service.preview(session, payload)
        return PreviewFacts(payload, preview, preview.plan, None, template.id if template else None)
    return PreviewFacts(payload, None, plan, None, template.id if template else None)


def _missing(plan: PlanRead) -> list[str]:
    found: list[str] = []
    for model in plan.models:
        if model.status not in ("included", "blocked"):
            continue
        for issue in model.issues:
            if issue.severity == "error" and issue.message not in found:
                found.append(issue.message)
    for issue in plan.issues:
        if issue.severity == "error" and issue.message not in found:
            found.append(issue.message)
    return found[:10]


def _preview_render(
    ctx: RenderContext, args: PreviewInput, found: PreviewFacts, read_at: datetime
) -> ToolOutput:
    plan = found.plan
    payload = found.payload
    tool = "preview_scenario"
    names = plan.names
    changes = [
        ScenarioChange(
            variable_id=change.variable_id,
            name=change.name,
            change_type=change.change_type.value,
            value=exact(change.value) or "0",
            unit=change.unit,
            modelled=change.modelled,
        )
        for change in plan.changes
    ]
    entity = (
        EntityRef(key=plan.entity.key, name=plan.entity.name, link=node_link(plan.entity.key))
        if plan.entity
        else None
    )
    included = [m for m in plan.models if m.status == "included"]
    models = [f"{m.model_id} {m.version}" for m in included]
    draft = payload.model_dump(mode="json", exclude_none=True)
    ids: list[str] = []
    display: list[Block] = []
    results = found.preview.results if found.preview else None
    if results is not None:
        values: dict[str, Any] = {}
        for line in results.lines:
            values[f"{line.id}.baseline"] = line.baseline
            values[f"{line.id}.change"] = line.change
            values[f"{line.id}.scenario"] = line.scenario
            values[f"{line.id}.percent_change"] = line.percent_change
        for metric in results.metrics:
            values[f"{metric.id}.baseline"] = metric.baseline
            values[f"{metric.id}.scenario"] = metric.scenario
            values[f"{metric.id}.change"] = metric.change
        for change in plan.changes:
            values[f"change.{change.variable_id}"] = change.value
        values["horizon_months"] = results.horizon_months
        assumptions = [
            f"{item.label}: {item.value}{' ' + item.unit_label if item.unit_label else ''} "
            f"({'stated default' if item.source == 'default' else 'entered'})"
            for model in included
            for item in model.inputs
            if item.category == "assumption" and item.value is not None
        ]
        preview_id = ctx.ledger.add(
            tool=tool,
            call=ctx.call,
            kind=Knowledge.PREVIEW,
            title=f"Preview for {entity.name if entity else 'no company'}: "
            + ", ".join(
                f"{c.name} {c.value}{' %' if c.change_type == 'percent_change' else ''}"
                for c in changes
            ),
            detail="Computed by the registered models on request, from the changes asked about "
            "and the figures shown; not stored and not a forecast.",
            source=SourceRef(
                kind="preview", id=f"preview:{ctx.call}", label="Scenario preview", link=None
            ),
            retrieved_at=read_at,
            period=f"{results.horizon_months} months simulated",
            currency=results.currency,
            models=models,
            assumptions=assumptions[:12],
            values=values,
        )
        ids.append(preview_id)
        if found.base is not None:
            scenario_id, name, version = found.base
            figures = {
                "annual_revenue": payload.company.annual_revenue,
                "annual_operating_costs": payload.company.annual_operating_costs,
                **{
                    f"{model}.{key}": item.value
                    for model, settings in payload.models.items()
                    for key, item in settings.inputs.items()
                    if item.value is not None
                },
            }
            ids.append(
                ctx.ledger.add(
                    tool=tool,
                    call=ctx.call,
                    kind=Knowledge.USER_INPUT,
                    title=f"Figures entered in '{data_text(name, 120)}' (version {version})",
                    detail="Entered by a person in the Scenario Lab and reused for this preview; "
                    "not RUMIN data.",
                    source=SourceRef(
                        kind="scenario", id=scenario_id, label=name, link=scenario_link(scenario_id)
                    ),
                    retrieved_at=read_at,
                    period=f"version {version}",
                    currency=payload.company.reporting_currency,
                    values={
                        "version": version,
                        **{k: str(v) for k, v in figures.items() if v is not None},
                    },
                )
            )
        display.append(
            ScenarioBlock(
                status="preview",
                title="Preview: "
                + ", ".join(
                    f"{c.name} {'+' if not c.value.startswith('-') else ''}{c.value}"
                    f"{' %' if c.change_type == 'percent_change' else ' ' + c.unit}"
                    for c in changes
                ),
                entity=entity,
                changes=changes,
                horizon_months=results.horizon_months,
                lines=[
                    ScenarioLine(
                        id=line.id,
                        label=line.label,
                        currency=line.currency,
                        baseline=exact(line.baseline),
                        change=exact(line.change) or "0",
                        scenario=exact(line.scenario),
                        percent_change=exact(line.percent_change),
                        citations=[preview_id],
                    )
                    for line in results.lines
                ],
                models=models,
                draft=draft,
                notes=[
                    "Computed on request and not stored. Open it in the Scenario Lab to save "
                    "or execute it.",
                    *(data_text(item.reason, 200) for item in results.not_modelled[:4]),
                ],
                citations=ids,
            )
        )
    else:
        missing = _missing(plan)
        applicable = [m for m in plan.models if m.status in ("included", "available", "blocked")]
        plan_id = ctx.ledger.add(
            tool=tool,
            call=ctx.call,
            kind=Knowledge.RECORD,
            title="Scenario plan: what the models need",
            detail="The Scenario Lab's plan for these changes. It cannot run until the figures "
            "listed are entered; RUMIN never fills them in.",
            source=SourceRef(
                kind="catalogue", id=f"plan:{ctx.call}", label="Scenario plan", link=None
            ),
            retrieved_at=read_at,
            models=[f"{m.model_id} {m.version}" for m in applicable],
            values={"models": len(applicable), "missing": len(missing)},
        )
        ids.append(plan_id)
        display.append(
            ScenarioBlock(
                status="plan",
                title="Plan: " + ", ".join(f"{c.name} {c.value}" for c in changes),
                entity=entity,
                changes=changes,
                horizon_months=payload.timing.horizon_months,
                models=[f"{m.model_id} {m.version}" for m in applicable],
                missing=missing,
                draft=draft,
                notes=[
                    "Nothing was computed: the models need the company's own figures. Open the "
                    "draft in the Scenario Lab to enter them.",
                ],
                citations=[plan_id],
            )
        )
    data: dict[str, Any] = {
        "evidence": ids,
        "stored": False,
        "company": entity.name if entity else None,
        "changes": [
            {
                "variable": names.get(c.variable_id, c.name),
                "type": c.change_type,
                "value": c.value,
                "unit": c.unit,
                "modelled": c.modelled,
            }
            for c in changes
        ],
        "models_included": models,
        "executable": plan.executable,
    }
    if results is not None:
        data["currency"] = results.currency
        data["horizon_months"] = results.horizon_months
        data["lines"] = [
            {
                "id": line.id,
                "label": line.label,
                "baseline": exact(line.baseline),
                "change": exact(line.change),
                "percent_change": exact(line.percent_change),
            }
            for line in results.lines
        ]
        data["figures_from"] = (
            {"scenario": found.base[1], "version": found.base[2]} if found.base else None
        )
    else:
        data["missing"] = _missing(plan)
    return ToolOutput(
        data=data,
        summary="preview computed, not stored"
        if results is not None
        else f"plan only: {len(_missing(plan))} figures missing",
        evidence=ids,
        display=display,
        facts=found,
    )


PREVIEW_SCENARIO = Tool(
    name="preview_scenario",
    description="Compute a what-if with the registered models WITHOUT storing it: the changes "
    "(each a variable, percent_change or absolute_change, and a value; rates in percentage "
    "points), optionally a company and a horizon. It reuses the figures a person entered in "
    "that company's latest stored scenario; without them it returns the plan (which models "
    "apply and which figures are missing). Results are simulated, not forecasts.",
    input_model=PreviewInput,
    fetch=_preview,
    render=_preview_render,
    kind="compute",
    timeout_seconds=15,
)
