"""Command line for data ingestion: ``python -m app.ingestion <command>``.

Ingestion is started from here only. The HTTP API is read-only for jobs until RUMIN has
authentication, so no anonymous client can make RUMIN send requests to a provider.

    catalog [--check]                  validate the series catalogue and sync it
    run DATASET [--series ID …]        fetch series from the dataset's provider
        [--start PERIOD] [--end PERIOD]
    import-prices --manifest M --file F   import a licensed price file
    manifest-template                  print a blank price-file manifest
    jobs [--limit N]                   list recent jobs
    job JOB_ID                         show one job, its targets and its issues

Exit codes: 0 completed (possibly with warnings) · 1 failed · 2 not started (bad input,
another run in progress, database not ready) · 3 partially failed · 130 cancelled.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.base import utcnow
from app.db.session import create_db_engine, create_session_factory
from app.domain.enums import DatasetKind, JobItemStatus, JobStatus
from app.ingestion import jobs
from app.ingestion.catalog import (
    DEFAULT_CATALOG_PATH,
    Catalog,
    CatalogError,
    read_catalog,
    sync_catalog,
)
from app.ingestion.economic import run_economic_ingestion
from app.ingestion.http import HttpClient
from app.ingestion.normalize import (
    NormalizationError,
    current_period,
    parse_provider_period,
    provider_period_label,
)
from app.ingestion.prices import ManifestError, import_price_file, manifest_template, read_manifest
from app.ingestion.providers.base import EconomicSeriesSource
from app.ingestion.registry import PROFILES, build_economic_source, build_price_file
from app.models import DataQualityIssue, Dataset, EconomicSeries, IngestionJob

EXIT_OK, EXIT_FAILED, EXIT_NOT_STARTED, EXIT_PARTIAL, EXIT_CANCELLED = 0, 1, 2, 3, 130
EXIT_BY_STATUS = {
    JobStatus.COMPLETED: EXIT_OK,
    JobStatus.COMPLETED_WITH_WARNINGS: EXIT_OK,
    JobStatus.PARTIALLY_FAILED: EXIT_PARTIAL,
    JobStatus.FAILED: EXIT_FAILED,
    JobStatus.CANCELLED: EXIT_CANCELLED,
}
ITEM_MARK = {
    JobItemStatus.SUCCEEDED: "✓",
    JobItemStatus.FAILED: "✗",
    JobItemStatus.SKIPPED: "-",
    JobItemStatus.PENDING: "…",
}

SourceFactory = Callable[[str, Settings], EconomicSeriesSource | None]


class UsageError(Exception):
    """The command could not start: explain why, change nothing."""


def _err(message: str) -> None:
    print(message, file=sys.stderr)


# --- Output -------------------------------------------------------------------------------


def _size(count: int) -> str:
    return f"{count / 1024:,.0f} KB" if count >= 1024 else f"{count} bytes"


def print_job(session: Session, job: IngestionJob, *, issues: int = 0) -> None:
    dataset = session.get(Dataset, job.dataset_id)
    print(f"Job {job.id}")
    print(f"  dataset   {job.dataset_id}" + (f" — {dataset.name}" if dataset else ""))
    print(f"  provider  {job.provider_id}")
    print(f"  created   {job.created_at:%Y-%m-%d %H:%M:%S} UTC")
    for item in jobs.job_items(session, job):
        mark = ITEM_MARK[item.status]
        if item.status is JobItemStatus.SUCCEEDED or item.records_received:
            detail = (
                f"received {item.records_received} · new {item.records_new} · revised "
                f"{item.records_revised} · unchanged {item.records_unchanged} · missing "
                f"{item.records_missing} · rejected {item.records_rejected}"
            )
        else:
            detail = ""
        if item.error_code:
            detail = f"{detail} · " if detail else ""
            detail += f"{item.error_code}: {item.error_message}"
        print(f"  {mark} {item.target_label}")
        if detail:
            print(f"      {detail}")
    print(f"Status: {job.status}")
    if job.error_summary:
        print(f"  {job.error_summary}")
    print(
        f"  {job.items_succeeded} of {job.items_total} target(s) succeeded · "
        f"{job.warning_count} warning(s) · {job.records_rejected} record(s) rejected · "
        f"{job.request_count} request(s) · {_size(job.bytes_received)} received"
    )
    if dataset is not None and dataset.attribution:
        print(f"  Attribution: {dataset.attribution} (licence: {dataset.license})")
    if issues:
        rows = session.execute(
            select(DataQualityIssue.rule, DataQualityIssue.outcome, func.count())
            .where(DataQualityIssue.job_id == job.id)
            .group_by(DataQualityIssue.rule, DataQualityIssue.outcome)
            .order_by(func.count().desc(), DataQualityIssue.rule)
            .limit(issues)
        ).all()
        if rows:
            print("Quality issues:")
            for rule, outcome, count in rows:
                print(f"  {count:>5}  {rule} ({outcome})")


# --- Commands -----------------------------------------------------------------------------


def _load_catalog(path: Path) -> Catalog:
    try:
        return read_catalog(path, PROFILES)
    except CatalogError as error:
        problems = "".join(f"\n  - {problem}" for problem in error.problems)
        raise UsageError(f"{error}{problems}") from error


def cmd_catalog(session: Session, args: argparse.Namespace) -> int:
    catalog = _load_catalog(args.file)
    print(
        f"✓ {args.file.name} is valid (catalogue v{catalog.version}: "
        f"{len(catalog.datasets)} dataset(s), {len(catalog.series)} series)"
    )
    if args.check:
        return EXIT_OK
    report = sync_catalog(session, catalog, PROFILES)
    session.commit()
    print(
        f"✓ Synced {report.providers} provider(s), {report.datasets} dataset(s), "
        f"{report.series_created} new and {report.series_updated} updated series"
    )
    for link in report.unlinked:
        print(f"  ! not linked (reference data missing?): {link}")
    for series_id in report.not_in_catalog:
        print(f"  ! kept, but no longer in the catalogue: {series_id}")
    return EXIT_OK


def _periods(
    series: Sequence[EconomicSeries],
    catalog: Catalog,
    start: str | None,
    end: str | None,
    today: date,
) -> tuple[dict[str, str], dict[str, str]]:
    """Each series' period range in provider notation, validated before anything runs."""
    catalog_start = {spec.id: spec.start for spec in catalog.series}
    starts: dict[str, str] = {}
    ends: dict[str, str] = {}
    for entry in series:
        latest = current_period(entry.frequency, today)
        try:
            first = parse_provider_period(start or catalog_start[entry.id], entry.frequency)
            last = parse_provider_period(end, entry.frequency) if end else latest
        except NormalizationError as error:
            raise UsageError(f"{entry.id}: {error.message}") from error
        if last.start > latest.start:
            raise UsageError(f"{entry.id}: the end period {last.label} is in the future.")
        if first.start > last.start:
            raise UsageError(f"{entry.id}: the start {first.label} is after the end {last.label}.")
        starts[entry.id] = provider_period_label(first)
        ends[entry.id] = provider_period_label(last)
    return starts, ends


def cmd_run(
    session: Session,
    args: argparse.Namespace,
    settings: Settings,
    factory: SourceFactory,
    clock: Callable[[], datetime],
) -> int:
    catalog = _load_catalog(args.catalog)
    sync_catalog(session, catalog, PROFILES)
    session.commit()
    now = clock()
    for job in jobs.recover_stale_jobs(session, now):
        print(f"! Closed abandoned job {job.id} ({job.status}).")
    session.commit()

    listed = [spec.id for spec in catalog.datasets]
    dataset = session.get(Dataset, args.dataset)
    if dataset is None or dataset.kind is not DatasetKind.PROVIDER or dataset.id not in listed:
        names = ", ".join(listed)
        raise UsageError(f"Unknown dataset '{args.dataset}'. Datasets in the catalogue: {names}.")
    in_dataset = [spec.id for spec in catalog.series if spec.dataset_id == dataset.id]
    wanted = args.series or in_dataset
    unknown = [series_id for series_id in wanted if series_id not in in_dataset]
    if unknown:
        raise UsageError(f"Not series of {dataset.id}: {', '.join(unknown)}.")
    series = [session.get_one(EconomicSeries, series_id) for series_id in dict.fromkeys(wanted)]

    running = jobs.active_job(session, dataset.id, now)
    if running is not None:
        raise UsageError(
            f"Job {running.id} for {dataset.id} is still running (last activity "
            f"{running.heartbeat_at or running.created_at:%Y-%m-%d %H:%M} UTC). Wait for it "
            "to finish; a job with no activity for 2 hours is closed automatically."
        )
    if dataset.provider_id is None:  # pragma: no cover - guaranteed by a CHECK constraint
        raise UsageError(f"{dataset.id} has no provider.")
    source = factory(dataset.provider_id, settings)
    if source is None:
        raise UsageError(f"Provider '{dataset.provider_id}' cannot fetch economic series.")

    today = now.date()
    starts, ends = _periods(series, catalog, args.start, args.end, today)
    client = getattr(source, "client", None)
    print(f"Fetching {len(series)} series from {source.profile.name} …")
    job = run_economic_ingestion(
        session,
        source,
        dataset=dataset,
        series=series,
        start=starts,
        end=ends,
        parameters={
            "catalogue_version": catalog.version,
            "series": [entry.id for entry in series],
            "start": args.start,
            "end": args.end,
        },
        today=today,
        keep_bodies=settings.store_source_bodies,
        http=client if isinstance(client, HttpClient) else None,
        clock=clock,
    )
    print_job(session, job, issues=10)
    return EXIT_BY_STATUS.get(job.status, EXIT_FAILED)


def cmd_import_prices(
    session: Session,
    args: argparse.Namespace,
    settings: Settings,
    clock: Callable[[], datetime],
) -> int:
    try:
        manifest = read_manifest(args.manifest)
    except ManifestError as error:
        problems = "".join(f"\n  - {problem}" for problem in error.problems)
        raise UsageError(f"{error}{problems}") from error
    if not args.file.is_file():
        raise UsageError(f"{args.file} is not a file.")
    for job in jobs.recover_stale_jobs(session, clock()):
        print(f"! Closed abandoned job {job.id} ({job.status}).")
    session.commit()
    try:
        result = import_price_file(
            session,
            build_price_file(settings),
            manifest=manifest,
            file_path=args.file,
            profiles=PROFILES,
            today=clock().date(),
            keep_bodies=settings.store_source_bodies,
            clock=clock,
        )
    except ManifestError as error:
        session.rollback()
        raise UsageError(str(error)) from error
    for note in result.notes:
        print(f"! {note}")
    print_job(session, result.job, issues=10)
    return EXIT_BY_STATUS.get(result.job.status, EXIT_FAILED)


def cmd_jobs(session: Session, args: argparse.Namespace) -> int:
    rows = session.scalars(
        select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(args.limit)
    ).all()
    if not rows:
        print("No ingestion jobs yet.")
        return EXIT_OK
    print(f"{'created (UTC)':<17} {'status':<24} {'dataset':<24} {'targets ok/all':>14}  id")
    for job in rows:
        print(
            f"{job.created_at:%Y-%m-%d %H:%M}  {job.status:<24} {job.dataset_id:<24} "
            f"{f'{job.items_succeeded}/{job.items_total}':>14}  {job.id}"
        )
    return EXIT_OK


def cmd_job(session: Session, args: argparse.Namespace) -> int:
    try:
        job_id = uuid.UUID(args.job_id)
    except ValueError as error:
        raise UsageError(f"'{args.job_id}' is not a job id.") from error
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise UsageError(f"No job {job_id}.")
    print_job(session, job, issues=50)
    return EXIT_OK


# --- Entry point --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion", description="RUMIN data ingestion."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    catalog = commands.add_parser("catalog", help="Validate the series catalogue and sync it.")
    catalog.add_argument("--file", type=Path, default=DEFAULT_CATALOG_PATH)
    catalog.add_argument("--check", action="store_true", help="Validate only; no database.")

    run = commands.add_parser("run", help="Fetch a provider dataset's series.")
    run.add_argument("dataset", help="Dataset id from the catalogue, e.g. worldbank-wdi.")
    run.add_argument("--series", nargs="+", metavar="ID", help="Only these series.")
    run.add_argument("--start", help="First period, e.g. 2000 (default: the catalogue's).")
    run.add_argument("--end", help="Last period (default: the current period).")
    run.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH, help=argparse.SUPPRESS)

    prices = commands.add_parser("import-prices", help="Import a licensed price file.")
    prices.add_argument("--manifest", type=Path, required=True)
    prices.add_argument("--file", type=Path, required=True)

    commands.add_parser("manifest-template", help="Print a blank price-file manifest.")

    jobs_parser = commands.add_parser("jobs", help="List recent ingestion jobs.")
    jobs_parser.add_argument("--limit", type=int, default=20, choices=range(1, 201), metavar="N")

    job = commands.add_parser("job", help="Show one ingestion job.")
    job.add_argument("job_id")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    economic_sources: SourceFactory = build_economic_source,
    clock: Callable[[], datetime] = utcnow,
) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "manifest-template":
        print(manifest_template())
        return EXIT_OK
    if args.command == "catalog" and args.check:
        try:
            _load_catalog(args.file)
        except UsageError as error:
            _err(f"✗ {error}")
            return EXIT_NOT_STARTED
        print(f"✓ {args.file.name} is valid")
        return EXIT_OK

    settings = settings or get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if args.command == "catalog":
                return cmd_catalog(session, args)
            if args.command == "run":
                return cmd_run(session, args, settings, economic_sources, clock)
            if args.command == "import-prices":
                return cmd_import_prices(session, args, settings, clock)
            if args.command == "jobs":
                return cmd_jobs(session, args)
            return cmd_job(session, args)
    except UsageError as error:
        _err(f"✗ {error}")
        return EXIT_NOT_STARTED
    except (OperationalError, ProgrammingError) as error:
        _err(f"✗ Database error: {error.orig}")
        _err("  If the database schema has not been created yet, run: make migrate")
        return EXIT_NOT_STARTED
    finally:
        engine.dispose()
