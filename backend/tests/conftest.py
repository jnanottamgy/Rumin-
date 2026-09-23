"""Shared test fixtures.

By default the suite runs against a temporary SQLite file. To run the *same* suite
against PostgreSQL, point RUMIN_TEST_DATABASE_URL at an empty, disposable database:

    RUMIN_TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/rumin_test pytest

The schema is always built with the real Alembic migrations (not ``create_all``), so
every test run also exercises the migration path.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BACKEND_DIR, Settings
from app.db.seed import load_dataset
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
from app.models import Scenario

ALLOWED_ORIGIN = "http://localhost:5173"


def alembic_config(database_url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def make_settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": database_url,
        "cors_origins": [ALLOWED_ORIGIN],
        "log_level": "WARNING",
        "docs_enabled": True,
        "max_request_body_bytes": 64 * 1024,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    configured = os.environ.get("RUMIN_TEST_DATABASE_URL")
    if configured:
        return configured
    return f"sqlite:///{tmp_path_factory.mktemp('db') / 'rumin_test.db'}"


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    config = alembic_config(database_url)
    command.downgrade(config, "base")  # start clean, even on a reused PostgreSQL database
    command.upgrade(config, "head")
    engine = create_db_engine(database_url)
    with create_session_factory(engine)() as session:
        load_dataset(session)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture(scope="session")
def app(database_url: str, engine: Engine) -> FastAPI:
    return create_app(make_settings(database_url))


@pytest.fixture
def client(app: FastAPI, session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    # Scenarios are the only data tests create; remove them so tests stay independent.
    with session_factory() as session:
        session.execute(delete(Scenario))
        session.commit()


@pytest.fixture
def fresh_sqlite_url(tmp_path: Path) -> str:
    """URL of a brand-new, empty SQLite database (no schema)."""
    return f"sqlite:///{tmp_path / 'fresh.db'}"
