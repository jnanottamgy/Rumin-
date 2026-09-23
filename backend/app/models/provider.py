"""Data providers: who publishes the data RUMIN ingests, and on what terms."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_column
from app.domain.enums import ProviderAuth, ProviderKind


class DataProvider(TimestampMixin, Base):
    """A source of data: an API or a kind of file.

    The descriptive fields are written from the provider's own documentation and kept in
    code next to the adapter that talks to it (``app.ingestion.providers``); this table
    mirrors them so data can reference its provider and the API can show them.
    """

    __tablename__ = "data_providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[ProviderKind] = mapped_column(enum_column(ProviderKind, "provider_kind"))
    description: Mapped[str] = mapped_column(Text)
    homepage_url: Mapped[str | None] = mapped_column(String(500))
    documentation_url: Mapped[str | None] = mapped_column(String(500))
    terms_url: Mapped[str | None] = mapped_column(String(500))
    authentication: Mapped[ProviderAuth] = mapped_column(enum_column(ProviderAuth, "provider_auth"))
    data_categories: Mapped[str] = mapped_column(Text)
    coverage: Mapped[str] = mapped_column(Text)
    update_frequency: Mapped[str] = mapped_column(Text)
    rate_limit_policy: Mapped[str] = mapped_column(Text)
    licensing: Mapped[str] = mapped_column(Text)
    commercial_use: Mapped[str] = mapped_column(Text)
    reliability: Mapped[str] = mapped_column(Text)
    known_limitations: Mapped[str] = mapped_column(Text)
