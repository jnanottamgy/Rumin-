"""Scenario Lab: versioned scenarios, executions, their runs and sensitivity analyses.

Scenarios become stable identities with numbered, immutable versions. Every existing draft
becomes version 1 of itself, with the same changes. Changes now belong to a version.
Executions store the plan, the Phase 4 runs of every model used and the aggregated
results. They refer to versions and runs with RESTRICT, so executed history can never be
deleted from under them.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-24
"""

import hashlib
import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXECUTION_STATUSES = (
    "queued",
    "validating",
    "simulating",
    "propagating",
    "aggregating",
    "completed",
    "failed",
    "cancelled",
)


def _decimal_text(value: Any) -> str:
    """The canonical plain form of a decimal (as app.scenario_lab.spec.decimal_text)."""
    text = format(Decimal(str(value)), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text


def _default_spec() -> dict[str, Any]:
    """A Phase 1 draft's version 1: its changes, and every Phase 5 section at its default."""
    return {
        "entity": None,
        "timing": {"start_month": 1, "duration_months": 0, "horizon_months": 12},
        "company": {
            "reporting_currency": None,
            "annual_revenue": None,
            "annual_operating_costs": None,
        },
        "markets": {"fx_rate": None},
        "models": {},
        "constraints": {"evidence": "any", "stored_market_data": False},
        "stress_cases": [],
    }


def _spec_hash(name: str, description: str, shocks: list[dict[str, Any]]) -> str:
    """As app.scenario_lab.spec.spec_hash for a migrated draft (a test checks they agree)."""
    document = {
        "name": name,
        "description": description,
        "template_id": None,
        "shocks": shocks,
        **_default_spec(),
    }
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def upgrade() -> None:
    with op.batch_alter_table("scenarios", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("current_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("template_id", sa.String(length=64), nullable=True))

    op.create_table(
        "scenario_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=True),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("derived_from", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.id"],
            name=op.f("fk_scenario_versions_scenario_id_scenarios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario_versions")),
        sa.UniqueConstraint(
            "scenario_id", "version", name=op.f("uq_scenario_versions_scenario_id_version")
        ),
    )
    with op.batch_alter_table("scenario_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_scenario_versions_scenario_id"), ["scenario_id"], unique=False
        )

    # Every existing draft becomes version 1 of itself. Typed table constructs, so that
    # identifiers and dates come back as the same Python types on SQLite and PostgreSQL.
    connection = op.get_bind()
    scenarios_table = sa.table(
        "scenarios",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    shocks_table = sa.table(
        "scenario_shocks",
        sa.column("scenario_id", sa.Uuid()),
        sa.column("position", sa.Integer()),
        sa.column("variable_id", sa.String()),
        sa.column("change_type", sa.String()),
        sa.column("value", sa.Numeric(14, 4)),
        sa.column("note", sa.Text()),
    )
    scenarios = connection.execute(
        sa.select(
            scenarios_table.c.id,
            scenarios_table.c.name,
            scenarios_table.c.description,
            scenarios_table.c.updated_at,
        )
    ).fetchall()
    versions = sa.table(
        "scenario_versions",
        sa.column("scenario_id", sa.Uuid()),
        sa.column("version", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("template_id", sa.String()),
        sa.column("spec", sa.JSON()),
        sa.column("spec_hash", sa.String()),
        sa.column("derived_from", sa.JSON()),
        sa.column("note", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    for scenario_id, name, description, updated_at in scenarios:
        shocks = connection.execute(
            sa.select(
                shocks_table.c.variable_id,
                shocks_table.c.change_type,
                shocks_table.c.value,
                shocks_table.c.note,
            )
            .where(shocks_table.c.scenario_id == scenario_id)
            .order_by(shocks_table.c.position)
        ).fetchall()
        documents = [
            {
                "variable_id": variable_id,
                "change_type": change_type,
                "value": _decimal_text(value),
                "note": note,
            }
            for variable_id, change_type, value, note in shocks
        ]
        connection.execute(
            versions.insert().values(
                scenario_id=scenario_id,
                version=1,
                name=name,
                description=description,
                template_id=None,
                spec=_default_spec(),
                spec_hash=_spec_hash(name, description, documents),
                derived_from=None,
                note="",
                created_at=updated_at,
            )
        )

    # Changes now belong to a version.
    with op.batch_alter_table("scenario_shocks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("scenario_version_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE scenario_shocks SET scenario_version_id = (SELECT v.id FROM scenario_versions v "
        "WHERE v.scenario_id = scenario_shocks.scenario_id AND v.version = 1)"
    )
    with op.batch_alter_table("scenario_shocks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scenario_shocks_scenario_id"))
        batch_op.drop_constraint(
            batch_op.f("uq_scenario_shocks_scenario_id_variable_id"), type_="unique"
        )
        batch_op.drop_constraint(
            batch_op.f("fk_scenario_shocks_scenario_id_scenarios"), type_="foreignkey"
        )
        batch_op.drop_column("scenario_id")
        batch_op.alter_column("scenario_version_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_scenario_shocks_scenario_version_id_scenario_versions"),
            "scenario_versions",
            ["scenario_version_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_scenario_shocks_scenario_version_id_variable_id"),
            ["scenario_version_id", "variable_id"],
        )
        batch_op.create_index(
            batch_op.f("ix_scenario_shocks_scenario_version_id"),
            ["scenario_version_id"],
            unique=False,
        )

    op.create_table(
        "scenario_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_version_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *EXECUTION_STATUSES,
                name="scenario_execution_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("inputs_hash", sa.String(length=64), nullable=True),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("lab_version", sa.String(length=16), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.id"],
            name=op.f("fk_scenario_executions_scenario_id_scenarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_version_id"],
            ["scenario_versions.id"],
            name=op.f("fk_scenario_executions_scenario_version_id_scenario_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario_executions")),
    )
    with op.batch_alter_table("scenario_executions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_scenario_executions_scenario_requested",
            ["scenario_id", "requested_at"],
            unique=False,
        )
        batch_op.create_index("ix_scenario_executions_status", ["status"], unique=False)

    op.create_table(
        "scenario_execution_runs",
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("simulation_run_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["scenario_executions.id"],
            name=op.f("fk_scenario_execution_runs_execution_id_scenario_executions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_scenario_execution_runs_simulation_run_id_simulation_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "execution_id", "simulation_run_id", name=op.f("pk_scenario_execution_runs")
        ),
    )

    op.create_table(
        "scenario_sensitivity_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("evaluations", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["scenario_executions.id"],
            name=op.f("fk_scenario_sensitivity_analyses_execution_id_scenario_executions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario_sensitivity_analyses")),
    )
    with op.batch_alter_table("scenario_sensitivity_analyses", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_scenario_sensitivity_analyses_execution_id"),
            ["execution_id"],
            unique=False,
        )


def downgrade() -> None:
    """Back to Phase 4 drafts: each scenario keeps its current version's changes. Executions
    and older versions are removed (their Phase 4 runs stay)."""
    with op.batch_alter_table("scenario_sensitivity_analyses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scenario_sensitivity_analyses_execution_id"))
    op.drop_table("scenario_sensitivity_analyses")
    op.drop_table("scenario_execution_runs")
    with op.batch_alter_table("scenario_executions", schema=None) as batch_op:
        batch_op.drop_index("ix_scenario_executions_status")
        batch_op.drop_index("ix_scenario_executions_scenario_requested")
    op.drop_table("scenario_executions")

    # Keep only the current version's changes, and point them back at their scenario.
    op.execute(
        "DELETE FROM scenario_shocks WHERE scenario_version_id NOT IN (SELECT v.id FROM "
        "scenario_versions v JOIN scenarios s ON s.id = v.scenario_id "
        "WHERE v.version = s.current_version)"
    )
    with op.batch_alter_table("scenario_shocks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("scenario_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE scenario_shocks SET scenario_id = (SELECT v.scenario_id FROM scenario_versions v "
        "WHERE v.id = scenario_shocks.scenario_version_id)"
    )
    with op.batch_alter_table("scenario_shocks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scenario_shocks_scenario_version_id"))
        batch_op.drop_constraint(
            batch_op.f("uq_scenario_shocks_scenario_version_id_variable_id"), type_="unique"
        )
        batch_op.drop_constraint(
            batch_op.f("fk_scenario_shocks_scenario_version_id_scenario_versions"),
            type_="foreignkey",
        )
        batch_op.drop_column("scenario_version_id")
        batch_op.alter_column("scenario_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_scenario_shocks_scenario_id_scenarios"),
            "scenarios",
            ["scenario_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_scenario_shocks_scenario_id_variable_id"), ["scenario_id", "variable_id"]
        )
        batch_op.create_index(
            batch_op.f("ix_scenario_shocks_scenario_id"), ["scenario_id"], unique=False
        )

    # A scenario keeps its current version's name and description.
    op.execute(
        "UPDATE scenarios SET name = (SELECT v.name FROM scenario_versions v WHERE "
        "v.scenario_id = scenarios.id AND v.version = scenarios.current_version), "
        "description = (SELECT v.description FROM scenario_versions v WHERE "
        "v.scenario_id = scenarios.id AND v.version = scenarios.current_version)"
    )
    with op.batch_alter_table("scenario_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scenario_versions_scenario_id"))
    op.drop_table("scenario_versions")
    with op.batch_alter_table("scenarios", schema=None) as batch_op:
        batch_op.drop_column("template_id")
        batch_op.drop_column("current_version")
