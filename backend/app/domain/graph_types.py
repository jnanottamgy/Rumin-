"""The knowledge graph's vocabulary: node types, edge types and evidence statuses.

Every edge type says what an edge *means*, which node types it may connect, whether it
has a direction, which evidence statuses it may carry, and what it does *not* mean (its
caveat). Phase 1's economic and structural relationship types keep their meaning: their
labels, descriptions and direction come from ``app.domain.relationship_types`` instead of
being written twice.

An edge reads as a sentence: ``<source> <label> <target>``, e.g.
"Aerisca Airways — operates in → Air transport".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import (
    EntityKind,
    EvidenceStatus,
    GraphEdgeType,
    GraphNodeType,
    IdentifierScheme,
    RelationshipCategory,
    RelationshipType,
    StructuralLinkType,
)
from app.domain.relationship_types import RELATIONSHIP_TYPES

# --- Node types -------------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeTypeSpec:
    type: GraphNodeType
    label: str
    plural: str
    description: str
    # The identifier shown first when two nodes need telling apart (None: no external one).
    primary_scheme: IdentifierScheme | None


NODE_TYPES: dict[GraphNodeType, NodeTypeSpec] = {
    spec.type: spec
    for spec in (
        NodeTypeSpec(
            GraphNodeType.COUNTRY,
            "Country",
            "Countries",
            "A country from the reference data, identified by its ISO 3166-1 code.",
            IdentifierScheme.ISO3166_ALPHA2,
        ),
        NodeTypeSpec(
            GraphNodeType.CURRENCY,
            "Currency",
            "Currencies",
            "A currency, identified by its ISO 4217 code wherever a record names one.",
            IdentifierScheme.ISO4217,
        ),
        NodeTypeSpec(
            GraphNodeType.SECTOR,
            "Sector",
            "Sectors",
            "A section of the ISIC Rev. 4 classification (the level above its divisions).",
            IdentifierScheme.ISIC_REV4_SECTION,
        ),
        NodeTypeSpec(
            GraphNodeType.INDUSTRY,
            "Industry",
            "Industries",
            "An ISIC Rev. 4 division from the reference data.",
            IdentifierScheme.ISIC_REV4_DIVISION,
        ),
        NodeTypeSpec(
            GraphNodeType.COMPANY,
            "Company",
            "Companies",
            "A company. Every company in the sample network is fictional.",
            None,
        ),
        NodeTypeSpec(
            GraphNodeType.ECONOMIC_VARIABLE,
            "Economic variable",
            "Economic variables",
            "The definition of a measurable economic quantity, such as a price or a rate.",
            None,
        ),
        NodeTypeSpec(
            GraphNodeType.DATA_SERIES,
            "Data series",
            "Data series",
            "A provider's time series (e.g. a World Bank indicator for one country).",
            IdentifierScheme.PROVIDER_SERIES,
        ),
        NodeTypeSpec(
            GraphNodeType.INSTRUMENT,
            "Instrument",
            "Instruments",
            "A listed security from a price file a user imported.",
            IdentifierScheme.ISIN,
        ),
        NodeTypeSpec(
            GraphNodeType.MARKET,
            "Market",
            "Markets",
            "A trading venue, identified by its ISO 10383 market identifier code (MIC).",
            IdentifierScheme.MIC,
        ),
    )
}

IDENTIFIER_LABELS: dict[IdentifierScheme, str] = {
    IdentifierScheme.ISO3166_ALPHA2: "ISO 3166-1 alpha-2",
    IdentifierScheme.ISO3166_ALPHA3: "ISO 3166-1 alpha-3",
    IdentifierScheme.ISO4217: "ISO 4217",
    IdentifierScheme.ISIC_REV4_SECTION: "ISIC Rev. 4 section",
    IdentifierScheme.ISIC_REV4_DIVISION: "ISIC Rev. 4 division",
    IdentifierScheme.PROVIDER_SERIES: "Provider series key",
    IdentifierScheme.ISIN: "ISIN",
    IdentifierScheme.MIC: "ISO 10383 MIC",
    IdentifierScheme.LISTING: "Listing (MIC:symbol)",
}

# --- Evidence statuses ------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceStatusSpec:
    status: EvidenceStatus
    label: str
    definition: str


EVIDENCE_STATUSES: dict[EvidenceStatus, EvidenceStatusSpec] = {
    spec.status: spec
    for spec in (
        EvidenceStatusSpec(
            EvidenceStatus.EVIDENCE_BACKED,
            "Evidence-backed",
            "Stated by a cited external source or standard (a classification, an ISO code, a "
            "provider's metadata). RUMIN transcribed it; it did not measure or validate it.",
        ),
        EvidenceStatusSpec(
            EvidenceStatus.ANALYST_CREATED,
            "Analyst-created",
            "Written by a RUMIN curator, with its reasoning recorded — for example a fictional "
            "company's industry, or a series recorded as a related measure of a variable.",
        ),
        EvidenceStatusSpec(
            EvidenceStatus.MODEL_ASSUMPTION,
            "Model assumption",
            "An assumed economic relationship with a written rationale. It is not an "
            "empirical finding and has not been validated.",
        ),
        EvidenceStatusSpec(
            EvidenceStatus.UNVERIFIED,
            "Unverified",
            "Declared in data supplied to RUMIN (for example a price-file manifest). "
            "Recorded as declared; RUMIN could not check it.",
        ),
    )
}

# --- Edge types -------------------------------------------------------------------------------


@dataclass(frozen=True)
class EdgeTypeSpec:
    type: GraphEdgeType
    category: RelationshipCategory
    label: str
    description: str
    # What the edge does not mean. Shown with every edge of the type.
    caveat: str
    directed: bool
    allowed_pairs: frozenset[tuple[GraphNodeType, GraphNodeType]]
    evidence_statuses: frozenset[EvidenceStatus]

    def allows(self, source: GraphNodeType, target: GraphNodeType) -> bool:
        return (source, target) in self.allowed_pairs


_NODE_FOR_KIND = {
    EntityKind.COMPANY: GraphNodeType.COMPANY,
    EntityKind.INDUSTRY: GraphNodeType.INDUSTRY,
    EntityKind.COUNTRY: GraphNodeType.COUNTRY,
    EntityKind.ECONOMIC_VARIABLE: GraphNodeType.ECONOMIC_VARIABLE,
}

_ASSUMED_EFFECT = (
    "An assumed effect, not a measured one: it says nothing about size or timing, and "
    "entities of the same kind can be affected very differently. A connection is not "
    "evidence of causation."
)

# Caveats and allowed evidence statuses for Phase 1's types (their meaning is Phase 1's).
_PHASE1: dict[RelationshipType | StructuralLinkType, tuple[str, frozenset[EvidenceStatus]]] = {
    RelationshipType.SUPPLIES_TO: (
        "A recorded supply relationship. It does not say how large or how important it is.",
        frozenset({EvidenceStatus.MODEL_ASSUMPTION, EvidenceStatus.EVIDENCE_BACKED}),
    ),
    RelationshipType.LENDS_TO: (
        "A recorded lending relationship. It says nothing about amounts, terms or risk.",
        frozenset({EvidenceStatus.MODEL_ASSUMPTION, EvidenceStatus.EVIDENCE_BACKED}),
    ),
    RelationshipType.COMPETES_WITH: (
        "The two sell similar products in the same market; it does not rank them.",
        frozenset({EvidenceStatus.MODEL_ASSUMPTION, EvidenceStatus.EVIDENCE_BACKED}),
    ),
    RelationshipType.AFFECTS_COSTS: (
        _ASSUMED_EFFECT,
        frozenset({EvidenceStatus.MODEL_ASSUMPTION, EvidenceStatus.EVIDENCE_BACKED}),
    ),
    RelationshipType.AFFECTS_REVENUE: (
        _ASSUMED_EFFECT,
        frozenset({EvidenceStatus.MODEL_ASSUMPTION, EvidenceStatus.EVIDENCE_BACKED}),
    ),
    RelationshipType.AFFECTS_FINANCING: (
        _ASSUMED_EFFECT,
        frozenset({EvidenceStatus.MODEL_ASSUMPTION, EvidenceStatus.EVIDENCE_BACKED}),
    ),
    RelationshipType.INFLUENCES: (
        "Assumed transmission between two variables, not a statistical or causal estimate.",
        frozenset({EvidenceStatus.MODEL_ASSUMPTION}),
    ),
    StructuralLinkType.IN_INDUSTRY: (
        "A primary-industry classification. A company can also operate in other industries.",
        frozenset({EvidenceStatus.ANALYST_CREATED, EvidenceStatus.EVIDENCE_BACKED}),
    ),
    StructuralLinkType.DOMICILED_IN: (
        "Country of domicile only — not where the company sells, produces or is exposed.",
        frozenset({EvidenceStatus.ANALYST_CREATED, EvidenceStatus.EVIDENCE_BACKED}),
    ),
    StructuralLinkType.MEASURED_FOR: (
        "The economy the variable describes. It does not mean the variable matters only there.",
        frozenset({EvidenceStatus.ANALYST_CREATED}),
    ),
}


def _from_phase1(edge_type: RelationshipType | StructuralLinkType) -> EdgeTypeSpec:
    spec = RELATIONSHIP_TYPES[edge_type]
    caveat, statuses = _PHASE1[edge_type]
    return EdgeTypeSpec(
        type=GraphEdgeType(edge_type.value),
        category=spec.category,
        label=spec.label,
        description=spec.description,
        caveat=caveat,
        directed=spec.directed,
        allowed_pairs=frozenset(
            (_NODE_FOR_KIND[source], _NODE_FOR_KIND[target])
            for source, target in spec.allowed_pairs
        ),
        evidence_statuses=statuses,
    )


def _structural(
    edge_type: GraphEdgeType,
    label: str,
    description: str,
    caveat: str,
    pair: tuple[GraphNodeType, GraphNodeType],
    status: EvidenceStatus,
) -> EdgeTypeSpec:
    return EdgeTypeSpec(
        type=edge_type,
        category=RelationshipCategory.STRUCTURAL,
        label=label,
        description=description,
        caveat=caveat,
        directed=True,
        allowed_pairs=frozenset({pair}),
        evidence_statuses=frozenset({status}),
    )


_T = GraphNodeType
_NEW_TYPES = (
    _structural(
        GraphEdgeType.IN_SECTOR,
        "belongs to",
        "The industry's ISIC Rev. 4 division belongs to this ISIC section.",
        "A classification hierarchy: every division sits in exactly one section. It says "
        "nothing about economic links between industries of the same section.",
        (_T.INDUSTRY, _T.SECTOR),
        EvidenceStatus.EVIDENCE_BACKED,
    ),
    _structural(
        GraphEdgeType.HAS_CURRENCY,
        "has currency",
        "The country's currency, by its ISO 4217 code.",
        "It says nothing about exchange-rate exposure, or about other places that use the "
        "currency.",
        (_T.COUNTRY, _T.CURRENCY),
        EvidenceStatus.EVIDENCE_BACKED,
    ),
    _structural(
        GraphEdgeType.COVERS,
        "covers",
        "The series describes this country's economy, as the provider defines it.",
        "The provider's geography, not a statement about influence between the series and "
        "the country.",
        (_T.DATA_SERIES, _T.COUNTRY),
        EvidenceStatus.EVIDENCE_BACKED,
    ),
    _structural(
        GraphEdgeType.RELATED_MEASURE_OF,
        "is a related measure of",
        "A curator recorded the series as a related measure of the variable, stating how "
        "the two differ.",
        "A related measure, not the same measure: frequency, definition or source differ "
        "(see the stated difference).",
        (_T.DATA_SERIES, _T.ECONOMIC_VARIABLE),
        EvidenceStatus.ANALYST_CREATED,
    ),
    _structural(
        GraphEdgeType.EXPRESSED_IN,
        "is expressed in",
        "The currency the series' unit is stated in.",
        "Values are shown as published and never converted.",
        (_T.DATA_SERIES, _T.CURRENCY),
        EvidenceStatus.EVIDENCE_BACKED,
    ),
    _structural(
        GraphEdgeType.LISTED_ON,
        "is listed on",
        "The market the instrument's prices come from, as declared in its price-file manifest.",
        "Declared by the importer; RUMIN did not verify the listing.",
        (_T.INSTRUMENT, _T.MARKET),
        EvidenceStatus.UNVERIFIED,
    ),
    _structural(
        GraphEdgeType.QUOTED_IN,
        "is quoted in",
        "The currency of the instrument's prices, as declared in its price-file manifest.",
        "Declared by the importer; prices are never converted.",
        (_T.INSTRUMENT, _T.CURRENCY),
        EvidenceStatus.UNVERIFIED,
    ),
    _structural(
        GraphEdgeType.ASSOCIATED_WITH,
        "is associated with",
        "The price-file manifest links the instrument to this country.",
        "The manifest does not say how (country of listing, of the issuer, or other).",
        (_T.INSTRUMENT, _T.COUNTRY),
        EvidenceStatus.UNVERIFIED,
    ),
)

EDGE_TYPES: dict[GraphEdgeType, EdgeTypeSpec] = {
    spec.type: spec for spec in (*(_from_phase1(edge_type) for edge_type in _PHASE1), *_NEW_TYPES)
}

# Display orders (the API returns types in these orders).
NODE_TYPE_ORDER: tuple[GraphNodeType, ...] = tuple(NODE_TYPES)
EDGE_TYPE_ORDER: tuple[GraphEdgeType, ...] = tuple(EDGE_TYPES)


def node_spec(node_type: GraphNodeType) -> NodeTypeSpec:
    return NODE_TYPES[node_type]


def edge_spec(edge_type: GraphEdgeType) -> EdgeTypeSpec:
    return EDGE_TYPES[edge_type]
