"""Shared FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_session
from app.scenario_lab.runner import ExecutionRunner
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, ErrorResponse

SessionDep = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_scenario_runner(request: Request) -> ExecutionRunner:
    runner: ExecutionRunner = request.app.state.scenario_runner
    return runner


RunnerDep = Annotated[ExecutionRunner, Depends(get_scenario_runner)]


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
ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "The request contains invalid values."},
    500: {"model": ErrorResponse, "description": "Unexpected server error (details are logged)."},
}
