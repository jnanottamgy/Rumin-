"""Alembic migration environment.

The database URL comes from, in order of precedence:
1. ``config.attributes["connection"]`` — an open connection supplied by tests;
2. the ``sqlalchemy.url`` main option (``alembic -x`` or programmatic config);
3. ``RUMIN_DATABASE_URL`` via the application settings.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy.engine import Connection

import app.models  # noqa: F401 — registers every table on Base.metadata
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_db_engine
from app.db.types import DECIMAL_PRECISION, DECIMAL_SCALE, ExactDecimal, UTCDateTime

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _render_item(type_: str, obj: Any, _: AutogenContext) -> str | bool:
    """Render custom column types as plain SQLAlchemy types.

    Migrations are frozen snapshots of the schema and must not import application code,
    which may change or disappear after the migration is written.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    if type_ == "type" and isinstance(obj, ExactDecimal):
        # Exact on both databases: NUMERIC on PostgreSQL, a decimal string on SQLite.
        return (
            f"sa.Numeric(precision={DECIMAL_PRECISION}, scale={DECIMAL_SCALE})"
            '.with_variant(sa.String(length=64), "sqlite")'
        )
    return False


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _run(connection: Connection) -> None:
    is_sqlite = connection.dialect.name == "sqlite"
    if is_sqlite:
        # Batch migrations recreate tables on SQLite; foreign keys must be off while that
        # happens (the pragma cannot change inside a transaction, hence before it starts).
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # portable ALTERs: required for SQLite, harmless elsewhere
        compare_type=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()

    if is_sqlite:
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        if violations:
            raise RuntimeError(f"Migration left foreign key violations: {violations}")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return

    engine = create_db_engine(_database_url())
    try:
        with engine.connect() as connection:
            _run(connection)
            connection.commit()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
