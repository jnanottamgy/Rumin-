"""Declarative base shared by all ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import UTCDateTime

# Deterministic constraint names are essential for migrations: without them, dropping
# or altering a constraint on PostgreSQL (or in SQLite batch mode) needs a guessed name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


def enum_column(enum_cls: type[Enum], name: str) -> SAEnum:
    """A portable enum column: VARCHAR + CHECK constraint, storing the enum *values*.

    Native PostgreSQL ENUM types are avoided because adding a value requires special
    migration handling; a CHECK constraint behaves identically on SQLite and PostgreSQL.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
