"""World Bank adapter against synthetic responses in the documented v2 format."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest

from app.domain.enums import CaptureKind, Frequency
from app.ingestion.errors import InvalidRequestError, MalformedResponseError
from app.ingestion.http import TransportError
from app.ingestion.providers.base import EconomicSeriesSource, SeriesRequest
from app.ingestion.providers.worldbank import WorldBankProvider
from tests.fakes import (
    ScriptedTransport,
    make_client,
    response,
    wb_error,
    wb_indicator,
    wb_page,
    wb_record,
)

REQUEST = SeriesRequest(
    provider_code="FP.CPI.TOTL.ZG",
    country_iso3="IND",
    frequency=Frequency.ANNUAL,
    start="2019",
    end="2023",
)


def provider_for(
    *steps: object, max_attempts: int = 1
) -> tuple[WorldBankProvider, ScriptedTransport]:
    transport = ScriptedTransport(list(steps))  # type: ignore[arg-type]
    client, _ = make_client(transport, max_attempts=max_attempts)
    return WorldBankProvider(client, base_url="https://api.worldbank.test/v2"), transport


def test_is_an_economic_series_source() -> None:
    provider, _ = provider_for()
    assert isinstance(provider, EconomicSeriesSource)
    assert provider.profile.id == "worldbank"


def test_builds_the_documented_request() -> None:
    provider, transport = provider_for(
        response(wb_page([wb_record("2023", "1.5")])), response(wb_indicator())
    )
    provider.fetch_series(REQUEST)
    url = urlsplit(transport.requests[0][0])
    assert url.path == "/v2/country/IND/indicator/FP.CPI.TOTL.ZG"
    assert parse_qs(url.query) == {
        "format": ["json"],
        "per_page": ["1000"],
        "page": ["1"],
        "date": ["2019:2023"],
    }
    assert urlsplit(transport.requests[1][0]).path == "/v2/indicator/FP.CPI.TOTL.ZG"


def test_keeps_values_exact_and_missing_values_missing() -> None:
    provider, _ = provider_for(
        response(
            wb_page(
                [
                    wb_record("2023", "3.14159265358979323"),  # more digits than a float holds
                    wb_record("2022", None),
                    wb_record("2021", "12"),
                ]
            )
        ),
        response(wb_indicator(source_organization="Synthetic statistics office")),
    )
    fetch = provider.fetch_series(REQUEST)
    values = {raw.period: raw.value for raw in fetch.observations}
    assert values == {
        "2023": Decimal("3.14159265358979323"),
        "2022": None,
        "2021": Decimal("12"),
    }
    first = fetch.observations[0]
    assert first.series_code == "FP.CPI.TOTL.ZG"
    assert first.country_iso3 == "IND"
    assert first.original["value"] == "3.14159265358979323"  # original literal kept
    assert fetch.provider_last_updated == date(2026, 7, 1)
    assert fetch.metadata is not None
    assert fetch.metadata.source_organization == "Synthetic statistics office"


def test_captures_every_response_it_used() -> None:
    provider, _ = provider_for(
        response(wb_page([wb_record("2023", "1.5")], page=1, pages=2)),
        response(wb_page([wb_record("2022", "1.4")], page=2, pages=2)),
        response(wb_indicator()),
    )
    fetch = provider.fetch_series(REQUEST)
    assert [raw.period for raw in fetch.observations] == ["2023", "2022"]
    assert len(fetch.captures) == 3  # two data pages and the indicator metadata
    assert all(capture.kind is CaptureKind.HTTP_RESPONSE for capture in fetch.captures)
    assert fetch.captures[0].request_params == {
        "format": "json",
        "per_page": "1000",
        "page": "1",
        "date": "2019:2023",
    }


def test_treats_an_empty_result_as_no_observations() -> None:
    provider, _ = provider_for(response(wb_page([])), response(wb_indicator()))
    assert provider.fetch_series(REQUEST).observations == []


def test_reports_the_error_envelope_even_with_http_200() -> None:
    provider, _ = provider_for(response(wb_error()))
    with pytest.raises(InvalidRequestError, match="120 Invalid value"):
        provider.fetch_series(REQUEST)


@pytest.mark.parametrize(
    "body",
    [
        "<html>maintenance</html>",
        '{"unexpected": "object"}',
        '[{"page": 1}]',
        '[{"page": 1, "pages": 1}, "not a list"]',
        '[{"page": 1, "pages": "many"}, []]',
    ],
)
def test_rejects_malformed_responses(body: str) -> None:
    provider, _ = provider_for(response(body))
    with pytest.raises(MalformedResponseError):
        provider.fetch_series(REQUEST)


def test_refuses_unbounded_pagination() -> None:
    provider, _ = provider_for(*[response(wb_page([], page=n, pages=99)) for n in range(1, 4)])
    provider.max_pages = 3
    with pytest.raises(MalformedResponseError, match="more than 3 pages"):
        provider.fetch_series(REQUEST)


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_code": "fp.cpi; DROP"},
        {"provider_code": "../indicator"},
        {"country_iso3": "IN"},
        {"country_iso3": None},
        {"start": "19"},
        {"end": "2023M01"},  # a monthly period for an annual series
        {"frequency": Frequency.DAILY},
    ],
)
def test_validates_requests_before_calling_the_provider(overrides: dict[str, object]) -> None:
    provider, transport = provider_for()
    values = {**REQUEST.__dict__, **overrides}
    with pytest.raises(InvalidRequestError):
        provider.fetch_series(SeriesRequest(**values))
    assert transport.requests == []


def test_still_returns_data_when_only_the_metadata_request_fails() -> None:
    provider, _ = provider_for(
        response(wb_page([wb_record("2023", "1.5")])),
        TransportError("connection", "refused"),
    )
    fetch = provider.fetch_series(REQUEST)
    assert len(fetch.observations) == 1
    assert fetch.metadata is None
