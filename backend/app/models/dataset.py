from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_column
from app.db.types import UTCDateTime
from app.domain.enums import DatasetKind


class Dataset(Base):
    """A versioned collection of records loaded into RUMIN (provenance anchor).

    Every stored record references the dataset it came from, so the origin of any number
    can always be traced — and illustrative data is always labelled. Two kinds exist:

    * ``curated`` — reference data written for RUMIN and loaded from a file in the
      repository (the Phase 1 illustrative network). Identified by the file's checksum.
    * ``provider`` — data retrieved from an external provider (for example the World
      Bank's World Development Indicators, or price files a user is licensed to use).
      Carries the provider's licence, attribution and terms.
    """

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[DatasetKind] = mapped_column(
        enum_column(DatasetKind, "dataset_kind"), server_default=DatasetKind.CURATED.value
    )
    version: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    is_illustrative: Mapped[bool]
    provenance_note: Mapped[str] = mapped_column(Text)
    license: Mapped[str] = mapped_column(String(200))
    # Curated datasets only: SHA-256 of the file the records were loaded from.
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    loaded_at: Mapped[datetime] = mapped_column(UTCDateTime())

    # Provider datasets only.
    provider_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("data_providers.id", ondelete="RESTRICT"), index=True
    )
    # The provider's own identifier for the dataset, e.g. World Bank source "2" (WDI).
    provider_dataset_code: Mapped[str | None] = mapped_column(String(64))
    homepage_url: Mapped[str | None] = mapped_column(String(500))
    license_url: Mapped[str | None] = mapped_column(String(500))
    terms_url: Mapped[str | None] = mapped_column(String(500))
    # The attribution the licence requires, shown wherever the data is shown.
    attribution: Mapped[str | None] = mapped_column(Text)
    update_frequency: Mapped[str | None] = mapped_column(String(200))
    # When the provider last revised the dataset, as the provider reports it.
    provider_last_updated: Mapped[date | None]

    __table_args__ = (
        CheckConstraint(
            "(kind = 'curated' AND checksum_sha256 IS NOT NULL) OR "
            "(kind = 'provider' AND provider_id IS NOT NULL)",
            name="kind_requirements",
        ),
    )
