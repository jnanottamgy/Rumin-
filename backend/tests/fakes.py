"""Test doubles for provider tests.

Every response built here is SYNTHETIC. Its structure follows the World Bank Indicators
API v2 format as documented; its numbers are made up for tests and are not World Bank
data. Nothing in this module is ever loaded into a real database.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.ingestion.http import HttpClient, HttpResponse, RateLimiter, RetryPolicy, TransportError

Step = HttpResponse | TransportError


def response(
    body: bytes | str | Any = b"", status: int = 200, headers: Mapping[str, str] | None = None
) -> HttpResponse:
    if not isinstance(body, bytes | str):
        body = json.dumps(body)
    if isinstance(body, str):
        body = body.encode()
    return HttpResponse(
        status=status,
        headers={
            k.lower(): v for k, v in (headers or {"Content-Type": "application/json"}).items()
        },
        body=body,
        url="",
        elapsed_ms=1.0,
    )


@dataclass
class ScriptedTransport:
    """Answers requests from a script; records every URL and header it was sent."""

    steps: list[Step]
    requests: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        self.requests.append((url, dict(headers)))
        if not self.steps:
            raise AssertionError(f"Unexpected request: {url}")
        step = self.steps.pop(0)
        if isinstance(step, TransportError):
            raise step
        return HttpResponse(step.status, step.headers, step.body, url, step.elapsed_ms)


@dataclass
class Sleeps:
    calls: list[float] = field(default_factory=list)

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_client(transport: ScriptedTransport, **policy: Any) -> tuple[HttpClient, Sleeps]:
    sleeps = Sleeps()
    client = HttpClient(
        transport=transport,
        limiter=RateLimiter(0, sleep=sleeps),
        policy=RetryPolicy(**policy),
        provider="test",
        sleep=sleeps,
        rand=lambda: 1.0,  # deterministic: always the maximum backoff
    )
    return client, sleeps


# --- Synthetic World Bank payloads -------------------------------------------------------------


def wb_record(
    period: str,
    value: str | None,
    *,
    code: str = "FP.CPI.TOTL.ZG",
    iso3: str = "IND",
    unit: str = "",
    obs_status: str = "",
) -> str:
    """One record as raw JSON text, so decimal literals keep their exact digits."""
    literal = "null" if value is None else value
    return (
        f'{{"indicator": {{"id": "{code}", "value": "Synthetic indicator"}}, '
        f'"country": {{"id": "IN", "value": "Synthetic country"}}, '
        f'"countryiso3code": "{iso3}", "date": "{period}", "value": {literal}, '
        f'"unit": "{unit}", "obs_status": "{obs_status}", "decimal": 1}}'
    )


def wb_page(
    records: list[str],
    *,
    page: int = 1,
    pages: int = 1,
    lastupdated: str = "2026-07-01",
    per_page: str = "1000",
) -> str:
    meta = (
        f'{{"page": {page}, "pages": {pages}, "per_page": "{per_page}", '
        f'"total": {len(records)}, "sourceid": "2", "lastupdated": "{lastupdated}"}}'
    )
    body = "null" if not records else "[" + ", ".join(records) + "]"
    return f"[{meta}, {body}]"


def wb_error(
    code: str = "120",
    key: str = "Invalid value",
    value: str = "The provided parameter value is not valid",
) -> str:
    return json.dumps([{"message": [{"id": code, "key": key, "value": value}]}])


def wb_indicator(
    code: str = "FP.CPI.TOTL.ZG",
    name: str = "Synthetic indicator name",
    source_organization: str = "Synthetic source organisation",
) -> str:
    return json.dumps(
        [
            {"page": 1, "pages": 1, "per_page": "50", "total": 1},
            [
                {
                    "id": code,
                    "name": name,
                    "unit": "",
                    "source": {"id": "2", "value": "World Development Indicators"},
                    "sourceNote": "Synthetic definition text.",
                    "sourceOrganization": source_organization,
                    "topics": [],
                }
            ],
        ]
    )
