"""Contribution analysis: what drives a simulated result, read from what was stored.

Numbers come only from completed Scenario Lab executions and their Phase 4 runs, never from
a new calculation: each line's ``by_change`` credits are the models' Shapley contributions
(per change), combined by the Lab. This module expresses them three ways — as an amount, as
percentage points of the line's baseline and as a share of the line's change — checks that
they add up to the change (the residual is reported, never hidden), and reads the stored
sensitivity rankings. Ratios (margin, coverage) are not attributed, and the result says so.

The **per-unit effect** of a change is its contribution to the headline line divided by the
change's size (per 1 % or per percentage point): an average over the scenario's change, not
a slope — the models are not linear (hedges, lags, compounding).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ScenarioExecutionStatus
from app.intelligence.stats import rounded
from app.models import (
    Scenario,
    ScenarioExecution,
    ScenarioExecutionRun,
    ScenarioSensitivityAnalysis,
    SimulationRun,
)
from app.simulation.decimal_math import HUNDRED, ZERO, arithmetic, to_output

HEADLINE_ORDER = ("profit_before_tax", "operating_profit", "operating_costs", "revenue")
# Inputs that name things rather than state figures.
IDENTITY_INPUTS = frozenset({"entity", "reporting_currency"})
MAX_EXECUTIONS = 20


def _d(value: object) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


@dataclass(frozen=True)
class ChangeInput:
    variable_id: str
    name: str
    change_type: str  # percent_change | absolute_change
    value: Decimal
    unit: str  # "%", "percentage points" or the variable's unit
    modelled: bool


@dataclass(frozen=True)
class Contribution:
    variable_id: str
    name: str
    value: Decimal  # in the line's currency, signed in the line's own direction
    share_of_change: Decimal | None  # percent of the line's change
    points_of_baseline: Decimal | None  # percent of the line's baseline
    per_unit: Decimal | None  # value per 1 unit of the change (per 1 % or per point)
    per_unit_label: str | None


@dataclass(frozen=True)
class ItemDrivers:
    model_id: str
    item: str
    label: str
    value: Decimal
    by_change: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True)
class LineDrivers:
    id: str
    label: str
    currency: str
    baseline: Decimal
    change: Decimal
    scenario: Decimal
    percent_change: Decimal | None
    direction: str
    effect: str
    contributions: tuple[Contribution, ...]
    residual: Decimal
    items: tuple[ItemDrivers, ...]


@dataclass(frozen=True)
class MetricChange:
    id: str
    label: str
    unit: str
    baseline: Decimal | None
    scenario: Decimal | None
    change: Decimal | None
    change_unit: str | None


@dataclass(frozen=True)
class ModelUsed:
    model_id: str
    version: str
    name: str
    run_id: str
    definition_hash: str


@dataclass(frozen=True)
class RankedQuantity:
    target: str
    label: str
    spread: Decimal


@dataclass(frozen=True)
class SensitivityRanking:
    analysis_id: str
    metric: str
    metric_label: str
    created_at: datetime
    ranking: tuple[RankedQuantity, ...]


@dataclass(frozen=True)
class ExecutionRef:
    id: str
    scenario_id: str
    scenario_name: str
    version: int
    finished_at: datetime | None
    currency: str
    horizon_months: int
    graph_build_id: int | None
    graph_freshness: str | None
    inputs_hash: str | None
    result_hash: str | None


@dataclass(frozen=True)
class UnstatedExposure:
    """A model the scenario included although the graph states no exposure of the entity
    to the variables it simulates: that part of the result rests on the user's figures."""

    model_id: str
    model_name: str
    variable_ids: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class DriverAnalysis:
    entity_key: str
    execution: ExecutionRef
    changes: tuple[ChangeInput, ...]
    lines: tuple[LineDrivers, ...]
    metrics: tuple[MetricChange, ...]
    headline: str | None
    models: tuple[ModelUsed, ...]
    assumptions: tuple[str, ...]
    figures: tuple[tuple[str, str, str], ...]  # (label, value, unit) entered by the user
    sensitivity: SensitivityRanking | None
    notes: tuple[str, ...]
    not_modelled: tuple[str, ...] = ()  # lines no included model covers (labels)
    unstated: tuple[UnstatedExposure, ...] = ()

    def unstated_for(self, variable_id: str) -> UnstatedExposure | None:
        return next((u for u in self.unstated if variable_id in u.variable_ids), None)

    def line(self, line_id: str) -> LineDrivers | None:
        return next((line for line in self.lines if line.id == line_id), None)


def executions_for(
    session: Session, entity_key: str, *, limit: int = MAX_EXECUTIONS
) -> list[ScenarioExecution]:
    """Completed executions whose model runs were for ``entity_key``, newest first."""
    ids = (
        select(ScenarioExecutionRun.execution_id)
        .join(SimulationRun, SimulationRun.id == ScenarioExecutionRun.simulation_run_id)
        .where(SimulationRun.entity_id == entity_key)
    )
    return list(
        session.scalars(
            select(ScenarioExecution)
            .where(
                ScenarioExecution.id.in_(ids),
                ScenarioExecution.status == ScenarioExecutionStatus.COMPLETED,
                ScenarioExecution.results.is_not(None),
            )
            .order_by(ScenarioExecution.finished_at.desc(), ScenarioExecution.id)
            .limit(limit)
        ).all()
    )


def _unit_label(change: ChangeInput) -> str:
    if change.change_type == "percent_change":
        return "1 %"
    if change.unit == "percentage points":
        return "1 percentage point"
    return f"1 {change.unit}".rstrip()


def _per_unit(value: Decimal, change: ChangeInput | None) -> tuple[Decimal | None, str | None]:
    if change is None or change.value == ZERO:
        return None, None
    with arithmetic():
        return value / change.value, _unit_label(change)


def _changes(plan: dict[str, Any]) -> list[ChangeInput]:
    found: list[ChangeInput] = []
    for item in plan.get("changes") or []:
        value = _d(item.get("value"))
        if value is None:
            continue
        found.append(
            ChangeInput(
                variable_id=str(item["variable_id"]),
                name=str(item.get("name") or item["variable_id"]),
                change_type=str(item.get("change_type") or "percent_change"),
                value=value,
                unit=str(item.get("unit") or ""),
                modelled=bool(item.get("modelled", True)),
            )
        )
    return found


def _line(
    data: dict[str, Any], names: dict[str, str], changes: dict[str, ChangeInput]
) -> LineDrivers:
    baseline = _d(data.get("baseline")) or ZERO
    change = _d(data.get("change")) or ZERO
    contributions: list[Contribution] = []
    total = ZERO
    with arithmetic():
        for variable_id, raw in (data.get("by_change") or {}).items():
            value = Decimal(str(raw))
            total += value
            share = value / change * HUNDRED if change != ZERO else None
            points = value / baseline * HUNDRED if baseline != ZERO else None
            per_unit, per_label = _per_unit(value, changes.get(variable_id))
            contributions.append(
                Contribution(
                    variable_id=variable_id,
                    name=names.get(variable_id, variable_id),
                    value=value,
                    share_of_change=rounded(share),
                    points_of_baseline=rounded(points),
                    per_unit=rounded(per_unit),
                    per_unit_label=per_label,
                )
            )
        residual = to_output(change - total, "A residual")
    items = tuple(
        ItemDrivers(
            model_id=str(item.get("model_id")),
            item=str(item.get("item")),
            label=str(item.get("label")),
            value=_d(item.get("value")) or ZERO,
            by_change=tuple(
                (str(key), Decimal(str(value)))
                for key, value in (item.get("by_change") or {}).items()
            ),
        )
        for item in data.get("items") or []
    )
    return LineDrivers(
        id=str(data["id"]),
        label=str(data.get("label") or data["id"]),
        currency=str(data.get("currency") or ""),
        baseline=baseline,
        change=change,
        scenario=_d(data.get("scenario")) or ZERO,
        percent_change=_d(data.get("percent_change")),
        direction=str(data.get("direction") or "none"),
        effect=str(data.get("effect") or "none"),
        contributions=tuple(sorted(contributions, key=lambda c: (-abs(c.value), c.name))),
        residual=residual,
        items=items,
    )


def _sensitivity(session: Session, execution: ScenarioExecution) -> SensitivityRanking | None:
    row = session.scalars(
        select(ScenarioSensitivityAnalysis)
        .where(ScenarioSensitivityAnalysis.execution_id == execution.id)
        .order_by(ScenarioSensitivityAnalysis.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    results = row.results or {}
    return SensitivityRanking(
        analysis_id=str(row.id),
        metric=row.metric,
        metric_label=str(results.get("metric_label") or row.metric),
        created_at=row.created_at,
        ranking=tuple(
            RankedQuantity(
                str(item["target"]),
                str(item.get("label") or item["target"]),
                Decimal(str(item["spread"])),
            )
            for item in results.get("ranking") or []
        ),
    )


def _assumptions(
    session: Session, execution: ScenarioExecution
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Each run's stated assumptions, and the figures the user entered (not RUMIN data)."""
    run_ids = [item.simulation_run_id for item in execution.runs]
    runs = session.scalars(select(SimulationRun).where(SimulationRun.id.in_(run_ids))).all()
    assumptions: list[str] = []
    figures: dict[str, tuple[str, str, str]] = {}
    for run in sorted(runs, key=lambda r: r.model_id):
        for item in run.assumptions or []:
            text = f"{run.model_id}: {item.get('text')}"
            if text not in assumptions:
                assumptions.append(text)
        for item in run.inputs or []:
            if item.get("id") in IDENTITY_INPUTS:
                continue
            if item.get("knowledge") == "user_input" and item.get("value") is not None:
                label = str(item.get("label") or item.get("id"))
                figures.setdefault(
                    label, (label, str(item.get("value")), str(item.get("unit_label") or ""))
                )
            elif item.get("knowledge") == "assumption" and item.get("value") is not None:
                source = "default" if item.get("source") == "default" else "entered"
                text = (
                    f"{run.model_id}: {item.get('label')} = {item.get('value')} "
                    f"{item.get('unit_label') or ''} ({source})"
                ).replace("  ", " ")
                if text not in assumptions:
                    assumptions.append(text)
    return assumptions, list(figures.values())


def _unstated(plan: dict[str, Any]) -> list[UnstatedExposure]:
    """Included models whose exposure the plan checked and found not stated in the graph."""
    found: list[UnstatedExposure] = []
    for model in plan.get("models") or []:
        exposure = model.get("exposure") or {}
        if model.get("status") != "included" or not exposure.get("checked"):
            continue
        if exposure.get("stated"):
            continue
        message = next(
            (
                str(issue.get("message"))
                for issue in model.get("issues") or []
                if issue.get("code") == "exposure_not_stated"
            ),
            f"{model.get('name')}: the knowledge graph does not state this exposure.",
        )
        found.append(
            UnstatedExposure(
                model_id=str(model.get("model_id")),
                model_name=str(model.get("name") or model.get("model_id")),
                variable_ids=tuple(str(v) for v in model.get("changes") or []),
                message=message,
            )
        )
    return found


def analyse(session: Session, execution: ScenarioExecution, entity_key: str) -> DriverAnalysis:
    results = execution.results or {}
    plan = execution.plan or {}
    changes = _changes(plan)
    by_variable = {change.variable_id: change for change in changes}
    names = {change.variable_id: change.name for change in changes}
    lines = tuple(_line(line, names, by_variable) for line in results.get("lines") or [])
    present = {line.id for line in lines}
    headline = next((line for line in HEADLINE_ORDER if line in present), None)
    metrics = tuple(
        MetricChange(
            id=str(m["id"]),
            label=str(m.get("label") or m["id"]),
            unit=str(m.get("unit") or ""),
            baseline=_d(m.get("baseline")),
            scenario=_d(m.get("scenario")),
            change=_d(m.get("change")),
            change_unit=m.get("change_unit"),
        )
        for m in results.get("metrics") or []
    )
    models = tuple(
        ModelUsed(
            model_id=str(m.get("model_id")),
            version=str(m.get("version")),
            name=str(m.get("name") or m.get("model_id")),
            run_id=str(m.get("run_id")),
            definition_hash=str(m.get("definition_hash") or ""),
        )
        for m in results.get("models") or []
    )
    scenario = session.get(Scenario, execution.scenario_id)
    graph = plan.get("graph") or {}
    assumptions, figures = _assumptions(session, execution)
    notes = [
        "Contributions are the models' Shapley credits per change, as stored with the "
        "execution; they add up to each line's change.",
        "Ratios (operating margin, interest coverage) are not attributed to changes.",
        "Simulated under the scenario's changes, figures and assumptions: not a forecast.",
    ]
    return DriverAnalysis(
        entity_key=entity_key,
        execution=ExecutionRef(
            id=str(execution.id),
            scenario_id=str(execution.scenario_id),
            scenario_name=scenario.name if scenario else str(execution.scenario_id),
            version=execution.version,
            finished_at=execution.finished_at,
            currency=str(results.get("currency") or ""),
            horizon_months=int(results.get("horizon_months") or 0),
            graph_build_id=graph.get("build_id"),
            graph_freshness=graph.get("freshness"),
            inputs_hash=execution.inputs_hash,
            result_hash=execution.result_hash,
        ),
        changes=tuple(changes),
        lines=lines,
        metrics=metrics,
        headline=headline,
        models=models,
        assumptions=tuple(assumptions),
        figures=tuple(figures),
        sensitivity=_sensitivity(session, execution),
        notes=tuple(notes),
        not_modelled=tuple(
            str(item.get("label") or item.get("id")) for item in results.get("not_modelled") or []
        ),
        unstated=tuple(_unstated(plan)),
    )


def latest_drivers(session: Session, entity_key: str) -> DriverAnalysis | None:
    found = executions_for(session, entity_key, limit=1)
    return analyse(session, found[0], entity_key) if found else None


def previous_of_same_scenario(
    executions: Sequence[ScenarioExecution], latest: ScenarioExecution
) -> ScenarioExecution | None:
    """The newest earlier completed execution of the same scenario, if any."""
    return next(
        (
            item
            for item in executions
            if item.scenario_id == latest.scenario_id and item.id != latest.id
        ),
        None,
    )
