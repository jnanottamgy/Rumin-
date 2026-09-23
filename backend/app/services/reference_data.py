"""Read access to reference data: entities, relationships and the type registry."""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, with_polymorphic

from app.core.errors import NotFoundError
from app.domain.enums import EntityKind, RelationshipType
from app.domain.relationship_types import RELATIONSHIP_TYPES
from app.models import Company, Country, EconomicVariable, Entity, Industry, Relationship
from app.schemas.entity import (
    EconomicVariablePage,
    EconomicVariableRead,
    EntityPage,
    EntityRead,
    IndustryPage,
    IndustryRead,
)
from app.schemas.relationship import (
    EntityKindPair,
    RelationshipPage,
    RelationshipRead,
    RelationshipTypeRead,
)
from app.services.common import paginate

ENTITY_ADAPTER: TypeAdapter[EntityRead] = TypeAdapter(EntityRead)

# Loads every subtype's columns in one query (LEFT OUTER JOINs), avoiding N+1 lazy loads.
AnyEntity = with_polymorphic(Entity, [Company, Industry, Country, EconomicVariable])


def to_entity_read(entity: Entity) -> EntityRead:
    return ENTITY_ADAPTER.validate_python(entity, from_attributes=True)


def list_entities(
    session: Session, *, kind: EntityKind | None, limit: int, offset: int
) -> EntityPage:
    statement = select(AnyEntity).order_by(AnyEntity.name, AnyEntity.id)
    if kind is not None:
        statement = statement.where(AnyEntity.kind == kind)
    rows, total = paginate(session, statement, limit, offset)
    return EntityPage(
        items=[to_entity_read(e) for e in rows], total=total, limit=limit, offset=offset
    )


def get_entity(session: Session, entity_id: str) -> EntityRead:
    entity = session.scalar(select(AnyEntity).where(AnyEntity.id == entity_id))
    if entity is None:
        raise NotFoundError(f"No entity with ID '{entity_id}'.")
    return to_entity_read(entity)


def list_industries(session: Session, *, limit: int, offset: int) -> IndustryPage:
    statement = select(Industry).order_by(Industry.name, Industry.id)
    rows, total = paginate(session, statement, limit, offset)
    items = [IndustryRead.model_validate(row) for row in rows]
    return IndustryPage(items=items, total=total, limit=limit, offset=offset)


def list_variables(session: Session, *, limit: int, offset: int) -> EconomicVariablePage:
    statement = select(EconomicVariable).order_by(EconomicVariable.name, EconomicVariable.id)
    rows, total = paginate(session, statement, limit, offset)
    items = [EconomicVariableRead.model_validate(row) for row in rows]
    return EconomicVariablePage(items=items, total=total, limit=limit, offset=offset)


def list_relationships(
    session: Session,
    *,
    relationship_type: RelationshipType | None,
    entity_id: str | None,
    limit: int,
    offset: int,
) -> RelationshipPage:
    statement = select(Relationship).order_by(Relationship.id)
    if relationship_type is not None:
        statement = statement.where(Relationship.type == relationship_type)
    if entity_id is not None:
        statement = statement.where(
            or_(Relationship.source_id == entity_id, Relationship.target_id == entity_id)
        )
    rows, total = paginate(session, statement, limit, offset)
    items = [RelationshipRead.model_validate(row) for row in rows]
    return RelationshipPage(items=items, total=total, limit=limit, offset=offset)


def list_relationship_types() -> list[RelationshipTypeRead]:
    items: list[RelationshipTypeRead] = []
    for spec in RELATIONSHIP_TYPES.values():
        pairs = sorted(spec.allowed_pairs)
        data: dict[str, Any] = {
            "type": spec.type,
            "category": spec.category,
            "label": spec.label,
            "description": spec.description,
            "directed": spec.directed,
            "has_polarity": spec.has_polarity,
            "allowed_pairs": [EntityKindPair(source_kind=s, target_kind=t) for s, t in pairs],
        }
        items.append(RelationshipTypeRead.model_validate(data))
    return items
