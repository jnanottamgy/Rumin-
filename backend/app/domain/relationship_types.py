"""The relationship type registry: what each edge type *means*.

Edges read as a sentence: ``<source> <label> <target>``, e.g.
"Brent crude oil price — affects costs of → Petroleum refining".

For types with polarity, ``positive`` means an *increase* in the source is assumed to
*increase* the target measure (the target's costs, revenue, financing costs, or the
target variable). A positive cost effect is therefore usually bad for margins.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import EntityKind, RelationshipCategory, RelationshipType, StructuralLinkType

EdgeType = RelationshipType | StructuralLinkType

_CO = EntityKind.COMPANY
_IND = EntityKind.INDUSTRY
_CTY = EntityKind.COUNTRY
_VAR = EntityKind.ECONOMIC_VARIABLE


@dataclass(frozen=True)
class RelationshipTypeSpec:
    type: EdgeType
    category: RelationshipCategory
    label: str
    description: str
    directed: bool
    has_polarity: bool
    allowed_pairs: frozenset[tuple[EntityKind, EntityKind]]

    def allows(self, source_kind: EntityKind, target_kind: EntityKind) -> bool:
        return (source_kind, target_kind) in self.allowed_pairs


_SPECS = (
    RelationshipTypeSpec(
        type=RelationshipType.SUPPLIES_TO,
        category=RelationshipCategory.ECONOMIC,
        label="supplies",
        description="The source provides goods or services that the target uses as inputs.",
        directed=True,
        has_polarity=False,
        allowed_pairs=frozenset({(_CO, _CO), (_IND, _IND)}),
    ),
    RelationshipTypeSpec(
        type=RelationshipType.LENDS_TO,
        category=RelationshipCategory.ECONOMIC,
        label="lends to",
        description="The source (a lender) provides credit facilities to the target.",
        directed=True,
        has_polarity=False,
        allowed_pairs=frozenset({(_CO, _CO)}),
    ),
    RelationshipTypeSpec(
        type=RelationshipType.COMPETES_WITH,
        category=RelationshipCategory.ECONOMIC,
        label="competes with",
        description="Both entities sell similar products or services in the same market.",
        directed=False,
        has_polarity=False,
        allowed_pairs=frozenset({(_CO, _CO)}),
    ),
    RelationshipTypeSpec(
        type=RelationshipType.AFFECTS_COSTS,
        category=RelationshipCategory.ECONOMIC,
        label="affects costs of",
        description=(
            "Changes in the source variable are assumed to change the target's operating "
            "or input costs."
        ),
        directed=True,
        has_polarity=True,
        allowed_pairs=frozenset({(_VAR, _CO), (_VAR, _IND)}),
    ),
    RelationshipTypeSpec(
        type=RelationshipType.AFFECTS_REVENUE,
        category=RelationshipCategory.ECONOMIC,
        label="affects revenue of",
        description=(
            "Changes in the source variable are assumed to change the target's revenue, "
            "through prices, volumes or currency translation."
        ),
        directed=True,
        has_polarity=True,
        allowed_pairs=frozenset({(_VAR, _CO), (_VAR, _IND)}),
    ),
    RelationshipTypeSpec(
        type=RelationshipType.AFFECTS_FINANCING,
        category=RelationshipCategory.ECONOMIC,
        label="affects financing costs of",
        description=(
            "Changes in the source variable are assumed to change the target's cost of "
            "borrowing or refinancing."
        ),
        directed=True,
        has_polarity=True,
        allowed_pairs=frozenset({(_VAR, _CO), (_VAR, _IND)}),
    ),
    RelationshipTypeSpec(
        type=RelationshipType.INFLUENCES,
        category=RelationshipCategory.ECONOMIC,
        label="influences",
        description=(
            "Changes in the source variable are assumed to transmit to the target variable."
        ),
        directed=True,
        has_polarity=True,
        allowed_pairs=frozenset({(_VAR, _VAR)}),
    ),
    RelationshipTypeSpec(
        type=StructuralLinkType.IN_INDUSTRY,
        category=RelationshipCategory.STRUCTURAL,
        label="operates in",
        description="The company's primary industry (derived from the company record).",
        directed=True,
        has_polarity=False,
        allowed_pairs=frozenset({(_CO, _IND)}),
    ),
    RelationshipTypeSpec(
        type=StructuralLinkType.DOMICILED_IN,
        category=RelationshipCategory.STRUCTURAL,
        label="is domiciled in",
        description="The company's country of domicile (derived from the company record).",
        directed=True,
        has_polarity=False,
        allowed_pairs=frozenset({(_CO, _CTY)}),
    ),
    RelationshipTypeSpec(
        type=StructuralLinkType.MEASURED_FOR,
        category=RelationshipCategory.STRUCTURAL,
        label="is measured for",
        description="The economy the variable describes (derived from the variable record).",
        directed=True,
        has_polarity=False,
        allowed_pairs=frozenset({(_VAR, _CTY)}),
    ),
)

RELATIONSHIP_TYPES: dict[EdgeType, RelationshipTypeSpec] = {spec.type: spec for spec in _SPECS}


def get_spec(edge_type: EdgeType) -> RelationshipTypeSpec:
    return RELATIONSHIP_TYPES[edge_type]
