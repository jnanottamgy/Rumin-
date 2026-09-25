"""Scenario executions and what is read from them; comparisons; templates.

Executions are append-only: once final (completed, failed or cancelled) they never
change. Results, pathways and explanations are read from what an execution and its Phase 4
runs stored, so they cannot drift from the calculation.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, Query, Response, status

from app.api.deps import NOT_FOUND, SessionDep
from app.scenario_lab.explain import TARGETS
from app.schemas.analysis import (
    AnalysisTargetsRead,
    AnalysisVerificationRead,
    JointSensitivityRequest,
    MonteCarloRequest,
    ScenarioAnalysisList,
    ScenarioAnalysisRead,
)
from app.schemas.common import ErrorResponse
from app.schemas.scenario import (
    ComparisonRead,
    ExecutionRead,
    ExecutionVerificationRead,
    LabExplanationRead,
    LabPathwayRead,
    LabSensitivityList,
    LabSensitivityRead,
    LabSensitivityRequest,
    ResultsRead,
    TemplateList,
    TemplateRead,
)
from app.services import scenario_analyses, scenario_lab

executions_router = APIRouter(prefix="/scenario-executions", tags=["scenario lab"])
comparisons_router = APIRouter(prefix="/scenario-comparisons", tags=["scenario lab"])
templates_router = APIRouter(prefix="/scenario-templates", tags=["scenario lab"])

NOT_READY: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "The execution has not completed."}
}
Target = Annotated[
    str,
    Query(
        pattern="^(" + "|".join(TARGETS) + ")$",
        description="The line or metric to explain.",
        examples=["operating_profit"],
    ),
]
TemplateId = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
ANALYSIS_BUSY: dict[int | str, dict[str, Any]] = {
    429: {
        "model": ErrorResponse,
        "description": "Other analyses are computing; nothing was stored. Try again shortly.",
    }
}
CHANGED_MODEL: dict[int | str, dict[str, Any]] = {
    409: {
        "model": ErrorResponse,
        "description": "The execution has not completed, or a model version it used is no "
        "longer registered with the same definition.",
    }
}


@executions_router.get(
    "/{execution_id}",
    response_model=ExecutionRead,
    summary="Get a scenario execution",
    description="Its status and every stage it has been through, with times; the plan it "
    "ran (models, reasons, inputs, graph relationships); the Phase 4 runs it stored; the "
    "error if it failed. While not final, `poll_after_ms` says when to ask again.",
    responses=NOT_FOUND,
)
def get_execution(session: SessionDep, execution_id: uuid.UUID) -> ExecutionRead:
    return scenario_lab.get_execution(session, execution_id)


@executions_router.get(
    "/{execution_id}/results",
    response_model=ResultsRead,
    summary="Get an execution's results",
    description="Baseline against scenario for every modelled line (absolute and percentage "
    "change, direction, currency, horizon), margins and coverage, each model's key "
    "outputs, the months and their events, the stress cases and the Lab's calculation "
    "steps. Every value is simulated from stated inputs; none is a forecast.",
    responses={**NOT_FOUND, **NOT_READY},
)
def get_results(session: SessionDep, execution_id: uuid.UUID) -> ResultsRead:
    return scenario_lab.get_results(session, execution_id)


@executions_router.get(
    "/{execution_id}/pathways",
    response_model=LabPathwayRead,
    summary="Get an execution's impact pathway",
    description="How each change travelled to each line: typed links (applied, propagated "
    "along a graph relationship with its coefficient and lag, computed by an equation, "
    "aggregated, or cited as context only) and the graph's relationships no included model "
    "simulates.",
    responses={**NOT_FOUND, **NOT_READY},
)
def get_pathways(session: SessionDep, execution_id: uuid.UUID) -> LabPathwayRead:
    return scenario_lab.get_pathways(session, execution_id)


@executions_router.get(
    "/{execution_id}/explanation",
    response_model=LabExplanationRead,
    summary="Explain a line or metric",
    description="What caused it: the Lab's equation and terms, each change's contribution, "
    "and for each model its inputs, equations, intermediate steps, graph relationships, "
    "transmission paths, assumptions, data snapshot and limitations — from stored runs.",
    responses={**NOT_FOUND, **NOT_READY},
)
def get_explanation(
    session: SessionDep, execution_id: uuid.UUID, target: Target = "operating_profit"
) -> LabExplanationRead:
    return scenario_lab.get_explanation(session, execution_id, target)


@executions_router.post(
    "/{execution_id}/cancel",
    response_model=ExecutionRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cancel a scenario execution",
    description="Asks a queued or running execution to stop at its next checkpoint; it then "
    "ends as cancelled and stores nothing. 409 if it is already final.",
    responses={**NOT_FOUND, **NOT_READY},
)
def cancel_execution(session: SessionDep, execution_id: uuid.UUID) -> ExecutionRead:
    return scenario_lab.cancel_execution(session, execution_id)


@executions_router.post(
    "/{execution_id}/verify",
    response_model=ExecutionVerificationRead,
    summary="Re-execute and compare",
    description="Re-executes every model from its stored run (never from current data), "
    "recombines them and compares the hashes. Stores nothing.",
    responses={**NOT_FOUND, **NOT_READY},
)
def verify_execution(session: SessionDep, execution_id: uuid.UUID) -> ExecutionVerificationRead:
    return scenario_lab.verify_execution(session, execution_id)


@executions_router.post(
    "/{execution_id}/sensitivity",
    response_model=LabSensitivityRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run a sensitivity analysis across the scenario",
    description="Moves one quantity at a time — a change, a shared figure or a model's input "
    "or assumption — re-evaluates every model that uses it and recombines the chosen line or "
    "metric. Points outside a range are skipped and reported, never clipped. Bounded: 8 "
    "quantities, 7 points each, 60 evaluations. Not a stochastic simulation.",
    responses={**NOT_FOUND, **NOT_READY},
)
def create_sensitivity(
    session: SessionDep,
    execution_id: uuid.UUID,
    payload: LabSensitivityRequest,
    response: Response,
) -> LabSensitivityRead:
    analysis = scenario_lab.run_sensitivity(session, execution_id, payload)
    response.headers["Location"] = (
        f"/api/v1/scenario-executions/{execution_id}/sensitivity/{analysis.id}"
    )
    return analysis


@executions_router.get(
    "/{execution_id}/sensitivity",
    response_model=LabSensitivityList,
    summary="List an execution's sensitivity analyses",
    responses=NOT_FOUND,
)
def list_sensitivity(session: SessionDep, execution_id: uuid.UUID) -> LabSensitivityList:
    return scenario_lab.list_sensitivity(session, execution_id)


@executions_router.get(
    "/{execution_id}/sensitivity/{analysis_id}",
    response_model=LabSensitivityRead,
    summary="Get a sensitivity analysis",
    responses=NOT_FOUND,
)
def get_sensitivity(
    session: SessionDep, execution_id: uuid.UUID, analysis_id: uuid.UUID
) -> LabSensitivityRead:
    return scenario_lab.get_sensitivity(session, execution_id, analysis_id)


@executions_router.get(
    "/{execution_id}/analysis-targets",
    response_model=AnalysisTargetsRead,
    summary="What an analysis of this execution can vary",
    description="Every quantity an analysis can vary — the changes, the shared figures, each "
    "model's company, market and assumption inputs — with its unit, range, decimals, the "
    "execution's value and the model's default variation; the lines and metrics with the "
    "execution's values; the analyses' limits.",
    responses={**NOT_FOUND, **CHANGED_MODEL},
)
def get_execution_analysis_targets(
    session: SessionDep, execution_id: uuid.UUID
) -> AnalysisTargetsRead:
    return scenario_analyses.analysis_targets(session, execution_id)


@executions_router.post(
    "/{execution_id}/analyses",
    response_model=ScenarioAnalysisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run a Monte Carlo or joint sensitivity analysis",
    description="`monte_carlo`: 100–2,000 draws from the uniform, triangular or discrete "
    "distributions you state for up to 8 quantities (independently, with a recorded seed); "
    "each draw re-evaluates the execution's stored runs. Draws that break a model's rule are "
    "rejected and counted, never clipped. `joint_sensitivity`: a grid over two quantities "
    "with the interaction of each cell. Stored append-only with the configuration it ran "
    "with; the results are conditional on the stated assumptions — not forecasts.",
    responses={**NOT_FOUND, **CHANGED_MODEL, **ANALYSIS_BUSY},
)
def create_execution_analysis(
    session: SessionDep,
    execution_id: uuid.UUID,
    payload: Annotated[MonteCarloRequest | JointSensitivityRequest, Body(discriminator="kind")],
    response: Response,
) -> ScenarioAnalysisRead:
    analysis = scenario_analyses.create_analysis(session, execution_id, payload)
    response.headers["Location"] = (
        f"/api/v1/scenario-executions/{execution_id}/analyses/{analysis.id}"
    )
    return analysis


@executions_router.get(
    "/{execution_id}/analyses",
    response_model=ScenarioAnalysisList,
    summary="List an execution's analyses",
    description="Newest first, with the settings that distinguish them (quantities, draws, "
    "seed) and a headline figure; read one for its results and configuration.",
    responses=NOT_FOUND,
)
def list_execution_analyses(session: SessionDep, execution_id: uuid.UUID) -> ScenarioAnalysisList:
    return scenario_analyses.list_analyses(session, execution_id)


@executions_router.get(
    "/{execution_id}/analyses/{analysis_id}",
    response_model=ScenarioAnalysisRead,
    summary="Get an analysis",
    responses=NOT_FOUND,
)
def get_execution_analysis(
    session: SessionDep, execution_id: uuid.UUID, analysis_id: uuid.UUID
) -> ScenarioAnalysisRead:
    return scenario_analyses.get_analysis(session, execution_id, analysis_id)


@executions_router.post(
    "/{execution_id}/analyses/{analysis_id}/verify",
    response_model=AnalysisVerificationRead,
    summary="Run an analysis again and compare",
    description="Runs the stored request again — with its seed — on the execution's stored "
    "runs and compares the hashes. Stores nothing.",
    responses={**NOT_FOUND, **CHANGED_MODEL, **ANALYSIS_BUSY},
)
def verify_execution_analysis(
    session: SessionDep, execution_id: uuid.UUID, analysis_id: uuid.UUID
) -> AnalysisVerificationRead:
    return scenario_analyses.verify_analysis(session, execution_id, analysis_id)


@comparisons_router.get(
    "",
    response_model=ComparisonRead,
    summary="Compare executions",
    description="2–6 completed executions side by side: lines, metrics, differences against "
    "the reference (only when currency and horizon match), the inputs and assumptions that "
    "differ, pathway differences and sensitivity rankings. Nothing is ranked or recommended.",
    responses={**NOT_FOUND, **NOT_READY},
)
def compare_executions(
    session: SessionDep,
    execution_id: Annotated[list[uuid.UUID], Query(min_length=2, max_length=6)],
    reference: Annotated[uuid.UUID | None, Query(description="Default: the first.")] = None,
) -> ComparisonRead:
    return scenario_lab.compare_executions(session, execution_id, reference)


@templates_router.get(
    "",
    response_model=TemplateList,
    summary="List scenario templates",
    description="Starting points built on implemented models, and the ones that are not "
    "offered, with the reason.",
)
def list_templates(session: SessionDep) -> TemplateList:
    return scenario_lab.list_templates(session)


@templates_router.get(
    "/{template_id}",
    response_model=TemplateRead,
    summary="Get a scenario template",
    description="Its changes and models; the required and optional inputs, validation "
    "rules and expected outputs derived from the models' definitions; and the scenario body "
    "to start from (it holds no company figures: RUMIN never fills those in).",
    responses=NOT_FOUND,
)
def get_template(session: SessionDep, template_id: TemplateId) -> TemplateRead:
    return scenario_lab.get_template(session, template_id)
