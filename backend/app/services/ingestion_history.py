"""Read access to what ingestion did: jobs, stored captures and data-quality issues."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domain.enums import IssueOutcome, IssueSeverity, JobStatus
from app.ingestion import jobs as job_tracking
from app.ingestion.quality import RULES
from app.models import DataQualityIssue, IngestionJob, SourceCapture
from app.schemas.ingestion import (
    CaptureRead,
    IssueCount,
    IssuePage,
    IssueRead,
    JobDetail,
    JobItemRead,
    JobPage,
    JobRead,
    RuleRead,
)
from app.services.common import paginate


def list_jobs(
    session: Session,
    *,
    status: JobStatus | None,
    dataset_id: str | None,
    provider_id: str | None,
    limit: int,
    offset: int,
) -> JobPage:
    statement = select(IngestionJob).order_by(
        IngestionJob.created_at.desc(), IngestionJob.id.desc()
    )
    if status is not None:
        statement = statement.where(IngestionJob.status == status)
    if dataset_id is not None:
        statement = statement.where(IngestionJob.dataset_id == dataset_id)
    if provider_id is not None:
        statement = statement.where(IngestionJob.provider_id == provider_id)
    rows, total = paginate(session, statement, limit, offset)
    items = [JobRead.model_validate(row) for row in rows]
    return JobPage(items=items, total=total, limit=limit, offset=offset)


def _capture_read(capture: SourceCapture) -> CaptureRead:
    return CaptureRead(
        id=capture.id,
        job_id=capture.job_id,
        provider_id=capture.provider_id,
        kind=capture.kind,
        locator=capture.locator,
        request_params=capture.request_params,
        http_status=capture.http_status,
        received_at=capture.received_at,
        content_type=capture.content_type,
        size_bytes=capture.size_bytes,
        sha256=capture.sha256,
        body_stored=capture.body_gzip is not None,
        provider_last_updated=capture.provider_last_updated,
    )


def get_job(session: Session, job_id: uuid.UUID) -> JobDetail:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise NotFoundError(f"No ingestion job with ID '{job_id}'.")
    counts = session.execute(
        select(
            DataQualityIssue.rule,
            DataQualityIssue.severity,
            DataQualityIssue.outcome,
            func.count(),
        )
        .where(DataQualityIssue.job_id == job.id)
        .group_by(DataQualityIssue.rule, DataQualityIssue.severity, DataQualityIssue.outcome)
        .order_by(func.count().desc(), DataQualityIssue.rule)
    ).tuples()
    # The body is deliberately not loaded: only its presence is reported.
    captures = session.scalars(
        select(SourceCapture).where(SourceCapture.job_id == job.id).order_by(SourceCapture.id)
    )
    return JobDetail.model_validate(
        {
            **JobRead.model_validate(job).model_dump(),
            "items": [
                JobItemRead.model_validate(item) for item in job_tracking.job_items(session, job)
            ],
            "issue_counts": [
                IssueCount(rule=rule, severity=severity, outcome=outcome, count=count)
                for rule, severity, outcome, count in counts
            ],
            "captures": [_capture_read(capture) for capture in captures],
        }
    )


def get_capture(session: Session, capture_id: int) -> CaptureRead:
    capture = session.get(SourceCapture, capture_id)
    if capture is None:
        raise NotFoundError(f"No source capture with ID {capture_id}.")
    return _capture_read(capture)


def list_issues(
    session: Session,
    *,
    job_id: uuid.UUID | None,
    series_id: str | None,
    instrument_id: str | None,
    rule: str | None,
    severity: IssueSeverity | None,
    outcome: IssueOutcome | None,
    limit: int,
    offset: int,
) -> IssuePage:
    statement = select(DataQualityIssue).order_by(
        DataQualityIssue.detected_at.desc(), DataQualityIssue.id.desc()
    )
    if job_id is not None:
        statement = statement.where(DataQualityIssue.job_id == job_id)
    if series_id is not None:
        statement = statement.where(DataQualityIssue.series_id == series_id)
    if instrument_id is not None:
        statement = statement.where(DataQualityIssue.instrument_id == instrument_id)
    if rule is not None:
        statement = statement.where(DataQualityIssue.rule == rule)
    if severity is not None:
        statement = statement.where(DataQualityIssue.severity == severity)
    if outcome is not None:
        statement = statement.where(DataQualityIssue.outcome == outcome)
    rows, total = paginate(session, statement, limit, offset)
    items = [IssueRead.model_validate(row) for row in rows]
    return IssuePage(items=items, total=total, limit=limit, offset=offset)


def list_rules() -> list[RuleRead]:
    return [RuleRead.model_validate(rule, from_attributes=True) for rule in RULES.values()]
