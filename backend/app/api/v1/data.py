"""Provider data: providers, datasets, economic series, observations, instruments, prices.

All read-only. Data values are decimal strings; see ``app.schemas.data``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import NOT_FOUND, PaginationDep, SessionDep
from app.domain.enums import DatasetKind, Frequency, InstrumentType, MeasureType
from app.schemas.common import SafeText
from app.schemas.data import (
    DatasetPage,
    DatasetRead,
    InstrumentDetail,
    InstrumentPage,
    ObservationPage,
    PriceBarPage,
    ProviderRead,
    SeriesDetail,
    SeriesPage,
)
from app.services import data
from app.services.data import SeriesSort

router = APIRouter()

PROVIDER_ID = r"^[a-z0-9][a-z0-9-]{1,63}$"
DATASET_ID = r"^[a-z0-9][a-z0-9_-]{1,63}$"
SERIES_ID = r"^[a-z0-9][a-z0-9-]{2,95}$"
INSTRUMENT_ID = r"^[a-z0-9][a-z0-9-]{2,95}$"

ProviderIdPath = Annotated[str, Path(pattern=PROVIDER_ID, examples=["worldbank"])]
DatasetIdPath = Annotated[str, Path(pattern=DATASET_ID, examples=["worldbank-wdi"])]
SeriesIdPath = Annotated[str, Path(pattern=SERIES_ID, examples=["wb-ind-fp-cpi-totl-zg"])]
InstrumentIdPath = Annotated[str, Path(pattern=INSTRUMENT_ID, examples=["xnse-reliance"])]
DatasetIdQuery = Annotated[
    str | None, Query(pattern=DATASET_ID, description="Only items from this dataset.")
]
StartQuery = Annotated[date | None, Query(description="First date to include (YYYY-MM-DD).")]
EndQuery = Annotated[date | None, Query(description="Last date to include (YYYY-MM-DD).")]
RevisionsQuery = Annotated[
    bool,
    Query(description="Also return superseded revisions (the full history of what was received)."),
]


@router.get(
    "/providers",
    response_model=list[ProviderRead],
    tags=["providers and datasets"],
    summary="List data providers",
    description="Who publishes the data RUMIN stores, with licensing, commercial-use and "
    "rate-limit notes taken from each provider's documentation.",
)
def list_providers(session: SessionDep) -> list[ProviderRead]:
    return data.list_providers(session)


@router.get(
    "/providers/{provider_id}",
    response_model=ProviderRead,
    tags=["providers and datasets"],
    summary="Get a data provider",
    responses=NOT_FOUND,
)
def get_provider(session: SessionDep, provider_id: ProviderIdPath) -> ProviderRead:
    return data.get_provider(session, provider_id)


@router.get(
    "/datasets",
    response_model=DatasetPage,
    tags=["providers and datasets"],
    summary="List datasets",
    description="Every dataset loaded into RUMIN — the illustrative curated network and "
    "provider data — with its licence, attribution and latest ingestion job.",
)
def list_datasets(
    session: SessionDep,
    page: PaginationDep,
    kind: Annotated[DatasetKind | None, Query(description="Only this kind.")] = None,
) -> DatasetPage:
    return data.list_datasets(session, kind=kind, limit=page.limit, offset=page.offset)


@router.get(
    "/datasets/{dataset_id}",
    response_model=DatasetRead,
    tags=["providers and datasets"],
    summary="Get a dataset",
    responses=NOT_FOUND,
)
def get_dataset(session: SessionDep, dataset_id: DatasetIdPath) -> DatasetRead:
    return data.get_dataset(session, dataset_id)


@router.get(
    "/economic-series",
    response_model=SeriesPage,
    tags=["economic series"],
    summary="List economic series",
    description="Series RUMIN retrieves from providers, with coverage, the latest reported "
    "value and the outcome of the last retrieval. Historical data only — nothing is live.",
)
def list_series(
    session: SessionDep,
    page: PaginationDep,
    dataset_id: DatasetIdQuery = None,
    country_iso3: Annotated[
        str | None, Query(pattern=r"^[A-Z]{3}$", description="ISO 3166-1 alpha-3 code.")
    ] = None,
    measure_type: Annotated[MeasureType | None, Query()] = None,
    frequency: Annotated[Frequency | None, Query()] = None,
    has_data: Annotated[
        bool | None, Query(description="Only series with (true) or without (false) values.")
    ] = None,
    q: Annotated[
        SafeText | None,
        Query(min_length=1, max_length=100, description="Search names and provider codes."),
    ] = None,
    sort: Annotated[SeriesSort, Query(description="Order; '-' means descending.")] = "name",
) -> SeriesPage:
    return data.list_series(
        session,
        dataset_id=dataset_id,
        country_iso3=country_iso3,
        measure_type=measure_type,
        frequency=frequency,
        has_data=has_data,
        q=q,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/economic-series/{series_id}",
    response_model=SeriesDetail,
    tags=["economic series"],
    summary="Get an economic series",
    responses=NOT_FOUND,
)
def get_series(session: SessionDep, series_id: SeriesIdPath) -> SeriesDetail:
    return data.get_series(session, series_id)


@router.get(
    "/economic-series/{series_id}/observations",
    response_model=ObservationPage,
    tags=["economic series"],
    summary="List a series' observations",
    description="Values in period order, exactly as published. Periods the provider listed "
    "without a value are included with `value: null` (never filled in). Each value records "
    "when it was retrieved and the stored response it came from.",
    responses=NOT_FOUND,
)
def list_observations(
    session: SessionDep,
    page: PaginationDep,
    series_id: SeriesIdPath,
    start: StartQuery = None,
    end: EndQuery = None,
    include_missing: Annotated[bool, Query(description="Include periods without a value.")] = True,
    include_revisions: RevisionsQuery = False,
) -> ObservationPage:
    return data.list_observations(
        session,
        series_id,
        start=start,
        end=end,
        include_missing=include_missing,
        include_revisions=include_revisions,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/instruments",
    response_model=InstrumentPage,
    tags=["market data"],
    summary="List instruments",
    description="Listed instruments declared by imported price files. RUMIN ships none.",
)
def list_instruments(
    session: SessionDep,
    page: PaginationDep,
    exchange_mic: Annotated[
        str | None, Query(pattern=r"^[A-Z0-9]{4}$", description="E.g. XNSE or XBOM.")
    ] = None,
    instrument_type: Annotated[InstrumentType | None, Query()] = None,
    dataset_id: DatasetIdQuery = None,
) -> InstrumentPage:
    return data.list_instruments(
        session,
        exchange_mic=exchange_mic,
        instrument_type=instrument_type,
        dataset_id=dataset_id,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/instruments/{instrument_id}",
    response_model=InstrumentDetail,
    tags=["market data"],
    summary="Get an instrument",
    responses=NOT_FOUND,
)
def get_instrument(session: SessionDep, instrument_id: InstrumentIdPath) -> InstrumentDetail:
    return data.get_instrument(session, instrument_id)


@router.get(
    "/instruments/{instrument_id}/prices",
    response_model=PriceBarPage,
    tags=["market data"],
    summary="List an instrument's daily prices",
    description="End-of-day prices from one dataset (an imported file), in date order. When "
    "prices come from several datasets, `dataset_id` is required: sources are never blended.",
    responses=NOT_FOUND,
)
def list_prices(
    session: SessionDep,
    page: PaginationDep,
    instrument_id: InstrumentIdPath,
    dataset_id: DatasetIdQuery = None,
    start: StartQuery = None,
    end: EndQuery = None,
    include_revisions: RevisionsQuery = False,
) -> PriceBarPage:
    return data.list_prices(
        session,
        instrument_id,
        dataset_id=dataset_id,
        start=start,
        end=end,
        include_revisions=include_revisions,
        limit=page.limit,
        offset=page.offset,
    )
