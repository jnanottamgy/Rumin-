"""The economic-series pipeline: fetch → capture → check → store → record, per series.

Each series is processed in its own database transaction, so a failure part-way through
never leaves half a series behind, and series that succeeded stay stored when a later one
fails. Every outcome — success, failure, skip, cancellation — is written to the job.

Failures are handled by kind:

* A **provider error** for one series (unknown indicator, malformed response) fails that
  series and the run continues.
* **Temporary provider errors** (unavailable, timeout, rate limited) that persist after
  the HTTP client's retries count towards a circuit breaker: after
  ``CIRCUIT_BREAKER_THRESHOLD`` in a row the provider is treated as down and the remaining
  series are skipped (with the reason) instead of hammering it.
* An **unexpected error** fails the series with a generic message (details go to the log,
  never to the database) and the run continues.
* **Ctrl+C** stops the run: the current series is rolled back and the job is recorded as
  ``cancelled``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.domain.enums import IssueSeverity, JobItemStatus, JobTargetKind
from app.ingestion import jobs
from app.ingestion.errors import ProviderError
from app.ingestion.http import HttpClient
from app.ingestion.jobs import ItemCounts
from app.ingestion.logs import log_event
from app.ingestion.persistence import (
    record_issues,
    refresh_series_summary,
    save_observations,
    store_captures,
)
from app.ingestion.providers.base import EconomicSeriesSource, SeriesFetch, SeriesRequest
from app.ingestion.quality import Finding, SeriesExpectation, assess_observations
from app.models import Dataset, EconomicSeries, IngestionJob, IngestionJobItem

logger = logging.getLogger(__name__)

CIRCUIT_BREAKER_THRESHOLD = 3


def _severity_counts(findings: Sequence[Finding]) -> tuple[int, int]:
    warnings = sum(f.severity is IssueSeverity.WARNING for f in findings)
    errors = sum(f.severity is IssueSeverity.ERROR for f in findings)
    return warnings, errors


def _store_series(
    session: Session,
    *,
    job: IngestionJob,
    series: EconomicSeries,
    fetch: SeriesFetch,
    today: date,
    now: datetime,
    keep_bodies: bool,
) -> ItemCounts:
    """Everything for one fetched series, inside the caller's transaction."""
    captures = store_captures(
        session,
        job_id=job.id,
        provider_id=job.provider_id,
        captures=fetch.captures,
        keep_bodies=keep_bodies,
    )
    expectation = SeriesExpectation(
        provider_code=series.provider_code,
        country_iso3=series.country_iso3,
        frequency=series.frequency,
        measure_type=series.measure_type,
        unit=series.unit,
        plausible_min=series.plausible_min,
        plausible_max=series.plausible_max,
    )
    assessment = assess_observations(expectation, fetch.observations, today)
    written, rows = save_observations(
        session,
        job_id=job.id,
        series=series,
        accepted=assessment.accepted,
        captures=captures,
        now=now,
    )

    findings: list[Finding] = [*assessment.rejected, *assessment.series_findings]
    record_issues(session, findings, job_id=job.id, now=now, series_id=series.id)
    for checked in assessment.accepted:
        if checked.findings:
            record_issues(
                session,
                checked.findings,
                job_id=job.id,
                now=now,
                series_id=series.id,
                observation_id=rows[checked.period.start].id,
            )
            findings.extend(checked.findings)

    if fetch.metadata is not None:
        # The provider's own definition and original source replace the catalogue text.
        if fetch.metadata.description:
            series.description = fetch.metadata.description
        if fetch.metadata.source_organization:
            series.source_organization = fetch.metadata.source_organization
    refresh_series_summary(session, series)

    warnings, errors = _severity_counts(findings)
    return ItemCounts(
        received=len(fetch.observations),
        new=written.new,
        revised=written.revised,
        unchanged=written.unchanged,
        missing=sum(o.value is None for o in assessment.accepted),
        rejected=len(assessment.rejected),
        warnings=warnings,
        errors=errors,
    )


def _record_series_outcome(
    series: EconomicSeries, job: IngestionJob, item: IngestionJobItem, now: datetime
) -> None:
    series.last_ingestion_job_id = job.id
    series.last_ingestion_status = item.status
    series.last_ingestion_at = now
    if item.status is JobItemStatus.SUCCEEDED:
        series.last_successful_ingestion_at = now


def run_economic_ingestion(
    session: Session,
    source: EconomicSeriesSource,
    *,
    dataset: Dataset,
    series: Sequence[EconomicSeries],
    start: Mapping[str, str],
    end: Mapping[str, str],
    parameters: dict[str, Any],
    today: date,
    keep_bodies: bool = True,
    http: HttpClient | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> IngestionJob:
    """Ingest ``series`` (all from ``dataset``) and return the finished job.

    ``start`` and ``end`` give each series' period range in the provider's notation.
    Commits as it goes: the job and its items are visible (``running``) while it runs.
    """
    job = jobs.create_job(
        session,
        provider_id=source.profile.id,
        dataset_id=dataset.id,
        parameters=parameters,
        now=clock(),
    )
    items = [
        jobs.add_item(
            session,
            job,
            target_kind=JobTargetKind.ECONOMIC_SERIES,
            label=f"{entry.id} ({entry.provider_series_key})",
            series_id=entry.id,
        )
        for entry in series
    ]
    jobs.start_job(job, clock())
    session.commit()
    log_event(logger, "ingestion.started", job=job.id, dataset=dataset.id, series=len(series))

    def progress() -> None:
        """Keep the job's counters current, so a running job shows how far it got."""
        jobs.refresh_totals(job, items, clock())
        if http is not None:
            job.request_count = http.request_count
            job.bytes_received = http.bytes_received

    last_updated: date | None = None
    consecutive_outages = 0
    cancelled = False
    note: str | None = None
    try:
        for entry, item in zip(series, items, strict=True):
            if consecutive_outages >= CIRCUIT_BREAKER_THRESHOLD:
                note = (
                    f"Stopped after {consecutive_outages} consecutive temporary provider "
                    "failures: the provider appears to be unavailable. Remaining series "
                    "were skipped; run again later."
                )
                jobs.skip_items(items, "circuit_open", note, clock())
                session.commit()
                break

            jobs.start_item(item, clock())
            session.commit()  # visible progress; survives a rollback of this series
            request = SeriesRequest(
                provider_code=entry.provider_code,
                country_iso3=entry.country_iso3,
                frequency=entry.frequency,
                start=start[entry.id],
                end=end[entry.id],
            )
            fetch: SeriesFetch | None = None
            try:
                fetch = source.fetch_series(request)
            except ProviderError as error:
                consecutive_outages = consecutive_outages + 1 if error.retryable else 0
                jobs.fail_item(item, error.code, error.message, clock())
            except Exception:
                logger.exception("event=ingestion.fetch_failed job=%s series=%s", job.id, entry.id)
                consecutive_outages = 0
                jobs.fail_item(
                    item,
                    "internal_error",
                    "An unexpected error occurred while fetching this series. See the server "
                    "log for details.",
                    clock(),
                )
            if fetch is None:
                _record_series_outcome(entry, job, item, clock())
                progress()
                session.commit()
                log_event(
                    logger,
                    "ingestion.series_failed",
                    level=logging.WARNING,
                    job=job.id,
                    series=entry.id,
                    error=item.error_code,
                )
                continue
            consecutive_outages = 0
            reported = fetch.provider_last_updated
            if reported is not None and (last_updated is None or reported > last_updated):
                last_updated = reported

            try:
                counts = _store_series(
                    session,
                    job=job,
                    series=entry,
                    fetch=fetch,
                    today=today,
                    now=clock(),
                    keep_bodies=keep_bodies,
                )
            except Exception:
                logger.exception("event=ingestion.store_failed job=%s series=%s", job.id, entry.id)
                session.rollback()
                jobs.fail_item(
                    item,
                    "storage_error",
                    "The data was received but could not be stored; nothing from this "
                    "series was saved. See the server log for details.",
                    clock(),
                )
            else:
                if counts.received and counts.rejected == counts.received:
                    jobs.fail_item(
                        item,
                        "all_records_rejected",
                        f"All {counts.received} records failed validation; see the quality "
                        "issues for the reasons.",
                        clock(),
                        counts,
                    )
                else:
                    jobs.succeed_item(item, counts, clock())
            _record_series_outcome(entry, job, item, clock())
            progress()
            session.commit()
            log_event(
                logger,
                "ingestion.series_done",
                job=job.id,
                series=entry.id,
                status=item.status,
                received=item.records_received,
                new=item.records_new,
                revised=item.records_revised,
                rejected=item.records_rejected,
            )
    except KeyboardInterrupt:
        session.rollback()
        cancelled = True
        jobs.cancel_items(items, clock())

    if last_updated is not None:
        dataset.provider_last_updated = last_updated
    progress()
    jobs.finish_job(job, items, clock(), cancelled=cancelled, note=note)
    session.commit()
    log_event(
        logger,
        "ingestion.finished",
        level=logging.INFO if job.status.startswith("completed") else logging.WARNING,
        job=job.id,
        status=job.status,
        succeeded=job.items_succeeded,
        failed=job.items_failed,
        skipped=job.items_skipped,
    )
    return job
