"""The migrations are the schema's source of truth — check they match the models."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401
from app.db.base import Base, utcnow
from app.db.session import create_db_engine, create_session_factory
from app.models import Company
from tests.conftest import alembic_config


def test_migrated_schema_matches_the_models(engine: Engine) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)

    assert differences == [], "Models changed without a migration — run alembic revision"


def test_migrations_downgrade_and_upgrade_cleanly(fresh_sqlite_url: str) -> None:
    config = alembic_config(fresh_sqlite_url)
    engine = create_db_engine(fresh_sqlite_url)

    command.upgrade(config, "head")
    assert "scenario_shocks" in inspect(engine).get_table_names()
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    assert "relationships" in inspect(engine).get_table_names()
    engine.dispose()


def test_foreign_keys_are_enforced(engine: Engine) -> None:
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        session.add(
            Company(
                id="co_orphan",
                name="Orphan",
                description="References an industry that does not exist.",
                is_fictional=True,
                industry_id="ind_does_not_exist",
                country_id="cty_in",
                dataset_id="rumin-sample",
                attributes={},
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
