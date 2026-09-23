"""What a data provider is, and what it can do.

A provider declares a ``ProviderProfile`` (who it is, on what terms) and implements only
the capabilities it really has. There is deliberately no catch-all interface with methods
a provider cannot fulfil: the pipeline asks for a capability (``EconomicSeriesSource``,
``PriceFileSource``) and a provider either has it or is not offered for that job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.domain.enums import CaptureKind, Frequency, ProviderAuth, ProviderKind


@dataclass(frozen=True)
class ProviderProfile:
    """Documentation-derived facts about a provider, mirrored into ``data_providers``."""

    id: str
    name: str
    kind: ProviderKind
    description: str
    authentication: ProviderAuth
    data_categories: str
    coverage: str
    update_frequency: str
    rate_limit_policy: str
    licensing: str
    commercial_use: str
    reliability: str
    known_limitations: str
    homepage_url: str | None = None
    documentation_url: str | None = None
    terms_url: str | None = None


@dataclass(frozen=True)
class Capture:
    """Bytes received from a source, before any interpretation."""

    kind: CaptureKind
    locator: str  # redacted URL or file name
    body: bytes
    received_at: datetime
    http_status: int | None = None
    content_type: str | None = None
    request_params: dict[str, Any] | None = None
    provider_last_updated: date | None = None


# --- Economic series -------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesRequest:
    provider_code: str
    country_iso3: str | None
    frequency: Frequency
    start: str  # provider period notation, e.g. "1990" or "2020M01"
    end: str


@dataclass(frozen=True)
class RawObservation:
    """One record as the provider sent it. Nothing is parsed or corrected yet."""

    period: object  # the provider's period value, usually a string like "2023"
    value: object  # a Decimal, None, or whatever else arrived (validated later)
    series_code: object  # the provider's series identifier in the record
    country_iso3: object
    unit: object = None
    flags: object = None
    original: dict[str, Any] = field(default_factory=dict)  # original field names/values
    capture_index: int | None = None  # which of the fetch's captures the record came from


@dataclass(frozen=True)
class SeriesMetadata:
    name: str | None
    description: str | None
    source_organization: str | None


@dataclass(frozen=True)
class SeriesFetch:
    observations: list[RawObservation]
    captures: list[Capture]
    provider_last_updated: date | None
    metadata: SeriesMetadata | None = None


@runtime_checkable
class EconomicSeriesSource(Protocol):
    profile: ProviderProfile

    def fetch_series(self, request: SeriesRequest) -> SeriesFetch: ...


# --- Price files ------------------------------------------------------------------------------


@dataclass(frozen=True)
class RawPriceRow:
    """One CSV row as read: column name → the text in the cell."""

    line: int
    fields: dict[str, str]


@dataclass(frozen=True)
class PriceFileRead:
    rows: list[RawPriceRow]
    captures: list[Capture]
    columns: list[str]


@runtime_checkable
class PriceFileSource(Protocol):
    profile: ProviderProfile

    def read_price_file(self, path: Path) -> PriceFileRead: ...
