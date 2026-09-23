"""Response schemas for ingestion jobs, stored source captures and data-quality issues."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from app.domain.enums import (
    CaptureKind,
    IssueOutcome,
    IssueSeverity,
    JobItemStatus,
    JobStatus,
    JobTargetKind,
    JobTrigger,
    ReviewStatus,
)
from app.schemas.common import ApiModel, Page


class JobRead(ApiModel):
    id: uuid.UUID
    provider_id: str
    dataset_id: str
    trigger: JobTrigger
    parameters: dict[str, Any] = Field(description="What was requested. Never holds secrets.")
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    items_total: int
    items_succeeded: int
    items_failed: int
    items_skipped: int
    records_received: int
    records_new: int
    records_revised: int
    records_unchanged: int
    records_missing: int = Field(description="Accepted records without a value (a subset).")
    records_rejected: int
    warning_count: int
    error_count: int
    request_count: int
    bytes_received: int
    error_summary: str | None


class JobPage(Page[JobRead]):
    """A page of ingestion jobs, newest first."""


class JobItemRead(ApiModel):
    id: int
    target_kind: JobTargetKind
    series_id: str | None
    instrument_id: str | None
    target_label: str
    status: JobItemStatus
    started_at: datetime | None
    finished_at: datetime | None
    records_received: int
    records_new: int
    records_revised: int
    records_unchanged: int
    records_missing: int
    records_rejected: int
    warning_count: int
    error_count: int
    error_code: str | None
    error_message: str | None


class IssueCount(ApiModel):
    rule: str
    severity: IssueSeverity
    outcome: IssueOutcome
    count: int


class CaptureRead(ApiModel):
    """Metadata of bytes RUMIN received. The body itself is not served by the API."""

    id: int
    job_id: uuid.UUID
    provider_id: str
    kind: CaptureKind
    locator: str = Field(description="Sanitised URL, or the imported file's name.")
    request_params: dict[str, Any] | None
    http_status: int | None
    received_at: datetime
    content_type: str | None
    size_bytes: int
    sha256: str
    body_stored: bool
    provider_last_updated: date | None


class JobDetail(JobRead):
    items: list[JobItemRead]
    issue_counts: list[IssueCount]
    captures: list[CaptureRead]


class IssueRead(ApiModel):
    id: int
    job_id: uuid.UUID
    series_id: str | None
    instrument_id: str | None
    observation_id: int | None
    price_bar_id: int | None
    rule: str
    severity: IssueSeverity
    outcome: IssueOutcome = Field(
        description="rejected: not stored as data (the raw record is kept here); flagged: "
        "stored with quality status 'warning'; noted: informational."
    )
    message: str
    record_key: str | None = Field(description="The period or trade date concerned.")
    raw_record: dict[str, Any] | None = Field(description="What the source sent.")
    detected_at: datetime
    review_status: ReviewStatus


class IssuePage(Page[IssueRead]):
    """A page of data-quality issues, newest first."""


class RuleRead(ApiModel):
    code: str
    applies_to: Literal["economic", "price", "both"]
    severity: IssueSeverity
    outcome: IssueOutcome
    description: str
