"""The migrations are the schema's source of truth — check they match the models."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401
from app.db.base import Base, utcnow
from app.db.seed import load_dataset
from app.db.session import create_db_engine, create_session_factory
from app.domain.enums import ChangeType
from app.models import Company
from app.scenario_lab.spec import ShockSpec, from_parts, spec_hash
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


def test_phase_1_drafts_become_version_one_of_themselves(fresh_sqlite_url: str) -> None:
    """Migration 0005 turns every existing draft into version 1, hashed exactly as the
    application hashes a version, and the downgrade keeps the latest version's changes."""
    config = alembic_config(fresh_sqlite_url)
    command.upgrade(config, "0004")
    engine = create_db_engine(fresh_sqlite_url)
    with create_session_factory(engine)() as session:
        load_dataset(session)
    draft = uuid.uuid4()
    with engine.begin() as connection:
        now = utcnow()
        connection.execute(
            sa.text(
                "INSERT INTO scenarios (id, name, description, status, created_at, updated_at) "
                "VALUES (:id, 'Oil shock', 'Brent rises.', 'draft', :now, :now)"
            ),
            {"id": draft.hex, "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO scenario_shocks (scenario_id, position, variable_id, change_type, "
                "value, note) VALUES (:id, 0, 'var_brent_crude', 'percent_change', 30.25, 'Up')"
            ),
            {"id": draft.hex},
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        version = connection.execute(
            sa.text("SELECT id, version, name, spec, spec_hash FROM scenario_versions")
        ).one()
        shocks = connection.execute(
            sa.text("SELECT scenario_version_id, variable_id, value FROM scenario_shocks")
        ).all()
        current = connection.execute(sa.text("SELECT current_version FROM scenarios")).scalar()
    assert (version.version, version.name, current) == (1, "Oil shock", 1)
    assert [(row.scenario_version_id, row.variable_id) for row in shocks] == [
        (version.id, "var_brent_crude")
    ]
    spec = from_parts(
        name="Oil shock",
        description="Brent rises.",
        template_id=None,
        shocks=[ShockSpec("var_brent_crude", ChangeType.PERCENT_CHANGE, Decimal("30.25"), "Up")],
        spec=json.loads(version.spec) if isinstance(version.spec, str) else version.spec,
    )
    assert version.spec_hash == spec_hash(spec)

    command.downgrade(config, "0004")
    with engine.connect() as connection:
        rows = connection.execute(sa.text("SELECT variable_id, note FROM scenario_shocks")).all()
    assert [(row.variable_id, row.note) for row in rows] == [("var_brent_crude", "Up")]
    engine.dispose()


def test_sensitivity_analyses_stored_before_0008_are_method_1_0_0(fresh_sqlite_url: str) -> None:
    """Migration 0008 marks every existing one-at-a-time analysis with the method that
    computed it, leaves no default for new rows, and the downgrade removes the column."""
    from app.domain.enums import ScenarioExecutionStatus
    from app.models import ScenarioExecution, ScenarioSensitivityAnalysis, ScenarioVersion
    from app.schemas.scenario import ScenarioInput
    from app.services.scenarios import create_scenario

    config = alembic_config(fresh_sqlite_url)
    command.upgrade(config, "head")
    engine = create_db_engine(fresh_sqlite_url)
    with create_session_factory(engine)() as session:
        load_dataset(session)
        created = create_scenario(
            session,
            ScenarioInput.model_validate(
                {
                    "name": "Oil shock",
                    "shocks": [
                        {
                            "variable_id": "var_brent_crude",
                            "change_type": "percent_change",
                            "value": "20",
                        }
                    ],
                }
            ),
        )
        version = session.scalars(
            sa.select(ScenarioVersion).where(ScenarioVersion.scenario_id == created.id)
        ).one()
        execution = ScenarioExecution(
            id=uuid.uuid4(),
            scenario_id=created.id,
            scenario_version_id=version.id,
            version=1,
            status=ScenarioExecutionStatus.FAILED,
            stages=[],
            lab_version="1.0.0",
        )
        session.add(execution)
        session.flush()
        session.add(
            ScenarioSensitivityAnalysis(
                execution_id=execution.id,
                metric="operating_margin",
                request=[],
                results={},
                evaluations=1,
                duration_ms=1,
                result_hash="0" * 64,
            )
        )
        session.commit()
    # Back to Phase 8's schema, where the analysis has no method, and forward again.
    command.downgrade(config, "0007")
    names = [item["name"] for item in inspect(engine).get_columns("scenario_sensitivity_analyses")]
    assert "method_version" not in names
    assert "scenario_analyses" not in inspect(engine).get_table_names()

    command.upgrade(config, "head")

    with engine.connect() as connection:
        method = connection.execute(
            sa.text("SELECT method_version FROM scenario_sensitivity_analyses")
        ).scalar()
    column = next(
        item
        for item in inspect(engine).get_columns("scenario_sensitivity_analyses")
        if item["name"] == "method_version"
    )
    assert method == "1.0.0"
    assert column["default"] is None
    assert "scenario_analyses" in inspect(engine).get_table_names()
    engine.dispose()
