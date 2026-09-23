"""Read access to the knowledge graph for the API.

Built on ``app.graph.store.GraphReader`` (the same interface later phases use). Every
traversal is bounded by limits the routes validate; nothing here writes.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any, Literal

from sqlalchemy import case, func, or_, select, union_all
from sqlalchemy.orm import Session, aliased

from app.core.errors import NotFoundError
from app.db.base import utcnow
from app.domain.enums import (
    Derivation,
    EvidenceSourceKind,
    EvidenceStatus,
    GraphEdgeType,
    GraphIssueSubject,
    GraphNodeType,
    IdentifierScheme,
    IssueSeverity,
    NodeNature,
)
from app.domain.graph_types import (
    EDGE_TYPES,
    EVIDENCE_STATUSES,
    IDENTIFIER_LABELS,
    NODE_TYPE_ORDER,
    NODE_TYPES,
)
from app.graph.algorithms import Direction, EdgeFilter
from app.graph.drafts import KEY_PREFIX
from app.graph.metrics import METRIC_DEFINITIONS
from app.graph.rules import CONSTRUCTION_RULES
from app.graph.sources import read_sources
from app.graph.store import (
    EdgeRecord,
    EvidenceRecord,
    GraphReader,
    NodeRecord,
    edge_ids_touching,
    node_record,
)
from app.graph.validation import GRAPH_RULES
from app.models import (
    EconomicSeries,
    GraphBuild,
    GraphEdge,
    GraphIssue,
    GraphNode,
    GraphNodeIdentifier,
    GraphResolutionDecision,
    Instrument,
)
from app.schemas.graph import (
    BuildChanges,
    BuildCounts,
    ComponentRead,
    ComponentsResponse,
    ConstructionRuleRead,
    DecisionCount,
    EdgeQualifiers,
    EdgeTypeRead,
    EndpointPair,
    EvidenceRead,
    EvidenceStatusRead,
    ExposureRead,
    Freshness,
    GraphBuildDetail,
    GraphBuildPage,
    GraphBuildSummary,
    GraphEdgeDetail,
    GraphEdgePage,
    GraphEdgeSummary,
    GraphIssuePage,
    GraphIssueRead,
    GraphNodeDetail,
    GraphNodeSummary,
    GraphOverview,
    GraphTypesResponse,
    IdentifierRead,
    IdentifierSchemeRead,
    MetricDefinitionRead,
    NeighborhoodResponse,
    NeighborNode,
    NodeDataRead,
    NodeSearchPage,
    NodeSearchResult,
    NodeTypeRead,
    PathRead,
    PathsResponse,
    RelationshipCount,
    ResolutionDecisionRead,
    RuleCount,
    SourceRecordRead,
    TraversalLimits,
    TypeMapLink,
    TypeMapNode,
    ValidationRuleRead,
)
from app.services.common import like_pattern, paginate

# Limits enforced by the routes (documented in docs/api.md).
MAX_DEPTH = 3
MAX_NEIGHBORHOOD_NODES = 200
MAX_PATH_DEPTH = 6
MAX_PATHS = 10
# Nodes a path search may visit before giving up (not user-settable).
PATH_SEARCH_BUDGET = 5_000

PATH_NOTE = (
    "A path shows how records are connected in RUMIN's data. It is not an influence, "
    "transmission or causal chain, and a shorter path is not a stronger relationship."
)
COMPONENT_NOTE = (
    "A component is a set of records reachable from each other through recorded "
    "relationships. It does not mean the entities form an integrated economic system."
)
NOTES = (
    "The graph connects the records RUMIN holds. It is not a map of the complete economy.",
    "Every company in the sample network is fictional, and the relationships among the "
    "sample entities are illustrative model assumptions.",
    "An edge records that a source states a relationship. It is not evidence of causation, "
    "and it says nothing about size or strength.",
)

_TYPE_BY_PREFIX = {prefix: node_type for node_type, prefix in KEY_PREFIX.items()}

SearchSort = Literal["name", "-degree"]


def _latest_build(session: Session) -> GraphBuild | None:
    return GraphReader(session).latest_build()


def _require_graph(session: Session) -> GraphBuild:
    build = _latest_build(session)
    if build is None:
        raise NotFoundError("No knowledge graph has been built yet. Run: make graph")
    return build


# --- Summaries --------------------------------------------------------------------------------


def _summaries(session: Session, records: Iterable[NodeRecord]) -> dict[str, GraphNodeSummary]:
    """Node summaries with each node's primary identifier and live data availability."""
    items = list(records)
    keys = [record.key for record in items]
    primary: dict[str, IdentifierRead] = {}
    if keys:
        for row in session.scalars(
            select(GraphNodeIdentifier).where(GraphNodeIdentifier.node_id.in_(keys))
        ):
            node_type = _TYPE_BY_PREFIX.get(row.node_id.split(":", 1)[0])
            scheme = NODE_TYPES[node_type].primary_scheme if node_type else None
            if scheme is not None and row.scheme == scheme.value and row.node_id not in primary:
                primary[row.node_id] = IdentifierRead(
                    scheme=row.scheme,
                    label=IDENTIFIER_LABELS[IdentifierScheme(row.scheme)],
                    value=row.value,
                )
    series_ids = {
        str(record.attributes.get("series_id"))
        for record in items
        if record.node_type is GraphNodeType.DATA_SERIES
    }
    instrument_ids = {
        str(record.attributes.get("instrument_id"))
        for record in items
        if record.node_type is GraphNodeType.INSTRUMENT
    }
    with_values: set[str] = set()
    if series_ids:
        with_values |= set(
            session.scalars(
                select(EconomicSeries.id).where(
                    EconomicSeries.id.in_(series_ids), EconomicSeries.observation_count > 0
                )
            )
        )
    if instrument_ids:
        with_values |= set(
            session.scalars(
                select(Instrument.id).where(
                    Instrument.id.in_(instrument_ids), Instrument.bar_count > 0
                )
            )
        )

    def data_status(
        record: NodeRecord,
    ) -> Literal["values_stored", "definition_only", "not_applicable"]:
        if record.node_type is GraphNodeType.DATA_SERIES:
            source_id = record.attributes.get("series_id")
        elif record.node_type is GraphNodeType.INSTRUMENT:
            source_id = record.attributes.get("instrument_id")
        else:
            return "not_applicable"
        return "values_stored" if source_id in with_values else "definition_only"

    return {
        record.key: GraphNodeSummary(
            id=record.key,
            type=record.node_type,
            name=record.name,
            subtitle=record.subtitle,
            nature=record.nature,
            quality_status=record.quality_status,
            degree=record.degree,
            primary_identifier=primary.get(record.key),
            data_status=data_status(record),
        )
        for record in items
    }


def _edge_summary(edge: EdgeRecord, today: date) -> GraphEdgeSummary:
    attributes = edge.attributes
    return GraphEdgeSummary(
        id=edge.key,
        type=edge.edge_type,
        category=edge.category,
        source=edge.source,
        target=edge.target,
        directed=edge.directed,
        label=EDGE_TYPES[edge.edge_type].label,
        description=edge.description,
        evidence_status=edge.evidence_status,
        is_illustrative=edge.is_illustrative,
        quality_status=edge.quality_status,
        valid_from=edge.valid_from,
        valid_to=edge.valid_to,
        historical=edge.is_historical(today),
        qualifiers=EdgeQualifiers(
            polarity=attributes.get("polarity"),
            strength=attributes.get("strength"),
            evidence_level=attributes.get("evidence_level"),
            rationale=attributes.get("rationale"),
            stated_difference=attributes.get("stated_difference"),
        ),
    )


def _build_summary(build: GraphBuild) -> GraphBuildSummary:
    return GraphBuildSummary(
        id=build.id,
        status=build.status,
        started_at=build.started_at,
        finished_at=build.finished_at,
        duration_ms=build.duration_ms,
        rules_version=build.rules_version,
        node_count=build.node_count,
        edge_count=build.edge_count,
        nodes=BuildCounts(
            processed=build.nodes_processed,
            valid=build.nodes_valid,
            flagged=build.nodes_flagged,
            rejected=build.nodes_rejected,
        ),
        edges=BuildCounts(
            processed=build.edges_processed,
            valid=build.edges_valid,
            flagged=build.edges_flagged,
            rejected=build.edges_rejected,
        ),
        node_changes=BuildChanges(
            added=build.nodes_added,
            changed=build.nodes_changed,
            retired=build.nodes_retired,
            unchanged=build.nodes_unchanged,
        ),
        edge_changes=BuildChanges(
            added=build.edges_added,
            changed=build.edges_changed,
            retired=build.edges_retired,
            unchanged=build.edges_unchanged,
        ),
        error_count=build.error_count,
        warning_count=build.warning_count,
        info_count=build.info_count,
        error_summary=build.error_summary,
    )


def _issue_read(row: GraphIssue) -> GraphIssueRead:
    return GraphIssueRead(
        id=row.id,
        build_id=row.build_id,
        subject_kind=row.subject_kind,
        subject_ref=row.subject_ref,
        node_id=row.node_id,
        edge_id=row.edge_id,
        rule=row.rule,
        severity=row.severity,
        outcome=row.outcome,
        message=row.message,
        details=row.details or {},
    )


# --- Overview and types -----------------------------------------------------------------------


# Checking freshness reads and hashes every source record, so its cost grows with the
# data (see docs/graph/performance.md). The answer is kept for a short time per API
# process: a source change can take up to this long to show as "stale".
FRESHNESS_TTL_SECONDS = 30.0
_freshness_cache: dict[tuple[int, str | None, str | None], tuple[float, bool]] = {}


def clear_freshness_cache() -> None:
    """Forget cached overview answers (tests, and anything that rewrites the graph)."""
    _freshness_cache.clear()
    _type_map_cache.clear()


def _sources_unchanged(session: Session, build: GraphBuild) -> bool:
    finished = build.finished_at.isoformat() if build.finished_at else None
    key = (build.id, finished, build.source_fingerprint)
    now = time.monotonic()
    cached = _freshness_cache.get(key)
    if cached and now - cached[0] < FRESHNESS_TTL_SECONDS:
        return cached[1]
    unchanged = build.source_fingerprint == read_sources(session).fingerprint()
    _freshness_cache.clear()  # only the latest build's answer is ever needed
    _freshness_cache[key] = (now, unchanged)
    return unchanged


def freshness(session: Session, build: GraphBuild | None) -> Freshness:
    if build is None:
        return Freshness(
            status="not_built",
            message="No knowledge graph has been built yet. Run `make graph` "
            "(python -m app.graph build).",
        )
    if _sources_unchanged(session, build):
        return Freshness(
            status="current", message=f"Built from the current sources (build #{build.id})."
        )
    return Freshness(
        status="stale",
        message=f"The sources changed after build #{build.id}. The graph shows the data as it was "
        "then; run `make graph` to rebuild it.",
    )


# The type map is a pure function of a build (the graph changes only when a build runs),
# so it is counted once per build and kept for the life of the API process.
_type_map_cache: dict[tuple[int, str], tuple[list[TypeMapNode], list[TypeMapLink]]] = {}


def _type_map(
    session: Session, build: GraphBuild | None
) -> tuple[list[TypeMapNode], list[TypeMapLink]]:
    # Only a finished build's map is cached: a running build is still changing the graph.
    key = (build.id, build.finished_at.isoformat()) if build and build.finished_at else None
    if key is not None and key in _type_map_cache:
        return _type_map_cache[key]
    counts: Counter[GraphNodeType] = Counter(
        {
            node_type: count
            for node_type, count in session.execute(
                select(GraphNode.node_type, func.count())
                .where(GraphNode.retired_build_id.is_(None))
                .group_by(GraphNode.node_type)
            )
        }
    )
    source, target = aliased(GraphNode), aliased(GraphNode)
    links = session.execute(
        select(source.node_type, target.node_type, GraphEdge.edge_type, func.count())
        .join(source, source.id == GraphEdge.source_node_id)
        .join(target, target.id == GraphEdge.target_node_id)
        .where(GraphEdge.retired_build_id.is_(None))
        .group_by(source.node_type, target.node_type, GraphEdge.edge_type)
    ).all()
    type_map = [
        TypeMapNode(
            type=node_type,
            label=NODE_TYPES[node_type].label,
            plural=NODE_TYPES[node_type].plural,
            count=counts[node_type],
        )
        for node_type in NODE_TYPE_ORDER
        if counts[node_type]
    ]
    type_links = sorted(
        (
            TypeMapLink(
                source_type=source_type,
                target_type=target_type,
                edge_type=edge_type,
                label=EDGE_TYPES[edge_type].label,
                count=count,
            )
            for source_type, target_type, edge_type, count in links
        ),
        key=lambda link: (-link.count, link.edge_type.value),
    )
    if key is not None:
        _type_map_cache.clear()  # only the latest build's map is ever needed
        _type_map_cache[key] = (type_map, type_links)
    return type_map, type_links


def overview(session: Session) -> GraphOverview:
    build = _latest_build(session)
    type_map, type_links = _type_map(session, build)
    return GraphOverview(
        build=_build_summary(build) if build else None,
        freshness=freshness(session, build),
        metrics=build.metrics if build else {},
        type_map=type_map,
        type_links=type_links,
        metric_definitions=[MetricDefinitionRead(**vars(item)) for item in METRIC_DEFINITIONS],
        notes=list(NOTES),
    )


def types() -> GraphTypesResponse:
    return GraphTypesResponse(
        node_types=[
            NodeTypeRead(
                type=spec.type,
                label=spec.label,
                plural=spec.plural,
                description=spec.description,
                primary_identifier=IDENTIFIER_LABELS[spec.primary_scheme]
                if spec.primary_scheme
                else None,
            )
            for spec in NODE_TYPES.values()
        ],
        edge_types=[
            EdgeTypeRead(
                type=spec.type,
                category=spec.category,
                label=spec.label,
                description=spec.description,
                caveat=spec.caveat,
                directed=spec.directed,
                endpoints=[
                    EndpointPair(source=source, target=target)
                    for source, target in sorted(spec.allowed_pairs)
                ],
                evidence_statuses=sorted(spec.evidence_statuses),
            )
            for spec in EDGE_TYPES.values()
        ],
        evidence_statuses=[
            EvidenceStatusRead(status=spec.status, label=spec.label, definition=spec.definition)
            for spec in EVIDENCE_STATUSES.values()
        ],
        identifier_schemes=[
            IdentifierSchemeRead(scheme=scheme.value, label=label)
            for scheme, label in IDENTIFIER_LABELS.items()
        ],
        construction_rules=[
            ConstructionRuleRead(**vars(rule)) for rule in CONSTRUCTION_RULES.values()
        ],
        validation_rules=[
            ValidationRuleRead(
                code=rule.code,
                subject=rule.subject,
                severity=rule.severity,
                outcome=rule.outcome,
                description=rule.description,
            )
            for rule in GRAPH_RULES.values()
        ],
    )


# --- Nodes ------------------------------------------------------------------------------------


def search_nodes(
    session: Session,
    *,
    q: str | None,
    node_types: Sequence[GraphNodeType],
    related_to: str | None,
    nature: NodeNature | None,
    sort: SearchSort,
    limit: int,
    offset: int,
) -> NodeSearchPage:
    statement = select(GraphNode).where(GraphNode.retired_build_id.is_(None))
    if node_types:
        statement = statement.where(GraphNode.node_type.in_(node_types))
    if nature is not None:
        statement = statement.where(GraphNode.nature == nature)
    if related_to:
        active = GraphEdge.retired_build_id.is_(None)
        statement = statement.where(
            GraphNode.id.in_(
                union_all(
                    select(GraphEdge.target_node_id).where(
                        active, GraphEdge.source_node_id == related_to
                    ),
                    select(GraphEdge.source_node_id).where(
                        active, GraphEdge.target_node_id == related_to
                    ),
                )
            )
        )
    order: list[Any] = []
    if q:
        text = q.strip().lower()
        identifier_hit = (
            select(GraphNodeIdentifier.id)
            .where(
                GraphNodeIdentifier.node_id == GraphNode.id,
                func.lower(GraphNodeIdentifier.value) == text,
            )
            .exists()
        )
        statement = statement.where(
            or_(GraphNode.search_text.like(like_pattern(text), escape="\\"), identifier_hit)
        )
        name = func.lower(GraphNode.display_name)
        order.append(
            case(
                (identifier_hit, 0),
                (name == text, 1),
                (name.like(like_pattern(text)[1:], escape="\\"), 2),
                (name.like(like_pattern(text), escape="\\"), 3),
                else_=4,
            )
        )
    if sort == "-degree":
        order.append(GraphNode.degree.desc())
    order += [func.lower(GraphNode.display_name), GraphNode.id]
    rows, total = paginate(session, statement.order_by(*order), limit, offset)

    records = [node_record(row) for row in rows]
    summaries = _summaries(session, records)
    names = {record.name.lower() for record in records}
    shared = set()
    if names:
        shared = set(
            session.scalars(
                select(func.lower(GraphNode.display_name))
                .where(
                    GraphNode.retired_build_id.is_(None),
                    func.lower(GraphNode.display_name).in_(names),
                )
                .group_by(func.lower(GraphNode.display_name))
                .having(func.count() > 1)
            )
        )
    identifier_matches: set[str] = set()
    if q and records:
        identifier_matches = set(
            session.scalars(
                select(GraphNodeIdentifier.node_id).where(
                    GraphNodeIdentifier.node_id.in_([record.key for record in records]),
                    func.lower(GraphNodeIdentifier.value) == q.strip().lower(),
                )
            )
        )

    def match(record: NodeRecord) -> str:
        if not q:
            return "filter"
        if record.key in identifier_matches:
            return "identifier"
        return "name" if q.strip().lower() in record.name.lower() else "details"

    return NodeSearchPage(
        items=[
            NodeSearchResult(
                **summaries[record.key].model_dump(),
                match=match(record),
                ambiguous=record.name.lower() in shared,
            )
            for record in records
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_node(session: Session, key: str) -> GraphNodeDetail:
    build = _require_graph(session)
    reader = GraphReader(session)
    record = reader.node(key)
    if record is None:
        raise NotFoundError(f"No node '{key}' in the current graph.")
    summary = _summaries(session, [record])[key]
    today = utcnow().date()

    counts: Counter[tuple[GraphEdgeType, str]] = Counter()
    for edge_type, source, directed in session.execute(
        select(GraphEdge.edge_type, GraphEdge.source_node_id, GraphEdge.directed).where(
            GraphEdge.id.in_(edge_ids_touching([key]))
        )
    ):
        direction = "undirected" if not directed else "outgoing" if source == key else "incoming"
        counts[(edge_type, direction)] += 1

    decisions = session.scalars(
        select(GraphResolutionDecision)
        .where(GraphResolutionDecision.build_id == build.id, GraphResolutionDecision.node_id == key)
        .order_by(GraphResolutionDecision.id)
    ).all()
    issues = session.scalars(
        select(GraphIssue)
        .where(
            GraphIssue.build_id == build.id,
            GraphIssue.node_id == key,
            GraphIssue.subject_kind != GraphIssueSubject.EDGE,
        )
        .order_by(GraphIssue.id)
    ).all()

    exposures = None
    if record.node_type in (GraphNodeType.COMPANY, GraphNodeType.INDUSTRY):
        found = reader.exposures(key)
        involved = [item.variable for item in found] + [item.via for item in found if item.via]
        linked = _summaries(session, {node.key: node for node in involved}.values())
        exposures = [
            ExposureRead(
                kind="via_industry" if item.via else "direct",
                variable=linked[item.variable.key],
                edge=_edge_summary(item.edge, today),
                via=linked[item.via.key] if item.via else None,
                explanation=_exposure_text(record, item.edge, item.via),
            )
            for item in found
        ]

    return GraphNodeDetail(
        **summary.model_dump(),
        description=record.description,
        attributes=record.attributes,
        identifiers=[
            IdentifierRead(
                scheme=scheme,
                label=IDENTIFIER_LABELS[IdentifierScheme(scheme)],
                value=value,
                source=source,
            )
            for scheme, value, source in reader.identifiers(key)
        ],
        sources=[SourceRecordRead(**source) for source in record.sources],
        in_degree=record.in_degree,
        out_degree=record.out_degree,
        component=record.component,
        relationships=[
            RelationshipCount(
                type=edge_type,
                label=EDGE_TYPES[edge_type].label,
                direction=direction,
                count=count,
            )
            for (edge_type, direction), count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0][0].value)
            )
        ],
        resolution=[
            ResolutionDecisionRead(
                method=row.method,
                outcome=row.outcome,
                source=f"{row.source_table}/{row.source_record_id}",
                identifier=row.identifier,
                candidates=list(row.candidate_node_ids or []),
                rationale=row.rationale,
            )
            for row in decisions
        ],
        issues=[_issue_read(row) for row in issues],
        exposures=exposures,
        data=_node_data(session, record),
        first_build_id=record.first_build_id,
        changed_build_id=record.changed_build_id,
    )


def _exposure_text(entity: NodeRecord, edge: EdgeRecord, via: NodeRecord | None) -> str:
    status = EVIDENCE_STATUSES[edge.evidence_status].label.lower()
    illustrative = " (illustrative)" if edge.is_illustrative else ""
    if via is None:
        return f"Stated for {entity.name} itself: a {status}{illustrative}."
    return (
        f"Stated for the industry {via.name} as a whole, not for {entity.name}: a "
        f"{status}{illustrative}. Companies in one industry can be affected very differently."
    )


def _node_data(session: Session, record: NodeRecord) -> NodeDataRead | None:
    if record.node_type is GraphNodeType.DATA_SERIES:
        series = session.get(EconomicSeries, str(record.attributes.get("series_id")))
        if series is None:
            return None
        return NodeDataRead(
            kind="series",
            record_id=series.id,
            value_count=series.observation_count,
            first=series.first_period,
            last=series.last_period,
            last_retrieved_at=series.last_successful_ingestion_at,
        )
    if record.node_type is GraphNodeType.INSTRUMENT:
        instrument = session.get(Instrument, str(record.attributes.get("instrument_id")))
        if instrument is None:
            return None
        return NodeDataRead(
            kind="instrument",
            record_id=instrument.id,
            value_count=instrument.bar_count,
            first=instrument.first_trade_date,
            last=instrument.last_trade_date,
        )
    return None


def _filter(
    *,
    edge_types: Sequence[GraphEdgeType],
    node_types: Sequence[GraphNodeType],
    direction: Direction,
    evidence_statuses: Sequence[EvidenceStatus],
    include_illustrative: bool,
) -> EdgeFilter:
    prefixes = tuple(f"{KEY_PREFIX[node_type]}:" for node_type in node_types)
    return EdgeFilter(
        edge_types=frozenset(item.value for item in edge_types) if edge_types else None,
        direction=direction,
        node_filter=(lambda key: key.startswith(prefixes)) if prefixes else None,
        evidence_statuses=frozenset(item.value for item in evidence_statuses)
        if evidence_statuses
        else None,
        include_illustrative=include_illustrative,
    )


def neighborhood(
    session: Session,
    key: str,
    *,
    depth: int,
    max_nodes: int,
    edge_types: Sequence[GraphEdgeType],
    node_types: Sequence[GraphNodeType],
    direction: Direction,
    evidence_statuses: Sequence[EvidenceStatus],
    include_illustrative: bool,
) -> NeighborhoodResponse:
    _require_graph(session)
    reader = GraphReader(session)
    if reader.node(key) is None:
        raise NotFoundError(f"No node '{key}' in the current graph.")
    rules = _filter(
        edge_types=edge_types,
        node_types=node_types,
        direction=direction,
        evidence_statuses=evidence_statuses,
        include_illustrative=include_illustrative,
    )
    found = reader.neighborhood(key, depth=depth, max_nodes=max_nodes, edge_filter=rules)
    summaries = _summaries(session, found.nodes.values())
    today = utcnow().date()
    unexplored = Counter(
        _TYPE_BY_PREFIX[item.split(":", 1)[0]].value
        for item in found.unexplored
        if item.split(":", 1)[0] in _TYPE_BY_PREFIX
    )
    return NeighborhoodResponse(
        center=summaries[key],
        depth=depth,
        nodes=[
            NeighborNode(**summaries[node].model_dump(), depth=found.depth[node])
            for node in sorted(found.nodes, key=lambda item: (found.depth[item], item))
        ],
        edges=[
            _edge_summary(edge, today)
            for edge in sorted(found.edges.values(), key=lambda item: item.key)
        ],
        truncated=bool(found.unexplored),
        unexplored_count=len(found.unexplored),
        unexplored_by_type=dict(sorted(unexplored.items())),
        limits=TraversalLimits(max_depth=MAX_DEPTH, max_nodes=max_nodes),
        queries=found.queries,
    )


# --- Edges ------------------------------------------------------------------------------------


def list_edges(
    session: Session,
    *,
    edge_types: Sequence[GraphEdgeType],
    evidence_statuses: Sequence[EvidenceStatus],
    node: str | None,
    illustrative: bool | None,
    limit: int,
    offset: int,
) -> GraphEdgePage:
    statement = select(GraphEdge).where(GraphEdge.retired_build_id.is_(None))
    if edge_types:
        statement = statement.where(GraphEdge.edge_type.in_(edge_types))
    if evidence_statuses:
        statement = statement.where(GraphEdge.evidence_status.in_(evidence_statuses))
    if node:
        statement = statement.where(GraphEdge.id.in_(edge_ids_touching([node])))
    if illustrative is not None:
        statement = statement.where(GraphEdge.is_illustrative.is_(illustrative))
    statement = statement.order_by(
        GraphEdge.edge_type, GraphEdge.source_node_id, GraphEdge.target_node_id
    )
    rows, total = paginate(session, statement, limit, offset)
    reader = GraphReader(session)
    records = reader.edges(row.id for row in rows)
    today = utcnow().date()
    return GraphEdgePage(
        items=[_edge_summary(records[row.id], today) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _evidence_read(item: EvidenceRecord) -> EvidenceRead:
    rule = CONSTRUCTION_RULES.get(item.rule.partition(" ")[2])
    return EvidenceRead(
        rule=item.rule,
        rule_description=rule.description if rule else "",
        source_kind=EvidenceSourceKind(item.source_kind),
        source_table=item.source_table,
        source_record_id=item.source_record_id,
        dataset_id=item.dataset_id,
        dataset_version=item.dataset_version,
        statement=item.statement,
        transformation=item.transformation,
        derivation=Derivation(item.derivation),
        derived_from=item.derived_from,
        citation=item.citation,
        citation_url=item.citation_url,
        retrieved_at=item.retrieved_at,
        recorded_at=item.recorded_at,
    )


def _explain(
    edge: EdgeRecord,
    source: GraphNodeSummary,
    target: GraphNodeSummary,
    evidence: list[EvidenceRecord],
) -> str:
    spec = EDGE_TYPES[edge.edge_type]
    parts = [f"{source.name} — {spec.label} → {target.name}."]
    for item in evidence:
        where = f"{item.source_table}/{item.source_record_id}"
        if item.dataset_id:
            where += f" (dataset {item.dataset_id}, {item.dataset_version})"
        parts.append(f"Rule {item.rule} built it from {where}: {item.statement}")
    status = EVIDENCE_STATUSES[edge.evidence_status]
    parts.append(f"Evidence status: {status.label}. {status.definition}")
    if edge.is_illustrative:
        parts.append(
            "Illustrative: it involves the fictional sample network or sample data, so it "
            "says nothing about the real world."
        )
    return " ".join(parts)


def get_edge(session: Session, key: str) -> GraphEdgeDetail:
    _require_graph(session)
    reader = GraphReader(session)
    edge = reader.edge(key)
    if edge is None:
        raise NotFoundError(f"No edge '{key}' in the current graph.")
    nodes = _summaries(session, reader.nodes([edge.source, edge.target]).values())
    evidence = reader.evidence([key]).get(key, [])
    spec = EDGE_TYPES[edge.edge_type]
    status = EVIDENCE_STATUSES[edge.evidence_status]
    return GraphEdgeDetail(
        **_edge_summary(edge, utcnow().date()).model_dump(),
        source_node=nodes[edge.source],
        target_node=nodes[edge.target],
        explanation=_explain(edge, nodes[edge.source], nodes[edge.target], evidence),
        evidence=[_evidence_read(item) for item in evidence],
        evidence_status_label=status.label,
        evidence_status_definition=status.definition,
        type_description=spec.description,
        caveat=spec.caveat,
        first_build_id=edge.first_build_id,
        changed_build_id=edge.changed_build_id,
    )


# --- Paths and components ---------------------------------------------------------------------


def paths(
    session: Session,
    source: str,
    target: str,
    *,
    max_depth: int,
    limit: int,
    direction: Direction,
    edge_types: Sequence[GraphEdgeType],
    evidence_statuses: Sequence[EvidenceStatus],
    include_illustrative: bool,
) -> PathsResponse:
    _require_graph(session)
    reader = GraphReader(session)
    for label, key in (("source", source), ("target", target)):
        if reader.node(key) is None:
            raise NotFoundError(f"No {label} node '{key}' in the current graph.")
    rules = _filter(
        edge_types=edge_types,
        node_types=(),
        direction=direction,
        evidence_statuses=evidence_statuses,
        include_illustrative=include_illustrative,
    )
    result = reader.paths(
        source,
        target,
        max_depth=max_depth,
        limit=limit,
        edge_filter=rules,
        max_nodes=PATH_SEARCH_BUDGET,
    )
    summaries = _summaries(session, result.nodes.values())
    today = utcnow().date()
    return PathsResponse(
        source=summaries[source],
        target=summaries[target],
        found=result.search.length is not None,
        length=result.search.length,
        paths=[
            PathRead(nodes=list(path.nodes), edges=list(path.edges), length=path.length)
            for path in result.search.paths
        ],
        nodes=[summaries[key] for key in sorted(summaries)],
        edges=[_edge_summary(result.edges[key], today) for key in sorted(result.edges)],
        direction=direction,
        max_depth=max_depth,
        budget_exhausted=result.search.budget_exhausted,
        nodes_explored=result.search.nodes_explored,
        note=PATH_NOTE,
    )


def components(session: Session, *, limit: int) -> ComponentsResponse:
    _require_graph(session)
    active = GraphNode.retired_build_id.is_(None)
    sizes = session.execute(
        select(GraphNode.component, func.count())
        .where(active, GraphNode.component.is_not(None))
        .group_by(GraphNode.component)
        .order_by(GraphNode.component)
    ).all()
    by_type: dict[int, dict[str, int]] = defaultdict(dict)
    for component, node_type, count in session.execute(
        select(GraphNode.component, GraphNode.node_type, func.count())
        .where(active, GraphNode.component.is_not(None))
        .group_by(GraphNode.component, GraphNode.node_type)
    ):
        by_type[component][node_type.value] = count
    shown: list[ComponentRead] = []
    for component, size in sizes[:limit]:
        rows = session.scalars(
            select(GraphNode)
            .where(active, GraphNode.component == component)
            .order_by(GraphNode.degree.desc(), GraphNode.id)
            .limit(5)
        ).all()
        sample = _summaries(session, [node_record(row) for row in rows])
        shown.append(
            ComponentRead(
                number=component,
                size=size,
                nodes_by_type=dict(sorted(by_type[component].items())),
                sample=[sample[row.id] for row in rows],
            )
        )
    return ComponentsResponse(
        count=len(sizes),
        isolated_nodes=sum(1 for _, size in sizes if size == 1),
        components=shown,
        note=COMPONENT_NOTE,
    )


# --- Builds and issues ------------------------------------------------------------------------


def list_builds(session: Session, *, limit: int, offset: int) -> GraphBuildPage:
    rows, total = paginate(
        session, select(GraphBuild).order_by(GraphBuild.id.desc()), limit, offset
    )
    return GraphBuildPage(
        items=[_build_summary(row) for row in rows], total=total, limit=limit, offset=offset
    )


def get_build(session: Session, build_id: int) -> GraphBuildDetail:
    build = session.get(GraphBuild, build_id)
    if build is None:
        raise NotFoundError(f"No graph build #{build_id}.")
    issues = session.execute(
        select(GraphIssue.rule, GraphIssue.outcome, func.count())
        .where(GraphIssue.build_id == build_id)
        .group_by(GraphIssue.rule, GraphIssue.outcome)
        .order_by(GraphIssue.rule)
    ).all()
    decisions = session.execute(
        select(GraphResolutionDecision.method, GraphResolutionDecision.outcome, func.count())
        .where(GraphResolutionDecision.build_id == build_id)
        .group_by(GraphResolutionDecision.method, GraphResolutionDecision.outcome)
        .order_by(GraphResolutionDecision.method, GraphResolutionDecision.outcome)
    ).all()
    return GraphBuildDetail(
        **_build_summary(build).model_dump(),
        source_fingerprint=build.source_fingerprint,
        sources=build.sources or {},
        metrics=build.metrics or {},
        issues_by_rule=[
            RuleCount(rule=rule, outcome=outcome, count=count) for rule, outcome, count in issues
        ],
        decisions=[
            DecisionCount(method=method, outcome=outcome, count=count)
            for method, outcome, count in decisions
        ],
    )


def list_issues(
    session: Session,
    *,
    build_id: int | None,
    rule: str | None,
    severity: IssueSeverity | None,
    node: str | None,
    limit: int,
    offset: int,
) -> GraphIssuePage:
    if build_id is None:
        latest = session.scalars(select(GraphBuild.id).order_by(GraphBuild.id.desc())).first()
        if latest is None:
            return GraphIssuePage(items=[], total=0, limit=limit, offset=offset)
        build_id = latest
    statement = select(GraphIssue).where(GraphIssue.build_id == build_id)
    if rule:
        statement = statement.where(GraphIssue.rule == rule)
    if severity:
        statement = statement.where(GraphIssue.severity == severity)
    if node:
        statement = statement.where(GraphIssue.node_id == node)
    rows, total = paginate(session, statement.order_by(GraphIssue.id), limit, offset)
    return GraphIssuePage(
        items=[_issue_read(row) for row in rows], total=total, limit=limit, offset=offset
    )
