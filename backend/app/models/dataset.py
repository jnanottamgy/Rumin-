from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class Dataset(Base):
    """A versioned collection of records loaded into RUMIN (provenance anchor).

    Every entity and relationship references the dataset it came from, so the origin
    of any record can always be traced — and illustrative data is always labelled.
    """

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    is_illustrative: Mapped[bool]
    provenance_note: Mapped[str] = mapped_column(Text)
    license: Mapped[str] = mapped_column(String(200))
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    loaded_at: Mapped[datetime] = mapped_column(UTCDateTime())
