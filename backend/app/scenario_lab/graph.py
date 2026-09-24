"""Bounded reads of the knowledge graph for the Scenario Lab.

Two questions only, both answered from the current, validated edges of the latest build:

* **Exposure** — does the graph state that a variable affects a company's costs, revenue
  or financing, directly or through the company's industry? A stated exposure is a model
  assumption or a curated fact, not a measured effect; it decides whether a model applies
  to a company by default. It is never used to size anything.
* **Affected entities** — which companies the graph ties to the scenario's changed
  variables (following at most two ``influences`` hops between variables), and whether a
  registered model covers each tie. Bounded in depth and size; truncation is reported.

A connection in the graph is not evidence of causation, and the results say so.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import GraphEdgeType, QualityStatus
from app.models import GraphEdge, GraphNode
from app.scenario_lab.profiles import Exposure, ScenarioProfile, lab_model

EXPOSURE_TYPES = (
    GraphEdgeType.AFFECTS_COSTS,
    GraphEdgeType.AFFECTS_REVENUE,
    GraphEdgeType.AFFECTS_FINANCING,
)
MAX_INFLUENCE_HOPS = 2
MAX_ENTITIES = 200


def variable_key(variable_id: str) -> str:
    return f"variable:{variable_id}"


def variable_id_of(key: str) -> str:
    return key.partition(":")[2]


@dataclass(frozen=True)
class EdgeView:
    key: str
    edge_type: str
    source: str
    target: str
    evidence_status: str
    is_illustrative: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "edge_key": self.key,
            "edge_type": self.edge_type,
            "source": self.source,
            "target": self.target,
            "evidence_status": self.evidence_status,
            "is_illustrative": self.is_illustrative,
        }


@dataclass(frozen=True)
class NodeView:
    key: str
    name: str
    node_type: str
    nature: str

    def to_json(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name, "type": self.node_type, "nature": self.nature}


def edges(
    session: Session,
    *,
    types: Iterable[GraphEdgeType],
    sources: Iterable[str] | None = None,
    targets: Iterable[str] | None = None,
) -> list[EdgeView]:
    """Current, validated edges of the given types between the given ends."""
    query = select(GraphEdge).where(
        GraphEdge.retired_build_id.is_(None),
        GraphEdge.quality_status == QualityStatus.VALIDATED,
        GraphEdge.edge_type.in_(list(types)),
    )
    if sources is not None:
        query = query.where(GraphEdge.source_node_id.in_(sorted(set(sources))))
    if targets is not None:
        query = query.where(GraphEdge.target_node_id.in_(sorted(set(targets))))
    rows = session.scalars(
        query.order_by(GraphEdge.source_node_id, GraphEdge.edge_type, GraphEdge.target_node_id)
    ).all()
    return [
        EdgeView(
            key=row.id,
            edge_type=str(row.edge_type.value),
            source=row.source_node_id,
            target=row.target_node_id,
            evidence_status=str(row.evidence_status.value),
            is_illustrative=row.is_illustrative,
        )
        for row in rows
    ]


def nodes(session: Session, keys: Iterable[str]) -> dict[str, NodeView]:
    wanted = sorted(set(keys))
    if not wanted:
        return {}
    rows = session.scalars(
        select(GraphNode).where(GraphNode.id.in_(wanted), GraphNode.retired_build_id.is_(None))
    ).all()
    return {
        row.id: NodeView(
            key=row.id,
            name=row.display_name,
            node_type=str(row.node_type.value),
            nature=str(row.nature.value),
        )
        for row in rows
    }


def industries_of(session: Session, entity_key: str) -> list[EdgeView]:
    return edges(session, types=(GraphEdgeType.IN_INDUSTRY,), sources=[entity_key])


def exposure_chains(session: Session, entity_key: str, exposure: Exposure) -> list[list[EdgeView]]:
    """Every way the graph states ``variable —relationship→ entity`` or
    ``variable —relationship→ industry ←in_industry— entity``."""
    types = [GraphEdgeType(name) for name in exposure.relationships]
    source = variable_key(exposure.variable_id)
    chains = [
        [edge] for edge in edges(session, types=types, sources=[source], targets=[entity_key])
    ]
    if exposure.via_industry:
        memberships = industries_of(session, entity_key)
        by_industry = {edge.target: edge for edge in memberships}
        for edge in edges(session, types=types, sources=[source], targets=list(by_industry)):
            chains.append([edge, by_industry[edge.target]])
    return chains


def profile_exposure(
    session: Session, entity_key: str, profile: ScenarioProfile
) -> list[list[EdgeView]]:
    chains: list[list[EdgeView]] = []
    for exposure in profile.exposures:
        chains.extend(exposure_chains(session, entity_key, exposure))
    return chains


# --- Affected entities -------------------------------------------------------------------------


def _covered_by(
    profiles: Mapping[str, ScenarioProfile],
    start: str,
    via: list[EdgeView],
    relationship: str,
    variable: str,
) -> list[str]:
    """Models that carry a change of ``start`` along ``via`` (influences hops) to an exposure
    ``variable —relationship→``: they must respond to ``start``, state that exposure, and
    declare a transmission rule for every hop."""
    covered: list[str] = []
    for profile in profiles.values():
        if variable_id_of(start) not in profile.variables:
            continue
        if not any(
            relationship in item.relationships and variable_id_of(variable) == item.variable_id
            for item in profile.exposures
        ):
            continue
        model = lab_model(profile.model_id)
        if model is None:
            continue
        rules = {(rule.source, rule.target) for rule in model.definition.transmission_rules}
        if all((hop.source, hop.target) in rules for hop in via):
            covered.append(profile.model_id)
    return covered


def affected_entities(
    session: Session,
    variable_ids: Iterable[str],
    profiles: Mapping[str, ScenarioProfile],
    *,
    limit: int = MAX_ENTITIES,
) -> dict[str, Any]:
    """Companies the graph ties to the changed variables, with the chain that ties them and
    the models that cover each tie."""
    starts = [variable_key(item) for item in variable_ids]
    # Variables reachable along `influences`, each with the hops that reach it.
    reached: dict[tuple[str, str], list[EdgeView]] = {(start, start): [] for start in starts}
    frontier: list[tuple[str, str, list[EdgeView]]] = [(start, start, []) for start in starts]
    for _ in range(MAX_INFLUENCE_HOPS):
        sources = sorted({node for _, node, _ in frontier})
        if not sources:
            break
        hops = edges(session, types=(GraphEdgeType.INFLUENCES,), sources=sources)
        following: list[tuple[str, str, list[EdgeView]]] = []
        for start, node, path in frontier:
            for hop in hops:
                if (
                    hop.source != node
                    or hop.target == start
                    or any(e.target == hop.target for e in path)
                ):
                    continue
                key = (start, hop.target)
                if key not in reached:
                    reached[key] = [*path, hop]
                    following.append((start, hop.target, [*path, hop]))
        frontier = following

    variables = sorted({node for _, node in reached})
    exposure_edges = edges(session, types=EXPOSURE_TYPES, sources=variables)
    industry_targets = sorted(
        {edge.target for edge in exposure_edges if edge.target.startswith("industry:")}
    )
    members = (
        edges(session, types=(GraphEdgeType.IN_INDUSTRY,), targets=industry_targets)
        if industry_targets
        else []
    )
    by_industry: dict[str, list[EdgeView]] = {}
    for member in members:
        by_industry.setdefault(member.target, []).append(member)

    found: dict[str, list[dict[str, Any]]] = {}
    truncated = False
    for (start, variable), via in sorted(reached.items()):
        for edge in exposure_edges:
            if edge.source != variable:
                continue
            ties: list[tuple[str, list[EdgeView], str | None]] = []
            if edge.target.startswith("company:"):
                ties.append((edge.target, [edge], None))
            else:
                ties.extend(
                    (member.source, [edge, member], edge.target)
                    for member in by_industry.get(edge.target, [])
                )
            for company, chain, industry in ties:
                if company not in found and len(found) >= limit:
                    truncated = True
                    continue
                models = _covered_by(profiles, start, via, edge.edge_type, variable)
                found.setdefault(company, []).append(
                    {
                        "changed_variable": variable_id_of(start),
                        "via": [variable_id_of(hop.target) for hop in via],
                        "relationship": edge.edge_type,
                        "exposed_variable": variable_id_of(variable),
                        "industry": industry,
                        "edges": [item.to_json() for item in [*via, *chain]],
                        "models": models,
                    }
                )

    names = nodes(
        session,
        [*found, *variables, *industry_targets],
    )
    entities = [
        {
            "entity": (
                names[key].to_json()
                if key in names
                else {"key": key, "name": key, "type": "company", "nature": "unknown"}
            ),
            "exposures": [
                {
                    **item,
                    "industry": names[item["industry"]].to_json()
                    if item["industry"] in names
                    else None,
                }
                for item in exposures
            ],
        }
        for key, exposures in sorted(
            found.items(),
            key=lambda pair: names.get(pair[0], NodeView(pair[0], pair[0], "", "")).name,
        )
    ]
    return {
        "entities": entities,
        "variables": {key: names[key].name for key in variables if key in names},
        "truncated": truncated,
        "limit": limit,
        "note": "Ties the knowledge graph states (assumptions or curated facts), not measured "
        "effects. A connection is not evidence of causation; only ties a model covers are "
        "simulated.",
    }
