"""AI Analyst: conversations, turns and tool calls.

A session is a conversation; a turn is one question with its answer, evidence, grounding
check, provider, usage and timings; a tool call is one call a turn made, with a bounded
copy of its result. Turns never change once final. Sessions can be renamed, and deleted
with their turns and tool calls (they may hold what a person typed). Nothing else changes:
the Analyst only reads the Phase 1–6 tables.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analyst_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("focus", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyst_sessions")),
    )
    with op.batch_alter_table("analyst_sessions", schema=None) as batch_op:
        batch_op.create_index("ix_analyst_sessions_updated", ["updated_at"], unique=False)

    op.create_table(
        "analyst_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column("answer_status", sa.String(length=16), nullable=True),
        sa.Column("headline", sa.String(length=300), nullable=True),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("answer_hash", sa.String(length=64), nullable=True),
        sa.Column("route", sa.JSON(), nullable=True),
        sa.Column("focus_after", sa.JSON(), nullable=True),
        sa.Column("grounded", sa.Boolean(), nullable=True),
        sa.Column("configured_provider", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("fallback", sa.Text(), nullable=True),
        sa.Column("rejected", sa.JSON(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("analyst_version", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name=op.f("ck_analyst_turns_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["analyst_sessions.id"],
            name=op.f("fk_analyst_turns_session_id_analyst_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyst_turns")),
        sa.UniqueConstraint(
            "session_id", "position", name=op.f("uq_analyst_turns_session_id_position")
        ),
    )
    with op.batch_alter_table("analyst_turns", schema=None) as batch_op:
        batch_op.create_index("ix_analyst_turns_requested", ["requested_at"], unique=False)
        batch_op.create_index("ix_analyst_turns_status", ["status"], unique=False)

    op.create_table(
        "analyst_tool_calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["analyst_turns.id"],
            name=op.f("fk_analyst_tool_calls_turn_id_analyst_turns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyst_tool_calls")),
        sa.UniqueConstraint(
            "turn_id", "position", name=op.f("uq_analyst_tool_calls_turn_id_position")
        ),
    )


def downgrade() -> None:
    op.drop_table("analyst_tool_calls")
    with op.batch_alter_table("analyst_turns", schema=None) as batch_op:
        batch_op.drop_index("ix_analyst_turns_status")
        batch_op.drop_index("ix_analyst_turns_requested")

    op.drop_table("analyst_turns")
    with op.batch_alter_table("analyst_sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_analyst_sessions_updated")

    op.drop_table("analyst_sessions")
