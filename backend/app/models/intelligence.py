"""Stored intelligence analyses (Phase 6).

An analysis is computed from the store on request; storing one keeps a snapshot of what it
said, with the thresholds it used, a fingerprint of everything it read (graph build, stored
values, executions) and hashes of both. Analyses are append-only: never updated or
deleted. When the inputs have changed since, a stored analysis is reported as stale rather
than silently recomputed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import UTCDateTime


class IntelligenceAnalysis(Base):
    """A stored snapshot of an entity or workspace analysis."""

    __tablename__ = "intelligence_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(16))  # entity | workspace
    subject_key: Mapped[str | None] = mapped_column(String(128))  # the entity's graph key
    subject_name: Mapped[str] = mapped_column(String(200))
    label: Mapped[str | None] = mapped_column(String(200))
    engine_version: Mapped[str] = mapped_column(String(16))
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON)
    graph_build_id: Mapped[int | None] = mapped_column(Integer)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    inputs_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_hash: Mapped[str] = mapped_column(String(64))
    insight_count: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # Who stored it (Phase 10; null before accounts existed).
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("scope IN ('entity', 'workspace')", name="scope_known"),
        CheckConstraint(
            "(scope = 'entity' AND subject_key IS NOT NULL) OR "
            "(scope = 'workspace' AND subject_key IS NULL)",
            name="subject_matches_scope",
        ),
        Index("ix_intelligence_analyses_scope_created", "scope", "created_at"),
        Index("ix_intelligence_analyses_subject_created", "subject_key", "created_at"),
    )
