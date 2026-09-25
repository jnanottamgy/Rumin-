"""Shared FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.throttle import ClientThrottle
from app.core.config import Settings
from app.db.session import get_session
from app.scenario_lab.runner import ExecutionRunner
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, ErrorResponse
from app.services import auth
from app.services.auth import Principal

SessionDep = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_scenario_runner(request: Request) -> ExecutionRunner:
    runner: ExecutionRunner = request.app.state.scenario_runner
    return runner


RunnerDep = Annotated[ExecutionRunner, Depends(get_scenario_runner)]


# --- Who is asking (Phase 10) --------------------------------------------------------------------


def client_address(request: Request) -> str:
    """The client's address (behind a proxy, the address it forwarded — see the deployment
    guide for uvicorn's ``--forwarded-allow-ips``)."""
    return request.client.host if request.client else "unknown"


ClientDep = Annotated[str, Depends(client_address)]


def get_login_throttle(request: Request) -> ClientThrottle:
    throttle: ClientThrottle = request.app.state.login_throttle
    return throttle


ThrottleDep = Annotated[ClientThrottle, Depends(get_login_throttle)]


def current_principal(request: Request, session: SessionDep, settings: SettingsDep) -> Principal:
    """The signed-in person, whether or not they must still change their password."""
    token = request.cookies.get(settings.session_cookie_name, "")
    principal = auth.resolve(session, token, settings) if token else None
    if principal is None:
        raise auth.NotSignedIn(
            "Your session has ended. Sign in again." if token else "Sign in to continue."
        )
    request.state.principal = principal
    return principal


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def active_principal(principal: PrincipalDep) -> Principal:
    """The signed-in person, once they have chosen their own password."""
    if principal.must_change_password:
        raise auth.PasswordChangeRequired()
    return principal


UserDep = Annotated[Principal, Depends(active_principal)]


def writer(user: UserDep) -> Principal:
    if not user.can_write:
        raise auth.PermissionDenied(
            "Your role can read the workspace but not change it. An administrator can give "
            "you the analyst role."
        )
    return user


WriterDep = Annotated[Principal, Depends(writer)]


def administrator(user: UserDep) -> Principal:
    if not user.is_admin:
        raise auth.PermissionDenied("Only administrators can do this.")
    return user


AdminDep = Annotated[Principal, Depends(administrator)]


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: Annotated[
        int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Maximum number of items to return.")
    ] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0, le=1_000_000, description="Items to skip.")] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(pagination)]

# Documented error responses (every error uses the same envelope).
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found."}
}
FORBIDDEN: dict[int | str, dict[str, Any]] = {
    403: {
        "model": ErrorResponse,
        "description": "Signed in, but the role or ownership does not allow this.",
    }
}
ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "The request contains invalid values."},
    500: {"model": ErrorResponse, "description": "Unexpected server error (details are logged)."},
}
SIGNED_IN: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in, or the session has ended."},
    403: {
        "model": ErrorResponse,
        "description": "Not allowed for this role or resource, a cross-site request, or a "
        "password that must be changed first (`password_change_required`).",
    },
}
