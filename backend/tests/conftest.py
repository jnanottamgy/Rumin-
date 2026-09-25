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
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.auth import tokens
from app.auth.passwords import hash_password
from app.core.config import BACKEND_DIR, Settings
from app.db.base import utcnow
from app.db.seed import load_dataset
from app.db.session import create_db_engine, create_session_factory
from app.domain.enums import DatasetKind
from app.main import create_app
from app.models import (
    AnalystSession,
    AnalystToolCall,
    AnalystTurn,
    DataProvider,
    DataQualityIssue,
    Dataset,
    EconomicObservation,
    EconomicSeries,
    GraphBuild,
    GraphEdge,
    GraphEdgeEvidence,
    GraphIssue,
    GraphNode,
    GraphNodeIdentifier,
    GraphResolutionDecision,
    IngestionJob,
    IngestionJobItem,
    Instrument,
    PriceBar,
    Scenario,
    ScenarioAnalysis,
    ScenarioExecution,
    ScenarioExecutionRun,
    ScenarioSensitivityAnalysis,
    SimulationRun,
    SimulationRunStep,
    SimulationSensitivityAnalysis,
    SourceCapture,
    User,
    UserSession,
)
from app.services.graph import clear_freshness_cache

ALLOWED_ORIGIN = "http://localhost:5173"

# The suite's own accounts (Phase 10): every API test runs signed in as the administrator
# unless it signs in as someone else. The password is for this disposable database only.
TEST_ADMIN_EMAIL = "admin@rumin.test"
TEST_PASSWORD = "a test-only passphrase"
COOKIE = "rumin_session"


def ensure_user(
    session: Session,
    email: str,
    *,
    role: str = "admin",
    name: str | None = None,
    password: str = TEST_PASSWORD,
    must_change_password: bool = False,
) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            name=name or email.split("@")[0].title(),
            role=role,
            password_hash=_hashed(password),
            must_change_password=must_change_password,
            is_active=True,
            failed_logins=0,
        )
        session.add(user)
        session.commit()
    return user


_HASHES: dict[str, str] = {}


def _hashed(password: str) -> str:
    # Argon2id takes tens of milliseconds by design; the suite hashes each password once.
    if password not in _HASHES:
        _HASHES[password] = hash_password(password)
    return _HASHES[password]


def session_token(session_factory: sessionmaker[Session], email: str, **user: object) -> str:
    """A fresh session for ``email`` (created if needed), written straight to the database."""
    with session_factory() as session:
        account = ensure_user(session, email, **user)  # type: ignore[arg-type]
        token = tokens.new_token()
        session.add(
            UserSession(
                user_id=account.id,
                token_hash=tokens.token_hash(token),
                expires_at=utcnow() + timedelta(hours=12),
            )
        )
        session.commit()
    return token


def sign_in_client(
    client: TestClient,
    session_factory: sessionmaker[Session],
    email: str = TEST_ADMIN_EMAIL,
    **user: object,
) -> TestClient:
    client.cookies.set(COOKIE, session_token(session_factory, email, **user))
    return client


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
        # Executions complete within the request that creates them, so tests read them at
        # once; the threaded runner has its own tests.
        "scenario_execution_mode": "inline",
        # The same for the Analyst's questions, answered by RUMIN's grounded composer: no
        # test reaches a language model unless it configures one explicitly.
        "analyst_execution_mode": "inline",
        "analyst_provider": "grounded",
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


@pytest.fixture(scope="session")
def admin_token(session_factory: sessionmaker[Session]) -> str:
    return session_token(session_factory, TEST_ADMIN_EMAIL, name="Test Administrator")


@pytest.fixture
def client(
    app: FastAPI, session_factory: sessionmaker[Session], admin_token: str
) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        test_client.cookies.set(COOKIE, admin_token)
        yield test_client
    # Conversations and scenarios (with their executions and runs) are the only data tests
    # create; remove them so tests stay independent.
    with session_factory() as session:
        wipe_analyst(session)
        wipe_scenarios(session)


@pytest.fixture
def fresh_sqlite_url(tmp_path: Path) -> str:
    """URL of a brand-new, empty SQLite database (no schema)."""
    return f"sqlite:///{tmp_path / 'fresh.db'}"


def wipe_analyst(session: Session) -> None:
    """Remove every conversation with its turns and tool calls."""
    session.execute(delete(AnalystToolCall))
    session.execute(delete(AnalystTurn))
    session.execute(delete(AnalystSession))
    session.commit()


def wipe_scenarios(session: Session) -> None:
    """Remove every scenario and everything executing one stored (in foreign-key order)."""
    run_ids = select(ScenarioExecutionRun.simulation_run_id)
    session.execute(delete(ScenarioSensitivityAnalysis))
    session.execute(delete(ScenarioAnalysis))
    runs = list(session.scalars(run_ids))
    session.execute(delete(ScenarioExecutionRun))
    session.execute(delete(ScenarioExecution))
    if runs:
        session.execute(
            delete(SimulationSensitivityAnalysis).where(
                SimulationSensitivityAnalysis.run_id.in_(runs)
            )
        )
        session.execute(delete(SimulationRunStep).where(SimulationRunStep.run_id.in_(runs)))
        session.execute(delete(SimulationRun).where(SimulationRun.id.in_(runs)))
    session.execute(delete(Scenario))
    session.commit()


def wipe_ingested_data(session: Session) -> None:
    """Remove everything ingestion creates (in foreign-key order), keeping the curated
    reference data that the rest of the suite relies on."""
    session.execute(delete(DataQualityIssue))
    session.execute(delete(EconomicObservation))
    session.execute(delete(PriceBar))
    session.execute(delete(SourceCapture))
    session.execute(delete(IngestionJobItem))
    session.execute(update(EconomicSeries).values(last_ingestion_job_id=None))
    session.execute(delete(IngestionJob))
    session.execute(delete(EconomicSeries))
    session.execute(delete(Instrument))
    session.execute(delete(Dataset).where(Dataset.kind == DatasetKind.PROVIDER))
    session.execute(delete(DataProvider))
    session.commit()


@pytest.fixture
def ingestion_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session on the shared test database; ingested data is removed afterwards."""
    with session_factory() as session:
        wipe_ingested_data(session)
        yield session
        session.rollback()
        wipe_ingested_data(session)


def wipe_graph(session: Session) -> None:
    """Remove every graph build and everything it stored (in foreign-key order)."""
    for model in (
        GraphEdgeEvidence,
        GraphNodeIdentifier,
        GraphIssue,
        GraphResolutionDecision,
        GraphEdge,
        GraphNode,
        GraphBuild,
    ):
        session.execute(delete(model))
    session.commit()


@pytest.fixture(autouse=True)
def _uncached_graph_freshness() -> Iterator[None]:
    """Every test computes graph freshness from its own data, never a cached answer."""
    clear_freshness_cache()
    yield
    clear_freshness_cache()


@pytest.fixture
def graph_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session with no graph and no ingested data; both are removed afterwards."""
    with session_factory() as session:
        wipe_graph(session)
        wipe_ingested_data(session)
        yield session
        session.rollback()
        wipe_graph(session)
        wipe_ingested_data(session)


@pytest.fixture
def built_graph(graph_session: Session) -> Iterator[Session]:
    """The reference network plus the World Bank catalogue, built into a knowledge graph
    (removed afterwards, like everything ``graph_session`` holds)."""
    from app.graph.build import run_build
    from app.ingestion.catalog import DEFAULT_CATALOG_PATH, read_catalog, sync_catalog
    from app.ingestion.registry import PROFILES

    sync_catalog(graph_session, read_catalog(DEFAULT_CATALOG_PATH, PROFILES), PROFILES)
    graph_session.commit()
    run_build(graph_session)
    yield graph_session
