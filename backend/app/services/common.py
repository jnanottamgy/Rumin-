"""Helpers shared by the read services."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

RowT = TypeVar("RowT")


def paginate(
    session: Session, statement: Select[tuple[RowT]], limit: int, offset: int
) -> tuple[Sequence[RowT], int]:
    """One page of ``statement``'s rows, and the total number of matching rows."""
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.scalars(statement.limit(limit).offset(offset)).all()
    return rows, total


def like_pattern(text: str) -> str:
    """A LIKE pattern matching ``text`` anywhere, with LIKE's wildcards escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
