"""Ingestion jobs: every run is recorded, and its status is computed from what happened.

A job has one item per target (an economic series or an instrument). Each item ends as
``succeeded``, ``failed`` or ``skipped``; the job's status is then *derived* from its
items (see ``derive_status``) — it is never set optimistically, so a run in which some
series failed can never be reported as ``completed``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import JobItemStatus, JobStatus, JobTargetKind, JobTrigger
from app.models import IngestionJob, IngestionJobItem

# A running job whose heartbeat is older than this is treated as abandoned (the process
# was killed or the machine stopped). Generous, because one series may take minutes when
# a provider is slow and requests are retried.
STALE_AFTER = timedelta(hours=2)
FINISHED = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.COMPLETED_WITH_WARNINGS,
        JobStatus.PARTIALLY_FAILED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
)
_SUMMARY_LIMIT = 2000


@dataclass
class ItemCounts:
    """What happened to the records of one target.

    ``received`` = ``rejected`` + ``new`` + ``revised`` + ``unchanged``; ``missing`` counts
    the accepted records that had no value (a subset, not a separate group).
    """

    received: int = 0
    new: int = 0
    revised: int = 0
    unchanged: int = 0
    missing: int = 0
    rejected: int = 0
    warnings: int = 0  # warning-severity quality issues
    errors: int = 0  # error-severity quality issues (rejected records)


def create_job(
    session: Session,
    *,
    provider_id: str,
    dataset_id: str,
    parameters: dict[str, Any],
    now: datetime,
    trigger: JobTrigger = JobTrigger.CLI,
) -> IngestionJob:
    job = IngestionJob(
        id=uuid.uuid4(),
        provider_id=provider_id,
        dataset_id=dataset_id,
        trigger=trigger,
        parameters=parameters,
        status=JobStatus.PENDING,
        created_at=now,
    )
    session.add(job)
    session.flush()
    return job


def add_item(
    session: Session,
    job: IngestionJob,
    *,
    target_kind: JobTargetKind,
    label: str,
    series_id: str | None = None,
    instrument_id: str | None = None,
) -> IngestionJobItem:
    item = IngestionJobItem(
        job_id=job.id,
        target_kind=target_kind,
        series_id=series_id,
        instrument_id=instrument_id,
        target_label=label[:300],
        status=JobItemStatus.PENDING,
    )
    session.add(item)
    session.flush()
    return item


def start_job(job: IngestionJob, now: datetime) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = now
    job.heartbeat_at = now


def start_item(item: IngestionJobItem, now: datetime) -> None:
    item.started_at = now


def succeed_item(item: IngestionJobItem, counts: ItemCounts, now: datetime) -> None:
    _set_counts(item, counts)
    item.status = JobItemStatus.SUCCEEDED
    item.finished_at = now


def fail_item(
    item: IngestionJobItem,
    code: str,
    message: str,
    now: datetime,
    counts: ItemCounts | None = None,
) -> None:
    if counts is not None:
        _set_counts(item, counts)
    item.status = JobItemStatus.FAILED
    item.error_code = code[:64]
    item.error_message = message[:_SUMMARY_LIMIT]
    item.finished_at = now


def skip_items(
    items: Sequence[IngestionJobItem], code: str, message: str, now: datetime
) -> list[IngestionJobItem]:
    """Mark every still-pending item as skipped (not attempted), with the reason."""
    skipped = [item for item in items if item.status is JobItemStatus.PENDING]
    for item in skipped:
        item.status = JobItemStatus.SKIPPED
        item.error_code = code[:64]
        item.error_message = message[:_SUMMARY_LIMIT]
        item.finished_at = now
    return skipped


def cancel_items(items: Sequence[IngestionJobItem], now: datetime) -> None:
    """After Ctrl+C: the target in progress was rolled back; later ones never started."""
    for item in items:
        if item.status is JobItemStatus.PENDING and item.started_at is not None:
            skip_items(
                [item],
                "cancelled",
                "The run was cancelled while this target was being processed; nothing from "
                "it was stored.",
                now,
            )
    skip_items(items, "cancelled", "The run was cancelled before this target.", now)


def _set_counts(item: IngestionJobItem, counts: ItemCounts) -> None:
    item.records_received = counts.received
    item.records_new = counts.new
    item.records_revised = counts.revised
    item.records_unchanged = counts.unchanged
    item.records_missing = counts.missing
    item.records_rejected = counts.rejected
    item.warning_count = counts.warnings
    item.error_count = counts.errors


def refresh_totals(job: IngestionJob, items: Sequence[IngestionJobItem], now: datetime) -> None:
    """Job counters are the sum of its items' counters (kept current while running)."""
    job.items_total = len(items)
    job.items_succeeded = sum(item.status is JobItemStatus.SUCCEEDED for item in items)
    job.items_failed = sum(item.status is JobItemStatus.FAILED for item in items)
    job.items_skipped = sum(item.status is JobItemStatus.SKIPPED for item in items)
    job.records_received = sum(item.records_received for item in items)
    job.records_new = sum(item.records_new for item in items)
    job.records_revised = sum(item.records_revised for item in items)
    job.records_unchanged = sum(item.records_unchanged for item in items)
    job.records_missing = sum(item.records_missing for item in items)
    job.records_rejected = sum(item.records_rejected for item in items)
    job.warning_count = sum(item.warning_count for item in items)
    job.error_count = sum(item.error_count for item in items)
    job.heartbeat_at = now


def derive_status(
    items: Sequence[IngestionJobItem], *, cancelled: bool = False
) -> tuple[JobStatus, str | None]:
    """The job's status from its items, with a short explanation when it is not clean.

    * ``cancelled`` — the run was stopped by the user.
    * ``failed`` — no target succeeded (including a job with no targets at all).
    * ``partially_failed`` — some targets succeeded, others failed or were skipped.
    * ``completed_with_warnings`` — every target succeeded, but records were rejected or
      flagged, or a target raised a warning (e.g. an empty response).
    * ``completed`` — every target succeeded with nothing to report.
    """
    total = len(items)
    succeeded = sum(item.status is JobItemStatus.SUCCEEDED for item in items)
    failed = [item for item in items if item.status is JobItemStatus.FAILED]
    not_done = [
        item for item in items if item.status in (JobItemStatus.SKIPPED, JobItemStatus.PENDING)
    ]
    problems = "; ".join(
        f"{item.target_label}: {item.error_code} ({(item.error_message or '').rstrip('.')})"
        for item in failed
    )
    failures = f" Failures: {problems}." if problems else ""
    if cancelled:
        return JobStatus.CANCELLED, _clip(
            f"Cancelled by the user after {succeeded} of {total} target(s) succeeded." + failures
        )
    if total == 0:
        return JobStatus.FAILED, "The job had no targets to process."
    if succeeded == 0:
        return JobStatus.FAILED, _clip(
            f"No target succeeded ({len(failed)} failed, {len(not_done)} not attempted)." + failures
        )
    if failed or not_done:
        return JobStatus.PARTIALLY_FAILED, _clip(
            f"{succeeded} of {total} target(s) succeeded; {len(failed)} failed and "
            f"{len(not_done)} were not attempted." + failures
        )
    if any(item.warning_count or item.error_count for item in items):
        return JobStatus.COMPLETED_WITH_WARNINGS, None
    return JobStatus.COMPLETED, None


def finish_job(
    job: IngestionJob,
    items: Sequence[IngestionJobItem],
    now: datetime,
    *,
    cancelled: bool = False,
    note: str | None = None,
) -> None:
    refresh_totals(job, items, now)
    status, summary = derive_status(items, cancelled=cancelled)
    job.status = status
    job.error_summary = _clip(" ".join(part for part in (note, summary) if part)) or None
    job.finished_at = now


def _clip(text: str) -> str:
    return text if len(text) <= _SUMMARY_LIMIT else text[: _SUMMARY_LIMIT - 1] + "…"


def job_items(session: Session, job: IngestionJob) -> list[IngestionJobItem]:
    return list(
        session.scalars(
            select(IngestionJobItem)
            .where(IngestionJobItem.job_id == job.id)
            .order_by(IngestionJobItem.id)
        )
    )


def recover_stale_jobs(
    session: Session, now: datetime, stale_after: timedelta = STALE_AFTER
) -> list[IngestionJob]:
    """Close jobs left ``pending`` or ``running`` by a process that stopped unexpectedly.

    Items that had started are marked failed (their work was rolled back); items that had
    not started are marked skipped. The job's status is then derived as usual, so a run
    that stored some series before dying is ``partially_failed``, not ``completed``.
    """
    cutoff = now - stale_after
    recovered: list[IngestionJob] = []
    candidates = session.scalars(
        select(IngestionJob).where(IngestionJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))
    ).all()
    for job in candidates:
        last_sign_of_life = job.heartbeat_at or job.started_at or job.created_at
        if last_sign_of_life > cutoff:
            continue
        items = job_items(session, job)
        for item in items:
            if item.status is JobItemStatus.PENDING and item.started_at is not None:
                fail_item(
                    item,
                    "interrupted",
                    "The process stopped while this target was being processed; nothing "
                    "from it was stored.",
                    now,
                )
        skip_items(items, "interrupted", "The process stopped before this target.", now)
        finish_job(
            job,
            items,
            now,
            note=(
                f"Abandoned: no sign of activity since {last_sign_of_life.isoformat()} "
                "(the process was stopped or crashed)."
            ),
        )
        recovered.append(job)
    session.flush()
    return recovered


def active_job(
    session: Session, dataset_id: str, now: datetime, stale_after: timedelta = STALE_AFTER
) -> IngestionJob | None:
    """A job for the dataset that is still running (recent heartbeat), if any."""
    cutoff = now - stale_after
    for job in session.scalars(
        select(IngestionJob).where(
            IngestionJob.dataset_id == dataset_id,
            IngestionJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
    ).all():
        if (job.heartbeat_at or job.started_at or job.created_at) > cutoff:
            return job
    return None
