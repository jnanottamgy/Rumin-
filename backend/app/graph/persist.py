"""Write a draft graph into the graph tables — add, change, retire; never delete.

Each node and edge is compared with its stored row by a content hash:

* not stored yet → inserted (**added**), with this build as first and last change;
* stored but retired → brought back (**added** again) with its new content;
* stored with a different hash → updated (**changed**);
* stored with the same hash → left alone (**unchanged**);
* stored but no longer produced → marked retired by this build (**retired**) and kept.

So rebuilding from unchanged sources changes nothing, and the graph's membership at any
past build can be reconstructed. Degree and component are refreshed on every build but
do not count as changes: they are derived from the edges, not stated by a source.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.domain.graph_types import EDGE_TYPES
from app.graph.algorithms import (
    Degree,
    Incidence,
    MemoryAdjacency,
    connected_components,
    degrees,
)
from app.graph.drafts import EdgeDraft, GraphDraft, NodeDraft, content_hash
from app.models import (
    GraphBuild,
    GraphEdge,
    GraphEdgeEvidence,
    GraphIssue,
    GraphNode,
    GraphNodeIdentifier,
    GraphResolutionDecision,
)

_BATCH = 500
T = TypeVar("T")


@dataclass
class Diff:
    added: int = 0
    changed: int = 0
    retired: int = 0
    unchanged: int = 0


def persist(
    session: Session, draft: GraphDraft, build: GraphBuild, now: datetime
) -> tuple[Diff, Diff]:
    """Write ``draft`` as the current graph. Flushes; the caller commits."""
    incidences = [
        Incidence(key, edge.edge_type.value, edge.source_key, edge.target_key, edge.directed)
        for key, edge in draft.edges.items()
    ]
    components = connected_components(draft.nodes, MemoryAdjacency(incidences))
    component_of = {
        node: number for number, members in enumerate(components, start=1) for node in members
    }
    degree = degrees(draft.nodes, incidences)

    node_diff = _write_nodes(session, draft.nodes, build.id, now, degree, component_of)
    _write_identifiers(session, draft.nodes.values())
    edge_diff = _write_edges(session, draft.edges, build.id, now)
    _write_log(session, draft, build.id, now)
    session.flush()
    return node_diff, edge_diff


def _node_values(node: NodeDraft) -> dict[str, object]:
    return {
        "node_type": node.node_type,
        "display_name": node.display_name,
        "subtitle": node.subtitle,
        "description": node.description,
        "nature": node.nature,
        "quality_status": node.quality_status,
        "attributes": node.attributes,
        "sources": [source.as_dict() for source in node.sources],
        "search_text": node.search_text,
    }


def _write_nodes(
    session: Session,
    nodes: dict[str, NodeDraft],
    build_id: int,
    now: datetime,
    degree: dict[str, Degree],
    component_of: dict[str, int],
) -> Diff:
    diff = Diff()
    # Compared by hash from plain rows: loading every node as an ORM object costs far more
    # than the comparison, and an unchanged rebuild writes nothing but derived values.
    stored = {
        key: (digest, retired, (total, incoming, outgoing, component))
        for key, digest, retired, total, incoming, outgoing, component in session.execute(
            select(
                GraphNode.id,
                GraphNode.content_hash,
                GraphNode.retired_build_id,
                GraphNode.degree,
                GraphNode.in_degree,
                GraphNode.out_degree,
                GraphNode.component,
            )
        )
    }
    inserts: list[dict[str, object]] = []
    rewrites: list[dict[str, object]] = []
    derived_only: list[dict[str, object]] = []
    for key, node in nodes.items():
        digest = content_hash(node.hash_payload())
        value = degree[key]
        # Derived from the edges: refreshed every build, never counted as a change.
        derived = {
            "degree": value.total,
            "in_degree": value.incoming,
            "out_degree": value.outgoing,
            "component": component_of[key],
        }
        found = stored.get(key)
        if found is None:
            inserts.append(
                {
                    "id": key,
                    **_node_values(node),
                    **derived,
                    "content_hash": digest,
                    "first_build_id": build_id,
                    "changed_build_id": build_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            diff.added += 1
        elif found[1] is not None or found[0] != digest:
            if found[1] is not None:
                diff.added += 1
            else:
                diff.changed += 1
            rewrites.append(
                {
                    "id": key,
                    **_node_values(node),
                    **derived,
                    "content_hash": digest,
                    "changed_build_id": build_id,
                    "retired_build_id": None,
                    "updated_at": now,
                }
            )
        else:
            diff.unchanged += 1
            if found[2] != tuple(derived.values()):
                derived_only.append({"id": key, **derived})
    retire = [key for key, found in stored.items() if key not in nodes and found[1] is None]
    diff.retired = len(retire)

    _bulk(session, insert(GraphNode), inserts)
    _bulk(session, update(GraphNode), rewrites)
    _bulk(session, update(GraphNode), derived_only)
    for batch in _batches(retire):
        session.execute(
            update(GraphNode)
            .where(GraphNode.id.in_(batch))
            .values(
                retired_build_id=build_id,
                component=None,
                degree=0,
                in_degree=0,
                out_degree=0,
                updated_at=now,
            ),
            execution_options={"synchronize_session": False},
        )
    session.flush()
    return diff


def _batches(items: list[T]) -> Iterator[list[T]]:
    for start in range(0, len(items), _BATCH):
        yield items[start : start + _BATCH]


def _bulk(session: Session, statement: Any, rows: list[dict[str, object]]) -> None:
    """An ORM bulk INSERT, or a bulk UPDATE by primary key, in batches."""
    for batch in _batches(rows):
        session.execute(statement, batch)


def _write_identifiers(session: Session, nodes: Iterable[NodeDraft]) -> None:
    """Make the identifier table equal to the current nodes' identifiers."""
    wanted = {
        (claim.scheme.value, claim.value): (node.key, claim.source.label)
        for node in nodes
        for claim in node.identifiers
    }
    stale: list[int] = []
    for row in session.scalars(select(GraphNodeIdentifier)):
        if wanted.get((row.scheme, row.value)) == (row.node_id, row.source):
            wanted.pop((row.scheme, row.value))
        else:
            stale.append(row.id)
    for start in range(0, len(stale), _BATCH):
        batch = stale[start : start + _BATCH]
        session.execute(delete(GraphNodeIdentifier).where(GraphNodeIdentifier.id.in_(batch)))
    session.flush()
    session.add_all(
        GraphNodeIdentifier(node_id=node_id, scheme=scheme, value=value, source=source)
        for (scheme, value), (node_id, source) in wanted.items()
    )
    session.flush()


def _edge_values(edge: EdgeDraft) -> dict[str, object]:
    spec = EDGE_TYPES[edge.edge_type]
    return {
        "edge_type": edge.edge_type,
        "category": spec.category,
        "source_node_id": edge.source_key,
        "target_node_id": edge.target_key,
        "directed": edge.directed,
        "description": edge.description,
        "evidence_status": edge.evidence_status,
        "is_illustrative": edge.is_illustrative,
        "quality_status": edge.quality_status,
        "valid_from": edge.valid_from,
        "valid_to": edge.valid_to,
        "attributes": edge.attributes,
    }


def _write_edges(
    session: Session, edges: dict[str, EdgeDraft], build_id: int, now: datetime
) -> Diff:
    diff = Diff()
    stored = {
        key: (digest, retired)
        for key, digest, retired in session.execute(
            select(GraphEdge.id, GraphEdge.content_hash, GraphEdge.retired_build_id)
        )
    }
    inserts: list[dict[str, object]] = []
    rewrites: list[dict[str, object]] = []
    rewrite_evidence: list[str] = []
    for key, edge in edges.items():
        digest = content_hash(edge.hash_payload())
        found = stored.get(key)
        if found is None:
            inserts.append(
                {
                    "id": key,
                    **_edge_values(edge),
                    "content_hash": digest,
                    "first_build_id": build_id,
                    "changed_build_id": build_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            rewrite_evidence.append(key)
            diff.added += 1
        elif found[1] is not None or found[0] != digest:
            if found[1] is not None:
                diff.added += 1
            else:
                diff.changed += 1
            rewrites.append(
                {
                    "id": key,
                    **_edge_values(edge),
                    "content_hash": digest,
                    "changed_build_id": build_id,
                    "retired_build_id": None,
                    "updated_at": now,
                }
            )
            rewrite_evidence.append(key)
        else:
            diff.unchanged += 1
    retire = [key for key, found in stored.items() if key not in edges and found[1] is None]
    diff.retired = len(retire)

    _bulk(session, insert(GraphEdge), inserts)
    _bulk(session, update(GraphEdge), rewrites)
    for batch in _batches(retire):
        session.execute(
            update(GraphEdge)
            .where(GraphEdge.id.in_(batch))
            .values(retired_build_id=build_id, updated_at=now),
            execution_options={"synchronize_session": False},
        )
    session.flush()

    # Evidence is replaced for new and changed edges; retired edges keep theirs (history).
    for start in range(0, len(rewrite_evidence), _BATCH):
        batch = rewrite_evidence[start : start + _BATCH]
        session.execute(delete(GraphEdgeEvidence).where(GraphEdgeEvidence.edge_id.in_(batch)))
    _bulk(
        session,
        insert(GraphEdgeEvidence),
        [
            {
                "edge_id": key,
                "rule_id": item.rule,
                "source_kind": item.source_kind,
                "source_table": item.source.table,
                "source_record_id": item.source.record_id,
                "dataset_id": item.source.dataset_id,
                "dataset_version": item.source.dataset_version,
                "statement": item.statement,
                "transformation": item.transformation,
                "derivation": item.derivation,
                "derived_from": list(item.derived_from),
                "citation": item.citation,
                "citation_url": item.citation_url,
                "retrieved_at": item.retrieved_at,
                "recorded_at": item.recorded_at,
            }
            for key in rewrite_evidence
            for item in edges[key].evidence
        ],
    )
    session.flush()
    return diff


def _write_log(session: Session, draft: GraphDraft, build_id: int, now: datetime) -> None:
    session.add_all(
        GraphIssue(
            build_id=build_id,
            subject_kind=item.subject_kind,
            subject_ref=item.subject_ref[:300],
            node_id=item.node_key,
            edge_id=item.edge_key,
            rule=item.rule,
            severity=item.severity,
            outcome=item.outcome,
            message=item.message,
            details=item.details,
            created_at=now,
        )
        for item in draft.issues
    )
    session.add_all(
        GraphResolutionDecision(
            build_id=build_id,
            source_table=item.source.table,
            source_record_id=item.source.record_id,
            source_values=item.source_values,
            node_id=item.node_key,
            method=item.method,
            outcome=item.outcome,
            identifier=item.identifier,
            candidate_node_ids=list(item.candidate_node_keys),
            rationale=item.rationale,
            created_at=now,
        )
        for item in draft.decisions
    )
