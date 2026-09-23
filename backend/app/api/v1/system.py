from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SessionDep, SettingsDep
from app.schemas.system import SystemStatus
from app.services.system import get_system_status

router = APIRouter(tags=["system"])


@router.get(
    "/system",
    response_model=SystemStatus,
    summary="System status",
    description="Environment, database and migration state, the loaded dataset, and the "
    "capabilities this build does and does not have.",
)
def system_status(session: SessionDep, settings: SettingsDep) -> SystemStatus:
    return get_system_status(session, settings)
