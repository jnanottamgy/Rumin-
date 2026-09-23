"""Economic time series and their observations."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_column
from app.db.types import ExactDecimal, UTCDateTime
from app.domain.enums import (
    Frequency,
    JobItemStatus,
    MeasureType,
    ObservationStatus,
    PriceBasis,
    QualityStatus,
    SeasonalAdjustment,
)


class EconomicSeries(TimestampMixin, Base):
    """One provider series — for the World Bank, one indicator for one country.

    Units, frequency, aggregation, price basis and seasonal adjustment are stored with the
    series so a number is never shown without them. ``provider_series_key`` is the
    provider's own identity for the series; RUMIN's ``id`` never pretends to be it.
    """

    __tablename__ = "economic_series"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )
    # E.g. "FP.CPI.TOTL.ZG|IND": unique within the dataset, meaningless across providers.
    provider_series_key: Mapped[str] = mapped_column(String(128))
    provider_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    # The organisation that originally produced the statistic, as the provider reports it.
    source_organization: Mapped[str | None] = mapped_column(Text)
    measure_type: Mapped[MeasureType] = mapped_column(enum_column(MeasureType, "measure_type"))
    unit: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str | None] = mapped_column(String(3))
    frequency: Mapped[Frequency] = mapped_column(enum_column(Frequency, "frequency"))
    aggregation: Mapped[str] = mapped_column(String(200))
    price_basis: Mapped[PriceBasis] = mapped_column(enum_column(PriceBasis, "price_basis"))
    seasonal_adjustment: Mapped[SeasonalAdjustment] = mapped_column(
        enum_column(SeasonalAdjustment, "seasonal_adjustment")
    )
    # Geography as the provider identifies it (ISO 3166-1 alpha-3), plus an optional link
    # to the Phase 1 country entity. SET NULL keeps observation history if reference data
    # is reloaded; the catalogue restores the link.
    country_iso3: Mapped[str | None] = mapped_column(String(3))
    country_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("countries.id", ondelete="SET NULL"), index=True
    )
    # Optional link to a Phase 1 economic variable, with how the two differ.
    variable_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("economic_variables.id", ondelete="SET NULL"), index=True
    )
    variable_relation: Mapped[str | None] = mapped_column(Text)
    # Values outside this range are stored but flagged for review (never corrected).
    plausible_min: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    plausible_max: Mapped[Decimal | None] = mapped_column(ExactDecimal())

    # Summary of current observations, refreshed after each ingestion of the series.
    first_period: Mapped[date | None]
    last_period: Mapped[date | None]
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    last_ingestion_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL")
    )
    last_ingestion_status: Mapped[JobItemStatus | None] = mapped_column(
        enum_column(JobItemStatus, "last_ingestion_status")
    )
    last_ingestion_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_successful_ingestion_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (UniqueConstraint("dataset_id", "provider_series_key"),)


class EconomicObservation(Base):
    """The value of a series for one period, as reported by the provider.

    Rows are never overwritten. When the provider revises a period, the current row gets
    ``superseded_at`` and a new row with ``revision + 1`` becomes current, so the full
    history of what RUMIN was told — and when — is kept.
    """

    __tablename__ = "economic_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("economic_series.id", ondelete="CASCADE")
    )
    # First day of the period the value describes (2023 → 2023-01-01; 2023-03 → 2023-03-01).
    period_start: Mapped[date]
    period_label: Mapped[str] = mapped_column(String(10))
    value: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    # The value exactly as the provider sent it (a JSON number's literal digits).
    raw_value: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[ObservationStatus] = mapped_column(
        enum_column(ObservationStatus, "observation_status")
    )
    quality_status: Mapped[QualityStatus] = mapped_column(
        enum_column(QualityStatus, "quality_status")
    )
    # Flags the provider attached to the value (e.g. the World Bank's ``obs_status``).
    provider_flags: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    superseded_by_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="RESTRICT")
    )
    first_seen_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="RESTRICT")
    )
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="RESTRICT")
    )
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    capture_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_captures.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        Index("ix_economic_observations_series_period", "series_id", "period_start"),
        # At most one current row per period. Superseded revisions are kept alongside.
        Index(
            "uq_economic_observations_current",
            "series_id",
            "period_start",
            unique=True,
            sqlite_where=text("superseded_at IS NULL"),
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )
