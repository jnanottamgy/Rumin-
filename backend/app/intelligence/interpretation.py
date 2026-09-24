"""Model interpretation of an observed change (rule S06).

*What would the stored scenario's models say if the change just observed in a related series
were applied to this company's figures?* The latest observed change of a series recorded as
a related measure of a scenario variable is applied — alone — to the stored scenario version
(same company, figures, timing, models and assumptions), and the Lab's planner and models are
run as a preview: computed on request, never stored.

This is an interpretation, labelled as such, never an observation: the series and the
variable differ (the curator's stated difference is shown), the change is applied as a step
for the scenario's timing, and every figure is conditional on the scenario's inputs. Only
changes whose measure matches the scenario's change type are applied (a relative change to a
percent change, percentage points to a change in percentage points); the size is rounded to
the four decimals the Lab accepts, and the rounding is shown.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy.orm import Session

from app.domain.enums import ChangeType
from app.intelligence.drivers import DriverAnalysis
from app.intelligence.series import Change, History
from app.models import ScenarioExecution, ScenarioVersion
from app.scenario_lab.executor import (
    combine,
    evaluate_stress,
    members_of,
    results_json,
    simulate,
    spec_of,
)
from app.scenario_lab.pathways import complete, trace
from app.scenario_lab.planner import build_plan
from app.scenario_lab.validation import load_variables
from app.simulation.decimal_math import NumericalError

LAB_DECIMALS = Decimal("0.0001")


@dataclass(frozen=True)
class InterpretedLine:
    id: str
    label: str
    currency: str
    baseline: Decimal
    change: Decimal
    percent_change: Decimal | None


@dataclass(frozen=True)
class Interpretation:
    execution_id: str
    scenario_name: str
    version: int
    variable_id: str
    variable_name: str
    series_id: str
    series_name: str
    stated_difference: str | None
    observed: Change
    observed_unit: str
    applied: Decimal
    applied_type: str
    lines: tuple[InterpretedLine, ...]
    headline: str | None
    models: tuple[str, ...]
    graph_build_id: int | None
    note: str

    def line(self, line_id: str) -> InterpretedLine | None:
        return next((line for line in self.lines if line.id == line_id), None)


@dataclass(frozen=True)
class NotInterpreted:
    variable_id: str
    series_id: str
    reason: str


def compatible(change_type: str, history: History) -> bool:
    if change_type == ChangeType.PERCENT_CHANGE.value:
        return history.subject.measure == "relative"
    return history.subject.measure == "points"


def interpret(
    session: Session,
    drivers: DriverAnalysis,
    history: History,
    observed: Change,
    *,
    freshness: str,
) -> Interpretation | NotInterpreted:
    """Apply ``observed`` alone to the scenario version behind ``drivers``."""
    variable_id = history.subject.variable_id or ""
    change = next((c for c in drivers.changes if c.variable_id == variable_id), None)
    if change is None:
        return NotInterpreted(
            variable_id, history.subject.id, "The scenario does not change this variable."
        )
    if not compatible(change.change_type, history):
        return NotInterpreted(
            variable_id,
            history.subject.id,
            "The series is measured differently from the scenario's change (percent against "
            "percentage points); it is not converted.",
        )
    execution = session.get(ScenarioExecution, uuid.UUID(drivers.execution.id))
    version = session.get(ScenarioVersion, execution.scenario_version_id) if execution else None
    if version is None:
        return NotInterpreted(variable_id, history.subject.id, "The scenario version is missing.")
    applied = observed.value.quantize(LAB_DECIMALS, rounding=ROUND_HALF_EVEN)
    if applied == 0:
        return NotInterpreted(
            variable_id, history.subject.id, "The observed change rounds to zero at four decimals."
        )
    base = spec_of(version)
    shock = next(s for s in base.shocks if s.variable_id == variable_id)
    spec = replace(
        base,
        name=f"{base.name} — observed change in {history.subject.name}",
        shocks=(replace(shock, value=applied, note="observed change (interpretation)"),),
        stress_cases=(),
    )
    plan = build_plan(
        session, spec, freshness=freshness, variables=load_variables(session), preview=False
    )
    if not plan.executable:
        reasons = "; ".join(issue.message for issue in plan.errors) or "the plan is blocked"
        return NotInterpreted(
            variable_id,
            history.subject.id,
            f"The scenario's models cannot run this change: {reasons}.",
        )
    members = members_of(plan)
    try:
        executions = simulate(members)
        combined = combine(plan.spec, members, executions, evaluate_stress(plan.spec, members))
    except NumericalError as error:
        return NotInterpreted(variable_id, history.subject.id, error.message)
    pathway = complete(trace(plan, executions), plan, combined.main)
    results = results_json(plan, members, executions, combined, pathway, {})
    lines = tuple(
        InterpretedLine(
            id=str(line["id"]),
            label=str(line["label"]),
            currency=str(line.get("currency") or ""),
            baseline=Decimal(str(line["baseline"])),
            change=Decimal(str(line["change"])),
            percent_change=None
            if line.get("percent_change") in (None, "")
            else Decimal(str(line["percent_change"])),
        )
        for line in results.get("lines") or []
    )
    present = {line.id for line in lines}
    headline = next(
        (
            item
            for item in ("profit_before_tax", "operating_profit", "operating_costs", "revenue")
            if item in present
        ),
        None,
    )
    return Interpretation(
        execution_id=drivers.execution.id,
        scenario_name=drivers.execution.scenario_name,
        version=drivers.execution.version,
        variable_id=variable_id,
        variable_name=change.name,
        series_id=history.subject.id,
        series_name=history.subject.name,
        stated_difference=history.subject.variable_relation,
        observed=observed,
        observed_unit=history.subject.change_unit,
        applied=applied,
        applied_type=change.change_type,
        lines=lines,
        headline=headline,
        models=tuple(f"{m.model.definition.id} {m.model.definition.version}" for m in members),
        graph_build_id=plan.graph_build_id,
        note=(
            "A model interpretation computed on request and not stored: the observed change "
            "is applied alone to the stored scenario's figures, timing, models and "
            "assumptions. It is not a forecast and not an observation."
        ),
    )
