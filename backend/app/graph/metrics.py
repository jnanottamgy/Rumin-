"""Graph metrics, each with its definition, calculation, interpretation and limitations.

Every number is computed from the graph a build produced. None of them is an economic
indicator: they describe RUMIN's *data* (how many records, how they connect), not the
economy, and nothing here ranks companies or other entities.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median
from typing import Any

from app.domain.graph_types import EDGE_TYPES
from app.graph.algorithms import Incidence, MemoryAdjacency, connected_components, degrees
from app.graph.drafts import GraphDraft


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    label: str
    definition: str
    calculation: str
    interpretation: str
    limitations: str


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "node_count",
        "Nodes",
        "Entities in the graph (countries, industries, companies, series, …).",
        "Count of current nodes, in total and per type.",
        "How much the graph describes.",
        "Counts what RUMIN holds, not the economy: the graph is a small, partly fictional "
        "sample and is far from complete.",
    ),
    MetricDefinition(
        "edge_count",
        "Edges",
        "Relationships between nodes.",
        "Count of current edges, in total, per type and per evidence status.",
        "How many recorded relationships connect the entities.",
        "An edge records that a source states a relationship; it says nothing about its size "
        "or strength, and it is not evidence of causation.",
    ),
    MetricDefinition(
        "components",
        "Connected components",
        "Groups of nodes that can reach each other through edges, direction ignored.",
        "Depth-first search from each unvisited node (weakly connected components).",
        "One component means every record is linked to every other by some chain of "
        "recorded relationships.",
        "Being in one component does not make entities economically integrated; long chains "
        "through classifications or currencies are common and uninformative.",
    ),
    MetricDefinition(
        "average_degree",
        "Average degree",
        "The mean number of edges touching a node.",
        "2 x edges / nodes (each edge touches two nodes). Median and maximum are also given.",
        "How densely records are linked on average.",
        "Degree reflects how much RUMIN's data says about a node, not its importance. Hubs "
        "such as a country or a currency are highly connected by construction.",
    ),
    MetricDefinition(
        "density",
        "Density",
        "The share of possible node pairs that are directly connected.",
        "Pairs of nodes joined by at least one edge / (n(n - 1) / 2); edge direction and "
        "multiple edges between the same pair are ignored.",
        "Close to 0: sparse. Close to 1: nearly every node is linked to every other.",
        "Sparse is normal for real-world graphs; the value says nothing about the economy.",
    ),
    MetricDefinition(
        "provenance_coverage",
        "Provenance coverage",
        "The share of edges with at least one evidence record, and with a citation.",
        "Edges with at least one evidence record / all edges; edges whose evidence cites a "
        "source / all edges.",
        "Should be 100 % for evidence records: an edge without one is rejected. The citation "
        "share shows how many edges point to an external source.",
        "A citation shows where a statement came from; it does not mean the statement was "
        "verified.",
    ),
)


def compute_metrics(draft: GraphDraft) -> dict[str, Any]:
    """Metrics of a draft graph (the graph a build stores)."""
    nodes = draft.nodes
    edges = draft.edges
    incidences = [
        Incidence(key, edge.edge_type.value, edge.source_key, edge.target_key, edge.directed)
        for key, edge in edges.items()
    ]
    components = connected_components(nodes, MemoryAdjacency(incidences))
    degree = degrees(nodes, incidences)
    totals = sorted(value.total for value in degree.values())
    n = len(nodes)
    pairs = {tuple(sorted((edge.source_key, edge.target_key))) for edge in edges.values()}
    possible = n * (n - 1) / 2
    cited = sum(
        1
        for edge in edges.values()
        if any(item.citation or item.citation_url for item in edge.evidence)
    )
    busiest = sorted(degree.items(), key=lambda item: (-item[1].total, item[0]))[:5]
    return {
        "node_count": n,
        "edge_count": len(edges),
        "nodes_by_type": dict(
            sorted(Counter(node.node_type.value for node in nodes.values()).items())
        ),
        "nodes_by_nature": dict(
            sorted(Counter(node.nature.value for node in nodes.values()).items())
        ),
        "edges_by_type": dict(
            sorted(Counter(edge.edge_type.value for edge in edges.values()).items())
        ),
        "edges_by_evidence_status": dict(
            sorted(Counter(edge.evidence_status.value for edge in edges.values()).items())
        ),
        "edges_by_category": dict(
            sorted(
                Counter(
                    EDGE_TYPES[edge.edge_type].category.value for edge in edges.values()
                ).items()
            )
        ),
        "illustrative_edges": sum(1 for edge in edges.values() if edge.is_illustrative),
        "components": {
            "count": len(components),
            "largest": len(components[0]) if components else 0,
            "sizes": [len(members) for members in components[:10]],
            "isolated_nodes": sum(1 for members in components if len(members) == 1),
        },
        "degree": {
            "average": round(2 * len(edges) / n, 3) if n else 0,
            "median": median(totals) if totals else 0,
            "maximum": totals[-1] if totals else 0,
            "most_connected": [
                {"node": key, "degree": value.total} for key, value in busiest if value.total
            ],
        },
        "density": round(len(pairs) / possible, 4) if possible else 0,
        "provenance": {
            "edges_with_evidence": sum(1 for edge in edges.values() if edge.evidence),
            "edges_with_citation": cited,
            "evidence_records": sum(len(edge.evidence) for edge in edges.values()),
            "derived_edges": sum(
                1
                for edge in edges.values()
                if any(item.derivation.value == "derived" for item in edge.evidence)
            ),
        },
        "quality": {
            "nodes_flagged": sum(
                1 for node in nodes.values() if node.quality_status.value == "warning"
            ),
            "edges_flagged": sum(
                1 for edge in edges.values() if edge.quality_status.value == "warning"
            ),
        },
    }
