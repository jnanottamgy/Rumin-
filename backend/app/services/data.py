"""Read access to provider data: providers, datasets, economic series and prices."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from app.core.errors import DomainValidationError, NotFoundError
from app.domain.enums import (
    DatasetKind,
    Frequency,
    InstrumentType,
    MeasureType,
    ObservationStatus,
    QualityStatus,
)
from app.ingestion.normalize import Period, next_period
from app.models import (
    DataProvider,
    Dataset,
    EconomicObservation,
    EconomicSeries,
    IngestionJob,
    Instrument,
    PriceBar,
)
from app.schemas.data import (
    DatasetPage,
    DatasetRead,
    DatasetRef,
    InstrumentDetail,
    InstrumentPage,
    InstrumentRead,
    InstrumentRef,
    JobRef,
    LatestObservation,
    ObservationPage,
    ObservationRead,
    PriceBarPage,
    PriceBarRead,
    ProviderRead,
    SeriesDetail,
    SeriesPage,
    SeriesRead,
    SeriesRef,
)
from app.services.common import like_pattern, paginate

SeriesSort = Literal["name", "-name", "last_period", "-last_period", "provider_code"]


# --- Providers ------------------------------------------------------------------------------


def _provider_read(provider: DataProvider, dataset_count: int) -> ProviderRead:
    data = {
        column: getattr(provider, column)
        for column in ProviderRead.model_fields
        if column != "dataset_count"
    }
    data["dataset_count"] = dataset_count
    return ProviderRead.model_validate(data)


def _dataset_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(Dataset.provider_id, func.count())
        .where(Dataset.provider_id.is_not(None))
        .group_by(Dataset.provider_id)
    ).tuples()
    return {str(provider_id): count for provider_id, count in rows}


def list_providers(session: Session) -> list[ProviderRead]:
    counts = _dataset_counts(session)
    providers = session.scalars(select(DataProvider).order_by(DataProvider.name))
    return [_provider_read(provider, counts.get(provider.id, 0)) for provider in providers]


def get_provider(session: Session, provider_id: str) -> ProviderRead:
    provider = session.get(DataProvider, provider_id)
    if provider is None:
        raise NotFoundError(f"No provider with ID '{provider_id}'.")
    return _provider_read(provider, _dataset_counts(session).get(provider_id, 0))


# --- Datasets -------------------------------------------------------------------------------


def _job_ref(job: IngestionJob | None) -> JobRef | None:
    return JobRef.model_validate(job) if job is not None else None


def _latest_jobs(session: Session, dataset_ids: Sequence[str]) -> dict[str, IngestionJob]:
    if not dataset_ids:
        return {}
    newer = aliased(IngestionJob)
    latest = session.scalars(
        select(IngestionJob).where(
            IngestionJob.dataset_id.in_(dataset_ids),
            ~select(newer.id)
            .where(
                newer.dataset_id == IngestionJob.dataset_id,
                newer.created_at > IngestionJob.created_at,
            )
            .exists(),
        )
    )
    return {job.dataset_id: job for job in latest}


def _count_by(
    session: Session, column: InstrumentedAttribute[str], ids: Sequence[str]
) -> dict[str, int]:
    if not ids:
        return {}
    rows = session.execute(
        select(column, func.count()).where(column.in_(ids)).group_by(column)
    ).tuples()
    return {str(key): count for key, count in rows}


def list_datasets(
    session: Session, *, kind: DatasetKind | None, limit: int, offset: int
) -> DatasetPage:
    statement = select(Dataset).order_by(Dataset.kind, Dataset.name, Dataset.id)
    if kind is not None:
        statement = statement.where(Dataset.kind == kind)
    rows, total = paginate(session, statement, limit, offset)
    ids = [row.id for row in rows]
    series = _count_by(session, EconomicSeries.dataset_id, ids)
    instruments = _count_by(session, Instrument.dataset_id, ids)
    jobs = _latest_jobs(session, ids)
    items = [
        _dataset_read(row, series.get(row.id, 0), instruments.get(row.id, 0), jobs.get(row.id))
        for row in rows
    ]
    return DatasetPage(items=items, total=total, limit=limit, offset=offset)


def _dataset_read(
    dataset: Dataset, series_count: int, instrument_count: int, job: IngestionJob | None
) -> DatasetRead:
    data = {
        name: getattr(dataset, name)
        for name in DatasetRead.model_fields
        if name not in {"series_count", "instrument_count", "last_job"}
    }
    return DatasetRead.model_validate(
        {
            **data,
            "series_count": series_count,
            "instrument_count": instrument_count,
            "last_job": _job_ref(job),
        }
    )


def get_dataset(session: Session, dataset_id: str) -> DatasetRead:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise NotFoundError(f"No dataset with ID '{dataset_id}'.")
    ids = [dataset.id]
    return _dataset_read(
        dataset,
        _count_by(session, EconomicSeries.dataset_id, ids).get(dataset.id, 0),
        _count_by(session, Instrument.dataset_id, ids).get(dataset.id, 0),
        _latest_jobs(session, ids).get(dataset.id),
    )


def _dataset_ref(session: Session, dataset_id: str) -> DatasetRef:
    return DatasetRef.model_validate(session.get_one(Dataset, dataset_id))


# --- Economic series ------------------------------------------------------------------------

_SERIES_ORDER: dict[str, tuple[ColumnElement[Any], ...]] = {
    "name": (EconomicSeries.name.asc(), EconomicSeries.id.asc()),
    "-name": (EconomicSeries.name.desc(), EconomicSeries.id.asc()),
    "last_period": (EconomicSeries.last_period.asc().nulls_last(), EconomicSeries.id.asc()),
    "-last_period": (EconomicSeries.last_period.desc().nulls_last(), EconomicSeries.id.asc()),
    "provider_code": (
        EconomicSeries.provider_code.asc(),
        EconomicSeries.country_iso3.asc(),
        EconomicSeries.id.asc(),
    ),
}


def _latest_values(session: Session, ids: Sequence[str]) -> dict[str, LatestObservation]:
    """The current value for each series' latest reported period (one query)."""
    if not ids:
        return {}
    rows = session.scalars(
        select(EconomicObservation)
        .join(
            EconomicSeries,
            and_(
                EconomicSeries.id == EconomicObservation.series_id,
                EconomicSeries.last_period == EconomicObservation.period_start,
            ),
        )
        .where(
            EconomicObservation.series_id.in_(ids),
            EconomicObservation.superseded_at.is_(None),
            EconomicObservation.status == ObservationStatus.REPORTED,
        )
    )
    return {row.series_id: LatestObservation.model_validate(row) for row in rows}


def _series_data(series: EconomicSeries, latest: LatestObservation | None) -> dict[str, object]:
    data: dict[str, object] = {
        name: getattr(series, name)
        for name in SeriesRead.model_fields
        if name not in {"latest", "epistemic_category"}
    }
    data["latest"] = latest
    return data


def list_series(
    session: Session,
    *,
    dataset_id: str | None,
    country_iso3: str | None,
    measure_type: MeasureType | None,
    frequency: Frequency | None,
    has_data: bool | None,
    q: str | None,
    sort: SeriesSort,
    limit: int,
    offset: int,
) -> SeriesPage:
    statement = select(EconomicSeries).order_by(*_SERIES_ORDER[sort])
    if dataset_id is not None:
        statement = statement.where(EconomicSeries.dataset_id == dataset_id)
    if country_iso3 is not None:
        statement = statement.where(EconomicSeries.country_iso3 == country_iso3)
    if measure_type is not None:
        statement = statement.where(EconomicSeries.measure_type == measure_type)
    if frequency is not None:
        statement = statement.where(EconomicSeries.frequency == frequency)
    if has_data is not None:
        statement = statement.where(
            EconomicSeries.observation_count > 0
            if has_data
            else EconomicSeries.observation_count == 0
        )
    if q:
        pattern = like_pattern(q)
        statement = statement.where(
            EconomicSeries.name.ilike(pattern, escape="\\")
            | EconomicSeries.provider_code.ilike(pattern, escape="\\")
        )
    rows, total = paginate(session, statement, limit, offset)
    latest = _latest_values(session, [row.id for row in rows])
    items = [SeriesRead.model_validate(_series_data(row, latest.get(row.id))) for row in rows]
    return SeriesPage(items=items, total=total, limit=limit, offset=offset)


def _get_series(session: Session, series_id: str) -> EconomicSeries:
    series = session.get(EconomicSeries, series_id)
    if series is None:
        raise NotFoundError(f"No economic series with ID '{series_id}'.")
    return series


def get_series(session: Session, series_id: str) -> SeriesDetail:
    series = _get_series(session, series_id)
    current = (
        EconomicObservation.series_id == series.id,
        EconomicObservation.superseded_at.is_(None),
    )
    flagged = session.scalar(
        select(func.count()).where(
            *current, EconomicObservation.quality_status == QualityStatus.WARNING
        )
    )
    revised = session.scalar(
        select(func.count(func.distinct(EconomicObservation.period_start))).where(
            EconomicObservation.series_id == series.id,
            EconomicObservation.superseded_at.is_not(None),
        )
    )
    dataset = session.get_one(Dataset, series.dataset_id)
    provider = session.get(DataProvider, dataset.provider_id) if dataset.provider_id else None
    job = (
        session.get(IngestionJob, series.last_ingestion_job_id)
        if series.last_ingestion_job_id
        else None
    )
    return SeriesDetail.model_validate(
        {
            **_series_data(series, _latest_values(session, [series.id]).get(series.id)),
            "dataset": DatasetRef.model_validate(dataset),
            "provider_name": provider.name if provider else None,
            "flagged_count": flagged or 0,
            "revised_period_count": revised or 0,
            "last_job": _job_ref(job),
        }
    )


def period_end(start: date, frequency: Frequency) -> date:
    """The last day of the period starting on ``start``."""
    if frequency in (Frequency.ANNUAL, Frequency.QUARTERLY, Frequency.MONTHLY):
        return next_period(Period(start, frequency, "")).start - timedelta(days=1)
    return start


def list_observations(
    session: Session,
    series_id: str,
    *,
    start: date | None,
    end: date | None,
    include_missing: bool,
    include_revisions: bool,
    limit: int,
    offset: int,
) -> ObservationPage:
    series = _get_series(session, series_id)
    statement = (
        select(EconomicObservation)
        .where(EconomicObservation.series_id == series.id)
        .order_by(
            EconomicObservation.period_start,
            EconomicObservation.revision,
            EconomicObservation.id,
        )
    )
    if not include_revisions:
        statement = statement.where(EconomicObservation.superseded_at.is_(None))
    if not include_missing:
        statement = statement.where(EconomicObservation.status == ObservationStatus.REPORTED)
    if start is not None:
        statement = statement.where(EconomicObservation.period_start >= start)
    if end is not None:
        statement = statement.where(EconomicObservation.period_start <= end)
    rows, total = paginate(session, statement, limit, offset)
    items = [
        ObservationRead(
            id=row.id,
            period_label=row.period_label,
            period_start=row.period_start,
            period_end=period_end(row.period_start, series.frequency),
            value=row.value,
            raw_value=row.raw_value,
            status=row.status,
            quality_status=row.quality_status,
            provider_flags=row.provider_flags,
            revision=row.revision,
            is_current=row.superseded_at is None,
            superseded_at=row.superseded_at,
            retrieved_at=row.first_seen_at,
            last_confirmed_at=row.last_seen_at,
            retrieved_by_job_id=row.first_seen_job_id,
            capture_id=row.capture_id,
        )
        for row in rows
    ]
    return ObservationPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        series=SeriesRef.model_validate(series),
        dataset=_dataset_ref(session, series.dataset_id),
    )


# --- Instruments and prices -----------------------------------------------------------------


def list_instruments(
    session: Session,
    *,
    exchange_mic: str | None,
    instrument_type: InstrumentType | None,
    dataset_id: str | None,
    limit: int,
    offset: int,
) -> InstrumentPage:
    statement = select(Instrument).order_by(Instrument.name, Instrument.id)
    if exchange_mic is not None:
        statement = statement.where(Instrument.exchange_mic == exchange_mic)
    if instrument_type is not None:
        statement = statement.where(Instrument.instrument_type == instrument_type)
    if dataset_id is not None:
        with_prices = select(PriceBar.instrument_id).where(PriceBar.dataset_id == dataset_id)
        statement = statement.where(
            (Instrument.dataset_id == dataset_id) | Instrument.id.in_(with_prices)
        )
    rows, total = paginate(session, statement, limit, offset)
    items = [InstrumentRead.model_validate(row) for row in rows]
    return InstrumentPage(items=items, total=total, limit=limit, offset=offset)


def _get_instrument(session: Session, instrument_id: str) -> Instrument:
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise NotFoundError(f"No instrument with ID '{instrument_id}'.")
    return instrument


def _price_dataset_ids(session: Session, instrument_id: str) -> list[str]:
    return list(
        session.scalars(
            select(PriceBar.dataset_id)
            .where(PriceBar.instrument_id == instrument_id)
            .distinct()
            .order_by(PriceBar.dataset_id)
        )
    )


def get_instrument(session: Session, instrument_id: str) -> InstrumentDetail:
    instrument = _get_instrument(session, instrument_id)
    datasets = [
        _dataset_ref(session, dataset_id)
        for dataset_id in _price_dataset_ids(session, instrument.id)
    ]
    data = InstrumentRead.model_validate(instrument).model_dump()
    return InstrumentDetail.model_validate({**data, "price_datasets": datasets})


def list_prices(
    session: Session,
    instrument_id: str,
    *,
    dataset_id: str | None,
    start: date | None,
    end: date | None,
    include_revisions: bool,
    limit: int,
    offset: int,
) -> PriceBarPage:
    instrument = _get_instrument(session, instrument_id)
    available = _price_dataset_ids(session, instrument.id)
    if dataset_id is None:
        if len(available) > 1:
            raise DomainValidationError(
                f"Prices for '{instrument.id}' come from {len(available)} datasets "
                f"({', '.join(available)}); choose one with dataset_id. Prices from "
                "different sources are never blended."
            )
        dataset_id = available[0] if available else instrument.dataset_id
    elif dataset_id not in available and dataset_id != instrument.dataset_id:
        raise NotFoundError(f"Dataset '{dataset_id}' holds no prices for '{instrument.id}'.")

    statement = (
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument.id, PriceBar.dataset_id == dataset_id)
        .order_by(PriceBar.trade_date, PriceBar.revision, PriceBar.id)
    )
    if not include_revisions:
        statement = statement.where(PriceBar.superseded_at.is_(None))
    if start is not None:
        statement = statement.where(PriceBar.trade_date >= start)
    if end is not None:
        statement = statement.where(PriceBar.trade_date <= end)
    rows, total = paginate(session, statement, limit, offset)
    items = [
        PriceBarRead(
            id=row.id,
            dataset_id=row.dataset_id,
            trade_date=row.trade_date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            adjusted_close=row.adjusted_close,
            volume=row.volume,
            currency=row.currency,
            adjustment=row.adjustment,
            quality_status=row.quality_status,
            revision=row.revision,
            is_current=row.superseded_at is None,
            superseded_at=row.superseded_at,
            retrieved_at=row.first_seen_at,
            last_confirmed_at=row.last_seen_at,
            source_row=row.source_row,
            capture_id=row.capture_id,
        )
        for row in rows
    ]
    return PriceBarPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        instrument=InstrumentRef.model_validate(instrument),
        dataset=_dataset_ref(session, dataset_id),
    )
