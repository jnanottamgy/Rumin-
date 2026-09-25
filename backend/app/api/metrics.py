"""Operational metrics (Phase 10), beside the health probes and outside the versioned API.

Read by the scrapers listed in ``RUMIN_METRICS_ALLOWED_CLIENTS`` without signing in, and by
administrators; everyone else is refused. The values are counts and durations only — no
person, scenario or figure appears in them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import ClientDep, SessionDep, SettingsDep
from app.core.metrics import Metrics
from app.schemas.common import ErrorResponse
from app.services import auth

router = APIRouter(tags=["health"])

PROMETHEUS_TEXT = "text/plain; version=0.0.4; charset=utf-8"

REFUSED: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not a listed scraper, and not signed in."},
    403: {"model": ErrorResponse, "description": "Signed in, but not an administrator."},
}


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Operational metrics",
    description="Requests by route template and status, their durations, requests in "
    "flight, security events by kind and the scenario and analyst queues, in the "
    "Prometheus text format. For the scrapers listed in `RUMIN_METRICS_ALLOWED_CLIENTS` and "
    "for administrators.",
    responses={200: {"content": {PROMETHEUS_TEXT: {}}}, **REFUSED},
)
def read_metrics(
    request: Request, session: SessionDep, settings: SettingsDep, client: ClientDep
) -> PlainTextResponse:
    if client not in settings.metrics_allowed_clients:
        token = request.cookies.get(settings.session_cookie_name, "")
        principal = auth.resolve(session, token, settings) if token else None
        if principal is None:
            raise auth.NotSignedIn()
        if principal.must_change_password:
            raise auth.PasswordChangeRequired()
        if not principal.is_admin:
            raise auth.PermissionDenied(
                "Only administrators and the configured scrapers read the metrics."
            )
    metrics: Metrics = request.app.state.metrics
    return PlainTextResponse(metrics.render(), media_type=PROMETHEUS_TEXT)
