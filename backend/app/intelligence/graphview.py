"""Bounded, read-only slices of the knowledge graph for the intelligence layer.

Only **validated** edges are read: current in the latest completed build and with
``quality_status = validated`` (they passed every validation rule of the build). Edges the
build flagged are read separately, only to be listed as *not used*. Every edge keeps its
evidence status, its registry label and caveat, and its curated attributes (polarity,
strength, rationale), so every statement built on it can say what kind of support it has.

Two loaders fill the same in-memory slice: one for a single entity (a handful of queries
around it) and one for the whole workspace (one query per edge type, bounded).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import GraphEdgeType, GraphNodeType, QualityStatus
from app.domain.graph_types import EDGE_TYPES
from app.models import EconomicSeries, GraphEdge, GraphNode

AFFECTS = (
    GraphEdgeType.AFFECTS_COSTS,
    GraphEdgeType.AFFECTS_REVENUE,
    GraphEdgeType.AFFECTS_FINANCING,
)
CHANNEL = {
    GraphEdgeType.AFFECTS_COSTS.value: "costs",
    GraphEdgeType.AFFECTS_REVENUE.value: "revenue",
    GraphEdgeType.AFFECTS_FINANCING.value: "financing",
}
AROUND_ENTITY = (
    GraphEdgeType.IN_INDUSTRY,
    GraphEdgeType.DOMICILED_IN,
    *AFFECTS,
    GraphEdgeType.SUPPLIES_TO,
    GraphEdgeType.LENDS_TO,
    GraphEdgeType.COMPETES_WITH,
)
MAX_INFLUENCE_HOPS = 2


@dataclass(frozen=True)
class NodeInfo:
    key: str
    name: str
    node_type: str
    nature: str
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def category(self) -> str | None:
        value = self.attributes.get("category")
        return str(value) if value else None


@dataclass(frozen=True)
class EdgeInfo:
    key: str
    edge_type: str
    label: str
    source: str
    target: str
    evidence_status: str
    is_illustrative: bool
    quality_status: str
    description: str
    caveat: str
    polarity: str | None
    strength: str | None
    rationale: str | None
    evidence_level: str | None
    stated_difference: str | None


@dataclass(frozen=True)
class SeriesInfo:
    series_id: str
    name: str
    unit: str
    frequency: str
    measure_type: str
    observation_count: int
    first_period: date | None
    last_period: date | None


@dataclass
class GraphSlice:
    build_id: int | None
    edges: dict[str, EdgeInfo] = field(default_factory=dict)
    flagged: dict[str, EdgeInfo] = field(default_factory=dict)
    nodes: dict[str, NodeInfo] = field(default_factory=dict)
    series: dict[str, SeriesInfo] = field(default_factory=dict)  # by series node key
    truncated: bool = False

    def add(self, edges: Iterable[EdgeInfo]) -> None:
        for edge in edges:
            self.edges[edge.key] = edge

    def by_target(self, target: str, *types: GraphEdgeType) -> list[EdgeInfo]:
        wanted = {item.value for item in types}
        return sorted(
            (e for e in self.edges.values() if e.target == target and e.edge_type in wanted),
            key=_edge_order,
        )

    def by_source(self, source: str, *types: GraphEdgeType) -> list[EdgeInfo]:
        wanted = {item.value for item in types}
        return sorted(
            (e for e in self.edges.values() if e.source == source and e.edge_type in wanted),
            key=_edge_order,
        )

    def of_type(self, *types: GraphEdgeType) -> list[EdgeInfo]:
        wanted = {item.value for item in types}
        return sorted((e for e in self.edges.values() if e.edge_type in wanted), key=_edge_order)

    def node(self, key: str) -> NodeInfo:
        return self.nodes.get(key) or NodeInfo(key, key, key.partition(":")[0], "unknown")


def _edge_order(edge: EdgeInfo) -> tuple[str, str, str]:
    return (edge.edge_type, edge.source, edge.target)


def _edge(row: GraphEdge) -> EdgeInfo:
    attributes = row.attributes or {}
    spec = EDGE_TYPES.get(GraphEdgeType(row.edge_type))
    return EdgeInfo(
        key=row.id,
        edge_type=str(row.edge_type.value),
        label=spec.label if spec else str(row.edge_type.value),
        source=row.source_node_id,
        target=row.target_node_id,
        evidence_status=str(row.evidence_status.value),
        is_illustrative=row.is_illustrative,
        quality_status=str(row.quality_status.value),
        description=row.description or (spec.description if spec else ""),
        caveat=spec.caveat if spec else "",
        polarity=_text(attributes.get("polarity")),
        strength=_text(attributes.get("strength")),
        rationale=_text(attributes.get("rationale")),
        evidence_level=_text(attributes.get("evidence_level")),
        stated_difference=_text(attributes.get("stated_difference")),
    )


def _text(value: object) -> str | None:
    return str(value) if value not in (None, "") else None


def query_edges(
    session: Session,
    *,
    types: Iterable[GraphEdgeType],
    sources: Iterable[str] | None = None,
    targets: Iterable[str] | None = None,
    flagged: bool = False,
    limit: int | None = None,
) -> list[EdgeInfo]:
    """Current edges of the given types between the given ends: validated ones, or (with
    ``flagged``) only those the build flagged."""
    query = select(GraphEdge).where(
        GraphEdge.retired_build_id.is_(None),
        GraphEdge.quality_status == (QualityStatus.WARNING if flagged else QualityStatus.VALIDATED),
        GraphEdge.edge_type.in_([item.value for item in types]),
    )
    if sources is not None:
        wanted = sorted(set(sources))
        if not wanted:
            return []
        query = query.where(GraphEdge.source_node_id.in_(wanted))
    if targets is not None:
        wanted = sorted(set(targets))
        if not wanted:
            return []
        query = query.where(GraphEdge.target_node_id.in_(wanted))
    query = query.order_by(GraphEdge.edge_type, GraphEdge.source_node_id, GraphEdge.target_node_id)
    if limit is not None:
        query = query.limit(limit)
    return [_edge(row) for row in session.scalars(query).all()]


def query_nodes(session: Session, keys: Iterable[str]) -> dict[str, NodeInfo]:
    wanted = sorted(set(keys))
    found: dict[str, NodeInfo] = {}
    for start in range(0, len(wanted), 500):
        rows = session.scalars(
            select(GraphNode).where(
                GraphNode.id.in_(wanted[start : start + 500]),
                GraphNode.retired_build_id.is_(None),
            )
        ).all()
        for row in rows:
            found[row.id] = NodeInfo(
                key=row.id,
                name=row.display_name,
                node_type=str(row.node_type.value),
                nature=str(row.nature.value),
                attributes=dict(row.attributes or {}),
            )
    return found


def _attach_series(session: Session, graph: GraphSlice) -> None:
    """Stored-data summaries for the series nodes in the slice."""
    ids = {
        str(node.attributes.get("series_id")): key
        for key, node in graph.nodes.items()
        if node.node_type == "data_series" and node.attributes.get("series_id")
    }
    if not ids:
        return
    rows = session.scalars(select(EconomicSeries).where(EconomicSeries.id.in_(sorted(ids)))).all()
    for row in rows:
        graph.series[ids[row.id]] = SeriesInfo(
            series_id=row.id,
            name=row.name,
            unit=row.unit,
            frequency=str(row.frequency.value),
            measure_type=str(row.measure_type.value),
            observation_count=row.observation_count,
            first_period=row.first_period,
            last_period=row.last_period,
        )


def _upstream(session: Session, graph: GraphSlice, variables: set[str]) -> set[str]:
    """Add `influences` edges ending at ``variables``, up to two hops back."""
    reached = set(variables)
    frontier = set(variables)
    for _ in range(MAX_INFLUENCE_HOPS):
        hops = query_edges(session, types=(GraphEdgeType.INFLUENCES,), targets=frontier)
        graph.add(hops)
        frontier = {edge.source for edge in hops} - reached
        reached |= frontier
        if not frontier:
            break
    return reached


def load_entity(session: Session, entity_key: str, build_id: int | None) -> GraphSlice:
    """Everything the exposure analysis reads around one company or industry."""
    graph = GraphSlice(build_id=build_id)
    graph.add(query_edges(session, types=AROUND_ENTITY, sources=[entity_key]))
    graph.add(query_edges(session, types=AROUND_ENTITY, targets=[entity_key]))
    industries = {e.target for e in graph.by_source(entity_key, GraphEdgeType.IN_INDUSTRY)}
    if entity_key.startswith("industry:"):
        industries.add(entity_key)
    countries = {e.target for e in graph.by_source(entity_key, GraphEdgeType.DOMICILED_IN)}
    graph.add(
        query_edges(
            session, types=(*AFFECTS, GraphEdgeType.SUPPLIES_TO), targets=industries - {entity_key}
        )
    )
    graph.add(
        query_edges(
            session,
            types=(GraphEdgeType.SUPPLIES_TO, GraphEdgeType.IN_SECTOR),
            sources=industries,
        )
    )
    graph.add(query_edges(session, types=(GraphEdgeType.HAS_CURRENCY,), sources=countries))
    exposed = {e.source for e in graph.of_type(*AFFECTS)}
    variables = _upstream(session, graph, exposed)
    graph.add(query_edges(session, types=(GraphEdgeType.RELATED_MEASURE_OF,), targets=variables))
    touching = [entity_key, *sorted(industries)]
    for edge in query_edges(session, types=AROUND_ENTITY, sources=touching, flagged=True):
        graph.flagged[edge.key] = edge
    for edge in query_edges(session, types=AROUND_ENTITY, targets=touching, flagged=True):
        graph.flagged[edge.key] = edge
    keys = {entity_key}
    for edge in [*graph.edges.values(), *graph.flagged.values()]:
        keys.update((edge.source, edge.target))
    graph.nodes = query_nodes(session, keys)
    _attach_series(session, graph)
    return graph


def load_workspace(session: Session, build_id: int | None, *, limit: int) -> GraphSlice:
    """The edges every company's exposures are computed from, in one pass, bounded."""
    graph = GraphSlice(build_id=build_id)
    graph.add(query_edges(session, types=AFFECTS, limit=limit))
    graph.add(query_edges(session, types=(GraphEdgeType.INFLUENCES,), limit=limit))
    industries = {e.target for e in graph.of_type(*AFFECTS) if e.target.startswith("industry:")}
    graph.add(query_edges(session, types=(GraphEdgeType.IN_INDUSTRY,), targets=industries))
    variables = {e.source for e in graph.of_type(*AFFECTS)} | {
        key for e in graph.of_type(GraphEdgeType.INFLUENCES) for key in (e.source, e.target)
    }
    graph.add(query_edges(session, types=(GraphEdgeType.RELATED_MEASURE_OF,), targets=variables))
    companies = session.scalars(
        select(GraphNode.id)
        .where(GraphNode.retired_build_id.is_(None), GraphNode.node_type == GraphNodeType.COMPANY)
        .order_by(GraphNode.display_name, GraphNode.id)
        .limit(limit + 1)
    ).all()
    graph.truncated = len(companies) > limit
    keys = set(companies[:limit])
    for edge in graph.edges.values():
        keys.update((edge.source, edge.target))
    graph.nodes = query_nodes(session, keys)
    _attach_series(session, graph)
    return graph


def members(graph: GraphSlice) -> dict[str, list[EdgeInfo]]:
    """Company → its `in_industry` edges, from a workspace slice."""
    found: dict[str, list[EdgeInfo]] = defaultdict(list)
    for edge in graph.of_type(GraphEdgeType.IN_INDUSTRY):
        found[edge.source].append(edge)
    return found
