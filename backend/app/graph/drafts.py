"""The in-memory graph a build assembles before anything is written.

Rules, resolution and validation all produce and refine these drafts; ``persist`` then
writes the accepted ones. Keeping them free of the database makes every step testable
with hand-made records.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain.enums import (
    Derivation,
    EvidenceSourceKind,
    EvidenceStatus,
    GraphEdgeType,
    GraphIssueSubject,
    GraphNodeType,
    IdentifierScheme,
    IssueOutcome,
    IssueSeverity,
    NodeNature,
    QualityStatus,
    ResolutionMethod,
    ResolutionOutcome,
)

# The prefix of each node type's keys, e.g. "variable:var_brent_crude".
KEY_PREFIX: dict[GraphNodeType, str] = {
    GraphNodeType.COUNTRY: "country",
    GraphNodeType.CURRENCY: "currency",
    GraphNodeType.SECTOR: "sector",
    GraphNodeType.INDUSTRY: "industry",
    GraphNodeType.COMPANY: "company",
    GraphNodeType.ECONOMIC_VARIABLE: "variable",
    GraphNodeType.DATA_SERIES: "series",
    GraphNodeType.INSTRUMENT: "instrument",
    GraphNodeType.MARKET: "market",
}

# What the API accepts as a node key (checked before any query).
NODE_KEY_PATTERN = (
    r"^(country|currency|sector|industry|company|variable|series|instrument|market)"
    r":[a-z0-9][a-z0-9_.-]{0,95}$"
)
EDGE_KEY_PATTERN = r"^e-[0-9a-f]{16}$"


def node_key(node_type: GraphNodeType, local_id: str) -> str:
    """A deterministic node key: the same record or code always gives the same key."""
    return f"{KEY_PREFIX[node_type]}:{local_id.lower()}"


def edge_key(edge_type: GraphEdgeType, source_key: str, target_key: str) -> str:
    """A deterministic edge key from (type, source, target): 64 bits of SHA-256."""
    digest = hashlib.sha256(f"{edge_type.value}|{source_key}|{target_key}".encode()).hexdigest()
    return f"e-{digest[:16]}"


def content_hash(payload: dict[str, Any]) -> str:
    """SHA-256 of a canonical JSON rendering, used to detect changes between builds."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, set | frozenset):
        return json.dumps(sorted(value))
    raise TypeError(f"Cannot hash {type(value).__name__}")


@dataclass(frozen=True)
class SourceRef:
    """A source record, e.g. ``companies/co_aerisca_airways`` in dataset rumin-sample."""

    table: str
    record_id: str
    dataset_id: str | None = None
    dataset_version: str | None = None
    fields: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.table}/{self.record_id}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "record_id": self.record_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "fields": list(self.fields),
        }


@dataclass(frozen=True)
class IdentifierClaim:
    """A record stating that a node has an identifier (e.g. ISO 4217 ``INR``)."""

    scheme: IdentifierScheme
    value: str
    source: SourceRef

    @property
    def label(self) -> str:
        return f"{self.scheme.value}:{self.value}"


@dataclass
class NodeDraft:
    key: str
    node_type: GraphNodeType
    display_name: str
    description: str
    nature: NodeNature
    attributes: dict[str, Any]
    sources: list[SourceRef]
    # Identifier claims before resolution; accepted identifiers afterwards.
    identifiers: list[IdentifierClaim] = field(default_factory=list)
    # Currency, sector and market nodes are made from codes named by other records.
    derived: bool = False
    quality_status: QualityStatus = QualityStatus.VALIDATED
    subtitle: str = ""
    search_text: str = ""

    def hash_payload(self) -> dict[str, Any]:
        return {
            "type": self.node_type.value,
            "name": self.display_name,
            "subtitle": self.subtitle,
            "description": self.description,
            "nature": self.nature.value,
            "quality": self.quality_status.value,
            "attributes": self.attributes,
            "sources": [source.as_dict() for source in self.sources],
            "identifiers": sorted((claim.label, claim.source.label) for claim in self.identifiers),
        }


@dataclass(frozen=True)
class EvidenceDraft:
    rule: str
    source_kind: EvidenceSourceKind
    source: SourceRef
    statement: str
    transformation: str
    derivation: Derivation = Derivation.DIRECT
    derived_from: tuple[str, ...] = ()
    citation: str | None = None
    citation_url: str | None = None
    retrieved_at: datetime | None = None
    recorded_at: datetime | None = None

    def hash_payload(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "kind": self.source_kind.value,
            "source": self.source.as_dict(),
            "statement": self.statement,
            "transformation": self.transformation,
            "derivation": self.derivation.value,
            "derived_from": list(self.derived_from),
            "citation": self.citation,
            "citation_url": self.citation_url,
            "retrieved_at": self.retrieved_at,
            "recorded_at": self.recorded_at,
        }


@dataclass
class EdgeDraft:
    edge_type: GraphEdgeType
    source_key: str
    target_key: str
    description: str
    evidence_status: EvidenceStatus
    evidence: list[EvidenceDraft]
    attributes: dict[str, Any] = field(default_factory=dict)
    valid_from: date | None = None
    valid_to: date | None = None
    # The source data itself is illustrative (e.g. a Phase 1 "illustrative" relationship).
    source_illustrative: bool = False
    # Set by validation.
    directed: bool = True
    is_illustrative: bool = False
    quality_status: QualityStatus = QualityStatus.VALIDATED

    @property
    def key(self) -> str:
        return edge_key(self.edge_type, self.source_key, self.target_key)

    def hash_payload(self) -> dict[str, Any]:
        return {
            "type": self.edge_type.value,
            "source": self.source_key,
            "target": self.target_key,
            "directed": self.directed,
            "description": self.description,
            "status": self.evidence_status.value,
            "illustrative": self.is_illustrative,
            "quality": self.quality_status.value,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "attributes": self.attributes,
            "evidence": [item.hash_payload() for item in self.evidence],
        }


@dataclass(frozen=True)
class IssueDraft:
    subject_kind: GraphIssueSubject
    subject_ref: str
    rule: str
    severity: IssueSeverity
    outcome: IssueOutcome
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    node_key: str | None = None
    edge_key: str | None = None


@dataclass(frozen=True)
class DecisionDraft:
    source: SourceRef
    source_values: dict[str, Any]
    node_key: str | None
    method: ResolutionMethod
    outcome: ResolutionOutcome
    rationale: str
    identifier: str | None = None
    candidate_node_keys: tuple[str, ...] = ()


@dataclass
class Tally:
    """Processed = valid + flagged + rejected."""

    processed: int = 0
    valid: int = 0
    flagged: int = 0
    rejected: int = 0


@dataclass
class GraphDraft:
    nodes: dict[str, NodeDraft]
    edges: dict[str, EdgeDraft]
    decisions: list[DecisionDraft]
    issues: list[IssueDraft]
    node_tally: Tally
    edge_tally: Tally
    duplicates_merged: int = 0
