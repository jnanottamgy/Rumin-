"""Graph builds against the database: counts, provenance, rebuilds, changes and failures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.domain.enums import GraphBuildStatus, JobTrigger, ResolutionOutcome
from app.graph.build import BuildInProgressError, run_build
from app.graph.persist import persist as real_persist
from app.graph.sources import RULES_VERSION, read_sources
from app.ingestion.catalog import DEFAULT_CATALOG_PATH, read_catalog, sync_catalog
from app.ingestion.registry import PROFILES
from app.models import (
    Company,
    GraphBuild,
    GraphEdge,
    GraphEdgeEvidence,
    GraphIssue,
    GraphNode,
    GraphNodeIdentifier,
    GraphResolutionDecision,
    Relationship,
)
from tests.test_price_import import CSV, do_import, manifest, write

# From the reference dataset alone: 3 countries, 3 currencies, 6 ISIC sections,
# 8 industries, 12 companies and 7 variables; 41 curated relationships, 24 company links,
# 6 variable links, 8 sector links and 3 currency links.
REFERENCE_NODES = 39
REFERENCE_EDGES = 82


def count(session: Session, model: type[Any], *where: Any) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


def active_nodes(session: Session) -> int:
    return count(session, GraphNode, GraphNode.retired_build_id.is_(None))


def active_edges(session: Session) -> int:
    return count(session, GraphEdge, GraphEdge.retired_build_id.is_(None))


def test_builds_the_reference_network(graph_session: Session) -> None:
    result = run_build(graph_session)
    build = result.build
    assert build.status is GraphBuildStatus.COMPLETED
    assert (build.node_count, build.edge_count) == (REFERENCE_NODES, REFERENCE_EDGES)
    assert (build.nodes_added, build.edges_added) == (REFERENCE_NODES, REFERENCE_EDGES)
    assert build.nodes_processed == build.nodes_valid + build.nodes_flagged + build.nodes_rejected
    assert build.edges_processed == build.edges_valid + build.edges_flagged + build.edges_rejected
    assert build.rules_version == RULES_VERSION and build.trigger is JobTrigger.CLI
    assert build.source_fingerprint == read_sources(graph_session).fingerprint()
    assert build.metrics["components"]["count"] == 1
    assert active_nodes(graph_session) == REFERENCE_NODES
    assert active_edges(graph_session) == REFERENCE_EDGES


def test_every_edge_has_evidence(graph_session: Session) -> None:
    run_build(graph_session)
    without = graph_session.scalars(
        select(GraphEdge.id).where(
            ~select(GraphEdgeEvidence.id).where(GraphEdgeEvidence.edge_id == GraphEdge.id).exists()
        )
    ).all()
    assert without == []
    evidence = graph_session.scalars(select(GraphEdgeEvidence)).all()
    assert all(item.statement and item.transformation and item.rule_id for item in evidence)
    assert {item.source_kind.value for item in evidence} == {
        "reference_dataset",
        "classification_standard",
    }


def test_rebuilding_unchanged_sources_changes_nothing(graph_session: Session) -> None:
    first = run_build(graph_session).build
    second = run_build(graph_session).build
    assert second.id == first.id + 1
    assert (second.nodes_added, second.nodes_changed, second.nodes_retired) == (0, 0, 0)
    assert (second.edges_added, second.edges_changed, second.edges_retired) == (0, 0, 0)
    assert (second.nodes_unchanged, second.edges_unchanged) == (REFERENCE_NODES, REFERENCE_EDGES)
    assert count(graph_session, GraphNode) == REFERENCE_NODES  # no duplicates, ever
    assert count(graph_session, GraphEdge) == REFERENCE_EDGES


def test_changes_are_recorded_and_nothing_is_deleted(graph_session: Session) -> None:
    first = run_build(graph_session).build
    rel = graph_session.get_one(Relationship, "rel_brent_influences_jet_fuel")
    original = rel.description
    saved = {column.key: getattr(rel, column.key) for column in Relationship.__table__.columns}
    try:
        rel.description = "Changed for a test."
        graph_session.commit()
        changed = run_build(graph_session).build
        assert (changed.edges_changed, changed.edges_added, changed.edges_retired) == (1, 0, 0)

        graph_session.delete(rel)
        graph_session.commit()
        removed = run_build(graph_session).build
        assert removed.edges_retired == 1 and removed.edge_count == REFERENCE_EDGES - 1
        retired = graph_session.scalars(
            select(GraphEdge).where(GraphEdge.retired_build_id == removed.id)
        ).one()
        assert retired.first_build_id == first.id  # kept, with its history
        assert count(graph_session, GraphEdgeEvidence, GraphEdgeEvidence.edge_id == retired.id)

        graph_session.add(Relationship(**saved))
        graph_session.commit()
        back = run_build(graph_session).build
        assert back.edges_added == 1 and back.edge_count == REFERENCE_EDGES
        graph_session.refresh(retired)
        assert retired.retired_build_id is None and retired.first_build_id == first.id
        assert retired.description == original
    finally:
        if graph_session.get(Relationship, saved["id"]) is None:
            graph_session.add(Relationship(**saved))
        graph_session.get_one(Relationship, saved["id"]).description = original
        graph_session.commit()


def test_the_fingerprint_notices_changed_sources(graph_session: Session) -> None:
    build = run_build(graph_session).build
    company = graph_session.get_one(Company, "co_aerisca_airways")
    try:
        company.name = "Aerisca Airways (renamed)"
        graph_session.commit()
        assert read_sources(graph_session).fingerprint() != build.source_fingerprint
    finally:
        company.name = "Aerisca Airways"
        graph_session.commit()
    assert read_sources(graph_session).fingerprint() == build.source_fingerprint


def test_series_and_instruments_join_the_graph(graph_session: Session, tmp_path: Path) -> None:
    sync_catalog(graph_session, read_catalog(DEFAULT_CATALOG_PATH, PROFILES), PROFILES)
    graph_session.commit()
    do_import(graph_session, write(tmp_path, CSV), manifest(instrument__country_id="cty_in"))
    build = run_build(graph_session).build
    assert build.status is GraphBuildStatus.COMPLETED
    assert build.node_count == REFERENCE_NODES + 11 + 2  # 11 series, 1 instrument, 1 market
    assert build.edge_count == REFERENCE_EDGES + 15 + 3  # covers/measure/currency; listing links

    identifiers = {
        (row.scheme, row.value): row.node_id
        for row in graph_session.scalars(select(GraphNodeIdentifier))
    }
    assert identifiers[("iso3166_alpha3", "IND")] == "country:cty_in"
    assert identifiers[("isin", "INTESTCO0007")] == "instrument:xnse-testco"
    assert identifiers[("mic", "XNSE")] == "market:xnse"
    market = graph_session.get_one(GraphNode, "market:xnse")
    assert market.nature.value == "sample"  # only a sample file declares it
    attached = count(
        graph_session,
        GraphResolutionDecision,
        GraphResolutionDecision.outcome == ResolutionOutcome.IDENTIFIER_ATTACHED,
    )
    assert attached == 11


def test_a_failed_build_changes_nothing(
    graph_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = run_build(graph_session).build

    def persist_then_fail(*args: Any, **kwargs: Any) -> Any:
        real_persist(*args, **kwargs)  # writes a whole graph…
        raise RuntimeError("simulated failure")  # …then fails before committing

    graph_session.get_one(Relationship, "rel_brent_influences_jet_fuel").description = "Changed."
    graph_session.commit()
    try:
        monkeypatch.setattr("app.graph.build.persist", persist_then_fail)
        failed = run_build(graph_session).build
    finally:
        graph_session.get_one(
            Relationship, "rel_brent_influences_jet_fuel"
        ).description = "The Brent crude oil price influences the jet fuel price."
        graph_session.commit()
    assert failed.status is GraphBuildStatus.FAILED
    assert failed.error_summary and "RuntimeError" not in failed.error_summary  # no internals
    assert count(graph_session, GraphIssue, GraphIssue.build_id == failed.id) == 0
    changed = graph_session.scalars(
        select(GraphEdge).where(GraphEdge.changed_build_id == failed.id)
    ).all()
    assert changed == []  # the graph is still exactly the good build's graph
    assert active_edges(graph_session) == good.edge_count


def test_one_build_at_a_time(graph_session: Session) -> None:
    graph_session.add(
        GraphBuild(
            status=GraphBuildStatus.RUNNING,
            trigger=JobTrigger.CLI,
            rules_version=RULES_VERSION,
            started_at=utcnow(),
        )
    )
    graph_session.commit()
    with pytest.raises(BuildInProgressError):
        run_build(graph_session)


def test_an_abandoned_build_is_closed(graph_session: Session) -> None:
    now = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    stale = GraphBuild(
        status=GraphBuildStatus.RUNNING,
        trigger=JobTrigger.CLI,
        rules_version=RULES_VERSION,
        started_at=now - timedelta(hours=3),
    )
    graph_session.add(stale)
    graph_session.commit()
    result = run_build(graph_session, clock=lambda: now)
    graph_session.refresh(stale)
    assert stale.status is GraphBuildStatus.FAILED
    assert "Interrupted" in (stale.error_summary or "")
    assert result.build.status is GraphBuildStatus.COMPLETED
