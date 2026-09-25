"""Accounts, sessions and security events (Phase 10).

Passwords are never stripped or echoed: the models that carry them keep whitespace exactly
as typed, and no response contains a password, a hash or a session token.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ApiModel, SafeText

Role = Literal["viewer", "analyst", "admin"]
Permission = Literal["read", "write", "administer"]

EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{1,60}$"


def _email(value: str) -> str:
    return value.strip().lower()


Email = Annotated[str, AfterValidator(_email), Field(max_length=254, pattern=EMAIL_PATTERN)]
# Checked against the password policy by the service, which names every problem.
Password = Annotated[str, Field(min_length=1, max_length=256)]


class _PasswordInput(BaseModel):
    """Strict like every input, but whitespace in a password is kept as typed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class LoginRequest(_PasswordInput):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Password

    @field_validator("email")
    @classmethod
    def _normalise(cls, value: str) -> str:
        return _email(value)


class PasswordChangeRequest(_PasswordInput):
    current_password: Password
    new_password: Password


class PasswordResetRequest(_PasswordInput):
    temporary_password: Password = Field(
        description="A password the person must replace at their next sign-in."
    )


class UserCreateRequest(_PasswordInput):
    email: Email
    name: Annotated[SafeText, Field(min_length=1, max_length=120)]
    role: Role
    temporary_password: Password = Field(
        description="A password the person must replace at their first sign-in."
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Give the person's name.")
        return stripped


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[SafeText, Field(min_length=1, max_length=120)] | None = None
    role: Role | None = None
    is_active: bool | None = Field(
        default=None, description="False deactivates the account and ends its sessions."
    )


class UserRead(ApiModel):
    id: uuid.UUID
    email: str
    name: str
    role: Role
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    password_changed_at: datetime
    created_at: datetime


class UserList(ApiModel):
    items: list[UserRead]


class CurrentSessionRead(ApiModel):
    user: UserRead
    permissions: list[Permission] = Field(
        description="What the role allows: read the workspace, write (create and run), "
        "administer (people and sessions)."
    )
    expires_at: datetime = Field(description="When the session ends, whatever happens.")
    idle_expires_at: datetime = Field(description="When it ends if no request arrives before.")


class PersonRef(ApiModel):
    id: uuid.UUID
    name: str


class AuditEventRead(ApiModel):
    id: uuid.UUID
    occurred_at: datetime
    event: str
    actor: PersonRef | None
    subject: PersonRef | None
    client: str | None
    request_id: str | None
    detail: dict[str, Any]


class AuditEventList(ApiModel):
    items: list[AuditEventRead]
