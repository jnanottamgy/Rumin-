"""One graph build: record it, read the sources, assemble, validate, persist, report.

The build record is committed *before* any work, so even a build that crashes leaves a
trace. The graph itself changes in one transaction: readers see the previous graph until
the new one is complete, and a failed build changes nothing but its own record.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.domain.enums import GraphBuildStatus, IssueOutcome, IssueSeverity, JobTrigger
from app.graph.assemble import assemble
from app.graph.drafts import GraphDraft
from app.graph.metrics import compute_metrics
from app.graph.persist import Diff, persist
from app.graph.sources import RULES_VERSION, read_sources
from app.ingestion.logs import log_event
from app.models import GraphBuild

logger = logging.getLogger(__name__)

# A build still "running" after this long was interrupted (the process died).
STALE_AFTER = timedelta(hours=1)


class BuildInProgressError(Exception):
    def __init__(self, build: GraphBuild) -> None:
        super().__init__(f"Graph build #{build.id} started at {build.started_at} is still running.")
        self.build = build


@dataclass
class BuildResult:
    build: GraphBuild
    draft: GraphDraft | None


def recover_stale_builds(session: Session, now: datetime) -> int:
    """Close builds left ``running`` by a process that died."""
    stale = session.scalars(
        select(GraphBuild).where(
            GraphBuild.status == GraphBuildStatus.RUNNING,
            GraphBuild.started_at < now - STALE_AFTER,
        )
    ).all()
    for build in stale:
        build.status = GraphBuildStatus.FAILED
        build.finished_at = now
        build.error_summary = "Interrupted: the build process stopped before finishing."
    if stale:
        session.commit()
    return len(stale)


def run_build(session: Session, *, clock: Callable[[], datetime] = utcnow) -> BuildResult:
    """Build the graph from the current sources. Raises ``BuildInProgressError`` if another
    build is running; any other failure is recorded on the build (status ``failed``)."""
    started = clock()
    recover_stale_builds(session, started)
    running = session.scalars(
        select(GraphBuild).where(GraphBuild.status == GraphBuildStatus.RUNNING)
    ).first()
    if running is not None:
        raise BuildInProgressError(running)

    build = GraphBuild(
        status=GraphBuildStatus.RUNNING,
        trigger=JobTrigger.CLI,
        rules_version=RULES_VERSION,
        started_at=started,
    )
    session.add(build)
    session.commit()
    build_id = build.id
    timer = time.perf_counter()
    log_event(logger, "graph.build_started", build=build_id)
    try:
        snapshot = read_sources(session)
        draft = assemble(snapshot, today=started.date())
        node_diff, edge_diff = persist(session, draft, build, started)
        _record(build, draft, node_diff, edge_diff)
        build.source_fingerprint = snapshot.fingerprint()
        build.sources = snapshot.summary()
        build.finished_at = clock()
        build.duration_ms = round((time.perf_counter() - timer) * 1000)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("event=graph.build_failed build=%s", build_id)
        failed = session.get_one(GraphBuild, build_id)
        failed.status = GraphBuildStatus.FAILED
        failed.finished_at = clock()
        failed.duration_ms = round((time.perf_counter() - timer) * 1000)
        failed.error_summary = (
            "The build failed with an internal error and changed nothing. Details are in the "
            "server log."
        )
        session.commit()
        return BuildResult(failed, None)
    log_event(
        logger,
        "graph.build_finished",
        build=build_id,
        status=build.status.value,
        nodes=build.node_count,
        edges=build.edge_count,
        duration_ms=build.duration_ms,
    )
    return BuildResult(build, draft)


def _record(build: GraphBuild, draft: GraphDraft, node_diff: Diff, edge_diff: Diff) -> None:
    nodes, edges = draft.node_tally, draft.edge_tally
    build.nodes_processed, build.nodes_valid = nodes.processed, nodes.valid
    build.nodes_flagged, build.nodes_rejected = nodes.flagged, nodes.rejected
    build.edges_processed, build.edges_valid = edges.processed, edges.valid
    build.edges_flagged, build.edges_rejected = edges.flagged, edges.rejected
    build.nodes_added, build.nodes_changed = node_diff.added, node_diff.changed
    build.nodes_retired, build.nodes_unchanged = node_diff.retired, node_diff.unchanged
    build.edges_added, build.edges_changed = edge_diff.added, edge_diff.changed
    build.edges_retired, build.edges_unchanged = edge_diff.retired, edge_diff.unchanged
    build.node_count, build.edge_count = len(draft.nodes), len(draft.edges)
    severities = [item.severity for item in draft.issues]
    build.error_count = severities.count(IssueSeverity.ERROR)
    build.warning_count = severities.count(IssueSeverity.WARNING)
    build.info_count = severities.count(IssueSeverity.INFO)
    build.metrics = compute_metrics(draft) | {"duplicates_merged": draft.duplicates_merged}
    problems = any(
        item.outcome in (IssueOutcome.REJECTED, IssueOutcome.FLAGGED) for item in draft.issues
    )
    build.status = (
        GraphBuildStatus.COMPLETED_WITH_WARNINGS
        if problems or build.warning_count
        else GraphBuildStatus.COMPLETED
    )
