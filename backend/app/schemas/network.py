"""The network projection: everything the financial network visualisation needs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.schemas.common import ApiModel
from app.schemas.entity import EntityRead
from app.schemas.relationship import RelationshipRead, RelationshipTypeRead, StructuralLinkRead


class DatasetSummary(ApiModel):
    id: str
    version: str
    name: str
    description: str
    is_illustrative: bool
    provenance_note: str
    license: str
    checksum_sha256: str
    loaded_at: datetime


class NetworkNode(ApiModel):
    id: str
    degree: int = Field(ge=0, description="Number of edges touching this node in the projection.")
    entity: EntityRead


NetworkEdge = Annotated[
    RelationshipRead | StructuralLinkRead,
    Field(discriminator="category"),
]


class NetworkStats(ApiModel):
    node_count: int
    edge_count: int
    economic_edge_count: int
    structural_edge_count: int


class NetworkResponse(ApiModel):
    dataset: DatasetSummary | None = Field(description="Null when no dataset has been loaded.")
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
    relationship_types: list[RelationshipTypeRead]
    stats: NetworkStats
