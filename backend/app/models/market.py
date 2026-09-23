"""Listed instruments and their daily prices, imported from files the user is licensed
to use. RUMIN ships no price data of its own."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_column
from app.db.types import ExactDecimal, UTCDateTime
from app.domain.enums import InstrumentType, PriceAdjustment, QualityStatus


class Instrument(TimestampMixin, Base):
    """A security listed on an exchange.

    Identifiers are kept separately and never merged: a ticker is only unique on its
    exchange (``exchange_mic`` + ``symbol``); the ISIN identifies the security globally.
    """

    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    instrument_type: Mapped[InstrumentType] = mapped_column(
        enum_column(InstrumentType, "instrument_type")
    )
    isin: Mapped[str | None] = mapped_column(String(12), unique=True)
    # ISO 10383 market identifier code, e.g. XNSE (NSE) or XBOM (BSE).
    exchange_mic: Mapped[str] = mapped_column(String(4))
    symbol: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    country_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("countries.id", ondelete="SET NULL")
    )
    # The dataset the instrument's details were declared in.
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )
    first_trade_date: Mapped[date | None]
    last_trade_date: Mapped[date | None]
    bar_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("exchange_mic", "symbol"),)


class PriceBar(Base):
    """One trading day's prices for an instrument, from one dataset.

    Prices from different datasets are kept apart (never blended). Like observations,
    rows are revised rather than overwritten.
    """

    __tablename__ = "price_bars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("instruments.id", ondelete="CASCADE")
    )
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )
    trade_date: Mapped[date]
    open: Mapped[Decimal] = mapped_column(ExactDecimal())
    high: Mapped[Decimal] = mapped_column(ExactDecimal())
    low: Mapped[Decimal] = mapped_column(ExactDecimal())
    close: Mapped[Decimal] = mapped_column(ExactDecimal())
    # Only when the file supplies one; RUMIN never computes adjustments itself.
    adjusted_close: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    volume: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    adjustment: Mapped[PriceAdjustment] = mapped_column(
        enum_column(PriceAdjustment, "price_adjustment")
    )
    quality_status: Mapped[QualityStatus] = mapped_column(
        enum_column(QualityStatus, "quality_status")
    )
    # Line number in the imported file (1 = header), to find the original row.
    source_row: Mapped[int | None]
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
        Index("ix_price_bars_instrument_date", "instrument_id", "trade_date"),
        Index(
            "uq_price_bars_current",
            "instrument_id",
            "dataset_id",
            "trade_date",
            unique=True,
            sqlite_where=text("superseded_at IS NULL"),
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )
