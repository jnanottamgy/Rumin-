"""API logic for the advanced analyses of an execution (Phase 9): what it can vary, Monte Carlo
analyses and joint sensitivity grids — run, stored, listed, read and re-run.

Every analysis re-evaluates the models an execution stored (its runs, rebuilt exactly; never
current data) through ``scenario_lab.evaluation``. It is stored append-only with the
configuration it ran with — the execution's result hash, each run's model version, inputs hash
and graph build, the seed and generator — so ``verify`` can run it again and compare hashes.
At most ``MAX_CONCURRENT`` analyses compute at once in a process; more are refused (429)
rather than queued, so no request waits unboundedly.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, DomainValidationError, NotFoundError
from app.models import ScenarioAnalysis, ScenarioExecution, SimulationRun
from app.scenario_lab import LAB_VERSION, joint, montecarlo
from app.scenario_lab import sensitivity as one_at_a_time
from app.scenario_lab.aggregate import LINE_EQUATIONS, METRIC_LABELS
from app.scenario_lab.evaluation import Evaluator, Target, targets
from app.scenario_lab.executor import Member, spec_of
from app.scenario_lab.profiles import LINE_LABELS
from app.scenario_lab.sampling import (
    GENERATOR,
    MAX_DISCRETE_VALUES,
    SAMPLER_VERSION,
    Discrete,
    Distribution,
    Triangular,
    Uniform,
    new_seed,
)
from app.scenario_lab.sensitivity import Item
from app.scenario_lab.spec import ScenarioSpec
from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisTargetRead,
    AnalysisTargetsRead,
    AnalysisVerificationRead,
    DiscreteInput,
    MonteCarloRequest,
    ScenarioAnalysisList,
    ScenarioAnalysisRead,
    ScenarioAnalysisSummaryRead,
    TriangularInput,
    UniformInput,
)
from app.schemas.common import ErrorDetail
from app.schemas.scenario import LabSensitivityItemInput
from app.services.scenario_lab import (
    completed_execution,
    execution_runs,
    run_definition,
    stored_members,
)
from app.services.scenarios import scenario_or_404, version_of
from app.simulation.decimal_math import text
from app.simulation.definitions import sha256
from app.simulation.registry import ENGINE_VERSION
from app.simulation.units import unit_label
from app.simulation.validation import parse_number

# Recorded with every analysis and part of its inputs hash.
ANALYSIS_VERSION = "1.0.0"
MAX_CONCURRENT = 2
JOINT_NOTE = (
    "Deterministic: every combination of the two quantities' values, everything else as "
    "executed. The interaction is what moving both together adds to moving each alone. No "
    "probability is involved."
)


class TooManyAnalyses(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Other analyses are computing; try again in a moment."


_slots = threading.BoundedSemaphore(MAX_CONCURRENT)


@contextmanager
def _slot() -> Iterator[None]:
    if not _slots.acquire(blocking=False):
        raise TooManyAnalyses(
            f"{MAX_CONCURRENT} analyses are already computing; try again in a moment."
        )
    try:
        yield
    finally:
        _slots.release()


def _invalid(
    message: str, field: str | None, kind: str = "analysis_limit"
) -> DomainValidationError:
    return DomainValidationError(
        "The analysis request is invalid.",
        details=[ErrorDetail(location="body", field=field, message=message, type=kind)],
    )


def _number(raw: str | int | float, field: str) -> Decimal:
    number = parse_number(raw)
    if number is None:
        raise _invalid("Use a plain number such as 10 or 2.5.", field, "invalid_number")
    return number


# --- The execution's members ------------------------------------------------------------------


def _loaded(
    session: Session, execution_id: uuid.UUID
) -> tuple[ScenarioExecution, ScenarioSpec, list[Member], list[SimulationRun]]:
    row = completed_execution(session, execution_id)
    spec = spec_of(version_of(scenario_or_404(session, row.scenario_id), row.version))
    runs = execution_runs(session, row)
    stored = stored_members(session, runs)
    if any(member is None for member, _ in stored):
        raise ConflictError(
            "A model version this execution used is no longer registered with the same "
            "definition, so it cannot be re-evaluated."
        )
    return row, spec, [member for member, _ in stored if member is not None], runs


def _default_metric(row: ScenarioExecution) -> str:
    lines = {line["id"] for line in (row.results or {}).get("lines", [])}
    return "profit_before_tax" if "profit_before_tax" in lines else "operating_profit"


def _metric_label(metric: str) -> str:
    return LINE_LABELS.get(metric) or METRIC_LABELS.get(metric, metric)


# --- What an execution can vary -----------------------------------------------------------------


def _target_read(target: Target, currency: str | None) -> AnalysisTargetRead:
    definition = target.definition
    unit = target.unit
    variation = definition.sensitivity
    return AnalysisTargetRead.model_validate(
        {
            "id": target.id,
            "label": target.label,
            "kind": target.kind,
            "models": target.models,
            "unit": unit,
            "unit_label": unit_label(unit, currency=currency) if unit else "",
            "integer": target.integer,
            "base_value": target.base,
            "minimum": definition.minimum,
            "maximum": definition.maximum,
            "minimum_exclusive": definition.minimum_exclusive,
            "maximum_exclusive": definition.maximum_exclusive,
            "max_decimals": 0 if target.integer else definition.max_decimals,
            "default_variation": {"mode": variation.mode, "step": variation.step}
            if variation
            else None,
        }
    )


def analysis_targets(session: Session, execution_id: uuid.UUID) -> AnalysisTargetsRead:
    row, spec, members, _ = _loaded(session, execution_id)
    currency = (row.results or {}).get("currency")
    base = Evaluator(spec, members, deadline_seconds=one_at_a_time.DEADLINE_SECONDS).base_totals
    order = [*LINE_EQUATIONS, *METRIC_LABELS]
    return AnalysisTargetsRead.model_validate(
        {
            "execution_id": row.id,
            "currency": currency,
            "horizon_months": spec.horizon_months,
            "targets": [
                _target_read(target, currency) for target in targets(spec, members).values()
            ],
            "metrics": [
                {
                    "id": metric,
                    "label": _metric_label(metric),
                    "kind": "line_change" if metric in LINE_EQUATIONS else "metric_value",
                    "base": base[metric],
                }
                for metric in order
                if metric in base
            ],
            "limits": {
                "monte_carlo": {
                    "min_draws": montecarlo.MIN_DRAWS,
                    "max_draws": montecarlo.MAX_DRAWS,
                    "default_draws": montecarlo.DEFAULT_DRAWS,
                    "max_quantities": montecarlo.MAX_QUANTITIES,
                    "max_discrete_values": MAX_DISCRETE_VALUES,
                    "min_accepted": montecarlo.MIN_ACCEPTED,
                    "deadline_seconds": montecarlo.DEADLINE_SECONDS,
                },
                "joint": {
                    "max_axis_points": joint.MAX_AXIS_POINTS,
                    "deadline_seconds": joint.DEADLINE_SECONDS,
                },
                "sensitivity": {
                    "max_items": one_at_a_time.MAX_ITEMS,
                    "max_points": one_at_a_time.MAX_POINTS,
                    "max_evaluations": one_at_a_time.MAX_EVALUATIONS,
                },
            },
        }
    )


# --- Requests as the analyses take them ---------------------------------------------------------


def _distribution(raw: UniformInput | TriangularInput | DiscreteInput, field: str) -> Distribution:
    if isinstance(raw, UniformInput):
        return Uniform(_number(raw.low, f"{field}.low"), _number(raw.high, f"{field}.high"))
    if isinstance(raw, TriangularInput):
        return Triangular(
            _number(raw.low, f"{field}.low"),
            _number(raw.mode, f"{field}.mode"),
            _number(raw.high, f"{field}.high"),
        )
    values = tuple(
        _number(value, f"{field}.values[{index}]") for index, value in enumerate(raw.values)
    )
    weights = (
        tuple(
            _number(weight, f"{field}.weights[{index}]") for index, weight in enumerate(raw.weights)
        )
        if raw.weights is not None
        else tuple(Decimal(1) for _ in values)
    )
    return Discrete(values, weights)


def _item(raw: LabSensitivityItemInput, field: str) -> Item:
    return Item(
        target=raw.target,
        mode=raw.mode,
        step=_number(raw.step, f"{field}.step") if raw.step is not None else None,
        values=tuple(
            _number(value, f"{field}.values[{index}]") for index, value in enumerate(raw.values)
        ),
    )


def _item_json(item: Item) -> dict[str, Any]:
    return {
        "target": item.target,
        "mode": item.mode,
        "step": text(item.step) if item.step is not None else None,
        "values": [text(value) for value in item.values],
    }


def _item_of(data: dict[str, Any]) -> Item:
    return Item(
        target=data["target"],
        mode=data["mode"],
        step=Decimal(data["step"]) if data["step"] is not None else None,
        values=tuple(Decimal(value) for value in data["values"]),
    )


def _distribution_of(data: dict[str, Any]) -> Distribution:
    if data["kind"] == "uniform":
        return Uniform(Decimal(data["low"]), Decimal(data["high"]))
    if data["kind"] == "triangular":
        return Triangular(Decimal(data["low"]), Decimal(data["mode"]), Decimal(data["high"]))
    return Discrete(
        tuple(Decimal(value) for value in data["values"]),
        tuple(Decimal(weight) for weight in data["weights"]),
    )


def _normalised(row: ScenarioExecution, payload: AnalysisRequest) -> dict[str, Any]:
    """The request as it will run and be stored: numbers as exact text, the metric and the
    seed resolved."""
    metric = payload.metric or _default_metric(row)
    if isinstance(payload, MonteCarloRequest):
        return {
            "kind": "monte_carlo",
            "metric": metric,
            "draws": payload.draws,
            "seed": payload.seed if payload.seed is not None else new_seed(),
            "threshold": text(_number(payload.threshold, "threshold"))
            if payload.threshold is not None
            else None,
            "quantities": [
                {
                    "target": item.target,
                    "distribution": montecarlo.distribution_json(
                        _distribution(item.distribution, f"quantities[{index}].distribution")
                    ),
                }
                for index, item in enumerate(payload.quantities)
            ],
        }
    return {
        "kind": "joint_sensitivity",
        "metric": metric,
        "rows": _item_json(_item(payload.rows, "rows")),
        "columns": _item_json(_item(payload.columns, "columns")),
    }


def _compute(
    request: dict[str, Any], spec: ScenarioSpec, members: Sequence[Member]
) -> dict[str, Any]:
    """Run a normalised request. Raises the domain errors of ``montecarlo`` and ``joint``."""
    if request["kind"] == "monte_carlo":
        return montecarlo.run(
            spec,
            members,
            [
                montecarlo.Assumption(item["target"], _distribution_of(item["distribution"]))
                for item in request["quantities"]
            ],
            metric=request["metric"],
            draws=request["draws"],
            seed=request["seed"],
            threshold=Decimal(request["threshold"]) if request["threshold"] is not None else None,
        )
    return joint.run(
        spec,
        members,
        _item_of(request["rows"]),
        _item_of(request["columns"]),
        metric=request["metric"],
    )


def _config(
    session: Session, row: ScenarioExecution, runs: Sequence[SimulationRun], request: dict[str, Any]
) -> dict[str, Any]:
    stochastic = request["kind"] == "monte_carlo"
    return {
        "analysis_version": ANALYSIS_VERSION,
        "lab_version": LAB_VERSION,
        "engine_version": ENGINE_VERSION,
        "execution_result_hash": row.result_hash,
        "runs": [
            {
                "model_id": run.model_id,
                "version": run.model_version,
                "definition_hash": run_definition(session, run).definition_hash,
                "run_id": str(run.id),
                "inputs_hash": run.inputs_hash,
                "graph_build_id": (run.graph_snapshot or {}).get("build_id"),
                "graph_fingerprint": (run.graph_snapshot or {}).get("source_fingerprint"),
            }
            for run in sorted(runs, key=lambda item: item.model_id)
        ],
        "seed": request["seed"] if stochastic else None,
        "generator": GENERATOR if stochastic else None,
        "sampler_version": SAMPLER_VERSION if stochastic else None,
        "draws": request["draws"] if stochastic else None,
    }


def _stored_results(results: dict[str, Any]) -> dict[str, Any]:
    """What is stored and hashed: the results without how long they took."""
    return {
        key: value for key, value in results.items() if key not in ("evaluations", "duration_ms")
    }


def _guarded(run: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        with _slot():
            return run()
    except (montecarlo.MonteCarloError, joint.JointError) as error:
        raise _invalid(error.message, error.field) from error


# --- Create, list, read, verify -----------------------------------------------------------------


def _read(row: ScenarioAnalysis) -> ScenarioAnalysisRead:
    stochastic = row.kind == "monte_carlo"
    return ScenarioAnalysisRead.model_validate(
        {
            "id": row.id,
            "execution_id": row.execution_id,
            "kind": row.kind,
            "metric": row.metric,
            "request": row.request,
            "config": row.config,
            "monte_carlo": row.results if stochastic else None,
            "joint": None if stochastic else row.results,
            "evaluations": row.evaluations,
            "duration_ms": row.duration_ms,
            "inputs_hash": row.inputs_hash,
            "result_hash": row.result_hash,
            "created_at": row.created_at,
            "note": montecarlo.CONDITIONAL_NOTE if stochastic else JOINT_NOTE,
        }
    )


def create_analysis(
    session: Session,
    execution_id: uuid.UUID,
    payload: AnalysisRequest,
    *,
    created_by: uuid.UUID | None = None,
) -> ScenarioAnalysisRead:
    row, spec, members, runs = _loaded(session, execution_id)
    request = _normalised(row, payload)
    results = _guarded(lambda: _compute(request, spec, members))
    stored = _stored_results(results)
    config = _config(session, row, runs, request)
    record = ScenarioAnalysis(
        id=uuid.uuid4(),
        execution_id=row.id,
        kind=request["kind"],
        metric=request["metric"],
        request=request,
        config=config,
        results=stored,
        evaluations=results["evaluations"],
        duration_ms=results["duration_ms"],
        inputs_hash=sha256({"config": config, "request": request}),
        result_hash=sha256(stored),
        created_by=created_by,
    )
    session.add(record)
    session.commit()
    return _read(record)


def _summary(row: ScenarioAnalysis) -> ScenarioAnalysisSummaryRead:
    results = row.results or {}
    stochastic = row.kind == "monte_carlo"
    if stochastic:
        labels = [str(item["label"]) for item in results.get("quantities", [])]
    else:
        labels = [str(results["rows"]["label"]), str(results["columns"]["label"])]
    largest = (results.get("summary") or {}).get("largest_interaction") if not stochastic else None
    return ScenarioAnalysisSummaryRead.model_validate(
        {
            "id": row.id,
            "execution_id": row.execution_id,
            "kind": row.kind,
            "metric": row.metric,
            "metric_label": results.get("metric_label", row.metric),
            "quantities": labels,
            "draws": row.config.get("draws"),
            "seed": row.config.get("seed"),
            "accepted": results.get("accepted") if stochastic else None,
            "mean": results["summary"]["mean"] if stochastic else None,
            "largest_interaction": largest["value"] if largest else None,
            "evaluations": row.evaluations,
            "duration_ms": row.duration_ms,
            "result_hash": row.result_hash,
            "created_at": row.created_at,
        }
    )


def list_analyses(session: Session, execution_id: uuid.UUID) -> ScenarioAnalysisList:
    row = session.get(ScenarioExecution, execution_id)
    if row is None:
        raise NotFoundError(f"No scenario execution '{execution_id}'.")
    records = session.scalars(
        select(ScenarioAnalysis)
        .where(ScenarioAnalysis.execution_id == row.id)
        .order_by(ScenarioAnalysis.created_at.desc(), ScenarioAnalysis.id)
    ).all()
    return ScenarioAnalysisList(items=[_summary(record) for record in records])


def _analysis_or_404(
    session: Session, execution_id: uuid.UUID, analysis_id: uuid.UUID
) -> ScenarioAnalysis:
    record = session.get(ScenarioAnalysis, analysis_id)
    if record is None or record.execution_id != execution_id:
        raise NotFoundError(f"No analysis '{analysis_id}' for this execution.")
    return record


def get_analysis(
    session: Session, execution_id: uuid.UUID, analysis_id: uuid.UUID
) -> ScenarioAnalysisRead:
    if session.get(ScenarioExecution, execution_id) is None:
        raise NotFoundError(f"No scenario execution '{execution_id}'.")
    return _read(_analysis_or_404(session, execution_id, analysis_id))


def verify_analysis(
    session: Session, execution_id: uuid.UUID, analysis_id: uuid.UUID
) -> AnalysisVerificationRead:
    """Run a stored analysis again from its stored request and seed, on the execution's
    stored runs, and compare the hashes. Stores nothing."""
    record = _analysis_or_404(session, execution_id, analysis_id)
    row, spec, members, runs = _loaded(session, execution_id)
    config = _config(session, row, runs, record.request)
    same_inputs = sha256({"config": config, "request": record.request}) == record.inputs_hash
    results = _guarded(lambda: _compute(record.request, spec, members))
    recomputed = sha256(_stored_results(results))
    same_result = recomputed == record.result_hash
    reproduced = same_inputs and same_result
    if reproduced:
        message = (
            "Run again from the stored runs and request"
            + (f" with seed {record.request['seed']}" if record.kind == "monte_carlo" else "")
            + ": identical results."
        )
    elif not same_inputs:
        message = (
            "The execution's runs or the analysis's versions differ from those recorded: the "
            "analysis cannot be reproduced exactly and should be investigated."
        )
    else:
        message = (
            "Running the stored request again gave different results: the analysis is not "
            "reproducible and should be investigated."
        )
    return AnalysisVerificationRead(
        analysis_id=record.id,
        reproduced=reproduced,
        inputs_hash_matches=same_inputs,
        result_hash_matches=same_result,
        stored_result_hash=record.result_hash,
        recomputed_result_hash=recomputed,
        message=message,
    )


__all__ = [
    "ANALYSIS_VERSION",
    "MAX_CONCURRENT",
    "TooManyAnalyses",
    "analysis_targets",
    "create_analysis",
    "get_analysis",
    "list_analyses",
    "verify_analysis",
]
