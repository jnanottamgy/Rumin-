"""Financial intelligence: stored analyses.

An analysis is computed on request from the stored data, graph and executions. Storing one
keeps a snapshot of what it said, with its thresholds, a fingerprint of what it read and
hashes of both. Stored analyses are append-only: nothing updates or deletes them. Nothing
else changes: the intelligence engine only reads the Phase 1–5 tables.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intelligence_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("subject_key", sa.String(length=128), nullable=True),
        sa.Column("subject_name", sa.String(length=200), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("engine_version", sa.String(length=16), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("graph_build_id", sa.Integer(), nullable=True),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("insight_count", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('entity', 'workspace')",
            name=op.f("ck_intelligence_analyses_scope_known"),
        ),
        sa.CheckConstraint(
            "(scope = 'entity' AND subject_key IS NOT NULL) OR "
            "(scope = 'workspace' AND subject_key IS NULL)",
            name=op.f("ck_intelligence_analyses_subject_matches_scope"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intelligence_analyses")),
    )
    with op.batch_alter_table("intelligence_analyses", schema=None) as batch_op:
        batch_op.create_index(
            "ix_intelligence_analyses_scope_created", ["scope", "created_at"], unique=False
        )
        batch_op.create_index(
            "ix_intelligence_analyses_subject_created",
            ["subject_key", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("intelligence_analyses", schema=None) as batch_op:
        batch_op.drop_index("ix_intelligence_analyses_subject_created")
        batch_op.drop_index("ix_intelligence_analyses_scope_created")
    op.drop_table("intelligence_analyses")
