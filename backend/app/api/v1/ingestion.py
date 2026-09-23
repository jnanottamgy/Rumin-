"""Ingestion history and data quality — read-only.

Jobs are started from the command line (``python -m app.ingestion``), never over HTTP:
RUMIN has no authentication yet, and an open endpoint would let anyone make the server
send requests to providers.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import NOT_FOUND, PaginationDep, SessionDep
from app.api.v1.data import DATASET_ID, INSTRUMENT_ID, PROVIDER_ID, SERIES_ID
from app.domain.enums import IssueOutcome, IssueSeverity, JobStatus
from app.schemas.ingestion import CaptureRead, IssuePage, JobDetail, JobPage, RuleRead
from app.services import ingestion_history

router = APIRouter()


@router.get(
    "/ingestion-jobs",
    response_model=JobPage,
    tags=["ingestion"],
    summary="List ingestion jobs",
    description="Every retrieval or import, newest first, with what it did. A job's status "
    "is derived from its targets: one that only partly succeeded is `partially_failed`.",
)
def list_jobs(
    session: SessionDep,
    page: PaginationDep,
    status: Annotated[JobStatus | None, Query()] = None,
    dataset_id: Annotated[str | None, Query(pattern=DATASET_ID)] = None,
    provider_id: Annotated[str | None, Query(pattern=PROVIDER_ID)] = None,
) -> JobPage:
    return ingestion_history.list_jobs(
        session,
        status=status,
        dataset_id=dataset_id,
        provider_id=provider_id,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/ingestion-jobs/{job_id}",
    response_model=JobDetail,
    tags=["ingestion"],
    summary="Get an ingestion job",
    description="The job with each target's outcome, issue counts by rule, and the "
    "responses or files it stored.",
    responses=NOT_FOUND,
)
def get_job(session: SessionDep, job_id: Annotated[uuid.UUID, Path()]) -> JobDetail:
    return ingestion_history.get_job(session, job_id)


@router.get(
    "/source-captures/{capture_id}",
    response_model=CaptureRead,
    tags=["ingestion"],
    summary="Get a stored source capture",
    description="Metadata of a stored response or file: where it came from, when, its size "
    "and SHA-256. The stored bytes are not served by the API.",
    responses=NOT_FOUND,
)
def get_capture(
    session: SessionDep, capture_id: Annotated[int, Path(ge=1, le=2**62)]
) -> CaptureRead:
    return ingestion_history.get_capture(session, capture_id)


@router.get(
    "/data-quality/issues",
    response_model=IssuePage,
    tags=["data quality"],
    summary="List data-quality issues",
    description="Rejected records (with what the source sent), flagged values and notes, "
    "newest first. Issues are recorded per job.",
)
def list_issues(
    session: SessionDep,
    page: PaginationDep,
    job_id: Annotated[uuid.UUID | None, Query()] = None,
    series_id: Annotated[str | None, Query(pattern=SERIES_ID)] = None,
    instrument_id: Annotated[str | None, Query(pattern=INSTRUMENT_ID)] = None,
    rule: Annotated[str | None, Query(pattern=r"^[a-z_]{2,64}$")] = None,
    severity: Annotated[IssueSeverity | None, Query()] = None,
    outcome: Annotated[IssueOutcome | None, Query()] = None,
) -> IssuePage:
    return ingestion_history.list_issues(
        session,
        job_id=job_id,
        series_id=series_id,
        instrument_id=instrument_id,
        rule=rule,
        severity=severity,
        outcome=outcome,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/data-quality/rules",
    response_model=list[RuleRead],
    tags=["data quality"],
    summary="List data-quality rules",
    description="Every rule applied during ingestion, what it checks and what happens to a "
    "record that fails it.",
)
def list_rules() -> list[RuleRead]:
    return ingestion_history.list_rules()
