"""Financial entities, mapped with joined-table inheritance.

``entities`` holds the columns every entity shares; each kind adds its own table
(``companies``, ``industries``, ``countries``, ``economic_variables``) keyed by the same
ID. Because every node lives in ``entities``, relationships can reference any node with
a real foreign key — something a table-per-kind design without a shared parent cannot do.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_column
from app.domain.enums import EntityKind, Frequency, ValueKind, VariableCategory


class Entity(TimestampMixin, Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[EntityKind] = mapped_column(enum_column(EntityKind, "entity_kind"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    is_fictional: Mapped[bool] = mapped_column(default=False)
    # Citation for the entity's definition, e.g. "ISIC Rev. 4 — Division 51".
    reference: Mapped[str | None] = mapped_column(String(500))
    reference_url: Mapped[str | None] = mapped_column(String(500))
    # Extensible descriptive metadata. Must never hold unsourced financial figures.
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )

    __mapper_args__ = {"polymorphic_on": "kind"}


class Industry(Entity):
    __tablename__ = "industries"

    id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    classification_system: Mapped[str] = mapped_column(String(32))
    classification_code: Mapped[str] = mapped_column(String(16))

    __mapper_args__ = {"polymorphic_identity": EntityKind.INDUSTRY}


class Country(Entity):
    __tablename__ = "countries"

    id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    iso_alpha2: Mapped[str] = mapped_column(String(2), unique=True)
    currency_code: Mapped[str] = mapped_column(String(3))

    __mapper_args__ = {"polymorphic_identity": EntityKind.COUNTRY}


class Company(Entity):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    industry_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("industries.id", ondelete="RESTRICT"), index=True
    )
    country_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("countries.id", ondelete="RESTRICT"), index=True
    )

    __mapper_args__ = {"polymorphic_identity": EntityKind.COMPANY}


class EconomicVariable(Entity):
    __tablename__ = "economic_variables"

    id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    unit: Mapped[str] = mapped_column(String(64))
    value_kind: Mapped[ValueKind] = mapped_column(enum_column(ValueKind, "value_kind"))
    frequency: Mapped[Frequency] = mapped_column(enum_column(Frequency, "frequency"))
    category: Mapped[VariableCategory] = mapped_column(
        enum_column(VariableCategory, "variable_category")
    )
    # The economy the variable describes; NULL for global benchmarks (e.g. Brent crude).
    country_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("countries.id", ondelete="RESTRICT"), index=True
    )

    __mapper_args__ = {"polymorphic_identity": EntityKind.ECONOMIC_VARIABLE}
