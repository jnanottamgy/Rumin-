from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_column
from app.domain.enums import EvidenceLevel, Polarity, RelationshipType, Strength


class Relationship(TimestampMixin, Base):
    """A curated economic relationship between two entities (a directed graph edge).

    Relationships are *model assumptions*: ``evidence_level`` records how well each one
    is supported and ``rationale`` explains why it is plausible. Undirected types
    (e.g. ``competes_with``) are stored once, with ``source_id < target_id``.
    """

    __tablename__ = "relationships"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[RelationshipType] = mapped_column(
        enum_column(RelationshipType, "relationship_type"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    polarity: Mapped[Polarity] = mapped_column(enum_column(Polarity, "polarity"))
    strength: Mapped[Strength] = mapped_column(enum_column(Strength, "strength"))
    evidence_level: Mapped[EvidenceLevel] = mapped_column(
        enum_column(EvidenceLevel, "evidence_level")
    )
    description: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    # Citation supporting the relationship; required for any evidence level above
    # "illustrative" (enforced when a dataset is loaded).
    reference: Mapped[str | None] = mapped_column(String(500))
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )

    __table_args__ = (
        UniqueConstraint("type", "source_id", "target_id"),
        CheckConstraint("source_id <> target_id", name="no_self_loop"),
    )
