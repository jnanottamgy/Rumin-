"""Response schemas for provider data: providers, datasets, economic series and prices.

Numbers that are data (observation values, prices, review thresholds) are ``Decimal`` and
travel as JSON **strings** ("5.649"), so no digit is lost to binary floating point on the
way to the client. Every value comes with the facts needed to read it honestly: its unit,
the period it describes, when RUMIN retrieved it, and the dataset's licence.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.domain.enums import (
    DatasetKind,
    Frequency,
    InstrumentType,
    JobItemStatus,
    JobStatus,
    MeasureType,
    ObservationStatus,
    PriceAdjustment,
    PriceBasis,
    ProviderAuth,
    ProviderKind,
    QualityStatus,
    SeasonalAdjustment,
)
from app.schemas.common import ApiModel, DecimalString, Page

# --- Providers and datasets -----------------------------------------------------------------


class ProviderRead(ApiModel):
    """Who publishes the data, and on what terms (from the provider's own documentation)."""

    id: str
    name: str
    kind: ProviderKind
    description: str
    homepage_url: str | None
    documentation_url: str | None
    terms_url: str | None
    authentication: ProviderAuth
    data_categories: str
    coverage: str
    update_frequency: str
    rate_limit_policy: str
    licensing: str
    commercial_use: str = Field(
        description="What the licence allows commercially, as understood from the provider's "
        "terms. Not legal advice: re-read the terms before commercial use."
    )
    reliability: str
    known_limitations: str
    dataset_count: int


class JobRef(ApiModel):
    id: uuid.UUID
    status: JobStatus
    created_at: datetime
    finished_at: datetime | None


class DatasetRead(ApiModel):
    """A provenance anchor. ``curated`` datasets are written for RUMIN (the illustrative
    Phase 1 network); ``provider`` datasets hold data retrieved from a provider or imported
    from a licensed file."""

    id: str
    kind: DatasetKind
    version: str
    name: str
    description: str
    is_illustrative: bool = Field(description="True for sample data that is not real.")
    provenance_note: str
    license: str
    license_url: str | None
    terms_url: str | None
    homepage_url: str | None
    attribution: str | None = Field(description="Attribution the licence requires.")
    update_frequency: str | None
    provider_id: str | None
    provider_dataset_code: str | None
    provider_last_updated: date | None = Field(
        description="When the provider last updated the dataset, as the provider reports it."
    )
    checksum_sha256: str | None
    loaded_at: datetime
    series_count: int
    instrument_count: int
    last_job: JobRef | None = Field(description="The most recent ingestion job, if any.")


class DatasetPage(Page[DatasetRead]):
    """A page of datasets."""


class DatasetRef(ApiModel):
    """What must accompany any value shown from a dataset."""

    id: str
    kind: DatasetKind
    name: str
    is_illustrative: bool
    license: str
    license_url: str | None
    attribution: str | None
    provider_id: str | None
    provider_last_updated: date | None


# --- Economic series ------------------------------------------------------------------------


class LatestObservation(ApiModel):
    period_label: str
    period_start: date
    value: DecimalString
    quality_status: QualityStatus


class SeriesRead(ApiModel):
    id: str
    dataset_id: str
    provider_code: str
    provider_series_key: str
    name: str
    description: str
    source_organization: str | None = Field(
        description="Who originally produced the statistic, as the provider reports it."
    )
    measure_type: MeasureType
    unit: str
    currency: str | None
    frequency: Frequency
    aggregation: str
    price_basis: PriceBasis
    seasonal_adjustment: SeasonalAdjustment
    country_iso3: str | None
    country_id: str | None
    variable_id: str | None
    variable_relation: str | None = Field(
        description="How the series differs from the linked Phase 1 variable."
    )
    plausible_min: DecimalString | None = Field(
        description="RUMIN's review threshold (an assumption, not a fact): values outside "
        "[plausible_min, plausible_max] are stored as reported and flagged for review."
    )
    plausible_max: DecimalString | None
    first_period: date | None = Field(description="First period with a reported value.")
    last_period: date | None = Field(description="Latest period with a reported value.")
    observation_count: int = Field(description="Current periods with a reported value.")
    missing_count: int = Field(description="Current periods the provider listed without a value.")
    last_ingestion_status: JobItemStatus | None
    last_ingestion_at: datetime | None
    last_successful_ingestion_at: datetime | None = Field(
        description="When RUMIN last retrieved the series successfully."
    )
    latest: LatestObservation | None
    epistemic_category: Literal["observation"] = "observation"


class SeriesPage(Page[SeriesRead]):
    """A page of economic series."""


class SeriesDetail(SeriesRead):
    dataset: DatasetRef
    provider_name: str | None
    flagged_count: int = Field(description="Current values flagged for review.")
    revised_period_count: int = Field(description="Periods the provider has revised.")
    last_job: JobRef | None


class SeriesRef(ApiModel):
    id: str
    name: str
    unit: str
    currency: str | None
    frequency: Frequency
    measure_type: MeasureType


class ObservationRead(ApiModel):
    id: int
    period_label: str
    period_start: date
    period_end: date
    value: DecimalString | None = Field(description="Null when the provider listed no value.")
    raw_value: str | None = Field(description="The value exactly as the provider sent it.")
    status: ObservationStatus
    quality_status: QualityStatus
    provider_flags: str | None
    revision: int
    is_current: bool
    superseded_at: datetime | None
    retrieved_at: datetime = Field(description="When RUMIN first received this value.")
    last_confirmed_at: datetime = Field(description="When a retrieval last returned it.")
    retrieved_by_job_id: uuid.UUID
    capture_id: int | None = Field(description="The stored response the value came from.")


class ObservationPage(Page[ObservationRead]):
    series: SeriesRef
    dataset: DatasetRef


# --- Instruments and prices -----------------------------------------------------------------


class InstrumentRead(ApiModel):
    id: str
    name: str
    instrument_type: InstrumentType
    isin: str | None
    exchange_mic: str = Field(description="ISO 10383 market identifier code, e.g. XNSE.")
    symbol: str
    currency: str
    country_id: str | None
    dataset_id: str = Field(description="Dataset the instrument was declared in.")
    first_trade_date: date | None
    last_trade_date: date | None
    bar_count: int


class InstrumentPage(Page[InstrumentRead]):
    """A page of instruments."""


class InstrumentDetail(InstrumentRead):
    price_datasets: list[DatasetRef] = Field(
        description="Datasets holding prices for the instrument. Prices from different "
        "datasets are kept apart, never blended."
    )


class InstrumentRef(ApiModel):
    id: str
    name: str
    exchange_mic: str
    symbol: str
    currency: str


class PriceBarRead(ApiModel):
    id: int
    dataset_id: str
    trade_date: date
    open: DecimalString
    high: DecimalString
    low: DecimalString
    close: DecimalString
    adjusted_close: DecimalString | None = Field(
        description="Only when the file supplied one. RUMIN never computes adjustments."
    )
    volume: int | None
    currency: str
    adjustment: PriceAdjustment
    quality_status: QualityStatus
    revision: int
    is_current: bool
    superseded_at: datetime | None
    retrieved_at: datetime = Field(description="When the row was imported.")
    last_confirmed_at: datetime
    source_row: int | None = Field(description="Line in the imported file (1 = header).")
    capture_id: int | None


class PriceBarPage(Page[PriceBarRead]):
    instrument: InstrumentRef
    dataset: DatasetRef
