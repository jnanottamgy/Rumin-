"""Graph projection of the database: nodes, curated edges and derived structural links.

This is the seam for Phase 3: the same projection can be handed to NetworkX (or a graph
database) for traversal and analytics without changing the API contract.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import DatasetKind, StructuralLinkType
from app.models import Company, Dataset, EconomicVariable, Entity, Relationship
from app.schemas.network import (
    DatasetSummary,
    NetworkEdge,
    NetworkNode,
    NetworkResponse,
    NetworkStats,
)
from app.schemas.relationship import RelationshipRead, StructuralLinkRead
from app.services.reference_data import AnyEntity, list_relationship_types, to_entity_read


def current_dataset(session: Session) -> Dataset | None:
    """The curated reference dataset behind the network (provider datasets hold series)."""
    return session.scalars(
        select(Dataset)
        .where(Dataset.kind == DatasetKind.CURATED)
        .order_by(Dataset.loaded_at.desc())
    ).first()


def structural_links(entities: list[Entity]) -> list[StructuralLinkRead]:
    """Derive attribute-based links: a company's industry and country, a variable's economy."""
    names = {entity.id: entity.name for entity in entities}
    links: list[StructuralLinkRead] = []
    for entity in entities:
        if isinstance(entity, Company):
            links.append(
                StructuralLinkRead(
                    id=f"structural:{StructuralLinkType.IN_INDUSTRY}:{entity.id}",
                    type=StructuralLinkType.IN_INDUSTRY,
                    source_id=entity.id,
                    target_id=entity.industry_id,
                    derived_from="companies.industry_id",
                    description=f"{entity.name} operates in {names[entity.industry_id]}.",
                )
            )
            links.append(
                StructuralLinkRead(
                    id=f"structural:{StructuralLinkType.DOMICILED_IN}:{entity.id}",
                    type=StructuralLinkType.DOMICILED_IN,
                    source_id=entity.id,
                    target_id=entity.country_id,
                    derived_from="companies.country_id",
                    description=f"{entity.name} is domiciled in {names[entity.country_id]}.",
                )
            )
        elif isinstance(entity, EconomicVariable) and entity.country_id is not None:
            links.append(
                StructuralLinkRead(
                    id=f"structural:{StructuralLinkType.MEASURED_FOR}:{entity.id}",
                    type=StructuralLinkType.MEASURED_FOR,
                    source_id=entity.id,
                    target_id=entity.country_id,
                    derived_from="economic_variables.country_id",
                    description=f"{entity.name} is measured for {names[entity.country_id]}.",
                )
            )
    return links


def build_network(session: Session) -> NetworkResponse:
    dataset = current_dataset(session)
    entities = list(session.scalars(select(AnyEntity).order_by(AnyEntity.id)).all())
    relationships = session.scalars(select(Relationship).order_by(Relationship.id)).all()

    economic = [RelationshipRead.model_validate(rel) for rel in relationships]
    structural = structural_links(entities)
    edges: list[NetworkEdge] = [*economic, *structural]

    degree: Counter[str] = Counter()
    for edge in edges:
        degree[edge.source_id] += 1
        degree[edge.target_id] += 1

    nodes = [
        NetworkNode(id=entity.id, degree=degree[entity.id], entity=to_entity_read(entity))
        for entity in entities
    ]
    return NetworkResponse(
        dataset=DatasetSummary.model_validate(dataset) if dataset else None,
        nodes=nodes,
        edges=edges,
        relationship_types=list_relationship_types(),
        stats=NetworkStats(
            node_count=len(nodes),
            edge_count=len(edges),
            economic_edge_count=len(economic),
            structural_edge_count=len(structural),
        ),
    )
