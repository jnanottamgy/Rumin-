"""People, sign-in, sessions and security events (Phase 10).

Sign-in checks the e-mail and password (Argon2id), refuses with one message whatever was
wrong, and slows guessing twice over: an account is locked after consecutive failures (in
the database), and a client address that fails too often must wait (in memory). A session is
a random token held in an ``HttpOnly`` cookie and stored as its SHA-256; it ends when idle,
at its maximum age, on sign-out, on a password change or reset, or when an administrator
revokes it or deactivates the account. Every one of those events is written to the audit
trail — never a password, a hash or a token.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import passwords, tokens
from app.auth.throttle import ClientThrottle
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, DomainValidationError, NotFoundError
from app.core.logging import request_id_ctx
from app.db.base import utcnow
from app.models.auth import AuditEvent, User, UserSession
from app.schemas.auth import (
    AuditEventList,
    AuditEventRead,
    CurrentSessionRead,
    PersonRef,
    UserCreateRequest,
    UserList,
    UserRead,
    UserUpdateRequest,
)
from app.schemas.common import ErrorDetail

logger = logging.getLogger(__name__)

WRITE_ROLES = frozenset({"analyst", "admin"})
PERMISSIONS = {
    "viewer": ["read"],
    "analyst": ["read", "write"],
    "admin": ["read", "write", "administer"],
}
# A session's last-seen time is written at most this often (reads stay cheap).
TOUCH_INTERVAL = timedelta(seconds=60)
BAD_CREDENTIALS = "The e-mail address or password is incorrect."


class NotSignedIn(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "Sign in to continue."


class BadCredentials(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = BAD_CREDENTIALS


class PermissionDenied(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "Your role does not allow this."


class PasswordChangeRequired(AppError):
    status_code = 403
    code = "password_change_required"
    default_message = "Choose a new password before continuing."


class TooManyAttempts(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after: int) -> None:
        minutes = max(1, round(retry_after / 60))
        super().__init__(
            f"Too many sign-in attempts. Try again in {minutes} minute{'s' if minutes > 1 else ''}."
        )
        self.headers = {"Retry-After": str(retry_after)}


@dataclass(frozen=True)
class Principal:
    """Who is making a request, as their session says."""

    id: uuid.UUID
    email: str
    name: str
    role: str
    must_change_password: bool
    session_id: uuid.UUID
    expires_at: datetime
    idle_expires_at: datetime

    @property
    def can_write(self) -> bool:
        return self.role in WRITE_ROLES

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# --- The audit trail -----------------------------------------------------------------------------


def record(
    session: Session,
    event: str,
    *,
    actor: uuid.UUID | None = None,
    subject: uuid.UUID | None = None,
    client: str | None = None,
    detail: dict[str, object] | None = None,
) -> None:
    """Add a security event to the session (committed with the change it describes)."""
    request_id = request_id_ctx.get()
    session.add(
        AuditEvent(
            event=event,
            actor_id=actor,
            subject_id=subject,
            client=(client or None) and client[:64],
            request_id=None if request_id == "-" else request_id,
            detail=detail or {},
        )
    )
    logger.info("Security event %s (actor %s, subject %s)", event, actor, subject)


# --- People --------------------------------------------------------------------------------------


def _policy_error(problems: Sequence[str], field: str) -> DomainValidationError:
    return DomainValidationError(
        "The password does not meet the policy.",
        details=[
            ErrorDetail(location="body", field=field, message=problem, type="password_policy")
            for problem in problems
        ],
    )


def user_read(user: User) -> UserRead:
    return UserRead.model_validate(user)


def people(session: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, PersonRef]:
    """The names behind account ids, for showing who owns or made something."""
    wanted = {item for item in ids if item is not None}
    if not wanted:
        return {}
    return {
        user.id: PersonRef(id=user.id, name=user.name)
        for user in session.scalars(select(User).where(User.id.in_(wanted)))
    }


def user_or_404(session: Session, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"No person with id {user_id}.")
    return user


def create_user(
    session: Session,
    payload: UserCreateRequest,
    *,
    actor: uuid.UUID | None,
    client: str | None = None,
    must_change_password: bool = True,
) -> UserRead:
    problems = passwords.password_problems(
        payload.temporary_password, email=payload.email, name=payload.name
    )
    if problems:
        raise _policy_error(problems, "temporary_password")
    if session.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise ConflictError(f"{payload.email} already has an account.")
    user = User(
        email=payload.email,
        name=payload.name,
        role=payload.role,
        password_hash=passwords.hash_password(payload.temporary_password),
        must_change_password=must_change_password,
        is_active=True,
        failed_logins=0,
    )
    session.add(user)
    session.flush()
    record(
        session,
        "user_created",
        actor=actor,
        subject=user.id,
        client=client,
        detail={"role": payload.role},
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ConflictError(f"{payload.email} already has an account.") from error
    return user_read(user)


def list_users(session: Session) -> UserList:
    rows = session.scalars(select(User).order_by(User.name, User.email)).all()
    return UserList(items=[user_read(row) for row in rows])


def _active_admins(session: Session) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
        )
        or 0
    )


def update_user(
    session: Session,
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    *,
    actor: Principal,
    client: str | None = None,
) -> UserRead:
    user = user_or_404(session, user_id)
    changes: dict[str, object] = {}
    losing_admin = (
        user.role == "admin"
        and user.is_active
        and ((payload.role is not None and payload.role != "admin") or payload.is_active is False)
    )
    if losing_admin and _active_admins(session) <= 1:
        raise ConflictError(
            "This is the only active administrator: make someone else an administrator first."
        )
    if payload.name is not None and payload.name != user.name:
        changes["name"] = [user.name, payload.name]
        user.name = payload.name
    if payload.role is not None and payload.role != user.role:
        changes["role"] = [user.role, payload.role]
        user.role = payload.role
    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = [user.is_active, payload.is_active]
        user.is_active = payload.is_active
        if not payload.is_active:
            revoke_all(session, user.id)
    if changes:
        record(
            session, "user_updated", actor=actor.id, subject=user.id, client=client, detail=changes
        )
        session.commit()
    return user_read(user)


def reset_password(
    session: Session,
    user_id: uuid.UUID,
    temporary_password: str,
    *,
    actor: Principal,
    client: str | None = None,
) -> UserRead:
    user = user_or_404(session, user_id)
    problems = passwords.password_problems(temporary_password, email=user.email, name=user.name)
    if problems:
        raise _policy_error(problems, "temporary_password")
    user.password_hash = passwords.hash_password(temporary_password)
    user.password_changed_at = utcnow()
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    revoke_all(session, user.id)
    record(session, "password_reset", actor=actor.id, subject=user.id, client=client)
    session.commit()
    return user_read(user)


def set_password(session: Session, email: str, password: str) -> None:
    """For the command line: set a person's password, which they keep (no forced change)."""
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise NotFoundError(f"No account for {email}.")
    problems = passwords.password_problems(password, email=user.email, name=user.name)
    if problems:
        raise _policy_error(problems, "password")
    user.password_hash = passwords.hash_password(password)
    user.password_changed_at = utcnow()
    user.must_change_password = False
    user.failed_logins = 0
    user.locked_until = None
    revoke_all(session, user.id)
    record(session, "password_reset", subject=user.id, detail={"via": "command line"})
    session.commit()


# --- Sessions ------------------------------------------------------------------------------------


def revoke_all(session: Session, user_id: uuid.UUID, *, keep: uuid.UUID | None = None) -> int:
    statement = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    if keep is not None:
        statement = statement.where(UserSession.id != keep)
    result = session.execute(statement)
    return int(getattr(result, "rowcount", 0) or 0)


def revoke_sessions(
    session: Session, user_id: uuid.UUID, *, actor: Principal, client: str | None = None
) -> int:
    user = user_or_404(session, user_id)
    ended = revoke_all(session, user.id)
    record(
        session,
        "sessions_revoked",
        actor=actor.id,
        subject=user.id,
        client=client,
        detail={"sessions": ended},
    )
    session.commit()
    return ended


def _lock_duration(failures: int, settings: Settings) -> timedelta:
    over = failures - settings.login_max_failures
    minutes = min(2**over, settings.login_lock_max_minutes)
    return timedelta(minutes=minutes)


def sign_in(
    session: Session,
    *,
    email: str,
    password: str,
    client: str,
    settings: Settings,
    throttle: ClientThrottle,
) -> tuple[str, Principal]:
    """Check the credentials and open a session: the token for the cookie, and who it is."""
    wait = throttle.retry_after(client)
    if wait:
        record(session, "login_throttled", client=client, detail={"scope": "client"})
        session.commit()
        raise TooManyAttempts(wait)
    now = utcnow()
    user = session.scalar(select(User).where(User.email == email))
    if user is not None and user.locked_until is not None and user.locked_until > now:
        record(
            session, "login_throttled", subject=user.id, client=client, detail={"scope": "account"}
        )
        session.commit()
        raise TooManyAttempts(max(1, int((user.locked_until - now).total_seconds()) + 1))
    if user is None:
        passwords.burn_verification(password)
        throttle.failed(client)
        record(session, "login_failed", client=client, detail={"reason": "unknown_account"})
        session.commit()
        raise BadCredentials()
    if not passwords.verify_password(user.password_hash, password) or not user.is_active:
        reason = "inactive" if user.is_active is False else "wrong_password"
        if reason == "wrong_password":
            user.failed_logins += 1
            if user.failed_logins >= settings.login_max_failures:
                user.locked_until = now + _lock_duration(user.failed_logins, settings)
        throttle.failed(client)
        record(session, "login_failed", subject=user.id, client=client, detail={"reason": reason})
        session.commit()
        raise BadCredentials()
    throttle.succeeded(client)
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    token = tokens.new_token()
    row = UserSession(
        user_id=user.id,
        token_hash=tokens.token_hash(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_max_hours),
    )
    session.add(row)
    session.flush()
    record(session, "login_succeeded", actor=user.id, subject=user.id, client=client)
    session.commit()
    return token, _principal(user, row, settings)


def _principal(user: User, row: UserSession, settings: Settings) -> Principal:
    idle = row.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    return Principal(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        must_change_password=user.must_change_password,
        session_id=row.id,
        expires_at=row.expires_at,
        idle_expires_at=min(idle, row.expires_at),
    )


def resolve(session: Session, token: str, settings: Settings) -> Principal | None:
    """The principal a session token belongs to, or None when the session is not valid."""
    if not token or len(token) > 128:
        return None
    row = session.scalar(
        select(UserSession).where(UserSession.token_hash == tokens.token_hash(token))
    )
    if row is None or row.revoked_at is not None:
        return None
    now = utcnow()
    idle_limit = row.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if now >= row.expires_at or now >= idle_limit:
        return None
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    if now - row.last_seen_at >= TOUCH_INTERVAL:
        row.last_seen_at = now
        session.commit()
    return _principal(user, row, settings)


def sign_out(session: Session, principal: Principal, *, client: str | None = None) -> None:
    row = session.get(UserSession, principal.session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()
    record(session, "logout", actor=principal.id, subject=principal.id, client=client)
    session.commit()


def change_password(
    session: Session,
    principal: Principal,
    *,
    current_password: str,
    new_password: str,
    settings: Settings,
    client: str | None = None,
) -> Principal:
    user = user_or_404(session, principal.id)
    if not passwords.verify_password(user.password_hash, current_password):
        record(session, "password_change_failed", actor=user.id, subject=user.id, client=client)
        session.commit()
        raise DomainValidationError(
            "The current password is incorrect.",
            details=[
                ErrorDetail(
                    location="body",
                    field="current_password",
                    message="The current password is incorrect.",
                    type="wrong_password",
                )
            ],
        )
    problems = passwords.password_problems(new_password, email=user.email, name=user.name)
    if passwords.verify_password(user.password_hash, new_password):
        problems.append("Choose a password different from the current one.")
    if problems:
        raise _policy_error(problems, "new_password")
    user.password_hash = passwords.hash_password(new_password)
    user.password_changed_at = utcnow()
    user.must_change_password = False
    ended = revoke_all(session, user.id, keep=principal.session_id)
    record(
        session,
        "password_changed",
        actor=user.id,
        subject=user.id,
        client=client,
        detail={"other_sessions_ended": ended},
    )
    session.commit()
    row = session.get(UserSession, principal.session_id)
    if row is None:  # the session was deleted while the password changed
        raise NotSignedIn("Your session has ended. Sign in again.")
    return _principal(user, row, settings)


def session_read(session: Session, principal: Principal) -> CurrentSessionRead:
    user = user_or_404(session, principal.id)
    return CurrentSessionRead(
        user=user_read(user),
        permissions=PERMISSIONS.get(user.role, ["read"]),
        expires_at=principal.expires_at,
        idle_expires_at=principal.idle_expires_at,
    )


# --- Reading the audit trail ---------------------------------------------------------------------


def list_events(session: Session, *, limit: int) -> AuditEventList:
    rows = session.scalars(
        select(AuditEvent).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id).limit(limit)
    ).all()
    people = {
        user.id: user.name
        for user in session.scalars(
            select(User).where(
                User.id.in_(
                    {row.actor_id for row in rows if row.actor_id}
                    | {row.subject_id for row in rows if row.subject_id}
                )
            )
        )
    }

    def ref(user_id: uuid.UUID | None) -> PersonRef | None:
        if user_id is None or user_id not in people:
            return None
        return PersonRef(id=user_id, name=people[user_id])

    return AuditEventList(
        items=[
            AuditEventRead(
                id=row.id,
                occurred_at=row.occurred_at,
                event=row.event,
                actor=ref(row.actor_id),
                subject=ref(row.subject_id),
                client=row.client,
                request_id=row.request_id,
                detail=row.detail,
            )
            for row in rows
        ]
    )


def prune_events(session: Session, *, older_than_days: int) -> int:
    """Delete audit events older than the retention period; returns how many."""
    cutoff = utcnow() - timedelta(days=older_than_days)
    result = session.execute(delete(AuditEvent).where(AuditEvent.occurred_at < cutoff))
    session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def prune_sessions(session: Session) -> int:
    """Delete sessions that ended more than a day ago (they can no longer be used)."""
    cutoff = utcnow() - timedelta(days=1)
    result = session.execute(
        delete(UserSession).where(
            or_(UserSession.expires_at < cutoff, UserSession.revoked_at < cutoff)
        )
    )
    session.commit()
    return int(getattr(result, "rowcount", 0) or 0)
