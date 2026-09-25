"""The simulation engine: registered models, input validation, runs, explanations,
provenance, verification and one-at-a-time sensitivity analysis.

Runs and analyses are append-only: they are created by ``POST`` and never replaced or
deleted, so a stored result can always be explained and re-checked. A run is a
deterministic calculation from the inputs and assumptions it records — not a forecast.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import NOT_FOUND, PaginationDep, SessionDep
from app.schemas.common import ErrorResponse
from app.schemas.simulation import (
    ExplanationRead,
    ModelVerificationRead,
    ProvenanceRead,
    SensitivityAnalysisList,
    SensitivityAnalysisRead,
    SensitivityRequest,
    SimulationModelDetail,
    SimulationModelSummary,
    SimulationRequest,
    SimulationRunPage,
    SimulationRunRead,
    SimulationRunRequest,
    ValidationReport,
    VerificationRead,
)
from app.services import simulation
from app.simulation.definitions import MODEL_ID_PATTERN, VERSION_PATTERN

models_router = APIRouter(prefix="/simulation-models", tags=["simulation"])
router = APIRouter(prefix="/simulations", tags=["simulation"])

CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {
        "model": ErrorResponse,
        "description": "The model version's code no longer matches its stored definition.",
    }
}
ModelId = Annotated[
    str, Path(pattern=MODEL_ID_PATTERN.pattern, max_length=64, examples=["airline_fuel_cost"])
]
ModelIdQuery = Annotated[
    str | None,
    Query(pattern=MODEL_ID_PATTERN.pattern, max_length=64, description="Only this model."),
]
VersionQuery = Annotated[
    str | None,
    Query(pattern=VERSION_PATTERN.pattern, max_length=32, description="Default: the latest."),
]


# --- Models -------------------------------------------------------------------------------------


@models_router.get(
    "",
    response_model=list[SimulationModelSummary],
    summary="List simulation models",
    description="The latest version of every registered model, with its status and the "
    "number of stored runs. Models are defined in code and versioned: a changed equation is "
    "a new version, never an edit of an old one.",
)
def list_simulation_models(session: SessionDep) -> list[SimulationModelSummary]:
    return simulation.list_models(session)


@models_router.get(
    "/{model_id}",
    response_model=SimulationModelDetail,
    summary="Get a simulation model",
    description="The full definition: inputs (units, ranges, defaults and any stored series "
    "an input can be read from), equations, outputs, transmission rules with the "
    "knowledge-graph relationship that confirms each, assumptions, limitations and "
    "validation rules.",
    responses=NOT_FOUND,
)
def get_simulation_model(
    session: SessionDep, model_id: ModelId, version: VersionQuery = None
) -> SimulationModelDetail:
    return simulation.get_model(session, model_id, version)


@models_router.get(
    "/{model_id}/verification",
    response_model=ModelVerificationRead,
    summary="Run a model's verification checks",
    description="Runs the model's checks through the engine now, on hypothetical figures: its "
    "worked example (a hand calculation) reproduced exactly; stated properties (no change, no "
    "effect; the bridge closes; months add up; contributions add up; linearity; direction; "
    "units); its documented limits; reproducibility. Also lists what is not verified — "
    "parameters are not estimated from data and results are not back-tested. Passing checks "
    "do not make a model validated.",
    responses=NOT_FOUND,
)
def get_simulation_model_verification(
    model_id: ModelId, version: VersionQuery = None
) -> ModelVerificationRead:
    return simulation.model_verification(model_id, version)


# --- Validation and runs ------------------------------------------------------------------------


@router.post(
    "/validate",
    response_model=ValidationReport,
    summary="Validate simulation inputs",
    description="Checks the inputs without running or storing anything: types, units, "
    "currencies, ranges and decimal places, the model's consistency rules and whether the "
    "knowledge graph confirms every relationship a shock would travel along. Always 200: "
    "`valid` says whether a run would be accepted; `errors` and `warnings` say why.",
)
def validate_simulation(session: SessionDep, payload: SimulationRequest) -> ValidationReport:
    return simulation.validate(session, payload)


@router.post(
    "",
    response_model=SimulationRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run a simulation",
    description="Validates the inputs, executes the model deterministically and stores the "
    "run with its input snapshot, graph snapshot, every calculation step and the result "
    "hash. Invalid inputs are refused (422) with one detail per problem; nothing is stored. "
    "Identical inputs give an identical result hash.",
    responses=CONFLICT,
)
def create_simulation_run(
    session: SessionDep, payload: SimulationRunRequest, response: Response
) -> SimulationRunRead:
    run = simulation.create_run(session, payload)
    response.headers["Location"] = f"/api/v1/simulations/{run.id}"
    return run


@router.get(
    "",
    response_model=SimulationRunPage,
    summary="List simulation runs",
    description="Stored runs, newest first, with their headline results.",
)
def list_simulation_runs(
    session: SessionDep, page: PaginationDep, model_id: ModelIdQuery = None
) -> SimulationRunPage:
    return simulation.list_runs(session, model_id=model_id, limit=page.limit, offset=page.offset)


@router.get(
    "/{run_id}",
    response_model=SimulationRunRead,
    summary="Get a simulation run",
    description="Inputs (each labelled as historical data, a user input, an assumption, a "
    "scenario change or a setting), outputs, monthly series, contributions, the accounting "
    "bridge, warnings and limitations.",
    responses=NOT_FOUND,
)
def get_simulation_run(session: SessionDep, run_id: uuid.UUID) -> SimulationRunRead:
    return simulation.get_run(session, run_id)


@router.get(
    "/{run_id}/explanation",
    response_model=ExplanationRead,
    summary="Explain a simulation run",
    description="The equations the run evaluated, every calculation step in order, the "
    "input-to-output pathway with the knowledge-graph relationships it used, the "
    "contribution of each change to each output, the assumptions with the values used, "
    "limitations and warnings. Built from what the run stored.",
    responses=NOT_FOUND,
)
def get_simulation_explanation(session: SessionDep, run_id: uuid.UUID) -> ExplanationRead:
    return simulation.get_explanation(session, run_id)


@router.get(
    "/{run_id}/provenance",
    response_model=ProvenanceRead,
    summary="Get a simulation run's provenance",
    description="The model version and definition hash, engine version, hashes, timestamps, "
    "every input with its source, the stored observations used (with licence and "
    "attribution), the graph snapshot and every transmission path.",
    responses=NOT_FOUND,
)
def get_simulation_provenance(session: SessionDep, run_id: uuid.UUID) -> ProvenanceRead:
    return simulation.get_provenance(session, run_id)


@router.post(
    "/{run_id}/verify",
    response_model=VerificationRead,
    summary="Re-execute a run and compare",
    description="Re-executes the run from its stored snapshot (never from current data) and "
    "compares the hashes. Stores nothing.",
    responses=NOT_FOUND,
)
def verify_simulation_run(session: SessionDep, run_id: uuid.UUID) -> VerificationRead:
    return simulation.verify(session, run_id)


# --- Sensitivity --------------------------------------------------------------------------------


@router.post(
    "/{run_id}/sensitivity",
    response_model=SensitivityAnalysisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run a sensitivity analysis",
    description="Moves one input at a time — low and high around the run's value, relative "
    "steps or listed values — while every other input keeps the run's value, and reports "
    "each result against the run. Points outside an input's allowed range are skipped and "
    "reported, never clipped. With no inputs listed, the model's default set is used. "
    "Bounded: at most 8 inputs, 7 points each and 60 evaluations.",
    responses={**NOT_FOUND, **CONFLICT},
)
def create_sensitivity_analysis(
    session: SessionDep, run_id: uuid.UUID, payload: SensitivityRequest, response: Response
) -> SensitivityAnalysisRead:
    analysis = simulation.run_sensitivity(session, run_id, payload)
    response.headers["Location"] = f"/api/v1/simulations/{run_id}/sensitivity/{analysis.id}"
    return analysis


@router.get(
    "/{run_id}/sensitivity",
    response_model=SensitivityAnalysisList,
    summary="List a run's sensitivity analyses",
    responses=NOT_FOUND,
)
def list_sensitivity_analyses(session: SessionDep, run_id: uuid.UUID) -> SensitivityAnalysisList:
    return simulation.list_sensitivity(session, run_id)


@router.get(
    "/{run_id}/sensitivity/{analysis_id}",
    response_model=SensitivityAnalysisRead,
    summary="Get a sensitivity analysis",
    responses=NOT_FOUND,
)
def get_sensitivity_analysis(
    session: SessionDep, run_id: uuid.UUID, analysis_id: uuid.UUID
) -> SensitivityAnalysisRead:
    return simulation.get_sensitivity(session, run_id, analysis_id)
