"""Custom column types."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on every database.

    PostgreSQL stores ``timestamptz`` natively, but SQLite has no timezone support and
    returns naive values. This type normalises writes to UTC and always returns
    timezone-aware UTC datetimes, so application code behaves identically on both.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use timezone-aware UTC values.")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
