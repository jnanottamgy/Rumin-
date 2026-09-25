"""Signing in and out, the current session and one's own password (Phase 10).

These routes are the only ones under ``/api/v1`` that answer without a session (``login``,
``logout``) or before a required password change (``session``, ``password``). The session
token travels only in an ``HttpOnly`` cookie; no response body ever contains it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    ClientDep,
    PrincipalDep,
    SessionDep,
    SettingsDep,
    ThrottleDep,
)
from app.core.config import Settings
from app.schemas.auth import CurrentSessionRead, LoginRequest, PasswordChangeRequest
from app.schemas.common import ErrorResponse
from app.services import auth

router = APIRouter(prefix="/auth", tags=["accounts"])

SIGN_IN_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "The e-mail address or password is incorrect."},
    429: {
        "model": ErrorResponse,
        "description": "Too many failed attempts from this client or for this account; "
        "`Retry-After` says how many seconds to wait.",
    },
}
NOT_SIGNED_IN: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in, or the session has ended."}
}


def _set_cookie(response: Response, token: str, settings: Settings) -> None:
    # A browser-session cookie: it goes when the browser closes; the server's idle and
    # maximum limits end the session sooner if they come first.
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.post(
    "/login",
    response_model=CurrentSessionRead,
    summary="Sign in",
    description="Checks the e-mail address and password and opens a session held in an "
    "`HttpOnly` cookie. One message for every wrong combination; repeated failures lock the "
    "account for a while and make the client wait (429 with `Retry-After`).",
    responses=SIGN_IN_ERRORS,
)
def login(
    session: SessionDep,
    settings: SettingsDep,
    throttle: ThrottleDep,
    client: ClientDep,
    payload: LoginRequest,
    response: Response,
) -> CurrentSessionRead:
    token, principal = auth.sign_in(
        session,
        email=payload.email,
        password=payload.password,
        client=client,
        settings=settings,
        throttle=throttle,
    )
    _set_cookie(response, token, settings)
    response.headers["Cache-Control"] = "no-store"
    return auth.session_read(session, principal)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out",
    description="Ends this session and clears its cookie. Signing out without a session is "
    "not an error.",
)
def logout(
    request: Request, session: SessionDep, settings: SettingsDep, client: ClientDep
) -> Response:
    token = request.cookies.get(settings.session_cookie_name, "")
    principal = auth.resolve(session, token, settings) if token else None
    if principal is not None:
        auth.sign_out(session, principal, client=client)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_cookie(response, settings)
    return response


@router.get(
    "/session",
    response_model=CurrentSessionRead,
    summary="The current session",
    description="Who is signed in, what their role allows and when the session ends. 401 "
    "when not signed in. Answers even when the password must be changed first "
    "(`must_change_password`).",
    responses=NOT_SIGNED_IN,
)
def get_session_info(
    session: SessionDep, principal: PrincipalDep, response: Response
) -> CurrentSessionRead:
    response.headers["Cache-Control"] = "no-store"
    return auth.session_read(session, principal)


@router.post(
    "/password",
    response_model=CurrentSessionRead,
    summary="Change one's own password",
    description="Needs the current password. The new one must meet the policy (at least 12 "
    "characters, not a common password, not one's e-mail or name). Every other session of "
    "the account ends; this one continues.",
    responses=NOT_SIGNED_IN,
)
def change_password(
    session: SessionDep,
    settings: SettingsDep,
    principal: PrincipalDep,
    client: ClientDep,
    payload: PasswordChangeRequest,
) -> CurrentSessionRead:
    updated = auth.change_password(
        session,
        principal,
        current_password=payload.current_password,
        new_password=payload.new_password,
        settings=settings,
        client=client,
    )
    return auth.session_read(session, updated)
