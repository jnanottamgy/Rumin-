"""Accounts: people, sign-in sessions, security events, and who owns and made what.

``users`` holds the people an administrator created (never deleted, only deactivated), with
an Argon2id password hash; ``user_sessions`` the sign-in sessions, stored only as the SHA-256
of the cookie's token; ``audit_events`` sign-ins, sign-outs and changes to people and their
sessions (never a password or a token).

Existing tables gain who owns a resource (``scenarios.owner_id``, ``simulation_runs.owner_id``,
``analyst_sessions.owner_id``) and who made a record (``created_by`` / ``requested_by`` on
versions, executions and analyses). Every such column is nullable: records made before
accounts existed have no author, and only administrators change them (or, for
conversations, see them). Downgrading drops the three tables and the columns.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('viewer', 'analyst', 'admin')", name=op.f("ck_users_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("client", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["users.id"],
            name=op.f("fk_audit_events_subject_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index("ix_audit_events_occurred", ["occurred_at"], unique=False)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    with op.batch_alter_table("user_sessions", schema=None) as batch_op:
        batch_op.create_index("ix_user_sessions_user", ["user_id"], unique=False)

    with op.batch_alter_table("analyst_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_analyst_sessions_owner_id"), ["owner_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_analyst_sessions_owner_id_users"),
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("intelligence_analyses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_intelligence_analyses_created_by_users"),
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("scenario_analyses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_scenario_analyses_created_by_users"),
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("scenario_executions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("requested_by", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_scenario_executions_requested_by_users"),
            "users",
            ["requested_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("scenario_sensitivity_analyses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_scenario_sensitivity_analyses_created_by_users"),
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("scenario_versions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_scenario_versions_created_by_users"),
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("scenarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_scenarios_owner_id"), ["owner_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_scenarios_owner_id_users"),
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_simulation_runs_owner_id_users"),
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("simulation_sensitivity_analyses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_simulation_sensitivity_analyses_created_by_users"),
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("simulation_sensitivity_analyses", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_simulation_sensitivity_analyses_created_by_users"), type_="foreignkey"
        )
        batch_op.drop_column("created_by")

    with op.batch_alter_table("simulation_runs", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_simulation_runs_owner_id_users"), type_="foreignkey"
        )
        batch_op.drop_column("owner_id")

    with op.batch_alter_table("scenarios", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_scenarios_owner_id_users"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_scenarios_owner_id"))
        batch_op.drop_column("owner_id")

    with op.batch_alter_table("scenario_versions", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_scenario_versions_created_by_users"), type_="foreignkey"
        )
        batch_op.drop_column("created_by")

    with op.batch_alter_table("scenario_sensitivity_analyses", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_scenario_sensitivity_analyses_created_by_users"), type_="foreignkey"
        )
        batch_op.drop_column("created_by")

    with op.batch_alter_table("scenario_executions", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_scenario_executions_requested_by_users"), type_="foreignkey"
        )
        batch_op.drop_column("requested_by")

    with op.batch_alter_table("scenario_analyses", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_scenario_analyses_created_by_users"), type_="foreignkey"
        )
        batch_op.drop_column("created_by")

    with op.batch_alter_table("intelligence_analyses", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_intelligence_analyses_created_by_users"), type_="foreignkey"
        )
        batch_op.drop_column("created_by")

    with op.batch_alter_table("analyst_sessions", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_analyst_sessions_owner_id_users"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_analyst_sessions_owner_id"))
        batch_op.drop_column("owner_id")

    with op.batch_alter_table("user_sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_user_sessions_user")

    op.drop_table("user_sessions")
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_events_occurred")

    op.drop_table("audit_events")
    op.drop_table("users")
