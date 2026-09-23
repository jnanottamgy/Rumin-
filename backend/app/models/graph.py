"""The knowledge graph: builds, nodes, identifiers, edges, evidence, resolution decisions
and validation issues.

The graph is a *derived projection* of the source tables (Phase 1 reference data, Phase 2
series and instruments), produced by ``python -m app.graph build``. It never replaces
them. That is why no graph table has a foreign key into a source table: reloading
reference data or ingesting a series is never blocked by the graph. Provenance rows name
their source by table and record ID instead, and the next build retires anything whose
source has gone.

Rows are never deleted by a build. Each node and edge records the build that added it,
the build that last changed it and, once its source disappears, the build that retired
it, so the graph's membership at any past build can be reconstructed.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_column, utcnow
from app.db.types import UTCDateTime
from app.domain.enums import (
    Derivation,
    EvidenceSourceKind,
    EvidenceStatus,
    GraphBuildStatus,
    GraphEdgeType,
    GraphIssueSubject,
    GraphNodeType,
    IssueOutcome,
    IssueSeverity,
    JobTrigger,
    NodeNature,
    QualityStatus,
    RelationshipCategory,
    ResolutionMethod,
    ResolutionOutcome,
)

_ACTIVE = "retired_build_id IS NULL"


class GraphBuild(Base):
    """One run of the graph construction pipeline, with its validation report and diff.

    Every count comes from the run itself. ``processed = valid + flagged + rejected``;
    ``valid`` items passed every rule, ``flagged`` items are stored with quality status
    ``warning``, ``rejected`` items were not stored (their issues were).
    """

    __tablename__ = "graph_builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[GraphBuildStatus] = mapped_column(
        enum_column(GraphBuildStatus, "graph_build_status"), index=True
    )
    trigger: Mapped[JobTrigger] = mapped_column(enum_column(JobTrigger, "job_trigger"))
    # Construction rules are versioned; a change of rules is a change of the graph.
    rules_version: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # SHA-256 over everything the build read; differs from a fresh one when sources changed.
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    # What was read: datasets with versions and checksums, record counts per table.
    sources: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    nodes_processed: Mapped[int] = mapped_column(Integer, default=0)
    nodes_valid: Mapped[int] = mapped_column(Integer, default=0)
    nodes_flagged: Mapped[int] = mapped_column(Integer, default=0)
    nodes_rejected: Mapped[int] = mapped_column(Integer, default=0)
    edges_processed: Mapped[int] = mapped_column(Integer, default=0)
    edges_valid: Mapped[int] = mapped_column(Integer, default=0)
    edges_flagged: Mapped[int] = mapped_column(Integer, default=0)
    edges_rejected: Mapped[int] = mapped_column(Integer, default=0)

    nodes_added: Mapped[int] = mapped_column(Integer, default=0)
    nodes_changed: Mapped[int] = mapped_column(Integer, default=0)
    nodes_retired: Mapped[int] = mapped_column(Integer, default=0)
    nodes_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    edges_added: Mapped[int] = mapped_column(Integer, default=0)
    edges_changed: Mapped[int] = mapped_column(Integer, default=0)
    edges_retired: Mapped[int] = mapped_column(Integer, default=0)
    edges_unchanged: Mapped[int] = mapped_column(Integer, default=0)

    # Active nodes and edges after the build.
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)
    # Graph metrics computed from the stored graph (see ``app.graph.metrics``).
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # A short, safe explanation when the build failed (no stack traces).
    error_summary: Mapped[str | None] = mapped_column(Text)


class GraphNode(TimestampMixin, Base):
    """An entity in the graph. ``id`` is a deterministic key such as ``country:cty_in``."""

    __tablename__ = "graph_nodes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    node_type: Mapped[GraphNodeType] = mapped_column(enum_column(GraphNodeType, "graph_node_type"))
    display_name: Mapped[str] = mapped_column(String(300))
    # Tells apart nodes with similar names, e.g. "Fictional company · Air transport · India".
    subtitle: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    nature: Mapped[NodeNature] = mapped_column(enum_column(NodeNature, "node_nature"))
    quality_status: Mapped[QualityStatus] = mapped_column(
        enum_column(QualityStatus, "quality_status")
    )
    # Type-specific descriptive fields (codes, units, frequency). Never financial figures.
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # The source records the node was built from (table, record ID, dataset, version).
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Lower-case name, normalised name and identifiers, for case-insensitive search.
    search_text: Mapped[str] = mapped_column(Text, default="")
    degree: Mapped[int] = mapped_column(Integer, default=0)
    in_degree: Mapped[int] = mapped_column(Integer, default=0)
    out_degree: Mapped[int] = mapped_column(Integer, default=0)
    # Weakly connected component (numbered from 1, largest first) in the latest build.
    component: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    first_build_id: Mapped[int] = mapped_column(ForeignKey("graph_builds.id", ondelete="RESTRICT"))
    changed_build_id: Mapped[int] = mapped_column(
        ForeignKey("graph_builds.id", ondelete="RESTRICT")
    )
    retired_build_id: Mapped[int | None] = mapped_column(
        ForeignKey("graph_builds.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        Index(
            "ix_graph_nodes_active_type",
            "node_type",
            sqlite_where=text(_ACTIVE),
            postgresql_where=text(_ACTIVE),
        ),
    )


class GraphNodeIdentifier(Base):
    """An external identifier of a current node. Unique per scheme: one ISIN, one ISO
    code, one MIC can belong to one node only — the database enforces it."""

    __tablename__ = "graph_node_identifiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("graph_nodes.id", ondelete="CASCADE"), index=True
    )
    scheme: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(128))
    # The record that stated it, e.g. "economic_series/wb-ind-fp-cpi-totl-zg".
    source: Mapped[str] = mapped_column(String(200))

    __table_args__ = (UniqueConstraint("scheme", "value"),)


class GraphEdge(TimestampMixin, Base):
    """A typed relationship between two nodes, with its evidence status.

    ``id`` is derived from (type, source, target), so the same relationship always gets
    the same ID. Undirected types are stored once, with the smaller node key as source.
    """

    __tablename__ = "graph_edges"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    edge_type: Mapped[GraphEdgeType] = mapped_column(enum_column(GraphEdgeType, "graph_edge_type"))
    category: Mapped[RelationshipCategory] = mapped_column(
        enum_column(RelationshipCategory, "relationship_category")
    )
    source_node_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("graph_nodes.id", ondelete="RESTRICT")
    )
    target_node_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("graph_nodes.id", ondelete="RESTRICT")
    )
    directed: Mapped[bool]
    description: Mapped[str] = mapped_column(Text)
    evidence_status: Mapped[EvidenceStatus] = mapped_column(
        enum_column(EvidenceStatus, "evidence_status")
    )
    # True when the edge touches a fictional or sample node, or comes from illustrative data.
    is_illustrative: Mapped[bool]
    quality_status: Mapped[QualityStatus] = mapped_column(
        enum_column(QualityStatus, "quality_status")
    )
    # Validity period, when a source states one. "Historical" = ended before today.
    valid_from: Mapped[date | None]
    valid_to: Mapped[date | None]
    # Type-specific qualifiers (e.g. assumed polarity and illustrative strength).
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    first_build_id: Mapped[int] = mapped_column(ForeignKey("graph_builds.id", ondelete="RESTRICT"))
    changed_build_id: Mapped[int] = mapped_column(
        ForeignKey("graph_builds.id", ondelete="RESTRICT")
    )
    retired_build_id: Mapped[int | None] = mapped_column(
        ForeignKey("graph_builds.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        # Traversal reads the current edges of a set of nodes, in either direction.
        Index(
            "ix_graph_edges_active_source",
            "source_node_id",
            "edge_type",
            sqlite_where=text(_ACTIVE),
            postgresql_where=text(_ACTIVE),
        ),
        Index(
            "ix_graph_edges_active_target",
            "target_node_id",
            "edge_type",
            sqlite_where=text(_ACTIVE),
            postgresql_where=text(_ACTIVE),
        ),
        Index("ix_graph_edges_edge_type", "edge_type"),
    )


class GraphEdgeEvidence(Base):
    """Why an edge exists: the source statement, the rule that turned it into the edge,
    and when the source was recorded or retrieved. An edge has at least one."""

    __tablename__ = "graph_edge_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edge_id: Mapped[str] = mapped_column(
        String(24), ForeignKey("graph_edges.id", ondelete="CASCADE"), index=True
    )
    # The construction rule, e.g. "R02 company_industry" (see ``app.graph.rules``).
    rule_id: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[EvidenceSourceKind] = mapped_column(
        enum_column(EvidenceSourceKind, "evidence_source_kind")
    )
    source_table: Mapped[str] = mapped_column(String(64))
    source_record_id: Mapped[str] = mapped_column(String(128))
    dataset_id: Mapped[str | None] = mapped_column(String(64))
    dataset_version: Mapped[str | None] = mapped_column(String(32))
    # What the source says, in words, e.g. "companies.industry_id = ind_air_transport".
    statement: Mapped[str] = mapped_column(Text)
    # How the rule turned the statement into this edge.
    transformation: Mapped[str] = mapped_column(Text)
    derivation: Mapped[Derivation] = mapped_column(enum_column(Derivation, "derivation"))
    # Records a derived edge was computed from, e.g. a division code and the ISIC table.
    derived_from: Mapped[list[str]] = mapped_column(JSON, default=list)
    citation: Mapped[str | None] = mapped_column(Text)
    citation_url: Mapped[str | None] = mapped_column(String(500))
    # When a provider last delivered the source (series), if it came from a provider.
    retrieved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # When the source record was loaded into RUMIN.
    recorded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (Index("ix_graph_edge_evidence_source", "source_table", "source_record_id"),)


class GraphResolutionDecision(Base):
    """The entity-resolution audit log: what was linked, merged, flagged or refused, and
    why. Original values are kept, so every decision can be reviewed and reversed."""

    __tablename__ = "graph_resolution_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(
        ForeignKey("graph_builds.id", ondelete="CASCADE"), index=True
    )
    source_table: Mapped[str] = mapped_column(String(64))
    source_record_id: Mapped[str] = mapped_column(String(128))
    # The record's values as the source holds them (name, codes), never altered.
    source_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # The node the record was linked to (null when nothing was linked).
    node_id: Mapped[str | None] = mapped_column(String(128), index=True)
    method: Mapped[ResolutionMethod] = mapped_column(
        enum_column(ResolutionMethod, "resolution_method")
    )
    outcome: Mapped[ResolutionOutcome] = mapped_column(
        enum_column(ResolutionOutcome, "resolution_outcome")
    )
    identifier: Mapped[str | None] = mapped_column(String(170))
    candidate_node_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class GraphIssue(Base):
    """A problem found while building the graph — the graph's validation report."""

    __tablename__ = "graph_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(
        ForeignKey("graph_builds.id", ondelete="CASCADE"), index=True
    )
    subject_kind: Mapped[GraphIssueSubject] = mapped_column(
        enum_column(GraphIssueSubject, "graph_issue_subject")
    )
    # The node key, edge key or source record the issue is about.
    subject_ref: Mapped[str] = mapped_column(String(300))
    # Set when the subject is (or would have been) a node or an edge; not foreign keys,
    # because a rejected node or edge is never stored.
    node_id: Mapped[str | None] = mapped_column(String(128), index=True)
    edge_id: Mapped[str | None] = mapped_column(String(24))
    rule: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[IssueSeverity] = mapped_column(enum_column(IssueSeverity, "issue_severity"))
    outcome: Mapped[IssueOutcome] = mapped_column(enum_column(IssueOutcome, "issue_outcome"))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


__all__ = [
    "GraphBuild",
    "GraphEdge",
    "GraphEdgeEvidence",
    "GraphIssue",
    "GraphNode",
    "GraphNodeIdentifier",
    "GraphResolutionDecision",
]
