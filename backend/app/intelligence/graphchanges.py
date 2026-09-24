"""Relationship changes: what the latest graph build changed in RUMIN's own records.

Each build records, per edge, the build that added it (``first_build_id``), last changed it
(``changed_build_id``) and retired it (``retired_build_id``). Comparing the latest completed
build with the one before it therefore needs no stored diff. These are changes in RUMIN's
records — a relationship added to the sample, a price file imported — not observed changes
in the economy. The build keeps only an edge's current content, so a *changed* edge can be
named, but its earlier attributes cannot be shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.enums import GraphBuildStatus, GraphEdgeType
from app.domain.graph_types import EDGE_TYPES
from app.models import GraphBuild, GraphEdge, GraphNode

EXPOSURE_RELEVANT = frozenset(
    {
        GraphEdgeType.AFFECTS_COSTS.value,
        GraphEdgeType.AFFECTS_REVENUE.value,
        GraphEdgeType.AFFECTS_FINANCING.value,
        GraphEdgeType.INFLUENCES.value,
        GraphEdgeType.IN_INDUSTRY.value,
        GraphEdgeType.SUPPLIES_TO.value,
        GraphEdgeType.LENDS_TO.value,
    }
)
MAX_CHANGES = 500
COMPLETED = (GraphBuildStatus.COMPLETED, GraphBuildStatus.COMPLETED_WITH_WARNINGS)


@dataclass(frozen=True)
class BuildRef:
    id: int
    finished_at: datetime | None
    status: str


@dataclass(frozen=True)
class EdgeChange:
    change: str  # added | changed | retired
    edge_key: str
    edge_type: str
    label: str
    source: str
    source_name: str
    target: str
    target_name: str
    evidence_status: str
    quality_status: str
    exposure_relevant: bool


@dataclass(frozen=True)
class RelationshipChanges:
    build: BuildRef | None
    previous: BuildRef | None
    edges: tuple[EdgeChange, ...]
    counts: dict[str, int]
    truncated: bool
    note: str


def _ref(build: GraphBuild | None) -> BuildRef | None:
    if build is None:
        return None
    return BuildRef(build.id, build.finished_at, str(build.status.value))


def relationship_changes(session: Session) -> RelationshipChanges:
    builds = session.scalars(
        select(GraphBuild)
        .where(GraphBuild.status.in_(COMPLETED))
        .order_by(GraphBuild.id.desc())
        .limit(2)
    ).all()
    latest = builds[0] if builds else None
    previous = builds[1] if len(builds) > 1 else None
    if latest is None:
        return RelationshipChanges(None, None, (), {}, False, "No graph has been built yet.")
    if previous is None:
        return RelationshipChanges(
            _ref(latest),
            None,
            (),
            {},
            False,
            "This is the first build: there is no earlier build to compare with.",
        )
    rows = session.scalars(
        select(GraphEdge)
        .where(
            or_(
                GraphEdge.first_build_id == latest.id,
                GraphEdge.changed_build_id == latest.id,
                GraphEdge.retired_build_id == latest.id,
            )
        )
        .order_by(GraphEdge.edge_type, GraphEdge.source_node_id, GraphEdge.target_node_id)
        .limit(MAX_CHANGES + 1)
    ).all()
    truncated = len(rows) > MAX_CHANGES
    rows = rows[:MAX_CHANGES]
    keys = {key for row in rows for key in (row.source_node_id, row.target_node_id)}
    names = {
        node.id: node.display_name
        for node in session.scalars(select(GraphNode).where(GraphNode.id.in_(sorted(keys)))).all()
    }
    edges: list[EdgeChange] = []
    for row in rows:
        if row.retired_build_id == latest.id:
            change = "retired"
        elif row.first_build_id == latest.id:
            change = "added"
        else:
            change = "changed"
        edge_type = str(row.edge_type.value)
        spec = EDGE_TYPES.get(GraphEdgeType(edge_type))
        edges.append(
            EdgeChange(
                change=change,
                edge_key=row.id,
                edge_type=edge_type,
                label=spec.label if spec else edge_type,
                source=row.source_node_id,
                source_name=names.get(row.source_node_id, row.source_node_id),
                target=row.target_node_id,
                target_name=names.get(row.target_node_id, row.target_node_id),
                evidence_status=str(row.evidence_status.value),
                quality_status=str(row.quality_status.value),
                exposure_relevant=edge_type in EXPOSURE_RELEVANT,
            )
        )
    edges.sort(key=lambda e: (not e.exposure_relevant, e.change, e.edge_type, e.source, e.target))
    counts = {
        "added": sum(1 for e in edges if e.change == "added"),
        "changed": sum(1 for e in edges if e.change == "changed"),
        "retired": sum(1 for e in edges if e.change == "retired"),
    }
    note = (
        "Changes in RUMIN's records between two builds of the knowledge graph, not changes "
        "observed in the economy. A changed edge's earlier content is not kept."
    )
    return RelationshipChanges(_ref(latest), _ref(previous), tuple(edges), counts, truncated, note)
