"""Who may change what (Phase 10).

RUMIN is one shared workspace: every signed-in person reads its scenarios, runs, analyses
and findings. Changing a resource — saving a version, executing, cancelling, analysing,
deleting — is for its **owner** or an **administrator**, and only roles that write
(analyst, admin) own anything. Resources made before accounts existed have no owner; only
administrators change them. Analyst conversations are private (``services.analyst``).
"""

from __future__ import annotations

import uuid

from app.services.auth import PermissionDenied, Principal

VIEWER_MESSAGE = (
    "Your role can read the workspace but not change it. An administrator can give you the "
    "analyst role."
)


def may_change(user: Principal, owner_id: uuid.UUID | None) -> bool:
    if user.is_admin:
        return True
    return user.can_write and owner_id is not None and owner_id == user.id


def require_change(user: Principal, owner_id: uuid.UUID | None, what: str) -> None:
    """Raise 403 unless ``user`` may change a ``what`` owned by ``owner_id``."""
    if may_change(user, owner_id):
        return
    if not user.can_write:
        raise PermissionDenied(VIEWER_MESSAGE)
    raise PermissionDenied(
        f"Only the {what}'s owner or an administrator can change it. Duplicate it to work on "
        "your own copy."
        if what == "scenario"
        else f"Only the {what}'s owner or an administrator can change it."
    )
