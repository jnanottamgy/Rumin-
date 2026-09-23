"""The knowledge-graph relationships a model may use, confirmed against the latest build.

Graph edges are not equations. A model *declares* the relationships it accepts
(transmission rules, which carry shocks, and supporting relationships, which it only
cites). This module checks each one against the latest completed graph build:

* the edge must exist as a current edge of the declared type and direction;
* it must have passed the graph's validation (quality status ``validated``).

It also lists the graph's other relationships around the model's variables that **no**
rule accepts — they are shown as "not used by this model", never followed. Everything
confirmed is recorded in the run's graph snapshot with the edge's evidence status and the
build it came from.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.enums import GraphEdgeType, GraphNodeType, QualityStatus
from app.domain.graph_types import EDGE_TYPES
from app.graph.store import GraphReader
from app.models import GraphEdge
from app.simulation.definitions import ModelDefinition
from app.simulation.runtime import Issue

ENTITY = "{entity}"
UNUSED_SHOWN = 30


@dataclass(frozen=True)
class GraphEdgeRef:
    rule: str
    role: Literal["transmission", "supporting"]
    edge_key: str
    edge_type: str
    source: str
    target: str
    evidence_status: str
    is_illustrative: bool
    description: str


@dataclass(frozen=True)
class EntityRef:
    key: str
    name: str
    nature: str


@dataclass(frozen=True)
class UnusedEdge:
    edge_key: str
    edge_type: str
    source: str
    target: str
    evidence_status: str


@dataclass(frozen=True)
class GraphContext:
    build_id: int | None
    build_finished_at: str | None
    source_fingerprint: str | None
    freshness: str
    transmission: dict[str, GraphEdgeRef | None]
    supporting: dict[str, GraphEdgeRef | None]
    entity: EntityRef | None
    unused: tuple[UnusedEdge, ...]
    unused_total: int
    # Names of the nodes the snapshot mentions, as the build recorded them.
    names: dict[str, str]

    def snapshot(self) -> dict[str, Any]:
        """The JSON form stored with a run."""
        return {
            "build_id": self.build_id,
            "build_finished_at": self.build_finished_at,
            "source_fingerprint": self.source_fingerprint,
            "freshness": self.freshness,
            "transmission": {
                rule: asdict(edge) if edge else None for rule, edge in self.transmission.items()
            },
            "supporting": {
                rule: asdict(edge) if edge else None for rule, edge in self.supporting.items()
            },
            "entity": asdict(self.entity) if self.entity else None,
            "unused": [asdict(edge) for edge in self.unused],
            "unused_total": self.unused_total,
            "names": dict(sorted(self.names.items())),
        }


def _find_edge(session: Session, edge_type: str, source: str, target: str) -> GraphEdge | None:
    return session.scalars(
        select(GraphEdge).where(
            GraphEdge.retired_build_id.is_(None),
            GraphEdge.edge_type == edge_type,
            GraphEdge.source_node_id == source,
            GraphEdge.target_node_id == target,
        )
    ).first()


def _ref(
    edge: GraphEdge, rule: str, role: Literal["transmission", "supporting"], description: str
) -> GraphEdgeRef:
    return GraphEdgeRef(
        rule=rule,
        role=role,
        edge_key=edge.id,
        edge_type=str(edge.edge_type.value),
        source=edge.source_node_id,
        target=edge.target_node_id,
        evidence_status=str(edge.evidence_status.value),
        is_illustrative=edge.is_illustrative,
        description=description,
    )


def model_nodes(definition: ModelDefinition) -> set[str]:
    """The graph nodes a model's inputs and rules refer to."""
    nodes = {item.variable for item in definition.inputs if item.variable}
    for rule in definition.transmission_rules:
        nodes |= {rule.source, rule.target}
    return nodes


def _unused(
    session: Session, definition: ModelDefinition, accepted: Iterable[tuple[str, str, str]]
) -> tuple[list[UnusedEdge], int]:
    nodes = sorted(model_nodes(definition))
    known = set(accepted)
    rows = session.scalars(
        select(GraphEdge)
        .where(
            GraphEdge.retired_build_id.is_(None),
            or_(GraphEdge.source_node_id.in_(nodes), GraphEdge.target_node_id.in_(nodes)),
        )
        .order_by(GraphEdge.source_node_id, GraphEdge.edge_type, GraphEdge.target_node_id)
    ).all()
    unused = [
        UnusedEdge(
            row.id,
            str(row.edge_type.value),
            row.source_node_id,
            row.target_node_id,
            str(row.evidence_status.value),
        )
        for row in rows
        if (str(row.edge_type.value), row.source_node_id, row.target_node_id) not in known
    ]
    return unused[:UNUSED_SHOWN], len(unused)


def load_graph_context(
    session: Session, definition: ModelDefinition, entity_key: str | None, freshness: str
) -> tuple[GraphContext, list[Issue]]:
    """Confirm a model's relationships in the latest graph build.

    ``freshness`` is the graph overview's answer ("current", "stale" or "not_built").
    Returns the context and the issues found about the entity or the build. Whether a
    missing transmission edge blocks a run depends on the shocks, so the engine decides.
    """
    issues: list[Issue] = []
    reader = GraphReader(session)
    build = reader.latest_build()
    if build is None:
        if entity_key:
            issues.append(
                Issue(
                    "entity_is_airline",
                    "The knowledge graph has not been built, so the airline cannot be looked "
                    "up. Build it (make graph) or leave the airline empty.",
                    field="entity",
                )
            )
        return (
            GraphContext(
                build_id=None,
                build_finished_at=None,
                source_fingerprint=None,
                freshness="not_built",
                transmission={rule.id: None for rule in definition.transmission_rules},
                supporting={item.id: None for item in definition.supporting_relationships},
                entity=None,
                unused=(),
                unused_total=0,
                names={},
            ),
            issues,
        )

    if freshness == "stale":
        issues.append(
            Issue(
                "graph_stale",
                f"The knowledge graph (build #{build.id}) is older than its sources. The "
                "relationships it confirms are those of that build; rebuild it with make graph "
                "to use the current data.",
                severity="warning",
            )
        )

    transmission: dict[str, GraphEdgeRef | None] = {}
    accepted: list[tuple[str, str, str]] = []
    for rule in definition.transmission_rules:
        accepted.append((rule.edge_type, rule.source, rule.target))
        edge = _find_edge(session, rule.edge_type, rule.source, rule.target)
        if edge is not None and edge.quality_status is not QualityStatus.VALIDATED:
            edge = None  # flagged by the graph's validation: not used for simulation
        transmission[rule.id] = (
            _ref(edge, rule.id, "transmission", rule.description) if edge else None
        )

    entity: EntityRef | None = None
    if entity_key:
        node = reader.node(entity_key)
        if node is None:
            issues.append(
                Issue(
                    "entity_is_airline",
                    f"'{entity_key}' is not a node in the current knowledge graph.",
                    field="entity",
                )
            )
            entity_key = None
        elif node.node_type is not GraphNodeType.COMPANY:
            issues.append(
                Issue(
                    "entity_is_airline",
                    f"{node.name} is a {node.node_type.value.replace('_', ' ')}, not a company.",
                    field="entity",
                )
            )
            entity_key = None
        else:
            entity = EntityRef(node.key, node.name, node.nature.value)

    supporting: dict[str, GraphEdgeRef | None] = {}
    for item in definition.supporting_relationships:
        needs_entity = ENTITY in (item.source, item.target)
        if needs_entity and entity is None:
            continue
        source = item.source.replace(ENTITY, entity.key if entity else "")
        target = item.target.replace(ENTITY, entity.key if entity else "")
        accepted.append((item.edge_type, source, target))
        edge = _find_edge(session, item.edge_type, source, target)
        supporting[item.id] = _ref(edge, item.id, "supporting", item.role) if edge else None
        if item.required_with_entity and entity is not None and edge is None:
            other = reader.node(target if source == entity.key else source)
            label = EDGE_TYPES[GraphEdgeType(item.edge_type)].label
            issues.append(
                Issue(
                    "entity_is_airline",
                    f"The knowledge graph does not state that {entity.name} {label} "
                    f"{other.name if other else target}, so this model cannot simulate it.",
                    field="entity",
                )
            )

    unused, unused_total = _unused(session, definition, accepted)
    mentioned = model_nodes(definition) | {
        end
        for edge in [*transmission.values(), *supporting.values()]
        if edge is not None
        for end in (edge.source, edge.target)
    }
    mentioned |= {end for edge in unused for end in (edge.source, edge.target)}
    names = {key: node.name for key, node in reader.nodes(mentioned).items()}
    return (
        GraphContext(
            build_id=build.id,
            build_finished_at=build.finished_at.isoformat() if build.finished_at else None,
            source_fingerprint=build.source_fingerprint,
            freshness=freshness,
            transmission=transmission,
            supporting=supporting,
            entity=entity,
            unused=tuple(unused),
            unused_total=unused_total,
            names=names,
        ),
        issues,
    )


def needed_rules(definition: ModelDefinition, shocked_nodes: set[str]) -> list[str]:
    """Transmission rules on some path from a shocked node (within the depth limit)."""
    needed: list[str] = []
    frontier = set(shocked_nodes)
    seen = set(frontier)
    for _ in range(definition.max_propagation_depth):
        next_frontier: set[str] = set()
        for rule in definition.transmission_rules:
            if rule.source in frontier:
                if rule.id not in needed:
                    needed.append(rule.id)
                if rule.target not in seen:
                    next_frontier.add(rule.target)
        seen |= next_frontier
        frontier = next_frontier
        if not frontier:
            break
    return needed
