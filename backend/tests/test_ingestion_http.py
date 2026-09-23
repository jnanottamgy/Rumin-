"""The provider HTTP client: throttling, bounded retries, typed errors, no leaked secrets."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from email.utils import format_datetime

import pytest

from app.ingestion.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.ingestion.http import RateLimiter, TransportError, parse_retry_after, redact_url
from tests.fakes import ScriptedTransport, make_client, response

URL = "https://provider.example/v1/series?id=ABC"


def test_redacts_credentials_in_urls() -> None:
    url = "https://provider.example/data?series=A&api_key=abc123&Token=xyz&page=2"
    redacted = redact_url(url)
    assert "abc123" not in redacted
    assert "xyz" not in redacted
    assert "series=A" in redacted
    assert "page=2" in redacted
    assert redact_url("https://provider.example/data") == "https://provider.example/data"


def test_returns_a_successful_response_after_one_request() -> None:
    transport = ScriptedTransport([response({"ok": True})])
    client, sleeps = make_client(transport)
    assert client.get(URL).status == 200
    assert client.request_count == 1
    assert sleeps.calls == []
    assert transport.requests[0][1]["User-Agent"].startswith("RUMIN-data-ingestion/")


def test_retries_server_errors_with_bounded_exponential_backoff() -> None:
    transport = ScriptedTransport(
        [response(status=503), response(status=502), response({"ok": True})]
    )
    client, sleeps = make_client(transport, base_delay=1.0, max_delay=30.0)
    assert client.get(URL).status == 200
    assert client.request_count == 3
    assert sleeps.calls == [1.0, 2.0]  # base * 2^(attempt - 1), full jitter at its maximum


def test_gives_up_after_the_maximum_number_of_attempts() -> None:
    transport = ScriptedTransport([response(status=500)] * 4)
    client, sleeps = make_client(transport, max_attempts=4)
    with pytest.raises(ProviderUnavailableError, match="HTTP 500"):
        client.get(URL)
    assert client.request_count == 4
    assert len(sleeps.calls) == 3  # never an endless loop


def test_honours_retry_after_on_rate_limits() -> None:
    transport = ScriptedTransport(
        [response(status=429, headers={"Retry-After": "7"}), response({"ok": True})]
    )
    client, sleeps = make_client(transport)
    assert client.get(URL).status == 200
    assert sleeps.calls == [7.0]


def test_fails_instead_of_stalling_when_asked_to_wait_too_long() -> None:
    transport = ScriptedTransport([response(status=429, headers={"Retry-After": "3600"})])
    client, sleeps = make_client(transport, max_retry_after=60.0)
    with pytest.raises(RateLimitedError) as caught:
        client.get(URL)
    assert caught.value.retry_after == 3600.0
    assert sleeps.calls == []
    assert client.request_count == 1


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, InvalidRequestError),
        (404, InvalidRequestError),
        (401, AuthenticationError),
        (403, AuthenticationError),
    ],
)
def test_client_errors_are_not_retried(status: int, error: type[Exception]) -> None:
    transport = ScriptedTransport([response(status=status)])
    client, sleeps = make_client(transport)
    with pytest.raises(error):
        client.get(URL)
    assert client.request_count == 1
    assert sleeps.calls == []


def test_retries_timeouts_and_reports_them_as_timeouts() -> None:
    transport = ScriptedTransport([TransportError("timeout", "slow")] * 2)
    client, _ = make_client(transport, max_attempts=2)
    with pytest.raises(ProviderTimeoutError):
        client.get(URL)
    assert client.request_count == 2


def test_connection_failures_become_provider_unavailable() -> None:
    transport = ScriptedTransport([TransportError("connection", "refused")])
    client, _ = make_client(transport, max_attempts=1)
    with pytest.raises(ProviderUnavailableError):
        client.get(URL)


def test_counts_bytes_received() -> None:
    transport = ScriptedTransport([response(b"12345")])
    client, _ = make_client(transport)
    client.get(URL)
    assert client.bytes_received == 5


def test_rate_limiter_keeps_a_minimum_interval() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(1.0, clock=lambda: now[0], sleep=sleep)
    limiter.wait()  # first request: no wait
    now[0] += 0.25
    limiter.wait()  # 0.25 s later: waits the remaining 0.75 s
    now[0] += 5.0
    limiter.wait()  # long after: no wait
    assert sleeps == [0.75]


def test_parses_retry_after_as_seconds_or_http_date() -> None:
    assert parse_retry_after("12") == 12.0
    moment = datetime(2026, 9, 23, 12, 0, 30, tzinfo=UTC)
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC).timestamp()
    assert parse_retry_after(format_datetime(moment, usegmt=True), now=now) == 30.0
    assert parse_retry_after("not a date") is None
    assert parse_retry_after(None) is None


def test_logs_never_contain_credentials(caplog: pytest.LogCaptureFixture) -> None:
    transport = ScriptedTransport([response(status=503), response({"ok": True})])
    client, _ = make_client(transport)
    with caplog.at_level(logging.INFO, logger="app.ingestion"):
        client.get("https://provider.example/data?api_key=very-secret-key&id=A")
    assert "very-secret-key" not in caplog.text
    assert "event=provider.retry" in caplog.text
    assert "event=provider.response" in caplog.text
