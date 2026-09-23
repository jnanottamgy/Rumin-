"""Liveness and readiness probes (unversioned, as infrastructure expects)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.api.deps import SessionDep
from app.schemas.system import HealthResponse, ReadinessResponse
from app.services.system import SERVICE_NAME, check_readiness

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns 200 whenever the process is serving requests. Does not touch "
    "the database, so a database outage does not make the process look dead.",
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=__version__)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Returns 200 when the database is reachable, migrations are current and a "
    "dataset is loaded; otherwise 503 with the failing checks.",
    responses={503: {"model": ReadinessResponse, "description": "Not ready."}},
)
def ready(session: SessionDep) -> JSONResponse:
    result = check_readiness(session)
    status_code = 200 if result.status == "ready" else 503
    return JSONResponse(result.model_dump(mode="json"), status_code=status_code)
