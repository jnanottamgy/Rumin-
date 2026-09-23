"""Assemble a draft graph from a source snapshot: rules → resolution → edges → validation.

Pure: no database access, no clock (``today`` is passed in). The same snapshot always
gives the same draft, which is what makes builds repeatable and testable.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.domain.enums import (
    GraphEdgeType,
    GraphIssueSubject,
    GraphNodeType,
    IssueOutcome,
    NodeNature,
    QualityStatus,
    ResolutionMethod,
    ResolutionOutcome,
)
from app.domain.graph_types import EDGE_TYPES, NODE_TYPES
from app.graph import rules
from app.graph.drafts import DecisionDraft, EdgeDraft, GraphDraft, IssueDraft, NodeDraft, Tally
from app.graph.names import normalize_name
from app.graph.resolution import resolve
from app.graph.sources import SourceSnapshot
from app.graph.validation import check_edge, issue


def assemble(snapshot: SourceSnapshot, *, today: date) -> GraphDraft:
    record_nodes, issues, rejected_records = rules.record_nodes(snapshot)
    resolution = resolve(snapshot, record_nodes, rules.code_claims(snapshot))
    nodes = resolution.nodes
    issues.extend(resolution.issues)
    decisions = list(resolution.decisions)

    drafts, edge_issues, found_by_code = rules.edge_drafts(snapshot, resolution.alpha3_index)
    issues.extend(edge_issues)
    for country_key, code, source in found_by_code:
        decisions.append(
            DecisionDraft(
                source=source,
                source_values={"country_iso3": code},
                node_key=country_key,
                method=ResolutionMethod.IDENTIFIER,
                outcome=ResolutionOutcome.LINKED,
                identifier=f"iso3166_alpha3:{code}",
                rationale=f"{source.label} has no catalogue link to a country, but names "
                f"{code}, which identifies exactly one country node ({country_key}).",
            )
        )

    edges, duplicates, edge_tally = _validate_edges(drafts, nodes, issues, today)

    touched = {key for edge in edges.values() for key in (edge.source_key, edge.target_key)}
    for node in nodes.values():
        if node.key not in touched:
            issues.append(
                issue(
                    "isolated_node",
                    node.key,
                    f"{node.display_name} has no edge to any other node.",
                    node_key=node.key,
                )
            )

    flagged_nodes = {
        item.node_key
        for item in issues
        if item.outcome is IssueOutcome.FLAGGED
        and item.node_key
        and item.subject_kind is not GraphIssueSubject.EDGE
    }
    node_tally = Tally(processed=len(nodes) + rejected_records + resolution.rejected)
    node_tally.rejected = rejected_records + resolution.rejected
    for node in nodes.values():
        if node.key in flagged_nodes:
            node.quality_status = QualityStatus.WARNING
            node_tally.flagged += 1
        else:
            node_tally.valid += 1

    _describe(nodes, edges)
    return GraphDraft(
        nodes=dict(sorted(nodes.items())),
        edges=dict(sorted(edges.items())),
        decisions=decisions,
        issues=issues,
        node_tally=node_tally,
        edge_tally=edge_tally,
        duplicates_merged=duplicates,
    )


def _validate_edges(
    drafts: list[EdgeDraft], nodes: dict[str, NodeDraft], issues: list[IssueDraft], today: date
) -> tuple[dict[str, EdgeDraft], int, Tally]:
    merged: dict[str, EdgeDraft] = {}
    duplicates = 0
    for edge in drafts:
        spec = EDGE_TYPES.get(edge.edge_type)
        edge.directed = spec.directed if spec else True
        # Undirected relationships are stored once, with the smaller key first.
        if spec and not spec.directed and edge.target_key < edge.source_key:
            edge.source_key, edge.target_key = edge.target_key, edge.source_key
        key = edge.key
        if key in merged:
            merged[key].evidence.extend(edge.evidence)
            duplicates += 1
            issues.append(
                issue(
                    "duplicate_edge",
                    f"{edge.edge_type.value}: {edge.source_key} → {edge.target_key}",
                    f"{edge.evidence[0].source.label} states a relationship already stated by "
                    f"{merged[key].evidence[0].source.label}; it is stored once with both "
                    "records as evidence.",
                    edge_key=key,
                    node_key=edge.source_key,
                )
            )
            continue
        merged[key] = edge

    accepted: dict[str, EdgeDraft] = {}
    tally = Tally(processed=len(merged))
    for key, edge in merged.items():
        problems = check_edge(edge, nodes, today)
        issues.extend(problems)
        if any(problem.outcome is IssueOutcome.REJECTED for problem in problems):
            tally.rejected += 1
            continue
        source, target = nodes[edge.source_key], nodes[edge.target_key]
        edge.is_illustrative = (
            edge.source_illustrative
            or source.nature is not NodeNature.REAL
            or target.nature is not NodeNature.REAL
        )
        if any(problem.outcome is IssueOutcome.FLAGGED for problem in problems):
            edge.quality_status = QualityStatus.WARNING
            tally.flagged += 1
        else:
            tally.valid += 1
        accepted[key] = edge
    return accepted, duplicates, tally


# --- Subtitles and search text -----------------------------------------------------------------


def _describe(nodes: dict[str, NodeDraft], edges: dict[str, EdgeDraft]) -> None:
    """Subtitles that tell apart nodes with similar names, and each node's search text."""
    linked: dict[tuple[str, GraphEdgeType], list[str]] = defaultdict(list)
    for edge in edges.values():
        linked[(edge.source_key, edge.edge_type)].append(edge.target_key)

    def first_name(key: str, edge_type: GraphEdgeType) -> str | None:
        targets = linked.get((key, edge_type))
        return nodes[targets[0]].display_name if targets else None

    for node in nodes.values():
        attrs = node.attributes
        parts: list[str]
        if node.node_type is GraphNodeType.COUNTRY:
            parts = [
                "Country",
                str(attrs.get("iso_alpha2", "")),
                str(attrs.get("currency_code", "")),
            ]
        elif node.node_type is GraphNodeType.CURRENCY:
            parts = ["Currency", "ISO 4217"]
        elif node.node_type is GraphNodeType.SECTOR:
            parts = [f"ISIC Rev. 4 section {attrs.get('code')}"]
        elif node.node_type is GraphNodeType.INDUSTRY:
            parts = [
                f"{attrs.get('classification_system')} division {attrs.get('classification_code')}",
                first_name(node.key, GraphEdgeType.IN_SECTOR) or "",
            ]
        elif node.node_type is GraphNodeType.COMPANY:
            parts = [
                "Fictional company" if node.nature is NodeNature.FICTIONAL else "Company",
                first_name(node.key, GraphEdgeType.IN_INDUSTRY) or "",
                first_name(node.key, GraphEdgeType.DOMICILED_IN) or "",
            ]
        elif node.node_type is GraphNodeType.ECONOMIC_VARIABLE:
            parts = [
                "Economic variable",
                first_name(node.key, GraphEdgeType.MEASURED_FOR) or "Global",
                f"{attrs.get('unit')}, {attrs.get('frequency')}",
            ]
        elif node.node_type is GraphNodeType.DATA_SERIES:
            parts = [
                str(attrs.get("dataset_name") or attrs.get("dataset_id")),
                first_name(node.key, GraphEdgeType.COVERS) or str(attrs.get("country_iso3") or ""),
                str(attrs.get("frequency", "")),
            ]
        elif node.node_type is GraphNodeType.INSTRUMENT:
            parts = [
                str(attrs.get("instrument_type", "instrument")).capitalize(),
                f"{attrs.get('exchange_mic')}:{attrs.get('symbol')}",
                "Sample data" if node.nature is NodeNature.SAMPLE else "",
            ]
        else:
            parts = ["Market", "ISO 10383 MIC"]
        node.subtitle = " · ".join(part for part in parts if part)

        words = [
            node.display_name,
            normalize_name(node.display_name),
            node.subtitle,
            NODE_TYPES[node.node_type].label,
            *(claim.value for claim in node.identifiers),
            *(source.record_id for source in node.sources),
        ]
        node.search_text = " ".join(word for word in words if word).lower()
