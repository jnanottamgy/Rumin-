"""Read access to the stored graph: the API uses it, and so will the simulation engine.

``GraphReader`` returns plain, typed records — never ORM objects — each edge with its
evidence status, so a consumer can decide which relationships it may rely on. The Phase 4
simulation engine must not treat edges as equations: it can use this interface to find
entities, paths, edge metadata, evidence and validity periods, and must model and
validate every simulated relationship itself (see docs/graph/phase-4-integration.md).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import CompoundSelect, select, union_all
from sqlalchemy.orm import Session

from app.domain.enums import (
    EvidenceStatus,
    GraphBuildStatus,
    GraphEdgeType,
    GraphNodeType,
    NodeNature,
    QualityStatus,
    RelationshipCategory,
)
from app.graph.algorithms import (
    EdgeFilter,
    Incidence,
    PathSearch,
    Traversal,
    neighborhood,
    shortest_paths,
)
from app.models import GraphBuild, GraphEdge, GraphEdgeEvidence, GraphNode, GraphNodeIdentifier

# SQLite accepts at most 32,766 bound parameters; stay far below it.
_CHUNK = 400

ASSUMED_EFFECTS = frozenset(
    {GraphEdgeType.AFFECTS_COSTS, GraphEdgeType.AFFECTS_REVENUE, GraphEdgeType.AFFECTS_FINANCING}
)


class SqlAdjacency:
    """``Adjacency`` over the current (non-retired) edges.

    One query per call fetches the edges touching every node in the set, using the partial
    indexes on active edges by source and by target. ``queries`` counts the round trips.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.queries = 0

    def incident(self, node_keys: Collection[str]) -> Mapping[str, Sequence[Incidence]]:
        keys = list(dict.fromkeys(node_keys))
        wanted = set(keys)
        result: dict[str, list[Incidence]] = {key: [] for key in keys}
        seen: dict[str, set[str]] = {key: set() for key in keys}
        columns = (
            GraphEdge.id,
            GraphEdge.edge_type,
            GraphEdge.source_node_id,
            GraphEdge.target_node_id,
            GraphEdge.directed,
            GraphEdge.evidence_status,
            GraphEdge.is_illustrative,
        )
        active = GraphEdge.retired_build_id.is_(None)
        for start in range(0, len(keys), _CHUNK):
            chunk = keys[start : start + _CHUNK]
            # Two index searches in one round trip. `source IN … OR target IN …` would make
            # SQLite scan every edge.
            rows = self.session.execute(
                union_all(
                    select(*columns).where(active, GraphEdge.source_node_id.in_(chunk)),
                    select(*columns).where(active, GraphEdge.target_node_id.in_(chunk)),
                )
            ).all()
            self.queries += 1
            for edge_id, edge_type, source, target, directed, status, illustrative in rows:
                edge = Incidence(
                    edge_id,
                    _value(edge_type),
                    source,
                    target,
                    directed,
                    _value(status),
                    bool(illustrative),
                )
                # An edge between two wanted keys comes back from both halves; keep one.
                for end in {source, target} & wanted:
                    if edge_id not in seen[end]:
                        seen[end].add(edge_id)
                        result[end].append(edge)
        return result


def _value(item: object) -> str:
    """Enum columns in a UNION may come back as plain strings."""
    return str(getattr(item, "value", item))


def edge_ids_touching(keys: Collection[str]) -> CompoundSelect[tuple[str]]:
    """IDs of the current edges with an end in ``keys``, as a UNION of two index searches
    (an ``OR`` across the two endpoint columns would scan every edge)."""
    active = GraphEdge.retired_build_id.is_(None)
    return union_all(
        select(GraphEdge.id).where(active, GraphEdge.source_node_id.in_(keys)),
        select(GraphEdge.id).where(active, GraphEdge.target_node_id.in_(keys)),
    )


# --- Records ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeRecord:
    key: str
    node_type: GraphNodeType
    name: str
    subtitle: str
    description: str
    nature: NodeNature
    quality_status: QualityStatus
    degree: int
    in_degree: int
    out_degree: int
    component: int | None
    attributes: dict[str, Any]
    sources: list[dict[str, Any]]
    first_build_id: int
    changed_build_id: int


@dataclass(frozen=True)
class EdgeRecord:
    key: str
    edge_type: GraphEdgeType
    category: RelationshipCategory
    source: str
    target: str
    directed: bool
    description: str
    evidence_status: EvidenceStatus
    is_illustrative: bool
    quality_status: QualityStatus
    valid_from: date | None
    valid_to: date | None
    attributes: dict[str, Any]
    first_build_id: int
    changed_build_id: int

    def is_historical(self, on: date) -> bool:
        """True when the edge's stated validity ended before ``on``."""
        return self.valid_to is not None and self.valid_to < on


@dataclass(frozen=True)
class EvidenceRecord:
    rule: str
    source_kind: str
    source_table: str
    source_record_id: str
    dataset_id: str | None
    dataset_version: str | None
    statement: str
    transformation: str
    derivation: str
    derived_from: list[str]
    citation: str | None
    citation_url: str | None
    retrieved_at: datetime | None
    recorded_at: datetime | None


@dataclass(frozen=True)
class Subgraph:
    center: str
    depth: dict[str, int]
    nodes: dict[str, NodeRecord]
    edges: dict[str, EdgeRecord]
    # Nodes within reach that were left out because the node budget was spent.
    unexplored: list[str]
    queries: int


@dataclass(frozen=True)
class PathsResult:
    source: str
    target: str
    search: PathSearch
    nodes: dict[str, NodeRecord]
    edges: dict[str, EdgeRecord]
    queries: int


@dataclass(frozen=True)
class Exposure:
    """A variable an entity is linked to by an assumed-effect edge, and how."""

    variable: NodeRecord
    edge: EdgeRecord
    # Set for an indirect exposure: the industry the assumed effect is stated for.
    via: NodeRecord | None


def node_record(row: GraphNode) -> NodeRecord:
    return NodeRecord(
        key=row.id,
        node_type=row.node_type,
        name=row.display_name,
        subtitle=row.subtitle,
        description=row.description,
        nature=row.nature,
        quality_status=row.quality_status,
        degree=row.degree,
        in_degree=row.in_degree,
        out_degree=row.out_degree,
        component=row.component,
        attributes=row.attributes or {},
        sources=row.sources or [],
        first_build_id=row.first_build_id,
        changed_build_id=row.changed_build_id,
    )


def edge_record(row: GraphEdge) -> EdgeRecord:
    return EdgeRecord(
        key=row.id,
        edge_type=row.edge_type,
        category=row.category,
        source=row.source_node_id,
        target=row.target_node_id,
        directed=row.directed,
        description=row.description,
        evidence_status=row.evidence_status,
        is_illustrative=row.is_illustrative,
        quality_status=row.quality_status,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        attributes=row.attributes or {},
        first_build_id=row.first_build_id,
        changed_build_id=row.changed_build_id,
    )


def _chunks(keys: Iterable[str]) -> Iterable[list[str]]:
    items = list(dict.fromkeys(keys))
    for start in range(0, len(items), _CHUNK):
        yield items[start : start + _CHUNK]


class GraphReader:
    """Typed, read-only access to the current graph (retired rows are excluded)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # Builds ----------------------------------------------------------------------------------

    def latest_build(self) -> GraphBuild | None:
        """The latest build that produced a graph (completed, with or without warnings)."""
        return self.session.scalars(
            select(GraphBuild)
            .where(
                GraphBuild.status.in_(
                    (GraphBuildStatus.COMPLETED, GraphBuildStatus.COMPLETED_WITH_WARNINGS)
                )
            )
            .order_by(GraphBuild.id.desc())
        ).first()

    # Nodes and edges -------------------------------------------------------------------------

    def node(self, key: str) -> NodeRecord | None:
        row = self.session.get(GraphNode, key)
        return node_record(row) if row is not None and row.retired_build_id is None else None

    def nodes(self, keys: Iterable[str]) -> dict[str, NodeRecord]:
        found: dict[str, NodeRecord] = {}
        for chunk in _chunks(keys):
            for row in self.session.scalars(
                select(GraphNode).where(
                    GraphNode.id.in_(chunk), GraphNode.retired_build_id.is_(None)
                )
            ):
                found[row.id] = node_record(row)
        return found

    def edge(self, key: str) -> EdgeRecord | None:
        row = self.session.get(GraphEdge, key)
        return edge_record(row) if row is not None and row.retired_build_id is None else None

    def edges(self, keys: Iterable[str]) -> dict[str, EdgeRecord]:
        found: dict[str, EdgeRecord] = {}
        for chunk in _chunks(keys):
            for row in self.session.scalars(
                select(GraphEdge).where(
                    GraphEdge.id.in_(chunk), GraphEdge.retired_build_id.is_(None)
                )
            ):
                found[row.id] = edge_record(row)
        return found

    def identifiers(self, key: str) -> list[tuple[str, str, str]]:
        """(scheme, value, source record) for a node, ordered by scheme."""
        rows = self.session.scalars(
            select(GraphNodeIdentifier)
            .where(GraphNodeIdentifier.node_id == key)
            .order_by(GraphNodeIdentifier.scheme, GraphNodeIdentifier.value)
        )
        return [(row.scheme, row.value, row.source) for row in rows]

    def evidence(self, edge_keys: Iterable[str]) -> dict[str, list[EvidenceRecord]]:
        found: dict[str, list[EvidenceRecord]] = defaultdict(list)
        for chunk in _chunks(edge_keys):
            for row in self.session.scalars(
                select(GraphEdgeEvidence)
                .where(GraphEdgeEvidence.edge_id.in_(chunk))
                .order_by(GraphEdgeEvidence.id)
            ):
                found[row.edge_id].append(
                    EvidenceRecord(
                        rule=row.rule_id,
                        source_kind=row.source_kind.value,
                        source_table=row.source_table,
                        source_record_id=row.source_record_id,
                        dataset_id=row.dataset_id,
                        dataset_version=row.dataset_version,
                        statement=row.statement,
                        transformation=row.transformation,
                        derivation=row.derivation.value,
                        derived_from=list(row.derived_from or []),
                        citation=row.citation,
                        citation_url=row.citation_url,
                        retrieved_at=row.retrieved_at,
                        recorded_at=row.recorded_at,
                    )
                )
        return dict(found)

    def subgraph(self, keys: Collection[str]) -> dict[str, EdgeRecord]:
        """Every current edge whose two ends are both in ``keys`` (an induced subgraph)."""
        adjacency = SqlAdjacency(self.session)
        wanted = set(keys)
        edge_keys = {
            edge.edge_key
            for edges in adjacency.incident(wanted).values()
            for edge in edges
            if edge.source in wanted and edge.target in wanted
        }
        return self.edges(edge_keys)

    # Traversal -------------------------------------------------------------------------------

    def neighborhood(
        self, center: str, *, depth: int, max_nodes: int, edge_filter: EdgeFilter
    ) -> Subgraph:
        adjacency = SqlAdjacency(self.session)
        found: Traversal = neighborhood(
            adjacency, center, depth=depth, max_nodes=max_nodes, edge_filter=edge_filter
        )
        return Subgraph(
            center=center,
            depth=found.depth,
            nodes=self.nodes(found.order),
            edges=self.edges(found.edges),
            unexplored=sorted(found.unexplored),
            queries=adjacency.queries,
        )

    def paths(
        self,
        source: str,
        target: str,
        *,
        max_depth: int,
        limit: int,
        edge_filter: EdgeFilter,
        max_nodes: int,
    ) -> PathsResult:
        adjacency = SqlAdjacency(self.session)
        search = shortest_paths(
            adjacency,
            source,
            target,
            max_depth=max_depth,
            limit=limit,
            edge_filter=edge_filter,
            max_nodes=max_nodes,
        )
        node_keys = {key for path in search.paths for key in path.nodes} | {source, target}
        edge_keys = {key for path in search.paths for key in path.edges}
        return PathsResult(
            source=source,
            target=target,
            search=search,
            nodes=self.nodes(node_keys),
            edges=self.edges(edge_keys),
            queries=adjacency.queries,
        )

    # Financial reading -----------------------------------------------------------------------

    def exposures(self, key: str) -> list[Exposure]:
        """Variables a company or industry is linked to by assumed-effect edges.

        *Direct*: an ``affects_*`` edge stated for the entity itself. *Via industry* (for a
        company): an ``affects_*`` edge stated for the company's industry — assumed for the
        industry as a whole, not stated for this company; companies in one industry can be
        affected very differently. Each exposure keeps its edge's evidence status.
        """
        node = self.node(key)
        if node is None or node.node_type not in (GraphNodeType.COMPANY, GraphNodeType.INDUSTRY):
            return []
        adjacency = SqlAdjacency(self.session)
        around = adjacency.incident([key])[key]
        industries = [
            edge.target
            for edge in around
            if edge.edge_type == GraphEdgeType.IN_INDUSTRY.value and edge.source == key
        ]
        direct: list[tuple[str, str | None]] = [
            (edge.edge_key, None)
            for edge in around
            if edge.edge_type in ASSUMED_EFFECTS and edge.target == key
        ]
        via: list[tuple[str, str | None]] = []
        if industries:
            for industry, incident in adjacency.incident(industries).items():
                via.extend(
                    (edge.edge_key, industry)
                    for edge in incident
                    if edge.edge_type in ASSUMED_EFFECTS and edge.target == industry
                )
        records = self.edges(edge for edge, _ in [*direct, *via])
        nodes = self.nodes(
            [edge.source for edge in records.values()]
            + [industry for _, industry in via if industry]
        )
        exposures = [
            Exposure(nodes[records[edge_key].source], records[edge_key], nodes.get(industry or ""))
            for edge_key, industry in [*direct, *via]
            if edge_key in records and records[edge_key].source in nodes
        ]
        return sorted(
            exposures,
            key=lambda item: (item.via is not None, item.variable.name, item.edge.edge_type.value),
        )
