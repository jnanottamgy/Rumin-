"""Guarantees of the Phase 2 schema, enforced by the database itself (SQLite and PostgreSQL).

Nothing here is committed: every test works inside a transaction that is rolled back.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.types import canonical_decimal, decimal_fits
from app.domain.enums import (
    DatasetKind,
    Frequency,
    JobStatus,
    JobTrigger,
    MeasureType,
    ObservationStatus,
    PriceBasis,
    ProviderAuth,
    ProviderKind,
    QualityStatus,
    SeasonalAdjustment,
)
from app.models import (
    DataProvider,
    Dataset,
    EconomicObservation,
    EconomicSeries,
    IngestionJob,
)


def _provider() -> DataProvider:
    return DataProvider(
        id="test-provider",
        name="Test provider",
        kind=ProviderKind.API,
        description="Used by schema tests only.",
        authentication=ProviderAuth.NONE,
        data_categories="test",
        coverage="test",
        update_frequency="test",
        rate_limit_policy="test",
        licensing="test",
        commercial_use="test",
        reliability="test",
        known_limitations="test",
    )


def _provider_dataset(**overrides: object) -> Dataset:
    values: dict[str, object] = {
        "id": "test-provider-dataset",
        "kind": DatasetKind.PROVIDER,
        "version": "test",
        "name": "Test provider dataset",
        "description": "Used by schema tests only.",
        "is_illustrative": False,
        "provenance_note": "test",
        "license": "test",
        "loaded_at": utcnow(),
        "provider_id": "test-provider",
    }
    values.update(overrides)
    return Dataset(**values)


def _series(**overrides: object) -> EconomicSeries:
    values: dict[str, object] = {
        "id": "test-series",
        "dataset_id": "test-provider-dataset",
        "provider_series_key": "TEST|IND",
        "provider_code": "TEST",
        "name": "Test series",
        "description": "Used by schema tests only.",
        "measure_type": MeasureType.LEVEL,
        "unit": "test units",
        "frequency": Frequency.ANNUAL,
        "aggregation": "test",
        "price_basis": PriceBasis.NOT_APPLICABLE,
        "seasonal_adjustment": SeasonalAdjustment.NOT_APPLICABLE,
    }
    values.update(overrides)
    return EconomicSeries(**values)


def _job() -> IngestionJob:
    return IngestionJob(
        id=uuid.uuid4(),
        provider_id="test-provider",
        dataset_id="test-provider-dataset",
        trigger=JobTrigger.CLI,
        parameters={},
        status=JobStatus.RUNNING,
    )


def _observation(job: IngestionJob, **overrides: object) -> EconomicObservation:
    now = utcnow()
    values: dict[str, object] = {
        "series_id": "test-series",
        "period_start": date(2023, 1, 1),
        "period_label": "2023",
        "value": Decimal("5.649"),
        "raw_value": "5.649",
        "status": ObservationStatus.REPORTED,
        "quality_status": QualityStatus.VALIDATED,
        "first_seen_job_id": job.id,
        "first_seen_at": now,
        "last_seen_job_id": job.id,
        "last_seen_at": now,
    }
    values.update(overrides)
    return EconomicObservation(**values)


@pytest.fixture
def base(db_session: Session) -> tuple[Session, IngestionJob]:
    db_session.add(_provider())
    db_session.flush()
    db_session.add(_provider_dataset())
    db_session.flush()
    db_session.add(_series())
    job = _job()
    db_session.add(job)
    db_session.flush()
    return db_session, job


def test_exact_decimals_round_trip_without_rounding(base: tuple[Session, IngestionJob]) -> None:
    session, _ = base
    series = session.get(EconomicSeries, "test-series")
    assert series is not None
    series.plausible_min = Decimal("0.000000000000000001")  # 18 decimal places
    series.plausible_max = Decimal("12345678901234567890.123456789012345678")  # 38 digits
    session.flush()
    session.expire_all()

    stored = session.get(EconomicSeries, "test-series")
    assert stored is not None
    assert stored.plausible_min == Decimal("0.000000000000000001")
    assert stored.plausible_max == Decimal("12345678901234567890.123456789012345678")


def test_values_that_do_not_fit_are_refused_not_rounded(base: tuple[Session, IngestionJob]) -> None:
    session, job = base
    assert not decimal_fits(Decimal("0.1234567890123456789"))  # 19 decimal places
    session.add(_observation(job, value=Decimal("0.1234567890123456789")))
    with pytest.raises(StatementError, match="does not fit"):
        session.flush()


def test_trailing_zeros_are_not_significant() -> None:
    assert canonical_decimal(Decimal("5.649000")) == Decimal("5.649")
    assert str(canonical_decimal(Decimal("1E+2"))) == "100"


def test_only_one_current_observation_per_period(base: tuple[Session, IngestionJob]) -> None:
    session, job = base
    session.add(_observation(job))
    session.flush()
    session.add(_observation(job, value=Decimal("5.7"), raw_value="5.7", revision=2))
    with pytest.raises(IntegrityError):
        session.flush()


def test_superseded_revisions_are_kept_alongside_the_current_one(
    base: tuple[Session, IngestionJob],
) -> None:
    session, job = base
    first = _observation(job)
    session.add(first)
    session.flush()
    first.superseded_at = utcnow()
    first.superseded_by_job_id = job.id
    session.add(_observation(job, value=Decimal("5.7"), raw_value="5.7", revision=2))
    session.flush()

    rows = session.scalars(
        select(EconomicObservation).where(EconomicObservation.series_id == "test-series")
    ).all()
    assert sorted(row.revision for row in rows) == [1, 2]
    assert [row.revision for row in rows if row.superseded_at is None] == [2]


def test_series_identity_is_unique_within_a_dataset(base: tuple[Session, IngestionJob]) -> None:
    session, _ = base
    session.add(_series(id="test-series-duplicate"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_provider_datasets_must_name_their_provider(db_session: Session) -> None:
    db_session.add(_provider_dataset(provider_id=None))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_curated_datasets_must_carry_a_checksum(db_session: Session) -> None:
    db_session.add(_provider_dataset(kind=DatasetKind.CURATED, provider_id=None))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_the_phase_one_dataset_is_curated(db_session: Session) -> None:
    dataset = db_session.get(Dataset, "rumin-sample")
    assert dataset is not None
    assert dataset.kind is DatasetKind.CURATED
    assert dataset.checksum_sha256
