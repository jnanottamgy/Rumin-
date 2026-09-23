"""Command line for the knowledge graph: ``python -m app.graph <command>``.

The graph is built from here only. The HTTP API is read-only until RUMIN has
authentication, so no anonymous client can change the graph.

    build                  build the graph from the current sources
    validate               check what a build would do, without writing anything
    status                 the latest build, and whether the sources changed since
    builds [--limit N]     recent builds
    report [BUILD]         one build's validation report, changes, issues and decisions

Exit codes: 0 completed (possibly with warnings) · 1 failed (or, for ``validate``,
records would be rejected) · 2 not started (another build running, database not ready).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.base import utcnow
from app.db.session import create_db_engine, create_session_factory
from app.domain.enums import GraphBuildStatus, IssueOutcome
from app.graph.assemble import assemble
from app.graph.build import BuildInProgressError, run_build
from app.graph.drafts import GraphDraft
from app.graph.sources import read_sources
from app.models import GraphBuild, GraphIssue, GraphResolutionDecision

EXIT_OK, EXIT_FAILED, EXIT_NOT_STARTED = 0, 1, 2


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _report_block(
    title: str,
    nodes: tuple[int, int, int, int],
    edges: tuple[int, int, int, int],
) -> None:
    print(title)
    print()
    print(f"Nodes processed: {nodes[0]}")
    print(f"Valid nodes: {nodes[1]}")
    print(f"Flagged nodes: {nodes[2]}")
    print(f"Rejected nodes: {nodes[3]}")
    print()
    print(f"Edges processed: {edges[0]}")
    print(f"Valid edges: {edges[1]}")
    print(f"Flagged edges: {edges[2]}")
    print(f"Rejected edges: {edges[3]}")


def print_build(session: Session, build: GraphBuild) -> None:
    duration = f"{build.duration_ms / 1000:.2f} s" if build.duration_ms is not None else "—"
    print(
        f"Graph build #{build.id} · {build.status.value} · {duration} · "
        f"rules v{build.rules_version}"
    )
    if build.error_summary:
        print(f"  {build.error_summary}")
    if build.status is GraphBuildStatus.FAILED:
        return
    print()
    _report_block(
        "GRAPH VALIDATION REPORT",
        (build.nodes_processed, build.nodes_valid, build.nodes_flagged, build.nodes_rejected),
        (build.edges_processed, build.edges_valid, build.edges_flagged, build.edges_rejected),
    )
    print()
    print(
        f"Changes: nodes +{build.nodes_added} added, {build.nodes_changed} changed, "
        f"{build.nodes_retired} retired, {build.nodes_unchanged} unchanged · edges "
        f"+{build.edges_added} added, {build.edges_changed} changed, {build.edges_retired} "
        f"retired, {build.edges_unchanged} unchanged"
    )
    metrics = build.metrics or {}
    components = metrics.get("components", {})
    provenance = metrics.get("provenance", {})
    print(
        f"Graph: {build.node_count} nodes · {build.edge_count} edges · "
        f"{components.get('count', 0)} connected component(s) · "
        f"evidence on {provenance.get('edges_with_evidence', 0)} of {build.edge_count} edges"
    )
    issues = Counter(
        (row.rule, row.outcome.value)
        for row in session.scalars(select(GraphIssue).where(GraphIssue.build_id == build.id))
    )
    print(
        f"Issues: {build.error_count} error(s) · {build.warning_count} warning(s) · "
        f"{build.info_count} note(s)"
    )
    for (rule, outcome), count in sorted(issues.items()):
        print(f"  {count:>4}  {rule} ({outcome})")
    decisions = Counter(
        (row.method.value, row.outcome.value)
        for row in session.scalars(
            select(GraphResolutionDecision).where(GraphResolutionDecision.build_id == build.id)
        )
    )
    print("Entity resolution:")
    if not decisions:
        print("  no decisions beyond each record's own key")
    for (method, outcome), count in sorted(decisions.items()):
        print(f"  {count:>4}  {outcome} by {method.replace('_', ' ')}")


def cmd_build(session: Session, clock: Callable[[], datetime]) -> int:
    try:
        result = run_build(session, clock=clock)
    except BuildInProgressError as error:
        _err(f"✗ {error} Wait for it to finish, or for an hour if its process died.")
        return EXIT_NOT_STARTED
    print_build(session, result.build)
    return EXIT_FAILED if result.build.status is GraphBuildStatus.FAILED else EXIT_OK


def cmd_validate(session: Session, today: date) -> int:
    draft: GraphDraft = assemble(read_sources(session), today=today)
    tally_n, tally_e = draft.node_tally, draft.edge_tally
    _report_block(
        "GRAPH VALIDATION REPORT (dry run: nothing was written)",
        (tally_n.processed, tally_n.valid, tally_n.flagged, tally_n.rejected),
        (tally_e.processed, tally_e.valid, tally_e.flagged, tally_e.rejected),
    )
    print()
    for item in draft.issues:
        print(f"  [{item.severity.value}] {item.rule}: {item.message}")
    if not draft.issues:
        print("No issues.")
    rejected = any(item.outcome is IssueOutcome.REJECTED for item in draft.issues)
    return EXIT_FAILED if rejected else EXIT_OK


def cmd_status(session: Session) -> int:
    latest = session.scalars(
        select(GraphBuild)
        .where(
            GraphBuild.status.in_(
                (GraphBuildStatus.COMPLETED, GraphBuildStatus.COMPLETED_WITH_WARNINGS)
            )
        )
        .order_by(GraphBuild.id.desc())
    ).first()
    if latest is None:
        print("No graph has been built yet. Run: make graph")
        return EXIT_OK
    current = read_sources(session).fingerprint()
    print(
        f"Latest build #{latest.id} ({latest.status.value}) at {latest.finished_at:%Y-%m-%d %H:%M} "
        f"UTC: {latest.node_count} nodes, {latest.edge_count} edges."
    )
    if current == latest.source_fingerprint:
        print("✓ The graph is up to date with its sources.")
    else:
        print("! The sources have changed since this build. Run: make graph")
    return EXIT_OK


def cmd_builds(session: Session, limit: int) -> int:
    builds = session.scalars(select(GraphBuild).order_by(GraphBuild.id.desc()).limit(limit)).all()
    total = session.scalar(select(func.count()).select_from(GraphBuild)) or 0
    if not builds:
        print("No graph builds yet. Run: make graph")
        return EXIT_OK
    print(f"{len(builds)} of {total} build(s), newest first:")
    for build in builds:
        when = f"{build.started_at:%Y-%m-%d %H:%M}"
        print(
            f"  #{build.id:<4} {when}  {build.status.value:<24} {build.node_count:>5} nodes "
            f"{build.edge_count:>6} edges  +{build.edges_added} ~{build.edges_changed} "
            f"-{build.edges_retired} edges"
        )
    return EXIT_OK


def cmd_report(session: Session, build_id: int | None) -> int:
    statement = select(GraphBuild).order_by(GraphBuild.id.desc())
    if build_id is not None:
        statement = select(GraphBuild).where(GraphBuild.id == build_id)
    build = session.scalars(statement).first()
    if build is None:
        _err(f"✗ No build {'#' + str(build_id) if build_id else 'yet'}.")
        return EXIT_NOT_STARTED
    print_build(session, build)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.graph", description="RUMIN knowledge graph."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="build the graph from the current sources")
    commands.add_parser("validate", help="check what a build would do, without writing")
    commands.add_parser("status", help="the latest build and whether sources changed since")
    builds = commands.add_parser("builds", help="list recent builds")
    builds.add_argument("--limit", type=int, default=10, choices=range(1, 101), metavar="N")
    report = commands.add_parser("report", help="one build's report (default: the latest)")
    report.add_argument("build", nargs="?", type=int, help="build number")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> int:
    args = build_parser().parse_args(argv)
    settings = settings or get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if args.command == "build":
                return cmd_build(session, clock)
            if args.command == "validate":
                return cmd_validate(session, clock().date())
            if args.command == "status":
                return cmd_status(session)
            if args.command == "builds":
                return cmd_builds(session, args.limit)
            return cmd_report(session, args.build)
    except (OperationalError, ProgrammingError) as error:
        _err(f"✗ Database error: {error.orig}")
        _err("  If the database schema has not been created yet, run: make migrate")
        return EXIT_NOT_STARTED
    finally:
        engine.dispose()
