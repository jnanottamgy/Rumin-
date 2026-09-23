"""Response schemas for relationships, structural links and the type registry."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, computed_field

from app.domain.enums import (
    EntityKind,
    EpistemicCategory,
    EvidenceLevel,
    Polarity,
    RelationshipCategory,
    RelationshipType,
    Strength,
    StructuralLinkType,
)
from app.domain.relationship_types import get_spec
from app.schemas.common import ApiModel, Page


class RelationshipRead(ApiModel):
    """A curated economic relationship — always a model assumption."""

    id: str
    category: Literal[RelationshipCategory.ECONOMIC] = RelationshipCategory.ECONOMIC
    type: RelationshipType
    source_id: str
    target_id: str
    polarity: Polarity = Field(
        description="Assumed effect of an increase in the source on the target measure."
    )
    strength: Strength = Field(description="Illustrative ordinal strength.")
    evidence_level: EvidenceLevel
    epistemic_category: Literal[EpistemicCategory.ASSUMPTION] = Field(
        default=EpistemicCategory.ASSUMPTION,
        description="Relationships are modelling assumptions; evidence_level says how well "
        "each one is supported.",
    )
    description: str
    rationale: str = Field(description="Why the relationship is plausible.")
    reference: str | None
    dataset_id: str

    @computed_field(  # type: ignore[prop-decorator]
        description="False for symmetric types such as competes_with."
    )
    @property
    def directed(self) -> bool:
        return get_spec(self.type).directed


class StructuralLinkRead(ApiModel):
    """A link derived from an entity attribute, e.g. a company's industry."""

    id: str
    category: Literal[RelationshipCategory.STRUCTURAL] = RelationshipCategory.STRUCTURAL
    type: StructuralLinkType
    source_id: str
    target_id: str
    directed: bool = True
    derived_from: str = Field(examples=["companies.industry_id"])
    description: str


class EntityKindPair(ApiModel):
    source_kind: EntityKind
    target_kind: EntityKind


class RelationshipTypeRead(ApiModel):
    type: RelationshipType | StructuralLinkType
    category: RelationshipCategory
    label: str = Field(description="Reads as '<source> <label> <target>'.")
    description: str
    directed: bool
    has_polarity: bool
    allowed_pairs: list[EntityKindPair]


class RelationshipPage(Page[RelationshipRead]):
    """A page of relationships."""
