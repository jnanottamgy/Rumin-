"""Exposure analysis: what the knowledge graph states an entity is exposed to.

An **exposure path** runs from an economic variable to the entity:

* **direct** — ``variable —affects_costs|revenue|financing→ company``;
* **via its industry** — ``variable —affects_*→ industry ←in_industry— company``: stated for
  the industry as a whole, not for this company;
* **upstream** — ``origin —influences→ … —influences→ variable`` (at most two hops) in front
  of a direct or via-industry path: the origin is assumed to transmit to the variable.

Only validated edges are used (see ``graphview``). Every path keeps the evidence status of
each edge; its own status is the weakest of them. Supply and credit relationships are listed
as **counterparties** (with the registry's caveat that they say nothing about size), and the
entity's industry, sector, country and that country's currency as **context** — none of
these is presented as an exposure. A stated exposure says *that* an entity is exposed, never
*how much*: sizes come only from simulations with the user's figures.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import GraphEdgeType
from app.intelligence.graphview import (
    AFFECTS,
    CHANNEL,
    EdgeInfo,
    GraphSlice,
    NodeInfo,
    SeriesInfo,
    companies_reached,
    load_companies,
    load_entity,
    load_industries,
    load_workspace,
    members,
    query_nodes,
)
from app.intelligence.model import EDGE_GRADE, GRADE_STRENGTH
from app.scenario_lab.graph import EdgeView, covered_by
from app.scenario_lab.profiles import PROFILES

CATEGORY_GROUP = {
    "commodity": "Commodities",
    "exchange_rate": "Exchange rates",
    "monetary_policy": "Interest rates",
    "inflation": "Inflation",
}
GROUP_ORDER = ("Commodities", "Exchange rates", "Interest rates", "Inflation", "Other variables")
DIRECTNESS_ORDER = {"direct": 0, "via_industry": 1, "upstream": 2}
EVIDENCE_FILTERS = ("any", "evidence_backed")
WORKSPACE_LIMIT = 200

INDUSTRY_NOTE = (
    "Stated for the industry as a whole, not for this company; companies in one industry can "
    "be affected very differently."
)
UPSTREAM_NOTE = (
    "The origin is assumed to transmit to the exposed variable ({hops} hop{s}); a change in "
    "the origin reaches the company only through that assumption."
)
NOT_SIZE = (
    "A stated exposure says that the entity is exposed, not how much: sizes come only from "
    "simulations with the user's own figures."
)
NO_CAUSATION = "A connection in the graph is not evidence of causation."


@dataclass(frozen=True)
class ExposurePath:
    origin: NodeInfo
    variable: NodeInfo
    channel: str
    directness: str  # direct | via_industry | upstream
    base: str  # direct | via_industry: how the exposed variable reaches the entity
    industry: NodeInfo | None
    hops: tuple[NodeInfo, ...]  # origin … variable (one element unless upstream)
    edges: tuple[EdgeInfo, ...]  # in order from the origin to the entity
    evidence_status: str  # the weakest along the path
    models: tuple[str, ...]  # registered models that can simulate this path
    group: str

    @property
    def affect_edge(self) -> EdgeInfo:
        return next(edge for edge in self.edges if edge.edge_type in CHANNEL)

    @property
    def variable_keys(self) -> tuple[str, ...]:
        return tuple(node.key for node in self.hops)


@dataclass(frozen=True)
class Counterparty:
    relationship: str  # supplies_to | lends_to
    role: str  # supplier | customer | lender | borrower
    counterparty: NodeInfo
    level: str  # company | industry
    edge: EdgeInfo


@dataclass(frozen=True)
class ContextLink:
    kind: str  # industry | sector | country | currency | competitor
    node: NodeInfo
    edges: tuple[EdgeInfo, ...]


@dataclass(frozen=True)
class SeriesCoverage:
    variable: str
    series_key: str
    info: SeriesInfo | None
    edge: EdgeInfo


@dataclass(frozen=True)
class ExposureMap:
    entity: NodeInfo
    build_id: int | None
    evidence_filter: str
    paths: tuple[ExposurePath, ...]
    counterparties: tuple[Counterparty, ...]
    context: tuple[ContextLink, ...]
    series: tuple[SeriesCoverage, ...]
    flagged: tuple[EdgeInfo, ...]
    removed_by_filter: int
    notes: tuple[str, ...]

    @property
    def variables(self) -> list[NodeInfo]:
        """Every variable on a path, in order of first appearance."""
        seen: dict[str, NodeInfo] = {}
        for path in self.paths:
            for node in path.hops:
                seen.setdefault(node.key, node)
        return list(seen.values())

    @property
    def names(self) -> dict[str, str]:
        """key → name for every node the map mentions (to write edges in words)."""
        nodes = [
            self.entity,
            *(node for path in self.paths for node in path.hops),
            *(path.industry for path in self.paths if path.industry is not None),
            *(item.counterparty for item in self.counterparties),
            *(link.node for link in self.context),
        ]
        return {node.key: node.name for node in nodes}


def weakest(edges: Sequence[EdgeInfo]) -> str:
    return min(
        (edge.evidence_status for edge in edges),
        key=lambda status: GRADE_STRENGTH[EDGE_GRADE[status]],
    )


def _group(node: NodeInfo) -> str:
    return CATEGORY_GROUP.get(node.category or "", "Other variables")


def _view(edge: EdgeInfo) -> EdgeView:
    return EdgeView(
        edge.key,
        edge.edge_type,
        edge.source,
        edge.target,
        edge.evidence_status,
        edge.is_illustrative,
    )


def _models(origin: str, influences: Sequence[EdgeInfo], affect: EdgeInfo) -> tuple[str, ...]:
    return tuple(
        covered_by(
            PROFILES, origin, [_view(e) for e in influences], affect.edge_type, affect.source
        )
    )


def _influence_chains(graph: GraphSlice, variable: str) -> list[list[EdgeInfo]]:
    """Chains of `influences` edges ending at ``variable``: one or two hops, no repeats."""
    chains: list[list[EdgeInfo]] = []
    for first in graph.by_target(variable, GraphEdgeType.INFLUENCES):
        if first.source == variable:
            continue
        chains.append([first])
        for second in graph.by_target(first.source, GraphEdgeType.INFLUENCES):
            if second.source in (variable, first.source):
                continue
            chains.append([second, first])
    return chains


def paths_for(
    graph: GraphSlice, entity_key: str, industry_edges: Sequence[EdgeInfo]
) -> list[ExposurePath]:
    """Every exposure path to ``entity_key`` in ``graph`` (no evidence filter)."""
    base: list[tuple[EdgeInfo, str, NodeInfo | None, tuple[EdgeInfo, ...]]] = []
    for edge in graph.by_target(entity_key, *AFFECTS):
        base.append((edge, "direct", None, (edge,)))
    for membership in industry_edges:
        member_of = graph.node(membership.target)
        for edge in graph.by_target(membership.target, *AFFECTS):
            base.append((edge, "via_industry", member_of, (edge, membership)))

    paths: list[ExposurePath] = []
    for affect, how, industry, tail in base:
        variable = graph.node(affect.source)
        paths.append(
            ExposurePath(
                origin=variable,
                variable=variable,
                channel=CHANNEL[affect.edge_type],
                directness=how,
                base=how,
                industry=industry,
                hops=(variable,),
                edges=tail,
                evidence_status=weakest(tail),
                models=_models(variable.key, [], affect),
                group=_group(variable),
            )
        )
        for chain in _influence_chains(graph, variable.key):
            origin = graph.node(chain[0].source)
            hops = (origin, *(graph.node(edge.target) for edge in chain))
            edges = (*chain, *tail)
            paths.append(
                ExposurePath(
                    origin=origin,
                    variable=variable,
                    channel=CHANNEL[affect.edge_type],
                    directness="upstream",
                    base=how,
                    industry=industry,
                    hops=hops,
                    edges=edges,
                    evidence_status=weakest(edges),
                    models=_models(origin.key, chain, affect),
                    group=_group(origin),
                )
            )
    return sorted(
        paths,
        key=lambda p: (
            DIRECTNESS_ORDER[p.directness],
            GROUP_ORDER.index(p.group),
            p.origin.name,
            p.channel,
            len(p.hops),
            p.variable.name,
        ),
    )


def _counterparties(
    graph: GraphSlice, entity_key: str, industries: Sequence[str]
) -> list[Counterparty]:
    found: list[Counterparty] = []
    for edge in graph.by_target(entity_key, GraphEdgeType.SUPPLIES_TO):
        found.append(
            Counterparty("supplies_to", "supplier", graph.node(edge.source), "company", edge)
        )
    for edge in graph.by_source(entity_key, GraphEdgeType.SUPPLIES_TO):
        found.append(
            Counterparty("supplies_to", "customer", graph.node(edge.target), "company", edge)
        )
    for edge in graph.by_target(entity_key, GraphEdgeType.LENDS_TO):
        found.append(Counterparty("lends_to", "lender", graph.node(edge.source), "company", edge))
    for edge in graph.by_source(entity_key, GraphEdgeType.LENDS_TO):
        found.append(Counterparty("lends_to", "borrower", graph.node(edge.target), "company", edge))
    for industry in industries:
        if industry == entity_key:
            continue
        for edge in graph.by_target(industry, GraphEdgeType.SUPPLIES_TO):
            found.append(
                Counterparty("supplies_to", "supplier", graph.node(edge.source), "industry", edge)
            )
        for edge in graph.by_source(industry, GraphEdgeType.SUPPLIES_TO):
            found.append(
                Counterparty("supplies_to", "customer", graph.node(edge.target), "industry", edge)
            )
    return found


def _context(graph: GraphSlice, entity_key: str) -> list[ContextLink]:
    links: list[ContextLink] = []
    for membership in graph.by_source(entity_key, GraphEdgeType.IN_INDUSTRY):
        industry = graph.node(membership.target)
        links.append(ContextLink("industry", industry, (membership,)))
        for sector in graph.by_source(industry.key, GraphEdgeType.IN_SECTOR):
            links.append(ContextLink("sector", graph.node(sector.target), (membership, sector)))
    for domicile in graph.by_source(entity_key, GraphEdgeType.DOMICILED_IN):
        links.append(ContextLink("country", graph.node(domicile.target), (domicile,)))
        for currency in graph.by_source(domicile.target, GraphEdgeType.HAS_CURRENCY):
            links.append(ContextLink("currency", graph.node(currency.target), (domicile, currency)))
    for edge in [
        *graph.by_source(entity_key, GraphEdgeType.COMPETES_WITH),
        *graph.by_target(entity_key, GraphEdgeType.COMPETES_WITH),
    ]:
        other = edge.target if edge.source == entity_key else edge.source
        links.append(ContextLink("competitor", graph.node(other), (edge,)))
    return links


def _series(graph: GraphSlice, variables: Sequence[NodeInfo]) -> list[SeriesCoverage]:
    coverage: list[SeriesCoverage] = []
    for variable in variables:
        for edge in graph.by_target(variable.key, GraphEdgeType.RELATED_MEASURE_OF):
            coverage.append(
                SeriesCoverage(variable.key, edge.source, graph.series.get(edge.source), edge)
            )
    return coverage


def analyse(graph: GraphSlice, entity_key: str, *, evidence: str = "any") -> ExposureMap:
    """The exposure map of one company or industry from a loaded slice."""
    entity = graph.node(entity_key)
    industry_edges = graph.by_source(entity_key, GraphEdgeType.IN_INDUSTRY)
    every = paths_for(graph, entity_key, industry_edges)
    kept = [
        path
        for path in every
        if evidence == "any" or all(e.evidence_status == "evidence_backed" for e in path.edges)
    ]
    industries = [edge.target for edge in industry_edges]
    variables: dict[str, NodeInfo] = {}
    for path in kept:
        for node in path.hops:
            variables.setdefault(node.key, node)
    notes = [NOT_SIZE, NO_CAUSATION]
    if every and not any(p.evidence_status == "evidence_backed" for p in every):
        notes.append(
            "None of these exposures is evidence-backed: each rests on at least one "
            "relationship recorded as a model assumption."
        )
    if any(p.directness == "via_industry" for p in kept):
        notes.append(INDUSTRY_NOTE)
    return ExposureMap(
        entity=entity,
        build_id=graph.build_id,
        evidence_filter=evidence,
        paths=tuple(kept),
        counterparties=tuple(_counterparties(graph, entity_key, industries)),
        context=tuple(_context(graph, entity_key)),
        series=tuple(_series(graph, list(variables.values()))),
        flagged=tuple(sorted(graph.flagged.values(), key=lambda e: e.key)),
        removed_by_filter=len(every) - len(kept),
        notes=tuple(notes),
    )


def entity_exposure(
    session: Session, entity_key: str, build_id: int | None, *, evidence: str = "any"
) -> ExposureMap:
    return analyse(load_entity(session, entity_key, build_id), entity_key, evidence=evidence)


# --- Across entities --------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkspaceExposure:
    build_id: int | None
    companies: tuple[NodeInfo, ...]
    variables: tuple[NodeInfo, ...]
    paths: dict[str, tuple[ExposurePath, ...]]  # company key → its paths
    truncated: bool


def workspace_exposure(session: Session, build_id: int | None) -> WorkspaceExposure:
    """Every company's exposure paths, from one bounded read of the graph."""
    graph = load_workspace(session, build_id, limit=WORKSPACE_LIMIT)
    membership = members(graph)
    companies = sorted(
        (node for node in graph.nodes.values() if node.node_type == "company"),
        key=lambda node: (node.name, node.key),
    )
    paths = {
        company.key: tuple(paths_for(graph, company.key, membership.get(company.key, [])))
        for company in companies
    }
    seen: dict[str, NodeInfo] = {}
    for company_paths in paths.values():
        for path in company_paths:
            for node in path.hops:
                seen.setdefault(node.key, node)
    variables = sorted(seen.values(), key=lambda node: (GROUP_ORDER.index(_group(node)), node.name))
    return WorkspaceExposure(
        build_id=build_id,
        companies=tuple(companies),
        variables=tuple(variables),
        paths=paths,
        truncated=graph.truncated,
    )


def industry_exposure(
    session: Session, build_id: int | None, *, limit: int = WORKSPACE_LIMIT
) -> list[tuple[NodeInfo, list[ExposurePath]]]:
    """Every listed industry's exposure paths, from one bounded read of the graph."""
    graph = load_industries(session, build_id, limit=limit)
    industries = sorted(
        (node for node in graph.nodes.values() if node.node_type == "industry"),
        key=lambda node: (node.name, node.key),
    )
    return [(industry, paths_for(graph, industry.key, [])) for industry in industries]


def reach_index(
    workspace: WorkspaceExposure,
) -> dict[str, list[tuple[NodeInfo, list[ExposurePath]]]]:
    """variable key → the companies it reaches (in listing order) with the paths through it,
    for every variable on a path, from one pass over the workspace."""
    index: dict[str, dict[str, list[ExposurePath]]] = {}
    for company in workspace.companies:
        for path in workspace.paths.get(company.key, ()):
            for key in dict.fromkeys(node.key for node in path.hops):
                index.setdefault(key, {}).setdefault(company.key, []).append(path)
    companies = {company.key: company for company in workspace.companies}
    return {
        key: [(companies[company], paths) for company, paths in reached.items()]
        for key, reached in index.items()
    }


def variable_exposure(
    workspace: WorkspaceExposure, variable_key: str
) -> list[tuple[NodeInfo, list[ExposurePath]]]:
    """The listed companies with at least one path through ``variable_key``: what the
    workspace's own findings (X01, D02) count. ``variable_reach`` searches the whole graph."""
    found: list[tuple[NodeInfo, list[ExposurePath]]] = []
    for company in workspace.companies:
        through = [p for p in workspace.paths[company.key] if variable_key in p.variable_keys]
        if through:
            found.append((company, through))
    return found


@dataclass(frozen=True)
class VariableReach:
    companies: tuple[tuple[NodeInfo, tuple[ExposurePath, ...]], ...]  # the first ``limit`` by name
    total: int  # every company the variable reaches
    truncated: bool


def variable_reach(
    session: Session, build_id: int | None, variable_key: str, *, limit: int = WORKSPACE_LIMIT
) -> VariableReach:
    """Every company ``variable_key`` reaches in the whole graph (not only the workspace's
    listing): found by walking downstream from the variable, then the first ``limit`` by name
    with their paths through it. Each company's paths are those of its own analysis."""
    reached = sorted(
        (node for node in query_nodes(session, companies_reached(session, variable_key)).values()),
        key=lambda node: (node.name, node.key),
    )
    listed = reached[:limit]
    graph = load_companies(session, build_id, [node.key for node in listed])
    membership = members(graph)
    found: list[tuple[NodeInfo, tuple[ExposurePath, ...]]] = []
    for company in listed:
        through = tuple(
            path
            for path in paths_for(graph, company.key, membership.get(company.key, []))
            if variable_key in path.variable_keys
        )
        if through:
            found.append((company, through))
    return VariableReach(tuple(found), total=len(reached), truncated=len(reached) > limit)


def summary(paths: Sequence[ExposurePath]) -> dict[str, Any]:
    """Counts by channel, directness, group and evidence status (for signals and lists)."""
    return {
        "paths": len(paths),
        "variables": len({key for p in paths for key in p.variable_keys}),
        "by_channel": dict(Counter(p.channel for p in paths)),
        "by_directness": dict(Counter(p.directness for p in paths)),
        "by_group": dict(Counter(p.group for p in paths)),
        "by_evidence": dict(Counter(p.evidence_status for p in paths)),
    }
