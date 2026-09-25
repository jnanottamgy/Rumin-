"""Application errors and the handlers that turn them into consistent JSON responses.

Every error leaves the API in the same envelope (see ``ErrorResponse``)::

    {"error": {"code": "not_found", "message": "...", "details": [...], "request_id": "..."}}

Unexpected exceptions are logged with a traceback server-side, but the client only
ever receives a generic message — internal details are never leaked.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, cast, get_args

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx
from app.schemas.common import ErrorBody, ErrorDetail, ErrorLocation, ErrorResponse

logger = logging.getLogger(__name__)

_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}

_DEFAULT_MESSAGES: dict[int, str] = {
    404: "The requested resource was not found.",
    405: "This HTTP method is not allowed for the requested resource.",
    413: "The request body is too large.",
    500: "An unexpected error occurred. The error has been logged.",
}

# Starlette's default reason phrases; they are replaced by the friendlier messages above.
_GENERIC_DETAILS = {"Not Found", "Method Not Allowed", "Request Entity Too Large"}


class AppError(Exception):
    """Base class for errors that map to a specific HTTP response."""

    status_code = 500
    code = "internal_error"
    default_message = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: Sequence[ErrorDetail] = ()):
        self.message = message or self.default_message
        self.details = list(details)
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    """The request conflicts with stored state (e.g. a model version whose stored
    definition differs from the code)."""

    status_code = 409
    code = "conflict"
    default_message = "The request conflicts with stored data."


class DomainValidationError(AppError):
    """Input is well-formed but violates a domain rule (e.g. unknown variable)."""

    status_code = 422
    code = "validation_error"
    default_message = "The request contains invalid values."


def error_payload(
    status_code: int,
    message: str,
    *,
    code: str | None = None,
    details: Sequence[ErrorDetail] = (),
) -> dict[str, Any]:
    body = ErrorBody(
        code=code or _STATUS_CODES.get(status_code, "http_error"),
        message=message,
        details=list(details),
        request_id=request_id_ctx.get(),
    )
    return ErrorResponse(error=body).model_dump(mode="json")


_LOCATIONS: tuple[str, ...] = get_args(ErrorLocation)


def format_location(loc: Sequence[str | int]) -> tuple[ErrorLocation | None, str | None]:
    """Convert a Pydantic error location to ``(location, "shocks[0].value")``."""
    parts = list(loc)
    location: ErrorLocation | None = None
    if parts and parts[0] in _LOCATIONS:
        location = cast(ErrorLocation, parts.pop(0))
    field = ""
    for part in parts:
        if isinstance(part, int):
            field += f"[{part}]"
        else:
            field += f".{part}" if field else str(part)
    return location, field or None


def _validation_details(exc: RequestValidationError) -> list[ErrorDetail]:
    details: list[ErrorDetail] = []
    for error in exc.errors():
        error_type = str(error.get("type", ""))
        if error_type == "json_invalid":
            details.append(
                ErrorDetail(
                    location="body", message="Request body is not valid JSON.", type=error_type
                )
            )
            continue
        location, field = format_location(error.get("loc", ()))
        message = str(error.get("msg", "Invalid value.")).removeprefix("Value error, ")
        details.append(
            ErrorDetail(
                location=location,
                field=field,
                message=message,
                type=error_type or None,
            )
        )
    return details


# Starlette types every handler as (Request, Exception); each handler is only ever
# registered for its own exception class, so the casts below are safe.


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)
    return JSONResponse(
        error_payload(error.status_code, error.message, code=error.code, details=error.details),
        status_code=error.status_code,
        headers=getattr(error, "headers", None),
    )


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    details = _validation_details(cast(RequestValidationError, exc))
    return JSONResponse(
        error_payload(422, "The request contains invalid values.", details=details),
        status_code=422,
    )


async def _http_error_handler(_: Request, error: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, error)
    if exc.status_code >= 500:
        message = _DEFAULT_MESSAGES[500]
    elif isinstance(exc.detail, str) and exc.detail and exc.detail not in _GENERIC_DETAILS:
        message = exc.detail
    else:
        message = _DEFAULT_MESSAGES.get(exc.status_code, "The request could not be processed.")
    return JSONResponse(
        error_payload(exc.status_code, message),
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


async def _database_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Connection failures and missing tables surface as OperationalError. The client gets
    # a generic 503; the underlying driver message stays in the server log.
    logger.error("Database unavailable: %s", exc)
    return JSONResponse(
        error_payload(
            503,
            "The database is unavailable or its schema is not up to date. "
            "See GET /health/ready for details.",
        ),
        status_code=503,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(OperationalError, _database_error_handler)
    # Unhandled exceptions are caught by RequestContextMiddleware, which logs the
    # traceback and returns a generic 500 envelope.
