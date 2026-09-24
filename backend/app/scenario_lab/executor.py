"""Executing a scenario version: the stages, the calculation and what is stored.

An execution moves through recorded stages, each stored with its start and end time as it
happens, so the page shows the real progression:

``validating``   the plan is rebuilt; every included model's inputs are validated, stored data
                 resolved and graph relationships confirmed. All or nothing.
``simulating``   each model is executed by the Phase 4 engine (its transmission along graph
                 relationships, its equations, its contributions); stress cases are
                 evaluated with the same models and assumptions.
``propagating``  each change is followed through the models' runs: the variables it moved,
                 the relationships and parameters that carried it, the line items it changed,
                 month by month.
``aggregating``  the Lab's equations combine the models into lines and metrics (AG0–AG7),
                 the timeline and its events, the stress cases; then every model run is
                 stored as a Phase 4 run and the results with their hashes, in one
                 transaction.

Cancellation and the time limit are checked between stages and between models. An
execution that fails, is cancelled or times out stores nothing but its state and the
reason. Once final, an execution never changes: every change of state is a conditional
update that applies only while the execution is not final, so a state recorded elsewhere
(another process marking it interrupted when it starts) is never overwritten, and a run
that finds its execution already final stops without storing anything.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CursorResult, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import set_committed_value

from app.db.base import utcnow
from app.domain.enums import ScenarioExecutionStatus
from app.models import ScenarioExecution, ScenarioExecutionRun, ScenarioVersion
from app.scenario_lab import LAB_VERSION
from app.scenario_lab.aggregate import (
    EQUATIONS,
    Aggregate,
    Outcome,
    Part,
    aggregate,
    aggregate_json,
    line_json,
    metric_json,
    outcome_of,
    outcome_of_result,
    totals,
)
from app.scenario_lab.pathways import complete, trace
from app.scenario_lab.planner import Plan, build_plan, plan_json
from app.scenario_lab.profiles import (
    ScenarioProfile,
    events,
    ordered,
    profile_hash,
    scenario_events,
)
from app.scenario_lab.spec import ScenarioSpec, ShockSpec, decimal_text, from_parts, spec_hash
from app.scenario_lab.validation import load_variables, stress_changes
from app.simulation.decimal_math import NumericalError, text
from app.simulation.definitions import plain, sha256
from app.simulation.engine import Execution, Preparation, evaluate_result, execute, links_for
from app.simulation.persistence import ModelVersionConflict, store_run
from app.simulation.registry import ENGINE_VERSION, RegisteredModel
from app.simulation.runtime import ResolvedValues, StepRecorder

logger = logging.getLogger(__name__)

S = ScenarioExecutionStatus
TERMINAL = frozenset({S.COMPLETED, S.FAILED, S.CANCELLED})
STAGES = (S.VALIDATING, S.SIMULATING, S.PROPAGATING, S.AGGREGATING)
RESULTS_NOTE = (
    "Simulated values: deterministic calculations from the changes, figures and assumptions "
    "shown, holding everything else constant. They are not forecasts, not guaranteed and not "
    "investment advice."
)


class ExecutionStopped(Exception):
    """Raised at a checkpoint when an execution is cancelled or runs out of time."""

    def __init__(self, status: ScenarioExecutionStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class ExecutionSuperseded(Exception):
    """The execution is already final: its state was recorded elsewhere (for example, a
    starting process marked it interrupted). It is left as it is; this run stores nothing."""


class ExecutionFailed(Exception):
    def __init__(self, code: str, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


Check = Callable[[], None]


def _no_check() -> None:
    return None


@dataclass(frozen=True)
class Member:
    """An included model with its prepared (or, when verifying, rebuilt) inputs."""

    profile: ScenarioProfile
    model: RegisteredModel
    preparation: Preparation

    @property
    def model_id(self) -> str:
        return self.profile.model_id

    @property
    def values(self) -> ResolvedValues:
        values = self.preparation.values
        if values is None:  # pragma: no cover - only valid preparations become members
            raise ValueError(f"{self.model_id} has no valid inputs.")
        return values


def members_of(plan: Plan) -> list[Member]:
    return [
        Member(item.profile, item.model, item.preparation)
        for item in plan.included
        if item.preparation is not None
    ]


def spec_of(version: ScenarioVersion) -> ScenarioSpec:
    return from_parts(
        name=version.name,
        description=version.description,
        template_id=version.template_id,
        shocks=[
            ShockSpec(shock.variable_id, shock.change_type, Decimal(shock.value), shock.note)
            for shock in version.shocks
        ],
        spec=version.spec,
    )


# --- The calculation (pure) ---------------------------------------------------------------------


def simulate(members: Sequence[Member], check: Check = _no_check) -> dict[str, Execution]:
    """Execute every included model (Phase 4 ``execute``)."""
    executions: dict[str, Execution] = {}
    for member in members:
        check()
        executions[member.model_id] = execute(member.preparation)
    return executions


def evaluate_stress(
    spec: ScenarioSpec, members: Sequence[Member], check: Check = _no_check
) -> list[dict[str, Outcome]]:
    """Every stress case: the same models and assumptions, with the changes' values
    replaced. The plan has already refused invalid cases."""
    cases: list[dict[str, Outcome]] = []
    for index in range(len(spec.stress_cases)):
        changes = stress_changes(spec, index)
        outcomes: dict[str, Outcome] = {}
        for member in members:
            check()
            values = member.values
            numbers = dict(values.numbers)
            for binding in member.profile.shocks:
                shock = spec.shock(binding.variable_id)
                if shock is not None and shock.change_type is binding.change_type:
                    numbers[binding.input_id] = changes[binding.variable_id]
            varied = replace(values, numbers=numbers)
            links = links_for(member.model, varied, member.preparation.graph)
            horizon = varied.integer(member.model.definition.horizon_input)
            outcomes[member.model_id] = outcome_of_result(
                member.model_id, evaluate_result(member.model, varied, links, horizon)
            )
        cases.append(outcomes)
    return cases


def _parts(members: Sequence[Member], outcomes: Mapping[str, Outcome]) -> list[Part]:
    return [Part(member.profile, member.values, outcomes[member.model_id]) for member in members]


@dataclass
class Combined:
    main: Aggregate
    steps: list[dict[str, Any]]
    stress: list[Aggregate]


def combine(
    spec: ScenarioSpec,
    members: Sequence[Member],
    executions: Mapping[str, Execution],
    stress: Sequence[Mapping[str, Outcome]],
) -> Combined:
    recorder = StepRecorder()
    main = aggregate(
        _parts(
            members, {m.model_id: outcome_of(m.model_id, executions[m.model_id]) for m in members}
        ),
        horizon=spec.horizon_months,
        recorder=recorder,
    )
    return Combined(
        main=main,
        steps=[
            {
                "sequence": index,
                "equation": step.equation,
                "label": step.label,
                "output": plain(step.output),
                "inputs": [plain(item) for item in step.inputs],
            }
            for index, step in enumerate(recorder.steps, start=1)
        ],
        stress=[
            aggregate(_parts(members, outcomes), horizon=spec.horizon_months) for outcomes in stress
        ],
    )


def stress_json(spec: ScenarioSpec, combined: Combined, currency: str) -> list[dict[str, Any]]:
    cases = []
    for index, result in enumerate(combined.stress):
        case = spec.stress_cases[index]
        cases.append(
            {
                "name": case.name,
                "scale": decimal_text(case.scale) if case.scale is not None else None,
                "changes": {
                    variable: decimal_text(value)
                    for variable, value in stress_changes(spec, index).items()
                },
                "lines": [line_json(line, currency=currency) for line in result.lines.values()],
                "metrics": [metric_json(metric) for metric in result.metrics.values()],
                "knowledge": "simulated",
            }
        )
    return cases


def hashed_result(
    combined: Combined, executions: Mapping[str, Execution], spec: ScenarioSpec
) -> dict[str, Any]:
    """What the result hash covers: every line, metric, monthly value and stress case, and
    each model run's own result hash."""
    return {
        "lines": {
            line_id: {
                "baseline": text(line.baseline),
                "change": text(line.change),
                "monthly": [text(value) for value in line.monthly],
            }
            for line_id, line in sorted(combined.main.lines.items())
        },
        "metrics": {
            metric_id: {"baseline": text(metric.baseline), "scenario": text(metric.scenario)}
            for metric_id, metric in sorted(combined.main.metrics.items())
        },
        "stress": [
            {
                "name": spec.stress_cases[index].name,
                "totals": {key: text(value) for key, value in sorted(totals(result).items())},
                "monthly": {
                    line_id: [text(value) for value in line.monthly]
                    for line_id, line in sorted(result.lines.items())
                },
            }
            for index, result in enumerate(combined.stress)
        ],
        "models": {
            model_id: execution.result_hash for model_id, execution in sorted(executions.items())
        },
    }


def inputs_hash(
    spec_hash: str, members: Sequence[Member], executions: Mapping[str, Execution]
) -> str:
    return sha256(
        {
            "lab_version": LAB_VERSION,
            "spec_hash": spec_hash,
            "models": [
                {
                    "model_id": member.model_id,
                    "version": member.model.definition.version,
                    "definition_hash": member.model.definition_hash,
                    "profile_hash": profile_hash(member.profile),
                    "inputs_hash": executions[member.model_id].inputs_hash,
                }
                for member in members
            ],
        }
    )


def _timeline(
    spec: ScenarioSpec,
    members: Sequence[Member],
    executions: Mapping[str, Execution],
    result: Aggregate,
) -> dict[str, Any]:
    horizon = spec.horizon_months
    found = scenario_events(spec.start_month, spec.end_month, horizon)
    for member in members:
        execution = executions[member.model_id]
        monthly = {name: item["values"] for name, item in execution.monthly.items()}
        found.extend(
            events(
                member.profile,
                member.values,
                monthly,
                spec.start_month,
                horizon,
            )
        )
    return {
        "months": horizon,
        "start_month": spec.start_month,
        "end_month": min(spec.end_month, horizon),
        "lines": [
            {"line": line_id, "values": [text(value) for value in line.monthly]}
            for line_id, line in result.lines.items()
        ],
        "events": [
            {"month": event.month, "label": event.label, "model_id": event.model_id}
            for event in ordered(found)
        ],
        "knowledge": "simulated",
        "note": "Months of the simulation, counted from its start: simulated values, not "
        "dates and not forecasts.",
    }


def _model_json(member: Member, execution: Execution, run_id: uuid.UUID | None) -> dict[str, Any]:
    definition = member.model.definition
    return {
        "model_id": member.model_id,
        "version": definition.version,
        "name": definition.name,
        "title": member.profile.title,
        "definition_hash": member.model.definition_hash,
        "profile_hash": profile_hash(member.profile),
        "run_id": str(run_id) if run_id else None,
        "inputs_hash": execution.inputs_hash,
        "result_hash": execution.result_hash,
        "key_outputs": [
            {
                "id": name,
                "label": definition.output(name).label,
                "value": text(execution.outputs[name]["value"]),
                "unit": execution.outputs[name]["unit"],
                "kind": execution.outputs[name]["kind"],
            }
            for name in member.profile.key_outputs
        ],
        "bridge": plain(execution.bridge),
        "warnings": [
            {"code": issue.code, "message": issue.message, "field": issue.field}
            for issue in execution.warnings
        ],
    }


def results_json(
    plan: Plan,
    members: Sequence[Member],
    executions: Mapping[str, Execution],
    combined: Combined,
    pathway: dict[str, Any],
    run_ids: Mapping[str, uuid.UUID],
) -> dict[str, Any]:
    spec = plan.spec
    currency = spec.reporting_currency or ""
    return {
        "lab_version": LAB_VERSION,
        "engine_version": ENGINE_VERSION,
        "currency": currency,
        "horizon_months": spec.horizon_months,
        "timing": {
            "start_month": spec.start_month,
            "end_month": min(spec.end_month, spec.horizon_months),
            "duration_months": spec.duration_months,
        },
        "entity": plan.entity.to_json() if plan.entity else None,
        **aggregate_json(combined.main, currency=currency),
        "models": [
            _model_json(member, executions[member.model_id], run_ids.get(member.model_id))
            for member in members
        ],
        "timeline": _timeline(spec, members, executions, combined.main),
        "pathway": pathway,
        "stress_cases": stress_json(spec, combined, currency),
        "steps": combined.steps,
        "equations": [{"id": key, **value} for key, value in EQUATIONS.items()],
        "configuration": {
            "lab_version": LAB_VERSION,
            "engine_version": ENGINE_VERSION,
            "time_step": "month",
            "horizon_months": spec.horizon_months,
            "rounding": "34 significant digits; results rounded half to even to 10 decimal places",
            "attribution": "Shapley values within each model; lines add the models' items",
        },
        "note": RESULTS_NOTE,
    }


# --- Staged execution with the database ---------------------------------------------------------


def _now_text(moment: datetime) -> str:
    return moment.isoformat()


def write_state(session: Session, row: ScenarioExecution, **values: Any) -> None:
    """Write ``values`` to the execution in the current transaction, only while it is not
    final (a conditional update); ``ExecutionSuperseded`` if it already is. The row's other
    pending changes are flushed first, so they belong to the same transaction."""
    session.flush()
    result = session.execute(
        update(ScenarioExecution)
        .where(ScenarioExecution.id == row.id, ScenarioExecution.status.not_in(list(TERMINAL)))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if not isinstance(result, CursorResult) or result.rowcount != 1:
        raise ExecutionSuperseded(str(row.id))
    for key, value in values.items():
        set_committed_value(row, key, value)


class _Stages:
    def __init__(self, session: Session, row: ScenarioExecution, clock: Callable[[], datetime]):
        self.session = session
        self.row = row
        self.clock = clock

    def enter(self, status: ScenarioExecutionStatus, detail: str) -> None:
        now = _now_text(self.clock())
        stages = [dict(item) for item in self.row.stages or []]
        if stages and stages[-1]["finished_at"] is None:
            stages[-1]["finished_at"] = now
        stages.append(
            {"stage": status.value, "started_at": now, "finished_at": None, "detail": detail}
        )
        write_state(self.session, self.row, stages=stages, status=status)
        self.session.commit()

    def closed(self) -> list[dict[str, Any]]:
        stages = [dict(item) for item in self.row.stages or []]
        if stages and stages[-1]["finished_at"] is None:
            stages[-1]["finished_at"] = _now_text(self.clock())
        return stages


def _finish(
    session: Session,
    row: ScenarioExecution,
    stages: _Stages,
    status: ScenarioExecutionStatus,
    clock: Callable[[], datetime],
    *,
    error: dict[str, Any] | None = None,
) -> None:
    """Record the final state, with whatever the transaction holds (the results and runs of
    a completed execution). If the execution is already final, nothing is written."""
    execution_id = row.id
    finished_at = clock()
    values: dict[str, Any] = {
        "stages": stages.closed(),
        "status": status,
        "finished_at": finished_at,
    }
    if error is not None:
        values["error"] = error
    if row.started_at is not None:
        values["duration_ms"] = max(0, round((finished_at - row.started_at).total_seconds() * 1000))
    try:
        write_state(session, row, **values)
    except ExecutionSuperseded:
        session.rollback()
        _superseded(execution_id)
        return
    session.commit()


def _superseded(execution_id: uuid.UUID) -> None:
    logger.warning(
        "Scenario execution %s was already final (recorded elsewhere); this run stored nothing",
        execution_id,
    )


def run_execution(
    session_factory: sessionmaker[Session],
    execution_id: uuid.UUID,
    *,
    freshness: Callable[[Session], str],
    timeout_seconds: float,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Carry out a queued execution to a final state. Never raises for a failed scenario:
    the failure is the execution's recorded outcome."""
    with session_factory() as session:
        row = session.get(ScenarioExecution, execution_id)
        if row is None or row.status is not S.QUEUED:
            return
        deadline = time.monotonic() + timeout_seconds
        stages = _Stages(session, row, clock)

        def check() -> None:
            if time.monotonic() > deadline:
                raise ExecutionStopped(
                    S.FAILED,
                    "timeout",
                    f"The execution exceeded its time limit of {timeout_seconds:g} seconds and "
                    "was stopped. Nothing was stored.",
                )
            session.refresh(row, attribute_names=["cancel_requested", "status"])
            if row.status in TERMINAL:
                raise ExecutionSuperseded(str(execution_id))
            if row.cancel_requested:
                raise ExecutionStopped(
                    S.CANCELLED, "cancelled", "Cancelled on request. Nothing was stored."
                )

        try:
            row.started_at = clock()
            check()
            stages.enter(S.VALIDATING, "Rebuilding the plan and validating every model's inputs")
            version = session.get(ScenarioVersion, row.scenario_version_id)
            if version is None:  # pragma: no cover - RESTRICT forbids it
                raise ExecutionFailed("version_missing", "The scenario version is missing.")
            spec = spec_of(version)
            plan = build_plan(
                session, spec, freshness=freshness(session), variables=load_variables(session)
            )
            row.plan = plan_json(plan)
            if not plan.executable:
                raise ExecutionFailed(
                    "plan_blocked",
                    "The scenario cannot be executed as it stands; nothing was simulated.",
                    [issue.to_json() for issue in plan.errors],
                )
            members = members_of(plan)
            check()

            stages.enter(
                S.SIMULATING,
                f"Executing {len(members)} model{'s' if len(members) != 1 else ''}"
                + (f" and {len(spec.stress_cases)} stress cases" if spec.stress_cases else ""),
            )
            simulated_at: dict[str, tuple[datetime, datetime]] = {}
            executions: dict[str, Execution] = {}
            for member in members:
                check()
                began = clock()
                executions[member.model_id] = execute(member.preparation)
                simulated_at[member.model_id] = (began, clock())
            stress = evaluate_stress(spec, members, check)
            check()

            stages.enter(S.PROPAGATING, "Following each change through the models' runs")
            path_state = trace(plan, executions)
            check()

            stages.enter(S.AGGREGATING, "Combining the models into lines, metrics and the timeline")
            combined = combine(spec, members, executions, stress)
            pathway = complete(path_state, plan, combined.main)
            check()
            run_ids: dict[str, uuid.UUID] = {}
            label = f"{spec.name} · v{row.version} · execution {str(row.id)[:8]}"
            for position, member in enumerate(members):
                began, ended = simulated_at[member.model_id]
                run = store_run(
                    session,
                    executions[member.model_id],
                    label=label[:120],
                    started_at=began,
                    finished_at=ended,
                )
                run_ids[member.model_id] = run.id
                session.add(
                    ScenarioExecutionRun(
                        execution_id=row.id,
                        simulation_run_id=run.id,
                        position=position,
                        model_id=member.model_id,
                        model_version=member.model.definition.version,
                    )
                )
            row.results = results_json(plan, members, executions, combined, pathway, run_ids)
            row.inputs_hash = inputs_hash(plan.spec_hash, members, executions)
            row.result_hash = sha256(hashed_result(combined, executions, spec))
            _finish(session, row, stages, S.COMPLETED, clock)
        except ExecutionSuperseded:
            session.rollback()
            _superseded(execution_id)
        except ExecutionStopped as stop:
            session.rollback()
            _finish(
                session,
                row,
                stages,
                stop.status,
                clock,
                error={"code": stop.code, "message": stop.message, "details": []},
            )
        except ExecutionFailed as failure:
            plan_data = row.plan
            session.rollback()
            row.plan = plan_data
            _finish(
                session,
                row,
                stages,
                S.FAILED,
                clock,
                error={
                    "code": failure.code,
                    "message": failure.message,
                    "details": failure.details,
                },
            )
        except NumericalError as error:
            session.rollback()
            _finish(
                session,
                row,
                stages,
                S.FAILED,
                clock,
                error={"code": error.code, "message": error.message, "details": []},
            )
        except ModelVersionConflict as error:
            session.rollback()
            _finish(
                session,
                row,
                stages,
                S.FAILED,
                clock,
                error={"code": "model_version_conflict", "message": str(error), "details": []},
            )
        except Exception:
            logger.exception("Scenario execution %s failed unexpectedly", execution_id)
            session.rollback()
            _finish(
                session,
                row,
                stages,
                S.FAILED,
                clock,
                error={
                    "code": "internal_error",
                    "message": "An unexpected error stopped the execution; it has been logged. "
                    "Nothing was stored.",
                    "details": [],
                },
            )


# --- Reproducing a stored execution -------------------------------------------------------------


@dataclass(frozen=True)
class RunCheck:
    model_id: str
    run_id: uuid.UUID
    inputs_hash_matches: bool
    result_hash_matches: bool


@dataclass(frozen=True)
class Reproduction:
    reproducible: bool
    inputs_hash: str | None
    result_hash: str | None
    runs: list[RunCheck]
    message: str


def reproduce(
    spec: ScenarioSpec,
    stored: Sequence[tuple[Member | None, Any]],
) -> Reproduction:
    """Re-execute an execution from its stored runs (``rebuild``: the stored values,
    observations and graph snapshot — never current data) and recompute the Lab's
    aggregation. ``stored`` pairs each run, in order, with its rebuilt member, or None when
    its model version is no longer registered with the same definition."""
    if any(member is None for member, _ in stored):
        return Reproduction(
            False,
            None,
            None,
            [],
            "A model version this execution used is no longer registered with the same "
            "definition, so it cannot be re-executed. Its stored results remain valid.",
        )
    members = [member for member, _ in stored if member is not None]
    executions = simulate(members)
    checks = [
        RunCheck(
            member.model_id,
            run.id,
            executions[member.model_id].inputs_hash == run.inputs_hash,
            executions[member.model_id].result_hash == run.result_hash,
        )
        for member, run in stored
        if member is not None
    ]
    combined = combine(spec, members, executions, evaluate_stress(spec, members))
    return Reproduction(
        all(check.inputs_hash_matches and check.result_hash_matches for check in checks),
        inputs_hash(spec_hash(spec), members, executions),
        sha256(hashed_result(combined, executions, spec)),
        checks,
        "",
    )
