"""System status and readiness — reported from real application state, never assumed."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import API_VERSION, __version__
from app.core.config import BACKEND_DIR, MIGRATIONS_DIR, Settings
from app.domain.enums import DatasetKind, ObservationStatus, QualityStatus
from app.models import (
    Dataset,
    EconomicObservation,
    EconomicSeries,
    Entity,
    IngestionJob,
    Instrument,
    PriceBar,
    Relationship,
)
from app.schemas.data import JobRef
from app.schemas.network import DatasetSummary
from app.schemas.system import (
    Capability,
    DatabaseStatus,
    DatasetStatus,
    DataStatus,
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
        note="Scenario inputs can be created and edited. Drafts are not run yet: connecting "
        "them to the simulation engine is the Scenario Lab (Phase 5).",
    ),
    Capability(
        id="historical_observations",
        label="Historical observations",
        available=True,
        planned_phase=2,
        note="Annual World Bank (WDI) series, retrieved with the ingestion command line "
        "and stored exactly as published, with every revision kept. Historical only: nothing "
        "is real-time.",
    ),
    Capability(
        id="price_file_import",
        label="Licensed price files",
        available=True,
        planned_phase=2,
        note="Daily prices from CSV files you are licensed to use, imported from the command "
        "line with a manifest stating the licence. RUMIN ships no price data.",
    ),
    Capability(
        id="data_quality",
        label="Data-quality checks",
        available=True,
        planned_phase=2,
        note="Every record is validated: structural problems are rejected (and kept for "
        "review), unusual values are stored as reported and flagged. Nothing is corrected.",
    ),
    Capability(
        id="ingestion_from_web",
        label="Ingestion from the web app",
        available=False,
        planned_phase=10,
        note="Retrievals and imports run from the command line; the API is read-only until "
        "authentication exists.",
    ),
    Capability(
        id="knowledge_graph",
        label="Knowledge graph",
        available=True,
        planned_phase=3,
        note="Entities, relationships and evidence built from the stored data, with entity "
        "resolution, validation and provenance on every edge. Built from the command line.",
    ),
    Capability(
        id="graph_analytics",
        label="Graph analytics",
        available=True,
        planned_phase=3,
        note="Bounded neighbourhoods, shortest paths (in hops), connected components and "
        "degree. Paths show how records connect; they are not influence or causal chains.",
    ),
    Capability(
        id="simulation_engine",
        label="Simulation engine",
        available=True,
        planned_phase=4,
        note="One model in preview: an airline fuel-cost shock, calculated month by month "
        "from stated inputs and assumptions, with one-at-a-time sensitivity. Every run stores "
        "its inputs, graph snapshot and calculation steps. Results are calculations, not "
        "forecasts.",
    ),
    Capability(
        id="probabilistic_simulation",
        label="Probabilistic simulation",
        available=False,
        planned_phase=9,
        note="Not implemented: runs are deterministic and no probabilities are estimated. "
        "Sensitivity analysis shows how results move with each input, not how likely they are.",
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


EMPTY_DATA = DataStatus(
    provider_datasets=0,
    series_total=0,
    series_with_data=0,
    observations=0,
    instruments=0,
    price_bars=0,
    flagged_values=0,
    last_job=None,
)


def _count(session: Session, statement: Select[tuple[int]]) -> int:
    return session.scalar(statement) or 0


def _data_status(session: Session) -> DataStatus:
    current_obs = EconomicObservation.superseded_at.is_(None)
    current_bars = PriceBar.superseded_at.is_(None)
    last_job = session.scalars(
        select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(1)
    ).first()
    return DataStatus(
        provider_datasets=_count(
            session,
            select(func.count()).select_from(Dataset).where(Dataset.kind == DatasetKind.PROVIDER),
        ),
        series_total=_count(session, select(func.count()).select_from(EconomicSeries)),
        series_with_data=_count(
            session,
            select(func.count())
            .select_from(EconomicSeries)
            .where(EconomicSeries.observation_count > 0),
        ),
        observations=_count(
            session,
            select(func.count()).where(
                current_obs, EconomicObservation.status == ObservationStatus.REPORTED
            ),
        ),
        instruments=_count(session, select(func.count()).select_from(Instrument)),
        price_bars=_count(session, select(func.count()).where(current_bars)),
        flagged_values=_count(
            session,
            select(func.count()).where(
                current_obs, EconomicObservation.quality_status == QualityStatus.WARNING
            ),
        )
        + _count(
            session,
            select(func.count()).where(
                current_bars, PriceBar.quality_status == QualityStatus.WARNING
            ),
        ),
        last_job=JobRef.model_validate(last_job) if last_job is not None else None,
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
        data=_data_status(session) if up_to_date else EMPTY_DATA,
        capabilities=list(CAPABILITIES),
    )
