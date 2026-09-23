"""The economic-series pipeline end to end, on the real database (SQLite or PostgreSQL).

Provider responses are SYNTHETIC (see ``tests/fakes.py``): World Bank structure, made-up
numbers. The HTTP transport is scripted, so no test touches the network.
"""

from __future__ import annotations

import gzip
import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import (
    IssueOutcome,
    JobItemStatus,
    JobStatus,
    JobTargetKind,
    ObservationStatus,
    QualityStatus,
)
from app.ingestion import economic, jobs
from app.ingestion.catalog import Catalog, sync_catalog
from app.ingestion.economic import run_economic_ingestion
from app.ingestion.http import HttpResponse, TransportError
from app.ingestion.providers.base import SeriesFetch, SeriesRequest
from app.ingestion.providers.worldbank import WorldBankProvider
from app.ingestion.registry import PROFILES
from app.models import (
    DataQualityIssue,
    Dataset,
    EconomicObservation,
    EconomicSeries,
    IngestionJob,
    IngestionJobItem,
    SourceCapture,
)
from tests.fakes import (
    ScriptedTransport,
    Sleeps,
    Step,
    make_client,
    response,
    wb_error,
    wb_indicator,
    wb_page,
    wb_record,
)

TODAY = date(2026, 9, 23)
START = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


class Clock:
    """Advances one second per call, so timestamps are ordered and deterministic."""

    def __init__(self, start: datetime = START) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _series_spec(series_id: str, code: str = "FP.CPI.TOTL.ZG", iso3: str = "IND") -> dict[str, Any]:
    return {
        "id": series_id,
        "dataset_id": "test-wdi",
        "provider_code": code,
        "country_iso3": iso3,
        "name": f"Synthetic series {series_id}",
        "description": "Catalogue description (replaced by the provider's definition).",
        "measure_type": "change",
        "unit": "% change on previous year",
        "frequency": "annual",
        "aggregation": "Synthetic",
        "price_basis": "not_applicable",
        "seasonal_adjustment": "not_applicable",
        "plausible_min": "-50",
        "plausible_max": "200",
        "start": "2019",
    }


def synthetic_catalog(*series_ids: str) -> Catalog:
    codes = ["FP.CPI.TOTL.ZG", "NY.GDP.MKTP.KD.ZG", "FR.INR.LEND", "NE.EXP.GNFS.ZS"]
    return Catalog.model_validate(
        {
            "version": "0.0.1",
            "datasets": [
                {
                    "id": "test-wdi",
                    "provider_id": "worldbank",
                    "provider_dataset_code": "2",
                    "name": "Synthetic test dataset",
                    "description": "Synthetic data for tests.",
                    "license": "CC BY 4.0",
                    "attribution": "Synthetic attribution",
                    "update_frequency": "Never (synthetic)",
                    "provenance_note": "Synthetic test data; not World Bank data.",
                }
            ],
            "series": [
                _series_spec(series_id, code=codes[index % len(codes)])
                for index, series_id in enumerate(series_ids)
            ],
        }
    )


SERIES = ("s-cpi", "s-gdp", "s-lend", "s-exp")


def page(
    *values: tuple[str, str | None], code: str = "FP.CPI.TOTL.ZG", **kwargs: Any
) -> HttpResponse:
    return response(wb_page([wb_record(p, v, code=code) for p, v in values], **kwargs))


def metadata(code: str = "FP.CPI.TOTL.ZG") -> HttpResponse:
    return response(wb_indicator(code))


def run(
    session: Session,
    steps: list[Step],
    series_ids: Sequence[str] = ("s-cpi",),
    *,
    source: Any = None,
    **policy: Any,
) -> tuple[IngestionJob, ScriptedTransport, Sleeps]:
    sync_catalog(session, synthetic_catalog(*SERIES), PROFILES)
    session.commit()
    transport = ScriptedTransport(steps)
    client, sleeps = make_client(transport, **policy)
    clock = Clock()
    source = source or WorldBankProvider(client, clock=clock)
    series = [session.get_one(EconomicSeries, series_id) for series_id in series_ids]
    job = run_economic_ingestion(
        session,
        source,
        dataset=session.get_one(Dataset, "test-wdi"),
        series=series,
        start={series_id: "2019" for series_id in series_ids},
        end={series_id: "2025" for series_id in series_ids},
        parameters={"test": True},
        today=TODAY,
        http=client,
        clock=clock,
    )
    return job, transport, sleeps


def current(session: Session, series_id: str = "s-cpi") -> dict[str, EconomicObservation]:
    rows = session.scalars(
        select(EconomicObservation).where(
            EconomicObservation.series_id == series_id,
            EconomicObservation.superseded_at.is_(None),
        )
    )
    return {row.period_label: row for row in rows}


def items(session: Session, job: IngestionJob) -> list[IngestionJobItem]:
    return jobs.job_items(session, job)


def issues(session: Session, job: IngestionJob) -> list[DataQualityIssue]:
    return list(session.scalars(select(DataQualityIssue).where(DataQualityIssue.job_id == job.id)))


# --- A clean first run -----------------------------------------------------------------------


def test_first_run_stores_exact_values_with_provenance(ingestion_session: Session) -> None:
    session = ingestion_session
    data = page(("2022", "6.699801"), ("2021", "5.131407"), ("2020", "6.623437"))
    job, transport, _ = run(session, [data, metadata()])

    assert job.status is JobStatus.COMPLETED
    assert job.error_summary is None
    assert (job.items_total, job.items_succeeded, job.records_received, job.records_new) == (
        1,
        1,
        3,
        3,
    )
    assert job.request_count == 2  # the data page and the indicator's metadata
    assert job.started_at is not None and job.finished_at is not None

    rows = current(session)
    assert set(rows) == {"2020", "2021", "2022"}
    row = rows["2022"]
    assert row.value == Decimal("6.699801")  # exact, never a float
    assert row.raw_value == "6.699801"
    assert (row.status, row.quality_status, row.revision) == (
        ObservationStatus.REPORTED,
        QualityStatus.VALIDATED,
        1,
    )
    assert row.first_seen_job_id == job.id and row.last_seen_job_id == job.id

    capture = session.get_one(SourceCapture, row.capture_id)
    assert capture.sha256 == hashlib.sha256(data.body).hexdigest()
    assert capture.body_gzip is not None and gzip.decompress(capture.body_gzip) == data.body
    assert capture.locator.startswith("https://api.worldbank.org/v2/country/IND/indicator/")
    assert capture.provider_last_updated == date(2026, 7, 1)
    assert "date=2019:2025" in transport.requests[0][0]

    series = session.get_one(EconomicSeries, "s-cpi")
    assert (series.first_period, series.last_period) == (date(2020, 1, 1), date(2022, 1, 1))
    assert (series.observation_count, series.missing_count) == (3, 0)
    assert series.last_ingestion_status is JobItemStatus.SUCCEEDED
    assert series.last_successful_ingestion_at is not None
    assert series.description == "Synthetic definition text."  # the provider's definition
    assert series.source_organization == "Synthetic source organisation"
    assert session.get_one(Dataset, "test-wdi").provider_last_updated == date(2026, 7, 1)


def test_rerunning_identical_data_changes_nothing_but_last_seen(
    ingestion_session: Session,
) -> None:
    session = ingestion_session
    values = (("2021", "5.1"), ("2020", "6.6"))
    first, _, _ = run(session, [page(*values), metadata()])
    second, _, _ = run(session, [page(*values), metadata()])

    assert second.status is JobStatus.COMPLETED
    assert (second.records_new, second.records_revised, second.records_unchanged) == (0, 0, 2)
    all_rows = session.scalars(
        select(EconomicObservation).where(EconomicObservation.series_id == "s-cpi")
    ).all()
    assert len(all_rows) == 2  # no duplicates
    for row in all_rows:
        assert row.first_seen_job_id == first.id
        assert row.last_seen_job_id == second.id


def test_a_revised_value_keeps_the_previous_one(ingestion_session: Session) -> None:
    session = ingestion_session
    run(session, [page(("2021", "5.1"), ("2020", "6.6")), metadata()])
    second, _, _ = run(session, [page(("2021", "5.3"), ("2020", "6.6")), metadata()])

    assert (second.records_revised, second.records_unchanged) == (1, 1)
    history = session.scalars(
        select(EconomicObservation)
        .where(
            EconomicObservation.series_id == "s-cpi",
            EconomicObservation.period_label == "2021",
        )
        .order_by(EconomicObservation.revision)
    ).all()
    assert [(row.revision, row.value) for row in history] == [
        (1, Decimal("5.1")),
        (2, Decimal("5.3")),
    ]
    old, new = history
    assert old.superseded_at is not None and old.superseded_by_job_id == second.id
    assert new.superseded_at is None and new.first_seen_job_id == second.id


def test_a_value_withdrawn_by_the_provider_is_a_revision_not_a_deletion(
    ingestion_session: Session,
) -> None:
    session = ingestion_session
    run(session, [page(("2021", "5.1")), metadata()])
    second, _, _ = run(session, [page(("2021", None)), metadata()])

    assert second.records_revised == 1
    row = current(session)["2021"]
    assert (row.status, row.value, row.revision) == (ObservationStatus.MISSING, None, 2)
    superseded = session.scalars(
        select(EconomicObservation).where(EconomicObservation.superseded_at.is_not(None))
    ).one()
    assert superseded.value == Decimal("5.1")


def test_equal_numbers_written_differently_are_not_a_revision(ingestion_session: Session) -> None:
    session = ingestion_session
    run(session, [page(("2021", "5.1")), metadata()])
    second, _, _ = run(session, [page(("2021", "5.10")), metadata()])
    assert (second.records_revised, second.records_unchanged) == (0, 1)


# --- Missing, flagged and rejected records ---------------------------------------------------


def test_missing_values_are_stored_as_missing_and_never_filled(ingestion_session: Session) -> None:
    session = ingestion_session
    job, _, _ = run(
        session,
        [page(("2023", None), ("2022", "2.0"), ("2021", None), ("2020", "1.0")), metadata()],
    )
    rows = current(session)
    assert rows["2021"].status is ObservationStatus.MISSING and rows["2021"].value is None
    assert rows["2023"].status is ObservationStatus.MISSING
    assert job.records_missing == 2
    rules = {issue.rule: issue for issue in issues(session, job)}
    assert rules["missing_values"].outcome is IssueOutcome.NOTED
    assert rules["missing_values"].raw_record == {"periods": ["2021"]}
    assert rules["recent_periods_without_values"].raw_record == {"periods": ["2023"]}
    # Informational notes do not turn a clean run into one "with warnings".
    assert job.status is JobStatus.COMPLETED
    series = session.get_one(EconomicSeries, "s-cpi")
    assert (series.observation_count, series.missing_count) == (2, 2)
    assert series.last_period == date(2022, 1, 1)


def test_an_unusual_value_is_stored_as_reported_and_flagged(ingestion_session: Session) -> None:
    session = ingestion_session
    job, _, _ = run(session, [page(("2021", "250.5"), ("2020", "4.0")), metadata()])

    row = current(session)["2021"]
    assert row.value == Decimal("250.5")  # never corrected
    assert row.quality_status is QualityStatus.WARNING
    flag = next(issue for issue in issues(session, job) if issue.rule == "outside_review_range")
    assert flag.outcome is IssueOutcome.FLAGGED and flag.observation_id == row.id
    assert flag.review_status == "unreviewed"
    assert job.status is JobStatus.COMPLETED_WITH_WARNINGS
    assert job.warning_count == 1


def test_invalid_records_are_rejected_and_kept_as_issues(ingestion_session: Session) -> None:
    session = ingestion_session
    records = [
        wb_record("2022", "3.5"),
        wb_record("2021", '"n/a"'),  # a string, not a number
        wb_record("2020", "1.5", iso3="USA"),  # another country's record
        wb_record("2031", "9.9"),  # a period that has not started
        wb_record("2019", "0.12345678901234567891"),  # 20 decimal places: not rounded
    ]
    job, _, _ = run(session, [response(wb_page(records)), metadata()])

    assert set(current(session)) == {"2022"}
    rejected = {i.rule: i for i in issues(session, job) if i.outcome is IssueOutcome.REJECTED}
    assert set(rejected) == {
        "invalid_number",
        "series_mismatch",
        "future_period",
        "precision_exceeded",
    }
    assert rejected["invalid_number"].raw_record is not None
    assert rejected["invalid_number"].raw_record["value"] == "n/a"
    assert rejected["precision_exceeded"].raw_record is not None
    assert rejected["precision_exceeded"].raw_record["value"] == "0.12345678901234567891"
    assert (job.records_received, job.records_rejected, job.records_new) == (5, 4, 1)
    assert job.status is JobStatus.COMPLETED_WITH_WARNINGS
    assert job.error_count == 4


def test_a_series_whose_records_are_all_rejected_fails(ingestion_session: Session) -> None:
    session = ingestion_session
    job, _, _ = run(session, [response(wb_page([wb_record("2021", '"x"')])), metadata()])
    (item,) = items(session, job)
    assert item.status is JobItemStatus.FAILED
    assert item.error_code == "all_records_rejected"
    assert item.records_rejected == 1
    assert job.status is JobStatus.FAILED
    assert len(issues(session, job)) == 1  # the reason is kept even though the item failed


def test_an_empty_response_is_a_warning_not_a_failure(ingestion_session: Session) -> None:
    session = ingestion_session
    job, _, _ = run(session, [response(wb_page([])), metadata()])
    assert job.status is JobStatus.COMPLETED_WITH_WARNINGS
    assert [issue.rule for issue in issues(session, job)] == ["empty_response"]
    assert current(session) == {}


# --- Failures --------------------------------------------------------------------------------


def test_one_failing_series_makes_the_job_partially_failed(ingestion_session: Session) -> None:
    session = ingestion_session
    job, _, _ = run(
        session,
        [page(("2021", "5.1")), metadata(), response(wb_error("120", "Invalid value"))],
        series_ids=("s-cpi", "s-gdp"),
    )
    assert job.status is JobStatus.PARTIALLY_FAILED
    ok, failed = items(session, job)
    assert ok.status is JobItemStatus.SUCCEEDED
    assert (failed.status, failed.error_code) == (JobItemStatus.FAILED, "invalid_request")
    assert failed.error_message is not None and "Invalid value" in failed.error_message
    assert job.error_summary is not None and "s-gdp" in job.error_summary
    assert set(current(session)) == {"2021"}  # the successful series stayed stored
    gdp = session.get_one(EconomicSeries, "s-gdp")
    assert gdp.last_ingestion_status is JobItemStatus.FAILED
    assert gdp.last_successful_ingestion_at is None


def test_repeated_outages_stop_the_run_instead_of_hammering_the_provider(
    ingestion_session: Session,
) -> None:
    session = ingestion_session
    outage = response("unavailable", status=503)
    job, transport, _ = run(session, [outage, outage, outage], series_ids=SERIES, max_attempts=1)

    assert len(transport.requests) == 3  # the fourth series was never requested
    statuses = [(item.status, item.error_code) for item in items(session, job)]
    assert statuses == [
        (JobItemStatus.FAILED, "provider_unavailable"),
        (JobItemStatus.FAILED, "provider_unavailable"),
        (JobItemStatus.FAILED, "provider_unavailable"),
        (JobItemStatus.SKIPPED, "circuit_open"),
    ]
    assert job.status is JobStatus.FAILED
    assert job.error_summary is not None
    assert job.error_summary.startswith("Stopped after 3 consecutive")


def test_a_rate_limited_request_is_retried_then_succeeds(ingestion_session: Session) -> None:
    session = ingestion_session
    limited = response("slow down", status=429, headers={"Retry-After": "2"})
    job, _, sleeps = run(session, [limited, page(("2021", "5.1")), metadata()])
    assert job.status is JobStatus.COMPLETED
    assert job.request_count == 3
    assert 2.0 in sleeps.calls


def test_refused_credentials_fail_without_retrying(ingestion_session: Session) -> None:
    session = ingestion_session
    job, transport, _ = run(session, [response("denied", status=401)])
    (item,) = items(session, job)
    assert (item.status, item.error_code) == (JobItemStatus.FAILED, "authentication_failed")
    assert len(transport.requests) == 1
    assert job.status is JobStatus.FAILED


def test_an_unreachable_provider_is_recorded(ingestion_session: Session) -> None:
    session = ingestion_session
    down = TransportError("connection", "The provider could not be reached.")
    job, _, _ = run(session, [down, down], max_attempts=2)
    (item,) = items(session, job)
    assert (item.status, item.error_code) == (JobItemStatus.FAILED, "provider_unavailable")
    assert job.status is JobStatus.FAILED


def test_a_malformed_response_fails_the_series(ingestion_session: Session) -> None:
    session = ingestion_session
    job, _, _ = run(session, [response("<html>maintenance</html>")])
    (item,) = items(session, job)
    assert item.error_code == "malformed_response"
    assert job.status is JobStatus.FAILED


def test_a_storage_error_rolls_back_the_whole_series(
    ingestion_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = ingestion_session

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(economic, "save_observations", broken)
    job, _, _ = run(session, [page(("2021", "5.1")), metadata()])
    (item,) = items(session, job)
    assert (item.status, item.error_code) == (JobItemStatus.FAILED, "storage_error")
    assert item.error_message is not None and "simulated" not in item.error_message
    assert session.scalars(select(SourceCapture)).all() == []  # rolled back with the series
    assert job.status is JobStatus.FAILED


class InterruptingSource:
    """Fetches normally, then behaves as if the user pressed Ctrl+C."""

    def __init__(self, inner: WorldBankProvider, interrupt_on: int) -> None:
        self.profile = inner.profile
        self.inner = inner
        self.calls = 0
        self.interrupt_on = interrupt_on

    def fetch_series(self, request: SeriesRequest) -> SeriesFetch:
        self.calls += 1
        if self.calls == self.interrupt_on:
            raise KeyboardInterrupt
        return self.inner.fetch_series(request)


def test_ctrl_c_cancels_the_job_and_keeps_what_was_stored(ingestion_session: Session) -> None:
    session = ingestion_session
    transport = ScriptedTransport([page(("2021", "5.1")), metadata()])
    client, _ = make_client(transport)
    source = InterruptingSource(WorldBankProvider(client, clock=Clock()), interrupt_on=2)
    job, _, _ = run(session, [], series_ids=("s-cpi", "s-gdp", "s-lend"), source=source)

    assert job.status is JobStatus.CANCELLED
    done, interrupted, never = items(session, job)
    assert done.status is JobItemStatus.SUCCEEDED
    assert (interrupted.status, interrupted.error_code) == (JobItemStatus.SKIPPED, "cancelled")
    assert interrupted.error_message is not None and "while" in interrupted.error_message
    assert never.error_message is not None and "before" in never.error_message
    assert set(current(session)) == {"2021"}


# --- Job bookkeeping -------------------------------------------------------------------------


def _abandoned_job(session: Session, *, hours_ago: float) -> IngestionJob:
    sync_catalog(session, synthetic_catalog(*SERIES), PROFILES)
    then = START - timedelta(hours=hours_ago)
    job = jobs.create_job(
        session, provider_id="worldbank", dataset_id="test-wdi", parameters={}, now=then
    )
    kind = JobTargetKind.ECONOMIC_SERIES
    started = jobs.add_item(session, job, target_kind=kind, label="s-cpi", series_id="s-cpi")
    jobs.add_item(session, job, target_kind=kind, label="s-gdp", series_id="s-gdp")
    jobs.start_job(job, then)
    jobs.start_item(started, then)
    session.commit()
    return job


def test_an_abandoned_job_is_closed_honestly(ingestion_session: Session) -> None:
    session = ingestion_session
    job = _abandoned_job(session, hours_ago=3)
    recovered = jobs.recover_stale_jobs(session, START)
    session.commit()

    assert recovered == [job]
    assert job.status is JobStatus.FAILED
    assert job.error_summary is not None and job.error_summary.startswith("Abandoned")
    started, never = items(session, job)
    assert (started.status, started.error_code) == (JobItemStatus.FAILED, "interrupted")
    assert (never.status, never.error_code) == (JobItemStatus.SKIPPED, "interrupted")


def test_a_recent_running_job_is_not_touched(ingestion_session: Session) -> None:
    session = ingestion_session
    job = _abandoned_job(session, hours_ago=0.5)
    assert jobs.recover_stale_jobs(session, START) == []
    assert jobs.active_job(session, "test-wdi", START) == job
    assert job.status is JobStatus.RUNNING


@pytest.mark.parametrize(
    ("statuses", "warnings", "expected"),
    [
        ([], 0, JobStatus.FAILED),
        (["succeeded", "succeeded"], 0, JobStatus.COMPLETED),
        (["succeeded", "succeeded"], 1, JobStatus.COMPLETED_WITH_WARNINGS),
        (["succeeded", "failed"], 0, JobStatus.PARTIALLY_FAILED),
        (["succeeded", "skipped"], 0, JobStatus.PARTIALLY_FAILED),
        (["failed", "skipped"], 0, JobStatus.FAILED),
    ],
)
def test_job_status_is_derived_from_what_happened(
    statuses: list[str], warnings: int, expected: JobStatus
) -> None:
    fake = [
        IngestionJobItem(
            status=JobItemStatus(status), warning_count=warnings, error_count=0, target_label="t"
        )
        for status in statuses
    ]
    assert jobs.derive_status(fake)[0] is expected
    assert jobs.derive_status(fake, cancelled=True)[0] is JobStatus.CANCELLED


class BrokenSource:
    """A provider with a bug: it raises something that is not a provider error."""

    profile = WorldBankProvider.profile

    def fetch_series(self, request: SeriesRequest) -> SeriesFetch:
        raise ValueError("simulated bug with internal details")


def test_an_unexpected_error_fails_the_series_without_leaking_details(
    ingestion_session: Session,
) -> None:
    session = ingestion_session
    job, _, _ = run(session, [], series_ids=("s-cpi", "s-gdp"), source=BrokenSource())
    failed = items(session, job)
    assert [(item.status, item.error_code) for item in failed] == [
        (JobItemStatus.FAILED, "internal_error"),
        (JobItemStatus.FAILED, "internal_error"),  # the run carried on to the next series
    ]
    assert all("simulated" not in (item.error_message or "") for item in failed)
    assert job.status is JobStatus.FAILED
