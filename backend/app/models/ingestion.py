"""Ingestion bookkeeping: jobs, their targets, captured source bytes and quality issues.

Together these answer "where did this number come from, and what happened when it was
fetched?" for every stored observation and price bar.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_column, utcnow
from app.db.types import UTCDateTime
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


class IngestionJob(Base):
    """One run of the pipeline for one provider dataset.

    Counters are totals over the job's items. ``status`` is set from what actually
    happened (see ``JobStatus``), never optimistically.
    """

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("data_providers.id", ondelete="RESTRICT"), index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )
    trigger: Mapped[JobTrigger] = mapped_column(enum_column(JobTrigger, "job_trigger"))
    # What was asked for (targets, period range, file name). Never contains secrets.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[JobStatus] = mapped_column(enum_column(JobStatus, "job_status"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Updated as the job progresses, so an abandoned run can be recognised later.
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    items_total: Mapped[int] = mapped_column(Integer, default=0)
    items_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, default=0)
    items_skipped: Mapped[int] = mapped_column(Integer, default=0)
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    records_new: Mapped[int] = mapped_column(Integer, default=0)
    records_revised: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    records_missing: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    bytes_received: Mapped[int] = mapped_column(BigInteger, default=0)
    # A short, safe explanation of failures (no secrets, no stack traces).
    error_summary: Mapped[str | None] = mapped_column(Text)


class IngestionJobItem(Base):
    """One target of a job — an economic series or an instrument — and its outcome."""

    __tablename__ = "ingestion_job_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), index=True
    )
    target_kind: Mapped[JobTargetKind] = mapped_column(
        enum_column(JobTargetKind, "job_target_kind")
    )
    series_id: Mapped[str | None] = mapped_column(
        String(96), ForeignKey("economic_series.id", ondelete="SET NULL"), index=True
    )
    instrument_id: Mapped[str | None] = mapped_column(
        String(96), ForeignKey("instruments.id", ondelete="SET NULL"), index=True
    )
    # Human-readable name of the target, kept even if the target is later removed.
    target_label: Mapped[str] = mapped_column(String(300))
    status: Mapped[JobItemStatus] = mapped_column(enum_column(JobItemStatus, "job_item_status"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    records_new: Mapped[int] = mapped_column(Integer, default=0)
    records_revised: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    records_missing: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


class SourceCapture(Base):
    """The exact bytes RUMIN received — an HTTP response or an imported file.

    Kept so every stored value can be traced to the response it came from and so data can
    be re-processed without asking the provider again. ``locator`` and ``request_params``
    are sanitised: credentials are removed before anything is stored.
    """

    __tablename__ = "source_captures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), index=True
    )
    provider_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("data_providers.id", ondelete="RESTRICT")
    )
    kind: Mapped[CaptureKind] = mapped_column(enum_column(CaptureKind, "capture_kind"))
    locator: Mapped[str] = mapped_column(String(1000))
    request_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    http_status: Mapped[int | None]
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # gzip-compressed body. May be pruned to save space; the hash and metadata remain.
    body_gzip: Mapped[bytes | None] = mapped_column(LargeBinary)
    provider_last_updated: Mapped[date | None]


class DataQualityIssue(Base):
    """A record that was rejected, or a stored record that was flagged or noted.

    ``raw_record`` holds what the source sent (for rejected records, the only copy RUMIN
    keeps), so nothing is lost silently and every decision can be reviewed.
    """

    __tablename__ = "data_quality_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), index=True
    )
    series_id: Mapped[str | None] = mapped_column(
        String(96), ForeignKey("economic_series.id", ondelete="SET NULL"), index=True
    )
    instrument_id: Mapped[str | None] = mapped_column(
        String(96), ForeignKey("instruments.id", ondelete="SET NULL"), index=True
    )
    observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("economic_observations.id", ondelete="SET NULL")
    )
    price_bar_id: Mapped[int | None] = mapped_column(
        ForeignKey("price_bars.id", ondelete="SET NULL")
    )
    rule: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[IssueSeverity] = mapped_column(enum_column(IssueSeverity, "issue_severity"))
    outcome: Mapped[IssueOutcome] = mapped_column(enum_column(IssueOutcome, "issue_outcome"))
    message: Mapped[str] = mapped_column(Text)
    # The period or trade date the issue is about, when there is one ("2023", "2024-03-28").
    record_key: Mapped[str | None] = mapped_column(String(32))
    raw_record: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus, "review_status"), default=ReviewStatus.UNREVIEWED
    )
