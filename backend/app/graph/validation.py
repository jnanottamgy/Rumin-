"""The graph's validation rules — defined once, used by the build, served by the API.

Like Phase 2's data-quality rules: **structural problems reject** (the node or edge is not
stored; the issue is), **doubtful identity flags** (stored with quality status
``warning`` and kept for review), and **informational findings are noted**.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.enums import (
    EvidenceStatus,
    GraphEdgeType,
    GraphIssueSubject,
    IssueOutcome,
    IssueSeverity,
    NodeNature,
)
from app.domain.graph_types import EDGE_TYPES
from app.graph.drafts import EdgeDraft, IssueDraft, NodeDraft

_NODE = GraphIssueSubject.NODE
_EDGE = GraphIssueSubject.EDGE
_ID = GraphIssueSubject.IDENTIFIER
_RES = GraphIssueSubject.RESOLUTION
_ERROR, _WARNING, _INFO = IssueSeverity.ERROR, IssueSeverity.WARNING, IssueSeverity.INFO
_REJECTED, _FLAGGED, _NOTED = IssueOutcome.REJECTED, IssueOutcome.FLAGGED, IssueOutcome.NOTED


@dataclass(frozen=True)
class GraphRule:
    code: str
    subject: GraphIssueSubject
    severity: IssueSeverity
    outcome: IssueOutcome
    description: str


GRAPH_RULES: dict[str, GraphRule] = {
    rule.code: rule
    for rule in (
        # Nodes
        GraphRule(
            "missing_node_key",
            _NODE,
            _ERROR,
            _REJECTED,
            "The source record has no ID, so no stable node key can be made.",
        ),
        GraphRule("missing_name", _NODE, _ERROR, _REJECTED, "The record has no name to display."),
        GraphRule(
            "missing_provenance",
            _NODE,
            _ERROR,
            _REJECTED,
            "The node would have no source record to explain it.",
        ),
        GraphRule(
            "invalid_code",
            _NODE,
            _ERROR,
            _REJECTED,
            "A code that would identify a currency, sector or market is not valid in its "
            "scheme, so no node is made for it (and no edge leads to it).",
        ),
        GraphRule(
            "unknown_classification",
            _NODE,
            _WARNING,
            _FLAGGED,
            "The industry's code is not a division of ISIC Rev. 4, so it is given no sector.",
        ),
        GraphRule("isolated_node", _NODE, _INFO, _NOTED, "The node has no edge to any other node."),
        # Identifiers
        GraphRule(
            "invalid_identifier",
            _ID,
            _WARNING,
            _FLAGGED,
            "An identifier is not in its scheme's format; it is not attached to the node.",
        ),
        GraphRule(
            "identifier_conflict",
            _ID,
            _WARNING,
            _FLAGGED,
            "The same identifier is claimed for different nodes; it is attached to none of "
            "them and the nodes are flagged for review.",
        ),
        # Entity resolution
        GraphRule(
            "unsupported_merge",
            _RES,
            _WARNING,
            _FLAGGED,
            "Two records of a kind RUMIN never merges automatically share an identifier. "
            "Both are kept and flagged for review.",
        ),
        GraphRule(
            "possible_duplicate",
            _RES,
            _WARNING,
            _FLAGGED,
            "Two records' names are identical once normalised. Both are kept and flagged for "
            "review: a name alone never merges entities.",
        ),
        GraphRule(
            "similar_name",
            _RES,
            _INFO,
            _NOTED,
            "Every word of one name appears in another (often a parent and a subsidiary, "
            "which are different entities). Noted for review; nothing is merged.",
        ),
        GraphRule(
            "possible_issuer",
            _RES,
            _INFO,
            _NOTED,
            "An instrument's name is similar to a company's. They are not linked: a similar "
            "name is not evidence that the company issued the instrument.",
        ),
        GraphRule(
            "match_ruled_out",
            _RES,
            _INFO,
            _NOTED,
            "Similar names, but one record is fictional or sample data and the other is not, "
            "so they cannot be the same entity.",
        ),
        # Edges
        GraphRule(
            "unknown_edge_type",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The relationship type has no definition in the graph's type registry.",
        ),
        GraphRule(
            "missing_source_node",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The edge's source does not exist in the graph.",
        ),
        GraphRule(
            "missing_target_node",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The edge's target does not exist in the graph.",
        ),
        GraphRule(
            "reversed_direction",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The edge points the wrong way: its type is defined from the target's kind to "
            "the source's kind.",
        ),
        GraphRule(
            "endpoint_types_not_allowed",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The edge's type is not defined between these kinds of node.",
        ),
        GraphRule("self_loop", _EDGE, _ERROR, _REJECTED, "The edge connects a node to itself."),
        GraphRule(
            "missing_evidence",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The edge has no evidence record, so nothing could explain why it exists.",
        ),
        GraphRule(
            "evidence_status_not_allowed",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The edge's evidence status is not allowed for its type (e.g. an assumed "
            "variable-to-variable effect claimed as evidence-backed).",
        ),
        GraphRule(
            "invalid_validity_period",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The validity period ends before it starts.",
        ),
        GraphRule(
            "future_validity",
            _EDGE,
            _WARNING,
            _FLAGGED,
            "The validity period starts in the future.",
        ),
        GraphRule(
            "reality_mismatch",
            _EDGE,
            _ERROR,
            _REJECTED,
            "The edge would mix fiction and fact: an evidence-backed edge touching a "
            "fictional or sample node, or a business relationship between a fictional and a "
            "real company.",
        ),
        GraphRule(
            "duplicate_edge",
            _EDGE,
            _INFO,
            _NOTED,
            "More than one record states the same relationship; it is stored once, with "
            "every record as evidence.",
        ),
        GraphRule(
            "unresolved_reference",
            _EDGE,
            _INFO,
            _NOTED,
            "A record refers to an entity that is not in the graph, so no edge was made.",
        ),
    )
}


def issue(
    code: str,
    subject_ref: str,
    message: str,
    *,
    node_key: str | None = None,
    edge_key: str | None = None,
    details: dict[str, Any] | None = None,
) -> IssueDraft:
    rule = GRAPH_RULES[code]
    return IssueDraft(
        subject_kind=rule.subject,
        subject_ref=subject_ref,
        rule=code,
        severity=rule.severity,
        outcome=rule.outcome,
        message=message,
        details=details or {},
        node_key=node_key,
        edge_key=edge_key,
    )


# Business relationships between companies: fiction and fact must never be connected.
_BUSINESS_TYPES = frozenset(
    {GraphEdgeType.SUPPLIES_TO, GraphEdgeType.LENDS_TO, GraphEdgeType.COMPETES_WITH}
)


def check_edge(edge: EdgeDraft, nodes: dict[str, NodeDraft], today: date) -> list[IssueDraft]:
    """Every rule an edge must pass. An empty list means the edge is valid."""
    key = edge.key
    ref = f"{edge.edge_type.value}: {edge.source_key} → {edge.target_key}"

    def problem(code: str, message: str) -> IssueDraft:
        return issue(code, ref, message, edge_key=key, node_key=edge.source_key)

    spec = EDGE_TYPES.get(edge.edge_type)
    if spec is None:
        return [problem("unknown_edge_type", f"'{edge.edge_type}' is not a known edge type.")]
    source = nodes.get(edge.source_key)
    target = nodes.get(edge.target_key)
    found: list[IssueDraft] = []
    if source is None:
        found.append(problem("missing_source_node", f"No node '{edge.source_key}' exists."))
    if target is None:
        found.append(problem("missing_target_node", f"No node '{edge.target_key}' exists."))
    if not edge.evidence:
        found.append(problem("missing_evidence", "The edge has no evidence record."))
    if edge.evidence_status not in spec.evidence_statuses:
        allowed = ", ".join(sorted(status.value for status in spec.evidence_statuses))
        found.append(
            problem(
                "evidence_status_not_allowed",
                f"'{edge.evidence_status.value}' is not allowed for '{spec.type.value}' "
                f"(allowed: {allowed}).",
            )
        )
    if edge.valid_from and edge.valid_to and edge.valid_to < edge.valid_from:
        found.append(
            problem(
                "invalid_validity_period",
                f"Valid from {edge.valid_from} to {edge.valid_to}: the end precedes the start.",
            )
        )
    if source is None or target is None:
        return found
    if edge.source_key == edge.target_key:
        found.append(problem("self_loop", f"'{edge.source_key}' would be linked to itself."))
    if not spec.allows(source.node_type, target.node_type):
        if spec.allows(target.node_type, source.node_type):
            found.append(
                problem(
                    "reversed_direction",
                    f"'{spec.type.value}' runs from {target.node_type.value} to "
                    f"{source.node_type.value}, not the other way round.",
                )
            )
        else:
            found.append(
                problem(
                    "endpoint_types_not_allowed",
                    f"'{spec.type.value}' is not defined from {source.node_type.value} to "
                    f"{target.node_type.value}.",
                )
            )
    real = {source.nature is NodeNature.REAL, target.nature is NodeNature.REAL}
    if edge.evidence_status is EvidenceStatus.EVIDENCE_BACKED and real != {True}:
        found.append(
            problem(
                "reality_mismatch",
                "An evidence-backed edge must connect real entities only.",
            )
        )
    elif edge.edge_type in _BUSINESS_TYPES and real == {True, False}:
        found.append(
            problem(
                "reality_mismatch",
                "A business relationship cannot connect a fictional and a real company.",
            )
        )
    if edge.valid_from and edge.valid_from > today:
        found.append(problem("future_validity", f"Validity starts on {edge.valid_from}."))
    return found
