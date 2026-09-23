"""Scenario workspace endpoints. Drafts only — a scenario has no "run" endpoint; model runs
are the separate ``/simulations`` resource."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import NOT_FOUND, PaginationDep, SessionDep
from app.schemas.scenario import ScenarioInput, ScenarioPage, ScenarioRead
from app.services import scenarios

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=ScenarioPage, summary="List scenarios")
def list_scenarios(session: SessionDep, page: PaginationDep) -> ScenarioPage:
    return scenarios.list_scenarios(session, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft scenario",
    description="Stores scenario *inputs*. Nothing is simulated: `latest_run` stays null "
    "until drafts are connected to the simulation engine (Phase 5 Scenario Lab).",
)
def create_scenario(
    session: SessionDep, payload: ScenarioInput, response: Response
) -> ScenarioRead:
    scenario = scenarios.create_scenario(session, payload)
    response.headers["Location"] = f"/api/v1/scenarios/{scenario.id}"
    return scenario


@router.get(
    "/{scenario_id}", response_model=ScenarioRead, summary="Get a scenario", responses=NOT_FOUND
)
def get_scenario(session: SessionDep, scenario_id: uuid.UUID) -> ScenarioRead:
    return scenarios.get_scenario(session, scenario_id)


@router.put(
    "/{scenario_id}",
    response_model=ScenarioRead,
    summary="Replace a scenario's configuration",
    responses=NOT_FOUND,
)
def replace_scenario(
    session: SessionDep, scenario_id: uuid.UUID, payload: ScenarioInput
) -> ScenarioRead:
    return scenarios.replace_scenario(session, scenario_id, payload)


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scenario",
    responses=NOT_FOUND,
)
def delete_scenario(session: SessionDep, scenario_id: uuid.UUID) -> Response:
    scenarios.delete_scenario(session, scenario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
