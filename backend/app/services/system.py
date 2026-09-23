"""System status and readiness — reported from real application state, never assumed."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import API_VERSION, __version__
from app.core.config import BACKEND_DIR, MIGRATIONS_DIR, Settings
from app.models import Entity, Relationship
from app.schemas.network import DatasetSummary
from app.schemas.system import (
    Capability,
    DatabaseStatus,
    DatasetStatus,
    ReadinessChecks,
    ReadinessResponse,
    SystemStatus,
)
from app.services.network import current_dataset

SERVICE_NAME = "rumin-api"

# What this build can and cannot do. The frontend renders these flags directly, so the
# UI can never claim a capability the backend does not have.
CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        id="reference_data",
        label="Reference data",
        available=True,
        planned_phase=1,
        note="Illustrative sample dataset: fictional companies linked to real-world "
        "classifications and variable definitions.",
    ),
    Capability(
        id="network_projection",
        label="Financial network",
        available=True,
        planned_phase=1,
        note="Graph projection of entities, curated relationships and structural links.",
    ),
    Capability(
        id="scenario_drafts",
        label="Scenario drafts",
        available=True,
        planned_phase=1,
        note="Scenario inputs can be created and edited. Nothing is simulated.",
    ),
    Capability(
        id="historical_observations",
        label="Historical observations",
        available=False,
        planned_phase=2,
        note="No time series are stored yet. Ingestion from cited sources is planned.",
    ),
    Capability(
        id="graph_analytics",
        label="Knowledge-graph analytics",
        available=False,
        planned_phase=3,
        note="Traversal, centrality and path analysis are planned.",
    ),
    Capability(
        id="simulation_engine",
        label="Simulation engine",
        available=False,
        planned_phase=4,
        note="No simulation engine exists; scenarios cannot be run and no results exist.",
    ),
    Capability(
        id="ai_analyst",
        label="AI analyst",
        available=False,
        planned_phase=7,
        note="No AI model is connected.",
    ),
    Capability(
        id="authentication",
        label="Authentication",
        available=False,
        planned_phase=10,
        note="Not implemented. Run this build locally only.",
    ),
    Capability(
        id="live_market_data",
        label="Live market data",
        available=False,
        planned_phase=None,
        note="Not connected. RUMIN makes no real-time data claims.",
    ),
)


@lru_cache
def migration_head() -> str | None:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config).get_current_head()


def _database_revision(session: Session) -> tuple[bool, str | None]:
    """Return (reachable, current migration revision)."""
    try:
        session.execute(text("SELECT 1"))
        revision = MigrationContext.configure(session.connection()).get_current_revision()
    except SQLAlchemyError:
        session.rollback()
        return False, None
    return True, revision


def _dataset_status(session: Session) -> DatasetStatus:
    dataset = current_dataset(session)
    counts = {
        str(kind): count
        for kind, count in session.execute(
            select(Entity.kind, func.count()).group_by(Entity.kind)
        ).tuples()
    }
    return DatasetStatus(
        loaded=dataset is not None,
        summary=DatasetSummary.model_validate(dataset) if dataset else None,
        entity_counts=counts,
        relationship_count=session.scalar(select(func.count()).select_from(Relationship)) or 0,
    )


def check_readiness(session: Session) -> ReadinessResponse:
    reachable, revision = _database_revision(session)
    if not reachable:
        checks = ReadinessChecks(database="unavailable", migrations="unknown", dataset="unknown")
        return ReadinessResponse(status="not_ready", checks=checks)

    if revision is None:
        checks = ReadinessChecks(database="ok", migrations="missing", dataset="unknown")
        return ReadinessResponse(status="not_ready", checks=checks)

    up_to_date = revision == migration_head()
    dataset_loaded = up_to_date and current_dataset(session) is not None
    checks = ReadinessChecks(
        database="ok",
        migrations="up_to_date" if up_to_date else "outdated",
        dataset="loaded" if dataset_loaded else ("missing" if up_to_date else "unknown"),
    )
    ready = up_to_date and dataset_loaded
    return ReadinessResponse(status="ready" if ready else "not_ready", checks=checks)


def get_system_status(session: Session, settings: Settings) -> SystemStatus:
    reachable, revision = _database_revision(session)
    head = migration_head()
    up_to_date = reachable and revision is not None and revision == head
    dataset = (
        _dataset_status(session)
        if up_to_date
        else DatasetStatus(loaded=False, summary=None, entity_counts={}, relationship_count=0)
    )
    return SystemStatus(
        service=SERVICE_NAME,
        version=__version__,
        api_version=API_VERSION,
        environment=settings.environment,
        server_time=datetime.now(UTC),
        database=DatabaseStatus(
            backend=settings.database_backend,
            reachable=reachable,
            migration_revision=revision,
            migration_head=head,
            schema_up_to_date=up_to_date,
        ),
        dataset=dataset,
        capabilities=list(CAPABILITIES),
    )
