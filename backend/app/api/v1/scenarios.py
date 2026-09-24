"""Scenarios, their versions, plans and previews, and requesting executions.

A scenario is a name with immutable, numbered versions: ``PUT`` saves a new version (and
never overwrites one), ``POST …/duplicate`` copies a version into a new scenario and
``POST …/versions/{n}/restore`` saves an earlier version's content as the newest. A plan
says which models apply and why; a preview computes results without storing anything. An
execution is requested with ``POST …/executions`` and read from ``/scenario-executions``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import NOT_FOUND, PaginationDep, RunnerDep, SessionDep
from app.schemas.common import ErrorResponse
from app.schemas.scenario import (
    ExecutionPage,
    ExecutionRead,
    ExecutionRequest,
    PlanRead,
    PreviewRead,
    ScenarioDuplicateRequest,
    ScenarioInput,
    ScenarioPage,
    ScenarioRead,
    ScenarioUpdate,
    VersionRead,
    VersionSummaryRead,
)
from app.services import scenario_lab, scenarios

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "The request conflicts with stored state."}
}
BUSY: dict[int | str, dict[str, Any]] = {
    429: {
        "model": ErrorResponse,
        "description": "Every worker is busy and the queue is full; nothing was stored.",
    }
}
VersionNumber = Annotated[int, Path(ge=1, le=100_000)]
VersionQuery = Annotated[int | None, Query(ge=1, le=100_000, description="Default: the latest.")]


@router.get("", response_model=ScenarioPage, summary="List scenarios")
def list_scenarios(session: SessionDep, page: PaginationDep) -> ScenarioPage:
    return scenarios.list_scenarios(session, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a scenario",
    description="Stores version 1 of a scenario: its changes, company, figures, timing, "
    "models, assumptions, constraints and stress cases. Nothing is simulated: execute it "
    "with `POST /scenarios/{id}/executions`. A draft may be incomplete; it may not be "
    "malformed (every problem is reported with its field).",
)
def create_scenario(
    session: SessionDep, payload: ScenarioInput, response: Response
) -> ScenarioRead:
    scenario = scenarios.create_scenario(session, payload)
    response.headers["Location"] = f"/api/v1/scenarios/{scenario.id}"
    return scenario


@router.post(
    "/plan",
    response_model=PlanRead,
    summary="Plan a draft scenario",
    description="Which models apply to the scenario and why, what each still needs, which "
    "changes no included model simulates, the constraints, the stress cases and the "
    "companies the knowledge graph ties to the changes. Stores nothing. Always 200: "
    "`executable` says whether it could run; `issues` say why not.",
)
def plan_scenario(session: SessionDep, payload: ScenarioInput) -> PlanRead:
    return scenarios.plan_draft(session, payload)


@router.post(
    "/preview",
    response_model=PreviewRead,
    summary="Preview a draft scenario",
    description="The plan and, when the scenario can run, its results computed by the same "
    "engine — without storing anything (for live what-if values while editing). Execute "
    "the scenario to keep a reproducible record.",
)
def preview_scenario(session: SessionDep, payload: ScenarioInput) -> PreviewRead:
    return scenarios.preview(session, payload)


@router.get(
    "/{scenario_id}", response_model=ScenarioRead, summary="Get a scenario", responses=NOT_FOUND
)
def get_scenario(session: SessionDep, scenario_id: uuid.UUID) -> ScenarioRead:
    return scenarios.get_scenario(session, scenario_id)


@router.put(
    "/{scenario_id}",
    response_model=ScenarioRead,
    summary="Save a new version of a scenario",
    description="Saves the body as a new version; earlier versions are never changed. A body "
    "identical to the latest version adds no version. With `base_version`, a save based on "
    "an older version than the latest is refused (409) so no change is lost.",
    responses={**NOT_FOUND, **CONFLICT},
)
def save_scenario(
    session: SessionDep, scenario_id: uuid.UUID, payload: ScenarioUpdate
) -> ScenarioRead:
    return scenarios.save_version(session, scenario_id, payload)


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scenario",
    description="Only a scenario that has never been executed can be deleted (409 "
    "otherwise): executions stay reproducible.",
    responses={**NOT_FOUND, **CONFLICT},
)
def delete_scenario(session: SessionDep, scenario_id: uuid.UUID) -> Response:
    scenarios.delete_scenario(session, scenario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{scenario_id}/duplicate",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a scenario",
    description="A new scenario whose version 1 is a copy of the chosen version, recording "
    "where it came from.",
    responses=NOT_FOUND,
)
def duplicate_scenario(
    session: SessionDep,
    scenario_id: uuid.UUID,
    payload: ScenarioDuplicateRequest,
    response: Response,
) -> ScenarioRead:
    scenario = scenarios.duplicate_scenario(session, scenario_id, payload)
    response.headers["Location"] = f"/api/v1/scenarios/{scenario.id}"
    return scenario


@router.get(
    "/{scenario_id}/versions",
    response_model=list[VersionSummaryRead],
    summary="List a scenario's versions",
    responses=NOT_FOUND,
)
def list_versions(session: SessionDep, scenario_id: uuid.UUID) -> list[VersionSummaryRead]:
    return scenarios.list_versions(session, scenario_id)


@router.get(
    "/{scenario_id}/versions/{version}",
    response_model=VersionRead,
    summary="Get one version of a scenario",
    responses=NOT_FOUND,
)
def get_version(session: SessionDep, scenario_id: uuid.UUID, version: VersionNumber) -> VersionRead:
    return scenarios.get_version(session, scenario_id, version)


@router.post(
    "/{scenario_id}/versions/{version}/restore",
    response_model=ScenarioRead,
    summary="Restore an earlier version",
    description="Saves the chosen version's content as the newest version. Nothing is "
    "deleted or rewritten.",
    responses={**NOT_FOUND, **CONFLICT},
)
def restore_version(
    session: SessionDep, scenario_id: uuid.UUID, version: VersionNumber
) -> ScenarioRead:
    return scenarios.restore_version(session, scenario_id, version)


@router.get(
    "/{scenario_id}/plan",
    response_model=PlanRead,
    summary="Plan a saved version",
    responses=NOT_FOUND,
)
def plan_version(
    session: SessionDep, scenario_id: uuid.UUID, version: VersionQuery = None
) -> PlanRead:
    return scenarios.plan_version(session, scenario_id, version)


@router.post(
    "/{scenario_id}/executions",
    response_model=ExecutionRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute a scenario version",
    description="Checks the plan (a scenario that cannot run is refused with every reason, "
    "422, and nothing is stored), then queues the execution on a bounded worker pool (429 "
    "when it is full). Follow it at `Location`: its status moves through validating, "
    "simulating, propagating and aggregating to completed, failed or cancelled.",
    responses={**NOT_FOUND, **BUSY},
)
def create_execution(
    session: SessionDep,
    runner: RunnerDep,
    scenario_id: uuid.UUID,
    payload: ExecutionRequest,
    response: Response,
) -> ExecutionRead:
    execution = scenario_lab.create_execution(session, runner, scenario_id, payload)
    response.headers["Location"] = f"/api/v1/scenario-executions/{execution.id}"
    return execution


@router.get(
    "/{scenario_id}/executions",
    response_model=ExecutionPage,
    summary="List a scenario's executions",
    description="Newest first, every version, with their status and headline results.",
    responses=NOT_FOUND,
)
def list_executions(
    session: SessionDep, scenario_id: uuid.UUID, page: PaginationDep
) -> ExecutionPage:
    return scenario_lab.list_executions(session, scenario_id, limit=page.limit, offset=page.offset)
