"""People and the security audit trail — administrators only (Phase 10).

There is no self-registration: an administrator creates each account with a temporary
password, which its owner must replace at the first sign-in. Accounts are deactivated, never
deleted, so everything a person made keeps its author. The last active administrator cannot
be demoted or deactivated.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import NOT_FOUND, AdminDep, ClientDep, SessionDep
from app.schemas.auth import (
    AuditEventList,
    PasswordResetRequest,
    UserCreateRequest,
    UserList,
    UserRead,
    UserUpdateRequest,
)
from app.schemas.common import ErrorResponse
from app.services import auth

router = APIRouter(tags=["accounts"])

CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {
        "model": ErrorResponse,
        "description": "The e-mail address already has an account, or the change would leave "
        "no active administrator.",
    }
}


@router.get("/users", response_model=UserList, summary="List people")
def list_users(session: SessionDep, _: AdminDep) -> UserList:
    return auth.list_users(session)


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description="With a temporary password the person must replace at their first sign-in.",
    responses=CONFLICT,
)
def create_user(
    session: SessionDep,
    admin: AdminDep,
    client: ClientDep,
    payload: UserCreateRequest,
    response: Response,
) -> UserRead:
    user = auth.create_user(session, payload, actor=admin.id, client=client)
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return user


@router.put(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Change a person's name, role or whether the account is active",
    description="Deactivating an account ends its sessions.",
    responses={**NOT_FOUND, **CONFLICT},
)
def update_user(
    session: SessionDep,
    admin: AdminDep,
    client: ClientDep,
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
) -> UserRead:
    return auth.update_user(session, user_id, payload, actor=admin, client=client)


@router.post(
    "/users/{user_id}/password",
    response_model=UserRead,
    summary="Reset a person's password",
    description="Sets a temporary password the person must replace at their next sign-in, "
    "ends their sessions and lifts any lock.",
    responses=NOT_FOUND,
)
def reset_password(
    session: SessionDep,
    admin: AdminDep,
    client: ClientDep,
    user_id: uuid.UUID,
    payload: PasswordResetRequest,
) -> UserRead:
    return auth.reset_password(
        session, user_id, payload.temporary_password, actor=admin, client=client
    )


@router.post(
    "/users/{user_id}/sessions/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign a person out everywhere",
    responses=NOT_FOUND,
)
def revoke_sessions(
    session: SessionDep, admin: AdminDep, client: ClientDep, user_id: uuid.UUID
) -> Response:
    auth.revoke_sessions(session, user_id, actor=admin, client=client)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/audit-events",
    response_model=AuditEventList,
    summary="The security audit trail",
    description="Sign-ins (successful, failed, throttled), sign-outs, password changes and "
    "resets, and changes to people and their sessions, newest first. Never a password or a "
    "token.",
)
def list_audit_events(
    session: SessionDep,
    _: AdminDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> AuditEventList:
    return auth.list_events(session, limit=limit)
