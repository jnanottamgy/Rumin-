"""Reference data: entities, industries, variables, relationships and relationship types."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import NOT_FOUND, PaginationDep, SessionDep
from app.domain.enums import EntityKind, RelationshipType
from app.schemas.common import ENTITY_ID_PATTERN
from app.schemas.entity import EconomicVariablePage, EntityPage, EntityRead, IndustryPage
from app.schemas.relationship import RelationshipPage, RelationshipTypeRead
from app.services import reference_data

router = APIRouter(tags=["reference data"])

EntityIdPath = Annotated[str, Path(pattern=ENTITY_ID_PATTERN, examples=["co_aerisca_airways"])]


@router.get(
    "/entities",
    response_model=EntityPage,
    summary="List entities",
    description="Companies, industries, countries and economic variables, ordered by name.",
)
def list_entities(
    session: SessionDep,
    page: PaginationDep,
    kind: Annotated[EntityKind | None, Query(description="Only return this kind.")] = None,
) -> EntityPage:
    return reference_data.list_entities(session, kind=kind, limit=page.limit, offset=page.offset)


@router.get(
    "/entities/{entity_id}",
    response_model=EntityRead,
    summary="Get an entity",
    responses=NOT_FOUND,
)
def get_entity(session: SessionDep, entity_id: EntityIdPath) -> EntityRead:
    return reference_data.get_entity(session, entity_id)


@router.get("/industries", response_model=IndustryPage, summary="List industries")
def list_industries(session: SessionDep, page: PaginationDep) -> IndustryPage:
    return reference_data.list_industries(session, limit=page.limit, offset=page.offset)


@router.get(
    "/variables",
    response_model=EconomicVariablePage,
    summary="List economic variables",
    description="Each variable includes `scenario_rules`: the kinds of change it accepts "
    "in a scenario and the limits the API enforces.",
)
def list_variables(session: SessionDep, page: PaginationDep) -> EconomicVariablePage:
    return reference_data.list_variables(session, limit=page.limit, offset=page.offset)


@router.get(
    "/relationships",
    response_model=RelationshipPage,
    summary="List relationships",
    description="Curated economic relationships. All are modelling assumptions; see "
    "`evidence_level` and `rationale` on each.",
)
def list_relationships(
    session: SessionDep,
    page: PaginationDep,
    type: Annotated[RelationshipType | None, Query(description="Filter by type.")] = None,
    entity_id: Annotated[
        str | None,
        Query(pattern=ENTITY_ID_PATTERN, description="Only relationships touching this entity."),
    ] = None,
) -> RelationshipPage:
    return reference_data.list_relationships(
        session,
        relationship_type=type,
        entity_id=entity_id,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/relationship-types",
    response_model=list[RelationshipTypeRead],
    summary="List relationship types",
    description="The registry that defines what every edge type means.",
)
def list_relationship_types() -> list[RelationshipTypeRead]:
    return reference_data.list_relationship_types()
