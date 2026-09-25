"""Advanced analyses of scenario executions: Monte Carlo and joint sensitivity.

``scenario_analyses`` holds one row per analysis: its kind, the normalised request, the
configuration it ran with (the seed and generator, the versions, every run and graph build it
re-evaluated), its results and hashes. Rows are append-only: nothing updates or deletes one.

``scenario_sensitivity_analyses`` gains ``method_version``. Every analysis stored before this
revision was computed by method 1.0.0, whose aggregation kept the execution's revenue,
operating costs and interest expense while the models used the varied values (so margins and
interest coverage did not move with them); analyses from now on use 1.1.0.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("evaluations", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["scenario_executions.id"],
            name=op.f("fk_scenario_analyses_execution_id_scenario_executions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario_analyses")),
    )
    with op.batch_alter_table("scenario_analyses", schema=None) as batch_op:
        batch_op.create_index(
            "ix_scenario_analyses_execution_created", ["execution_id", "created_at"], unique=False
        )

    with op.batch_alter_table("scenario_sensitivity_analyses", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "method_version", sa.String(length=16), nullable=False, server_default="1.0.0"
            )
        )
    # Existing rows now say 1.0.0; new rows state their method themselves.
    with op.batch_alter_table("scenario_sensitivity_analyses", schema=None) as batch_op:
        batch_op.alter_column("method_version", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("scenario_sensitivity_analyses", schema=None) as batch_op:
        batch_op.drop_column("method_version")
    with op.batch_alter_table("scenario_analyses", schema=None) as batch_op:
        batch_op.drop_index("ix_scenario_analyses_execution_created")
    op.drop_table("scenario_analyses")
