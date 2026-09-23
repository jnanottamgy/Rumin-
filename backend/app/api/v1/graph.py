"""The knowledge graph: overview, types, nodes, neighbourhoods, edges with provenance,
paths, components, builds and validation issues.

All read-only: the graph is built from the command line (``python -m app.graph build``).
Every traversal is bounded — depth, node count, path length and number of paths have
safe defaults and hard maximums — so no request can walk the whole graph.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import NOT_FOUND, PaginationDep, SessionDep
from app.domain.enums import EvidenceStatus, GraphEdgeType, GraphNodeType, IssueSeverity, NodeNature
from app.graph.algorithms import Direction
from app.graph.drafts import EDGE_KEY_PATTERN, NODE_KEY_PATTERN
from app.schemas.common import SafeText
from app.schemas.graph import (
    ComponentsResponse,
    GraphBuildDetail,
    GraphBuildPage,
    GraphEdgeDetail,
    GraphEdgePage,
    GraphIssuePage,
    GraphNodeDetail,
    GraphOverview,
    GraphTypesResponse,
    NeighborhoodResponse,
    NodeSearchPage,
    PathsResponse,
)
from app.services import graph
from app.services.graph import (
    MAX_DEPTH,
    MAX_NEIGHBORHOOD_NODES,
    MAX_PATH_DEPTH,
    MAX_PATHS,
    SearchSort,
)

router = APIRouter(prefix="/graph", tags=["knowledge graph"])

NodeKey = Annotated[
    str, Path(pattern=NODE_KEY_PATTERN, max_length=128, examples=["country:cty_in"])
]
NodeKeyQuery = Annotated[
    str | None, Query(pattern=NODE_KEY_PATTERN, max_length=128, description="A node key.")
]
# Repeated filters are capped: there are only so many types.
NodeTypes = Annotated[list[GraphNodeType], Query(max_length=9, description="Repeatable.")]
EdgeTypes = Annotated[list[GraphEdgeType], Query(max_length=18, description="Repeatable.")]
EvidenceStatuses = Annotated[list[EvidenceStatus], Query(max_length=4, description="Repeatable.")]
IncludeIllustrative = Annotated[
    bool,
    Query(
        description="Include edges that touch fictional or sample data (most of the sample "
        "network)."
    ),
]
DirectionQuery = Annotated[
    Direction,
    Query(
        description="`any` ignores direction; `out` follows edges from source to target; `in` "
        "the reverse. Undirected edges are followed both ways."
    ),
]


@router.get(
    "/overview",
    response_model=GraphOverview,
    summary="Graph overview",
    description="The latest build, whether it is up to date with its sources, graph metrics "
    "(with definitions and limitations), and a type-level map: node counts per type and edge "
    "counts between types. The map is an aggregate — its links count relationships between "
    "*kinds* of node, not between individual entities.",
)
def get_graph_overview(session: SessionDep) -> GraphOverview:
    return graph.overview(session)


@router.get(
    "/types",
    response_model=GraphTypesResponse,
    summary="Graph vocabulary",
    description="Node types, edge types (meaning, endpoints, direction, allowed evidence "
    "statuses and what each does not mean), evidence-status definitions, identifier schemes, "
    "construction rules and validation rules.",
)
def get_graph_types() -> GraphTypesResponse:
    return graph.types()


@router.get(
    "/nodes",
    response_model=NodeSearchPage,
    summary="Search nodes",
    description="Case-insensitive, partial search over names, subtitles and identifiers "
    "(ISO codes, ISIC codes, ISIN, MIC, provider series keys). An exact identifier match "
    "comes first. `ambiguous` marks names shared by more than one node.",
)
def search_graph_nodes(
    session: SessionDep,
    page: PaginationDep,
    q: Annotated[
        SafeText | None, Query(min_length=1, max_length=100, description="Search text.")
    ] = None,
    type: NodeTypes = [],  # noqa: B006 — FastAPI copies query defaults
    related_to: Annotated[
        str | None,
        Query(
            pattern=NODE_KEY_PATTERN,
            max_length=128,
            description="Only nodes with an edge to this node, e.g. companies in an industry.",
        ),
    ] = None,
    nature: Annotated[NodeNature | None, Query(description="real, fictional or sample.")] = None,
    sort: Annotated[
        SearchSort, Query(description="`name`, or `-degree` (most edges first).")
    ] = "name",
) -> NodeSearchPage:
    return graph.search_nodes(
        session,
        q=q,
        node_types=type,
        related_to=related_to,
        nature=nature,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/nodes/{node_id}",
    response_model=GraphNodeDetail,
    summary="Get a node",
    description="Identifiers, the source records it was built from, how entity resolution "
    "treated it, its relationships by type, quality issues, live data availability (series "
    "and instruments) and — for companies and industries — the variables linked to it by "
    "assumed-effect edges, direct or via its industry.",
    responses=NOT_FOUND,
)
def get_graph_node(session: SessionDep, node_id: NodeKey) -> GraphNodeDetail:
    return graph.get_node(session, node_id)


@router.get(
    "/nodes/{node_id}/neighborhood",
    response_model=NeighborhoodResponse,
    summary="A node's neighbourhood",
    description=f"The nodes within `depth` hops (at most {MAX_DEPTH}) and every edge among "
    f"them, found by breadth-first search with one database query per level. At most "
    f"`max_nodes` nodes (up to {MAX_NEIGHBORHOOD_NODES}); `truncated` and "
    "`unexplored_by_type` say what the limit left out.",
    responses=NOT_FOUND,
)
def get_graph_neighborhood(
    session: SessionDep,
    node_id: NodeKey,
    depth: Annotated[int, Query(ge=1, le=MAX_DEPTH)] = 1,
    max_nodes: Annotated[int, Query(ge=2, le=MAX_NEIGHBORHOOD_NODES)] = 60,
    edge_type: EdgeTypes = [],  # noqa: B006
    node_type: NodeTypes = [],  # noqa: B006
    direction: DirectionQuery = Direction.ANY,
    evidence_status: EvidenceStatuses = [],  # noqa: B006
    include_illustrative: IncludeIllustrative = True,
) -> NeighborhoodResponse:
    return graph.neighborhood(
        session,
        node_id,
        depth=depth,
        max_nodes=max_nodes,
        edge_types=edge_type,
        node_types=node_type,
        direction=direction,
        evidence_statuses=evidence_status,
        include_illustrative=include_illustrative,
    )


@router.get(
    "/edges",
    response_model=GraphEdgePage,
    summary="List edges",
    description="Current edges, filtered by type, evidence status, a node they touch, or "
    "whether they are illustrative.",
)
def list_graph_edges(
    session: SessionDep,
    page: PaginationDep,
    type: EdgeTypes = [],  # noqa: B006
    evidence_status: EvidenceStatuses = [],  # noqa: B006
    node: NodeKeyQuery = None,
    illustrative: Annotated[bool | None, Query()] = None,
) -> GraphEdgePage:
    return graph.list_edges(
        session,
        edge_types=type,
        evidence_statuses=evidence_status,
        node=node,
        illustrative=illustrative,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/edges/{edge_id}",
    response_model=GraphEdgeDetail,
    summary="Get an edge and its provenance",
    description="Why the connection exists: every evidence record (source record, dataset "
    "and version, what the source says, the rule and transformation that made the edge, "
    "retrieval and recording times), its evidence status with a definition, and what this "
    "kind of edge does not mean.",
    responses=NOT_FOUND,
)
def get_graph_edge(
    session: SessionDep, edge_id: Annotated[str, Path(pattern=EDGE_KEY_PATTERN)]
) -> GraphEdgeDetail:
    return graph.get_edge(session, edge_id)


@router.get(
    "/paths",
    response_model=PathsResponse,
    summary="Shortest paths between two nodes",
    description=f"Up to `limit` (at most {MAX_PATHS}) shortest paths, counted in hops, of at "
    f"most `max_depth` hops (at most {MAX_PATH_DEPTH}), found by bidirectional breadth-first "
    "search. A path shows how records are connected; it is not an influence or causal "
    "chain, and a shorter path is not a stronger relationship.",
    responses=NOT_FOUND,
)
def find_graph_paths(
    session: SessionDep,
    source: Annotated[str, Query(alias="from", pattern=NODE_KEY_PATTERN, max_length=128)],
    target: Annotated[str, Query(alias="to", pattern=NODE_KEY_PATTERN, max_length=128)],
    max_depth: Annotated[int, Query(ge=1, le=MAX_PATH_DEPTH)] = 4,
    limit: Annotated[int, Query(ge=1, le=MAX_PATHS)] = 3,
    direction: DirectionQuery = Direction.ANY,
    edge_type: EdgeTypes = [],  # noqa: B006
    evidence_status: EvidenceStatuses = [],  # noqa: B006
    include_illustrative: IncludeIllustrative = True,
) -> PathsResponse:
    return graph.paths(
        session,
        source,
        target,
        max_depth=max_depth,
        limit=limit,
        direction=direction,
        edge_types=edge_type,
        evidence_statuses=evidence_status,
        include_illustrative=include_illustrative,
    )


@router.get(
    "/components",
    response_model=ComponentsResponse,
    summary="Connected components",
    description="Groups of nodes linked by edges (direction ignored), largest first, with "
    "their composition. A component is not an economically integrated system.",
)
def get_graph_components(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> ComponentsResponse:
    return graph.components(session, limit=limit)


@router.get(
    "/builds",
    response_model=GraphBuildPage,
    summary="List graph builds",
    description="Every build, newest first, with its validation counts and changes.",
)
def list_graph_builds(session: SessionDep, page: PaginationDep) -> GraphBuildPage:
    return graph.list_builds(session, limit=page.limit, offset=page.offset)


@router.get(
    "/builds/{build_id}",
    response_model=GraphBuildDetail,
    summary="Get a graph build",
    description="A build's validation report, changes, sources (datasets and versions), "
    "metrics, issue counts by rule and entity-resolution decisions by outcome.",
    responses=NOT_FOUND,
)
def get_graph_build(
    session: SessionDep, build_id: Annotated[int, Path(ge=1, le=2_147_483_647)]
) -> GraphBuildDetail:
    return graph.get_build(session, build_id)


@router.get(
    "/issues",
    response_model=GraphIssuePage,
    summary="List graph validation issues",
    description="Issues found by a build (default: the latest), including entity-resolution "
    "candidates flagged for review.",
)
def list_graph_issues(
    session: SessionDep,
    page: PaginationDep,
    build_id: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
    rule: Annotated[str | None, Query(pattern=r"^[a-z_]{3,64}$")] = None,
    severity: Annotated[IssueSeverity | None, Query()] = None,
    node: NodeKeyQuery = None,
) -> GraphIssuePage:
    return graph.list_issues(
        session,
        build_id=build_id,
        rule=rule,
        severity=severity,
        node=node,
        limit=page.limit,
        offset=page.offset,
    )
