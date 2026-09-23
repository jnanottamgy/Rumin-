"""Knowledge graph: graph builds, nodes and their identifiers, edges and their evidence,
entity-resolution decisions and validation issues.

The graph is a derived projection of the Phase 1 and Phase 2 tables, rebuilt by
``python -m app.graph build``. No graph table has a foreign key into those tables, so
reloading reference data or ingesting series is never blocked by the graph. Existing
tables are not changed.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "graph_builds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "completed_with_warnings",
                "failed",
                name="graph_build_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "trigger",
            sa.Enum(
                "cli", name="job_trigger", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("rules_version", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("nodes_processed", sa.Integer(), nullable=False),
        sa.Column("nodes_valid", sa.Integer(), nullable=False),
        sa.Column("nodes_flagged", sa.Integer(), nullable=False),
        sa.Column("nodes_rejected", sa.Integer(), nullable=False),
        sa.Column("edges_processed", sa.Integer(), nullable=False),
        sa.Column("edges_valid", sa.Integer(), nullable=False),
        sa.Column("edges_flagged", sa.Integer(), nullable=False),
        sa.Column("edges_rejected", sa.Integer(), nullable=False),
        sa.Column("nodes_added", sa.Integer(), nullable=False),
        sa.Column("nodes_changed", sa.Integer(), nullable=False),
        sa.Column("nodes_retired", sa.Integer(), nullable=False),
        sa.Column("nodes_unchanged", sa.Integer(), nullable=False),
        sa.Column("edges_added", sa.Integer(), nullable=False),
        sa.Column("edges_changed", sa.Integer(), nullable=False),
        sa.Column("edges_retired", sa.Integer(), nullable=False),
        sa.Column("edges_unchanged", sa.Integer(), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("info_count", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_builds")),
    )
    with op.batch_alter_table("graph_builds", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_graph_builds_status"), ["status"], unique=False)

    op.create_table(
        "graph_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("build_id", sa.Integer(), nullable=False),
        sa.Column(
            "subject_kind",
            sa.Enum(
                "node",
                "edge",
                "identifier",
                "resolution",
                name="graph_issue_subject",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("subject_ref", sa.String(length=300), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=True),
        sa.Column("edge_id", sa.String(length=24), nullable=True),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "error",
                "warning",
                "info",
                name="issue_severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "rejected",
                "flagged",
                "noted",
                name="issue_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["build_id"],
            ["graph_builds.id"],
            name=op.f("fk_graph_issues_build_id_graph_builds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_issues")),
    )
    with op.batch_alter_table("graph_issues", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_graph_issues_build_id"), ["build_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_graph_issues_node_id"), ["node_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_graph_issues_rule"), ["rule"], unique=False)

    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column(
            "node_type",
            sa.Enum(
                "country",
                "currency",
                "sector",
                "industry",
                "company",
                "economic_variable",
                "data_series",
                "instrument",
                "market",
                name="graph_node_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("subtitle", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "nature",
            sa.Enum(
                "real",
                "fictional",
                "sample",
                name="node_nature",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "quality_status",
            sa.Enum(
                "validated",
                "warning",
                name="quality_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("degree", sa.Integer(), nullable=False),
        sa.Column("in_degree", sa.Integer(), nullable=False),
        sa.Column("out_degree", sa.Integer(), nullable=False),
        sa.Column("component", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("first_build_id", sa.Integer(), nullable=False),
        sa.Column("changed_build_id", sa.Integer(), nullable=False),
        sa.Column("retired_build_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_build_id"],
            ["graph_builds.id"],
            name=op.f("fk_graph_nodes_changed_build_id_graph_builds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_build_id"],
            ["graph_builds.id"],
            name=op.f("fk_graph_nodes_first_build_id_graph_builds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retired_build_id"],
            ["graph_builds.id"],
            name=op.f("fk_graph_nodes_retired_build_id_graph_builds"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_nodes")),
    )
    with op.batch_alter_table("graph_nodes", schema=None) as batch_op:
        batch_op.create_index(
            "ix_graph_nodes_active_type",
            ["node_type"],
            unique=False,
            sqlite_where=sa.text("retired_build_id IS NULL"),
            postgresql_where=sa.text("retired_build_id IS NULL"),
        )

    op.create_table(
        "graph_resolution_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("build_id", sa.Integer(), nullable=False),
        sa.Column("source_table", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=128), nullable=False),
        sa.Column("source_values", sa.JSON(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=True),
        sa.Column(
            "method",
            sa.Enum(
                "identifier",
                "explicit_link",
                "name_comparison",
                name="resolution_method",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "linked",
                "identifier_attached",
                "candidate_flagged",
                "conflict",
                "rejected",
                name="resolution_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("identifier", sa.String(length=170), nullable=True),
        sa.Column("candidate_node_ids", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["build_id"],
            ["graph_builds.id"],
            name=op.f("fk_graph_resolution_decisions_build_id_graph_builds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_resolution_decisions")),
    )
    with op.batch_alter_table("graph_resolution_decisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_graph_resolution_decisions_build_id"), ["build_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_graph_resolution_decisions_node_id"), ["node_id"], unique=False
        )

    op.create_table(
        "graph_edges",
        sa.Column("id", sa.String(length=24), nullable=False),
        sa.Column(
            "edge_type",
            sa.Enum(
                "supplies_to",
                "lends_to",
                "competes_with",
                "affects_costs",
                "affects_revenue",
                "affects_financing",
                "influences",
                "in_industry",
                "domiciled_in",
                "measured_for",
                "in_sector",
                "has_currency",
                "covers",
                "related_measure_of",
                "expressed_in",
                "listed_on",
                "quoted_in",
                "associated_with",
                name="graph_edge_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "economic",
                "structural",
                name="relationship_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_node_id", sa.String(length=128), nullable=False),
        sa.Column("target_node_id", sa.String(length=128), nullable=False),
        sa.Column("directed", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "evidence_status",
            sa.Enum(
                "evidence_backed",
                "analyst_created",
                "model_assumption",
                "unverified",
                name="evidence_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("is_illustrative", sa.Boolean(), nullable=False),
        sa.Column(
            "quality_status",
            sa.Enum(
                "validated",
                "warning",
                name="quality_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("first_build_id", sa.Integer(), nullable=False),
        sa.Column("changed_build_id", sa.Integer(), nullable=False),
        sa.Column("retired_build_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_build_id"],
            ["graph_builds.id"],
            name=op.f("fk_graph_edges_changed_build_id_graph_builds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_build_id"],
            ["graph_builds.id"],
            name=op.f("fk_graph_edges_first_build_id_graph_builds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retired_build_id"],
            ["graph_builds.id"],
            name=op.f("fk_graph_edges_retired_build_id_graph_builds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["graph_nodes.id"],
            name=op.f("fk_graph_edges_source_node_id_graph_nodes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["graph_nodes.id"],
            name=op.f("fk_graph_edges_target_node_id_graph_nodes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_edges")),
    )
    with op.batch_alter_table("graph_edges", schema=None) as batch_op:
        batch_op.create_index(
            "ix_graph_edges_active_source",
            ["source_node_id", "edge_type"],
            unique=False,
            sqlite_where=sa.text("retired_build_id IS NULL"),
            postgresql_where=sa.text("retired_build_id IS NULL"),
        )
        batch_op.create_index(
            "ix_graph_edges_active_target",
            ["target_node_id", "edge_type"],
            unique=False,
            sqlite_where=sa.text("retired_build_id IS NULL"),
            postgresql_where=sa.text("retired_build_id IS NULL"),
        )
        batch_op.create_index("ix_graph_edges_edge_type", ["edge_type"], unique=False)

    op.create_table(
        "graph_node_identifiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("scheme", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["graph_nodes.id"],
            name=op.f("fk_graph_node_identifiers_node_id_graph_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_node_identifiers")),
        sa.UniqueConstraint("scheme", "value", name=op.f("uq_graph_node_identifiers_scheme_value")),
    )
    with op.batch_alter_table("graph_node_identifiers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_graph_node_identifiers_node_id"), ["node_id"], unique=False
        )

    op.create_table(
        "graph_edge_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edge_id", sa.String(length=24), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column(
            "source_kind",
            sa.Enum(
                "reference_dataset",
                "series_catalogue",
                "price_file_manifest",
                "classification_standard",
                name="evidence_source_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_table", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=True),
        sa.Column("dataset_version", sa.String(length=32), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("transformation", sa.Text(), nullable=False),
        sa.Column(
            "derivation",
            sa.Enum(
                "direct",
                "derived",
                name="derivation",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("derived_from", sa.JSON(), nullable=False),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("citation_url", sa.String(length=500), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["edge_id"],
            ["graph_edges.id"],
            name=op.f("fk_graph_edge_evidence_edge_id_graph_edges"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_edge_evidence")),
    )
    with op.batch_alter_table("graph_edge_evidence", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_graph_edge_evidence_edge_id"), ["edge_id"], unique=False
        )
        batch_op.create_index(
            "ix_graph_edge_evidence_source", ["source_table", "source_record_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("graph_edge_evidence", schema=None) as batch_op:
        batch_op.drop_index("ix_graph_edge_evidence_source")
        batch_op.drop_index(batch_op.f("ix_graph_edge_evidence_edge_id"))

    op.drop_table("graph_edge_evidence")
    with op.batch_alter_table("graph_node_identifiers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_graph_node_identifiers_node_id"))

    op.drop_table("graph_node_identifiers")
    with op.batch_alter_table("graph_edges", schema=None) as batch_op:
        batch_op.drop_index("ix_graph_edges_edge_type")
        batch_op.drop_index(
            "ix_graph_edges_active_target",
            sqlite_where=sa.text("retired_build_id IS NULL"),
            postgresql_where=sa.text("retired_build_id IS NULL"),
        )
        batch_op.drop_index(
            "ix_graph_edges_active_source",
            sqlite_where=sa.text("retired_build_id IS NULL"),
            postgresql_where=sa.text("retired_build_id IS NULL"),
        )

    op.drop_table("graph_edges")
    with op.batch_alter_table("graph_resolution_decisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_graph_resolution_decisions_node_id"))
        batch_op.drop_index(batch_op.f("ix_graph_resolution_decisions_build_id"))

    op.drop_table("graph_resolution_decisions")
    with op.batch_alter_table("graph_nodes", schema=None) as batch_op:
        batch_op.drop_index(
            "ix_graph_nodes_active_type",
            sqlite_where=sa.text("retired_build_id IS NULL"),
            postgresql_where=sa.text("retired_build_id IS NULL"),
        )

    op.drop_table("graph_nodes")
    with op.batch_alter_table("graph_issues", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_graph_issues_rule"))
        batch_op.drop_index(batch_op.f("ix_graph_issues_node_id"))
        batch_op.drop_index(batch_op.f("ix_graph_issues_build_id"))

    op.drop_table("graph_issues")
    with op.batch_alter_table("graph_builds", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_graph_builds_status"))

    op.drop_table("graph_builds")
