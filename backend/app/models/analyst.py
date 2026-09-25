"""AI Analyst conversations (Phase 7).

A **session** is a conversation. Each **turn** is one question and its answer, stored with
everything needed to show how the answer was reached: the router's reading, the answer's
blocks and evidence, the grounding check, the provider that composed it (and why the
grounded composer replaced a language model's draft, if it did), token usage and timings.
Each **tool call** of a turn is stored with its arguments, status, a bounded copy of its
result, a hash of that result and its timing.

A turn is written while it runs (so its tool calls appear as they happen) and never
changes once it is final. A session can be renamed, and deleted with everything in it:
conversations are the one thing in RUMIN a person can delete, because they may contain
what that person typed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow
from app.db.types import UTCDateTime

TURN_STATUSES = ("queued", "running", "completed", "failed")


class AnalystSession(TimestampMixin, Base):
    __tablename__ = "analyst_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(120))
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    # What the conversation is about (keys only, see app.analyst.context).
    focus: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Whose conversation it is (Phase 10): only its owner reads, asks in or deletes it.
    # Null for conversations held before accounts existed, which only administrators see.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    turns: Mapped[list[AnalystTurn]] = relationship(
        back_populates="session",
        order_by="AnalystTurn.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_analyst_sessions_updated", "updated_at"),)


class AnalystTurn(Base):
    __tablename__ = "analyst_turns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyst_sessions.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    intent: Mapped[str | None] = mapped_column(String(32))
    answer_status: Mapped[str | None] = mapped_column(String(16))
    headline: Mapped[str | None] = mapped_column(String(300))
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    answer_hash: Mapped[str | None] = mapped_column(String(64))
    route: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    focus_after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    grounded: Mapped[bool | None] = mapped_column(Boolean)
    # What was configured, and what composed the answer (they differ after a fallback).
    configured_provider: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str | None] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(100))
    fallback: Mapped[str | None] = mapped_column(Text)
    rejected: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    analyst_version: Mapped[str] = mapped_column(String(16))
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    session: Mapped[AnalystSession] = relationship(back_populates="turns")
    tool_calls: Mapped[list[AnalystToolCall]] = relationship(
        back_populates="turn",
        order_by="AnalystToolCall.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')", name="status_known"
        ),
        UniqueConstraint("session_id", "position"),
        Index("ix_analyst_turns_status", "status"),
        Index("ix_analyst_turns_requested", "requested_at"),
    )


class AnalystToolCall(Base):
    __tablename__ = "analyst_tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyst_turns.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str | None] = mapped_column(String(300))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    duration_ms: Mapped[int] = mapped_column(Integer)

    turn: Mapped[AnalystTurn] = relationship(back_populates="tool_calls")

    __table_args__ = (UniqueConstraint("turn_id", "position"),)
