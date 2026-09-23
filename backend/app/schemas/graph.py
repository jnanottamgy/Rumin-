"""Knowledge-graph API models.

Every node says what it is (type, real / fictional / sample) and how it is identified;
every edge says what supports it (evidence status), whether it is illustrative, and — in
its detail — why it exists (evidence records) and what it does not mean (caveat). Paths
and neighbourhoods carry their limits, so a truncated answer is never mistaken for a
complete one.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from app.domain.enums import (
    Derivation,
    EvidenceSourceKind,
    EvidenceStatus,
    GraphBuildStatus,
    GraphEdgeType,
    GraphIssueSubject,
    GraphNodeType,
    IssueOutcome,
    IssueSeverity,
    NodeNature,
    QualityStatus,
    RelationshipCategory,
    ResolutionMethod,
    ResolutionOutcome,
)
from app.graph.algorithms import Direction
from app.schemas.common import ApiModel, Page

DataStatus = Literal["values_stored", "definition_only", "not_applicable"]


class IdentifierRead(ApiModel):
    scheme: str
    label: str = Field(description="The scheme's name, e.g. 'ISO 4217'.")
    value: str
    source: str | None = Field(default=None, description="The record that stated it.")


class GraphNodeSummary(ApiModel):
    id: str = Field(
        description="Stable node key, e.g. `country:cty_in`.", examples=["country:cty_in"]
    )
    type: GraphNodeType
    name: str
    subtitle: str = Field(description="Tells apart nodes with similar names.")
    nature: NodeNature = Field(description="`real`, `fictional` (sample network) or `sample` data.")
    quality_status: QualityStatus
    degree: int = Field(
        ge=0, description="Edges touching the node (data coverage, not importance)."
    )
    primary_identifier: IdentifierRead | None = None
    data_status: DataStatus = Field(
        description="For series and instruments: whether values are stored or only the "
        "definition exists."
    )


class NeighborNode(GraphNodeSummary):
    depth: int = Field(ge=0, description="Hops from the centre (shortest).")


class NodeSearchResult(GraphNodeSummary):
    match: str = Field(description="Why the node matched: 'name', 'identifier' or 'details'.")
    ambiguous: bool = Field(
        description="True when another node has the same name: check the subtitle and "
        "identifiers before choosing."
    )


class EdgeQualifiers(ApiModel):
    """Type-specific qualifiers, each with the meaning Phase 1 or the catalogue gave it."""

    polarity: str | None = Field(default=None, description="Assumed direction of effect.")
    strength: str | None = Field(
        default=None, description="Ordinal and illustrative, not measured."
    )
    evidence_level: str | None = Field(default=None, description="Phase 1 evidence level.")
    rationale: str | None = None
    stated_difference: str | None = Field(
        default=None, description="How a related measure differs from the variable."
    )


class GraphEdgeSummary(ApiModel):
    id: str = Field(examples=["e-3f0c9a2b7d1e4f56"])
    type: GraphEdgeType
    category: RelationshipCategory
    source: str
    target: str
    directed: bool
    label: str = Field(description="How the edge reads: '<source> <label> <target>'.")
    description: str
    evidence_status: EvidenceStatus
    is_illustrative: bool
    quality_status: QualityStatus
    valid_from: date | None = None
    valid_to: date | None = None
    historical: bool = Field(description="The stated validity period has ended.")
    qualifiers: EdgeQualifiers


class EvidenceRead(ApiModel):
    rule: str = Field(examples=["R02 company_industry"])
    rule_description: str
    source_kind: EvidenceSourceKind
    source_table: str
    source_record_id: str
    dataset_id: str | None
    dataset_version: str | None
    statement: str = Field(description="What the source says.")
    transformation: str = Field(description="How the rule turned it into this edge.")
    derivation: Derivation
    derived_from: list[str]
    citation: str | None
    citation_url: str | None
    retrieved_at: datetime | None = Field(
        description="When a provider last delivered the source (series only)."
    )
    recorded_at: datetime | None = Field(description="When the source record entered RUMIN.")


class GraphEdgeDetail(GraphEdgeSummary):
    source_node: GraphNodeSummary
    target_node: GraphNodeSummary
    explanation: str = Field(description="Why this connection exists, in one paragraph.")
    evidence: list[EvidenceRead]
    evidence_status_label: str
    evidence_status_definition: str
    type_description: str
    caveat: str = Field(description="What this kind of edge does not mean.")
    first_build_id: int
    changed_build_id: int


class SourceRecordRead(ApiModel):
    table: str
    record_id: str
    dataset_id: str | None = None
    dataset_version: str | None = None
    fields: list[str] = Field(default_factory=list)


class RelationshipCount(ApiModel):
    type: GraphEdgeType
    label: str
    direction: Literal["outgoing", "incoming", "undirected"]
    count: int


class ResolutionDecisionRead(ApiModel):
    method: ResolutionMethod
    outcome: ResolutionOutcome
    source: str
    identifier: str | None
    candidates: list[str]
    rationale: str


class GraphIssueRead(ApiModel):
    id: int
    build_id: int
    subject_kind: GraphIssueSubject
    subject_ref: str
    node_id: str | None
    edge_id: str | None
    rule: str
    severity: IssueSeverity
    outcome: IssueOutcome
    message: str
    details: dict[str, Any]


class ExposureRead(ApiModel):
    kind: Literal["direct", "via_industry"]
    variable: GraphNodeSummary
    edge: GraphEdgeSummary
    via: GraphNodeSummary | None
    explanation: str


class NodeDataRead(ApiModel):
    """Live data availability for series and instruments (read from the Phase 2 tables)."""

    kind: Literal["series", "instrument"]
    record_id: str
    value_count: int
    first: date | None
    last: date | None
    last_retrieved_at: datetime | None = None


class GraphNodeDetail(GraphNodeSummary):
    description: str
    attributes: dict[str, Any]
    identifiers: list[IdentifierRead]
    sources: list[SourceRecordRead]
    in_degree: int
    out_degree: int
    component: int | None
    relationships: list[RelationshipCount]
    resolution: list[ResolutionDecisionRead]
    issues: list[GraphIssueRead]
    exposures: list[ExposureRead] | None = Field(
        default=None,
        description="Companies and industries only: variables linked by assumed-effect edges.",
    )
    data: NodeDataRead | None = None
    first_build_id: int
    changed_build_id: int


class TraversalLimits(ApiModel):
    max_depth: int
    max_nodes: int


class NeighborhoodResponse(ApiModel):
    center: GraphNodeSummary
    depth: int
    nodes: list[NeighborNode]
    edges: list[GraphEdgeSummary]
    truncated: bool = Field(description="Some reachable nodes were left out (node limit).")
    unexplored_count: int
    unexplored_by_type: dict[str, int]
    limits: TraversalLimits
    queries: int = Field(description="Database round trips used (one per level, plus one).")


class PathRead(ApiModel):
    nodes: list[str]
    edges: list[str]
    length: int


class PathsResponse(ApiModel):
    source: GraphNodeSummary
    target: GraphNodeSummary
    found: bool
    length: int | None = Field(description="Hops on the shortest path; null when none found.")
    paths: list[PathRead]
    nodes: list[GraphNodeSummary]
    edges: list[GraphEdgeSummary]
    direction: Direction
    max_depth: int
    budget_exhausted: bool = Field(description="The search stopped at its node budget.")
    nodes_explored: int
    note: str


class ComponentRead(ApiModel):
    number: int
    size: int
    nodes_by_type: dict[str, int]
    sample: list[GraphNodeSummary]


class ComponentsResponse(ApiModel):
    count: int
    isolated_nodes: int
    components: list[ComponentRead]
    note: str


class BuildCounts(ApiModel):
    processed: int
    valid: int
    flagged: int
    rejected: int


class BuildChanges(ApiModel):
    added: int
    changed: int
    retired: int
    unchanged: int


class GraphBuildSummary(ApiModel):
    id: int
    status: GraphBuildStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    rules_version: str
    node_count: int
    edge_count: int
    nodes: BuildCounts
    edges: BuildCounts
    node_changes: BuildChanges
    edge_changes: BuildChanges
    error_count: int
    warning_count: int
    info_count: int
    error_summary: str | None


GraphBuildPage = Page[GraphBuildSummary]
GraphIssuePage = Page[GraphIssueRead]
NodeSearchPage = Page[NodeSearchResult]
GraphEdgePage = Page[GraphEdgeSummary]


class RuleCount(ApiModel):
    rule: str
    outcome: IssueOutcome
    count: int


class DecisionCount(ApiModel):
    method: ResolutionMethod
    outcome: ResolutionOutcome
    count: int


class GraphBuildDetail(GraphBuildSummary):
    source_fingerprint: str | None
    sources: dict[str, Any]
    metrics: dict[str, Any]
    issues_by_rule: list[RuleCount]
    decisions: list[DecisionCount]


class Freshness(ApiModel):
    status: Literal["current", "stale", "not_built"]
    message: str


class TypeMapNode(ApiModel):
    type: GraphNodeType
    label: str
    plural: str
    count: int


class TypeMapLink(ApiModel):
    source_type: GraphNodeType
    target_type: GraphNodeType
    edge_type: GraphEdgeType
    label: str
    count: int


class MetricDefinitionRead(ApiModel):
    id: str
    label: str
    definition: str
    calculation: str
    interpretation: str
    limitations: str


class GraphOverview(ApiModel):
    build: GraphBuildSummary | None
    freshness: Freshness
    metrics: dict[str, Any] = Field(description="Computed by the build (see metric_definitions).")
    type_map: list[TypeMapNode]
    type_links: list[TypeMapLink]
    metric_definitions: list[MetricDefinitionRead]
    notes: list[str]


class NodeTypeRead(ApiModel):
    type: GraphNodeType
    label: str
    plural: str
    description: str
    primary_identifier: str | None


class EndpointPair(ApiModel):
    source: GraphNodeType
    target: GraphNodeType


class EdgeTypeRead(ApiModel):
    type: GraphEdgeType
    category: RelationshipCategory
    label: str
    description: str
    caveat: str
    directed: bool
    endpoints: list[EndpointPair]
    evidence_statuses: list[EvidenceStatus]


class EvidenceStatusRead(ApiModel):
    status: EvidenceStatus
    label: str
    definition: str


class ConstructionRuleRead(ApiModel):
    code: str
    name: str
    reads: str
    produces: str
    evidence_status: EvidenceStatus | None
    description: str


class ValidationRuleRead(ApiModel):
    code: str
    subject: GraphIssueSubject
    severity: IssueSeverity
    outcome: IssueOutcome
    description: str


class IdentifierSchemeRead(ApiModel):
    scheme: str
    label: str


class GraphTypesResponse(ApiModel):
    node_types: list[NodeTypeRead]
    edge_types: list[EdgeTypeRead]
    evidence_statuses: list[EvidenceStatusRead]
    identifier_schemes: list[IdentifierSchemeRead]
    construction_rules: list[ConstructionRuleRead]
    validation_rules: list[ValidationRuleRead]
