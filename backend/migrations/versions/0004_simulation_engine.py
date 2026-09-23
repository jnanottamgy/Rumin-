"""Simulation engine: model versions, runs, run steps and sensitivity analyses.

Runs are append-only records of completed simulations: the model version and its
definition hash, the input snapshot, the knowledge-graph snapshot, every calculation step,
the outputs and the hashes that make a run verifiable. Existing tables are not changed.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulation_model_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "preview",
                "active",
                "deprecated",
                name="simulation_model_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simulation_model_versions")),
        sa.UniqueConstraint(
            "model_id", "version", name=op.f("uq_simulation_model_versions_model_id_version")
        ),
    )
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "completed",
                name="simulation_run_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("graph_snapshot", sa.JSON(), nullable=False),
        sa.Column("data_snapshot", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("monthly", sa.JSON(), nullable=False),
        sa.Column("contributions", sa.JSON(), nullable=False),
        sa.Column("bridge", sa.JSON(), nullable=True),
        sa.Column("transmission", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=16), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["simulation_model_versions.id"],
            name=op.f("fk_simulation_runs_model_version_id_simulation_model_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simulation_runs")),
    )
    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.create_index("ix_simulation_runs_entity_id", ["entity_id"], unique=False)
        batch_op.create_index("ix_simulation_runs_inputs_hash", ["inputs_hash"], unique=False)
        batch_op.create_index(
            "ix_simulation_runs_model_created", ["model_id", "created_at"], unique=False
        )

    op.create_table(
        "simulation_run_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("equation_id", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("output_symbol", sa.String(length=32), nullable=False),
        sa.Column(
            "output_value",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=False,
        ),
        sa.Column("output_unit", sa.String(length=100), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_simulation_run_steps_run_id_simulation_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simulation_run_steps")),
        sa.UniqueConstraint(
            "run_id", "sequence", name=op.f("uq_simulation_run_steps_run_id_sequence")
        ),
    )
    with op.batch_alter_table("simulation_run_steps", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_simulation_run_steps_run_id"), ["run_id"], unique=False
        )

    op.create_table(
        "simulation_sensitivity_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("evaluations", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_simulation_sensitivity_analyses_run_id_simulation_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simulation_sensitivity_analyses")),
    )
    with op.batch_alter_table("simulation_sensitivity_analyses", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_simulation_sensitivity_analyses_run_id"), ["run_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("simulation_sensitivity_analyses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_simulation_sensitivity_analyses_run_id"))

    op.drop_table("simulation_sensitivity_analyses")
    with op.batch_alter_table("simulation_run_steps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_simulation_run_steps_run_id"))

    op.drop_table("simulation_run_steps")
    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_simulation_runs_model_created")
        batch_op.drop_index("ix_simulation_runs_inputs_hash")
        batch_op.drop_index("ix_simulation_runs_entity_id")

    op.drop_table("simulation_runs")
    op.drop_table("simulation_model_versions")
