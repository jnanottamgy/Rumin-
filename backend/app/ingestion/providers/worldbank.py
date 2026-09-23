"""World Bank Indicators API (v2) — economic series by indicator and country.

Request: ``GET https://api.worldbank.org/v2/country/{ISO3}/indicator/{CODE}
?format=json&per_page=…&page=…&date=START:END``. No API key.

Response: a two-element JSON array — ``[metadata, records]``. The metadata carries
``page``, ``pages``, ``per_page``, ``total``, ``sourceid`` and ``lastupdated``; each record
carries ``indicator{id,value}``, ``country{id,value}``, ``countryiso3code``, ``date``,
``value`` (a number, or null when the period has no value), ``unit``, ``obs_status`` and
``decimal``. Errors arrive as ``[{"message": [{"id", "key", "value"}]}]``, often with
HTTP 200, so the body is always checked.

Numbers are parsed as ``Decimal`` straight from the JSON text: nothing passes through
binary floating point.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlencode

from app.db.base import utcnow
from app.domain.enums import CaptureKind, Frequency, ProviderAuth, ProviderKind
from app.ingestion.errors import InvalidRequestError, MalformedResponseError, ProviderError
from app.ingestion.http import HttpClient
from app.ingestion.logs import log_event
from app.ingestion.providers.base import (
    Capture,
    ProviderProfile,
    RawObservation,
    SeriesFetch,
    SeriesMetadata,
    SeriesRequest,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.worldbank.org/v2"

PROFILE = ProviderProfile(
    id="worldbank",
    name="World Bank — Indicators API (v2)",
    kind=ProviderKind.API,
    description=(
        "The World Bank's public API for its development indicators, including the World "
        "Development Indicators (WDI)."
    ),
    authentication=ProviderAuth.NONE,
    data_categories=(
        "Macroeconomic, financial-sector, trade, social and environmental indicators by "
        "country and region."
    ),
    coverage=(
        "About 200 economies plus regional and income-group aggregates. Most WDI series are "
        "annual; many start in 1960."
    ),
    update_frequency=(
        "WDI is refreshed several times a year and any value can be revised in an update. "
        "The API reports each source's last update date, which RUMIN records."
    ),
    rate_limit_policy=(
        "The official documentation reviewed for Phase 2 states no numeric limit (a "
        "third-party page claims about 1,000 requests per hour; unverified). RUMIN sends at "
        "most one request per second, retries only temporary failures (at most three "
        "retries, with backoff) and honours Retry-After."
    ),
    licensing=(
        "World Bank datasets are licensed under Creative Commons Attribution 4.0 (CC BY 4.0) "
        "unless labelled otherwise. Some indicators supplied by third parties may carry "
        "additional conditions, stated in the indicator's metadata."
    ),
    commercial_use=(
        "Permitted under CC BY 4.0 with attribution in the form 'The World Bank: <dataset>: "
        "<source>', without implying World Bank endorsement. Check each indicator's metadata "
        "for third-party conditions before commercial use."
    ),
    reliability=(
        "Official statistics compiled by the World Bank from national and international "
        "sources. Values are revised as sources update. Not real-time."
    ),
    known_limitations=(
        "Mostly annual data with publication lags of a year or more, so recent years are "
        "often missing; definitions and country aggregates change between releases; errors "
        "are returned inside the response body."
    ),
    homepage_url="https://data.worldbank.org/",
    documentation_url=(
        "https://datahelpdesk.worldbank.org/knowledgebase/articles/"
        "889392-about-the-indicators-api-documentation"
    ),
    terms_url="https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets",
)

INDICATOR_CODE = re.compile(r"^[A-Z][A-Z0-9_]*(\.[A-Z0-9_]+)*$")
COUNTRY_ISO3 = re.compile(r"^[A-Z]{3}$")
PERIOD_FORMATS: dict[Frequency, re.Pattern[str]] = {
    Frequency.ANNUAL: re.compile(r"^\d{4}$"),
    Frequency.QUARTERLY: re.compile(r"^\d{4}Q[1-4]$"),
    Frequency.MONTHLY: re.compile(r"^\d{4}M(0[1-9]|1[0-2])$"),
}


def _jsonable(value: Any) -> Any:
    """Original record values in a JSON-safe form (decimals keep their exact digits)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _as_int(value: Any, name: str) -> int:
    # The API has been seen to send some counters as strings ("per_page": "50").
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise MalformedResponseError(f"The response metadata has an invalid '{name}'.")


class WorldBankProvider:
    profile = PROFILE

    def __init__(
        self,
        client: HttpClient,
        *,
        base_url: str = BASE_URL,
        per_page: int = 1000,
        max_pages: int = 20,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.per_page = per_page
        self.max_pages = max_pages
        self.clock = clock

    # --- Public -------------------------------------------------------------------------

    def fetch_series(self, request: SeriesRequest) -> SeriesFetch:
        country = self._check_request(request)
        path = f"/country/{quote(country)}/indicator/{quote(request.provider_code)}"
        observations: list[RawObservation] = []
        captures: list[Capture] = []
        last_updated: date | None = None
        page = 1
        while True:
            params = {
                "format": "json",
                "per_page": str(self.per_page),
                "page": str(page),
                "date": f"{request.start}:{request.end}",
            }
            response = self.client.get(f"{self.base_url}{path}?{urlencode(params, safe=':')}")
            meta, records = self._parse_data_page(response.body)
            last_updated = self._last_updated(meta) or last_updated
            captures.append(
                Capture(
                    kind=CaptureKind.HTTP_RESPONSE,
                    locator=response.url,
                    body=response.body,
                    received_at=self.clock(),
                    http_status=response.status,
                    content_type=response.headers.get("content-type"),
                    request_params=params,
                    provider_last_updated=last_updated,
                )
            )
            index = len(captures) - 1
            observations.extend(self._raw_observation(record, index) for record in records)
            pages = _as_int(meta.get("pages", 0), "pages")
            if page >= pages:
                break
            if page >= self.max_pages:
                raise MalformedResponseError(
                    f"The response has more than {self.max_pages} pages; narrow the period range."
                )
            page += 1

        return SeriesFetch(
            observations=observations,
            captures=captures,
            provider_last_updated=last_updated,
            metadata=self._fetch_metadata(request.provider_code, captures),
        )

    # --- Parsing ------------------------------------------------------------------------

    def _check_request(self, request: SeriesRequest) -> str:
        """Validate everything that goes into the URL; returns the country code."""
        if not INDICATOR_CODE.match(request.provider_code):
            raise InvalidRequestError(
                f"'{request.provider_code}' is not a World Bank indicator code."
            )
        country = request.country_iso3
        if country is None or not COUNTRY_ISO3.match(country):
            raise InvalidRequestError("World Bank series need an ISO 3166-1 alpha-3 country code.")
        pattern = PERIOD_FORMATS.get(request.frequency)
        if pattern is None:
            raise InvalidRequestError(f"The World Bank API has no {request.frequency} periods.")
        for period in (request.start, request.end):
            if not pattern.match(period):
                raise InvalidRequestError(f"'{period}' is not a {request.frequency} period.")
        return country

    @staticmethod
    def _decode(body: bytes) -> Any:
        try:
            return json.loads(body, parse_float=Decimal, parse_int=Decimal)
        except (ValueError, UnicodeDecodeError) as error:
            raise MalformedResponseError(
                "The World Bank API returned a body that is not JSON."
            ) from error

    def _parse_data_page(self, body: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        payload = self._decode(body)
        self._raise_for_error_envelope(payload)
        if not (isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], dict)):
            raise MalformedResponseError(
                "The World Bank response does not have the expected shape."
            )
        meta, records = payload
        if records is None:  # the API sends null instead of [] when nothing matches
            return meta, []
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise MalformedResponseError(
                "The World Bank response's records are not a list of objects."
            )
        return meta, records

    @staticmethod
    def _raise_for_error_envelope(payload: Any) -> None:
        if (
            isinstance(payload, list)
            and payload
            and isinstance(payload[0], dict)
            and "message" in payload[0]
        ):
            messages = payload[0].get("message") or []
            parts = []
            for message in messages if isinstance(messages, list) else []:
                if isinstance(message, dict):
                    key = str(message.get("key", "")).strip()
                    value = str(message.get("value", "")).strip()
                    code = str(message.get("id", "")).strip()
                    parts.append(f"{code} {key}: {value}".strip())
            detail = "; ".join(parts)[:300] or "no details"
            raise InvalidRequestError(f"The World Bank API rejected the request ({detail}).")

    @staticmethod
    def _last_updated(meta: dict[str, Any]) -> date | None:
        value = meta.get("lastupdated")
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None

    @staticmethod
    def _raw_observation(record: dict[str, Any], capture_index: int) -> RawObservation:
        indicator = record.get("indicator")
        return RawObservation(
            period=record.get("date"),
            value=record.get("value"),
            series_code=indicator.get("id") if isinstance(indicator, dict) else None,
            country_iso3=record.get("countryiso3code"),
            unit=record.get("unit"),
            flags=record.get("obs_status"),
            original=_jsonable(
                {
                    key: record.get(key)
                    for key in ("date", "value", "unit", "obs_status", "decimal", "countryiso3code")
                }
            ),
            capture_index=capture_index,
        )

    def _fetch_metadata(self, code: str, captures: list[Capture]) -> SeriesMetadata | None:
        """The indicator's definition and original source. Optional: if it cannot be
        fetched the series is still ingested, and the gap is logged."""
        try:
            response = self.client.get(
                f"{self.base_url}/indicator/{quote(code)}?{urlencode({'format': 'json'})}"
            )
            payload = self._decode(response.body)
            self._raise_for_error_envelope(payload)
        except ProviderError as error:
            log_event(
                logger,
                "provider.metadata_unavailable",
                level=logging.WARNING,
                provider=PROFILE.id,
                series=code,
                error=error.code,
            )
            return None
        captures.append(
            Capture(
                kind=CaptureKind.HTTP_RESPONSE,
                locator=response.url,
                body=response.body,
                received_at=self.clock(),
                http_status=response.status,
                content_type=response.headers.get("content-type"),
                request_params={"format": "json"},
            )
        )
        if not (
            isinstance(payload, list)
            and len(payload) == 2
            and isinstance(payload[1], list)
            and payload[1]
            and isinstance(payload[1][0], dict)
        ):
            return None
        entry = payload[1][0]

        def text(key: str) -> str | None:
            value = entry.get(key)
            return value.strip() or None if isinstance(value, str) else None

        return SeriesMetadata(
            name=text("name"),
            description=text("sourceNote"),
            source_organization=text("sourceOrganization"),
        )
