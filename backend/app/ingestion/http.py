"""HTTP for data providers: one transport, polite throttling, bounded retries.

* **Transport** — a tiny interface over the standard library's ``urllib`` (no extra
  dependency). Tests replace it with a scripted fake, so no test depends on the network.
* **Throttling** — at most one request per ``min_interval`` seconds per provider, so a
  run never bursts at the provider.
* **Retries** — only for failures that can be temporary (connection errors, timeouts,
  HTTP 429 and 5xx), at most ``max_attempts`` attempts in total, with exponential
  backoff and jitter. A provider's ``Retry-After`` is honoured, up to a cap; anything
  asking for a longer wait fails the request instead of stalling the run.
* **Secrets** — URLs are redacted before they are logged or stored.
"""

from __future__ import annotations

import logging
import random
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.ingestion.errors import (
    AuthenticationError,
    InvalidRequestError,
    MalformedResponseError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.ingestion.logs import log_event

logger = logging.getLogger(__name__)

USER_AGENT = "RUMIN-data-ingestion/0.2 (+https://github.com/jnanottamgy/Rumin-)"
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
SECRET_PARAMETERS = frozenset(
    {"api_key", "apikey", "key", "token", "access_token", "auth", "password", "secret"}
)


def redact_url(url: str) -> str:
    """The URL with the values of credential-like query parameters replaced."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = [
        (name, "[redacted]" if name.lower() in SECRET_PARAMETERS else value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(query, safe="[]:,")))


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]  # lower-cased names
    body: bytes
    url: str  # redacted
    elapsed_ms: float


class TransportError(Exception):
    """The request did not produce an HTTP response at all."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind  # "timeout" or "connection"


class HttpTransport(Protocol):
    """Sends one GET request and returns the response, whatever its status. Raises
    ``TransportError`` only when no response arrived at all."""

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse: ...


class UrllibTransport:
    """The production transport, on the standard library's ``urllib``. It honours the
    ``HTTPS_PROXY`` environment variable, like most HTTP clients."""

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        request = urllib.request.Request(url, headers=dict(headers), method="GET")  # noqa: S310 (https URLs built by providers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as raw:  # noqa: S310
                return self._read(raw.status, raw.headers.items(), raw, url, started)
        except urllib.error.HTTPError as error:
            # 4xx/5xx still carry a response worth reading (e.g. an error envelope).
            with error:
                return self._read(error.code, error.headers.items(), error, url, started)
        except TimeoutError as error:
            raise TransportError("timeout", "The provider did not respond in time.") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError | socket.timeout):
                raise TransportError("timeout", "The provider did not respond in time.") from error
            raise TransportError("connection", "The provider could not be reached.") from error

    @staticmethod
    def _read(
        status: int,
        headers: object,
        stream: object,
        url: str,
        started: float,
    ) -> HttpResponse:
        body = stream.read(MAX_RESPONSE_BYTES + 1)  # type: ignore[attr-defined]
        if len(body) > MAX_RESPONSE_BYTES:
            raise MalformedResponseError(
                f"The response exceeded the {MAX_RESPONSE_BYTES // (1024 * 1024)} MB limit."
            )
        return HttpResponse(
            status=status,
            headers={name.lower(): value for name, value in headers},  # type: ignore[attr-defined]
            body=body,
            url=redact_url(url),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )


class RateLimiter:
    """Keeps at least ``min_interval`` seconds between consecutive requests."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self.min_interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 1.0
    max_delay: float = 30.0
    # A provider asking to wait longer than this fails the request instead.
    max_retry_after: float = 60.0

    def backoff(self, attempt: int, rand: Callable[[], float]) -> float:
        """Full jitter: a random delay up to base * 2^(attempt - 1), capped."""
        ceiling = min(self.max_delay, self.base_delay * float(2 ** (attempt - 1)))
        return rand() * ceiling


def parse_retry_after(value: str | None, now: float | None = None) -> float | None:
    """Seconds to wait from a ``Retry-After`` header (delta-seconds or an HTTP date)."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    reference = time.time() if now is None else now
    return max(0.0, moment.timestamp() - reference)


@dataclass
class HttpClient:
    """GET with throttling, bounded retries and typed errors. Counts what it does."""

    transport: HttpTransport
    limiter: RateLimiter
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout: float = 20.0
    provider: str = "provider"
    sleep: Callable[[float], None] = time.sleep
    rand: Callable[[], float] = random.random
    request_count: int = 0
    bytes_received: int = 0

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> HttpResponse:
        request_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            **(headers or {}),
        }
        safe_url = redact_url(url)
        for attempt in range(1, self.policy.max_attempts + 1):
            self.limiter.wait()
            self.request_count += 1
            try:
                response = self.transport.get(url, request_headers, self.timeout)
            except TransportError as error:
                failure: ProviderError = (
                    ProviderTimeoutError(str(error))
                    if error.kind == "timeout"
                    else ProviderUnavailableError(str(error))
                )
                self._retry_or_raise(failure, attempt, None, safe_url)
                continue

            self.bytes_received += len(response.body)
            log_event(
                logger,
                "provider.response",
                provider=self.provider,
                url=safe_url,
                status=response.status,
                attempt=attempt,
                ms=round(response.elapsed_ms),
            )
            if response.status in RETRYABLE_STATUSES:
                retry_after = parse_retry_after(response.headers.get("retry-after"))
                failure = (
                    RateLimitedError(
                        "The provider's rate limit was reached.",
                        status=429,
                        retry_after=retry_after,
                    )
                    if response.status == 429
                    else ProviderUnavailableError(
                        f"The provider answered with HTTP {response.status}.",
                        status=response.status,
                    )
                )
                self._retry_or_raise(failure, attempt, retry_after, safe_url)
                continue
            if response.status in (401, 403):
                raise AuthenticationError(
                    f"The provider refused access (HTTP {response.status}).",
                    status=response.status,
                )
            if response.status >= 400:
                raise InvalidRequestError(
                    f"The provider rejected the request (HTTP {response.status}).",
                    status=response.status,
                )
            return response
        raise AssertionError("unreachable")  # pragma: no cover - the loop always returns/raises

    def _retry_or_raise(
        self, failure: ProviderError, attempt: int, retry_after: float | None, url: str
    ) -> None:
        if attempt >= self.policy.max_attempts:
            raise failure
        if retry_after is not None and retry_after > self.policy.max_retry_after:
            raise failure  # waiting that long would stall the run; report it instead
        delay = retry_after if retry_after is not None else self.policy.backoff(attempt, self.rand)
        log_event(
            logger,
            "provider.retry",
            level=logging.WARNING,
            provider=self.provider,
            url=url,
            error=failure.code,
            attempt=attempt,
            wait_s=round(delay, 2),
        )
        self.sleep(delay)
