"""Typed failures of data providers.

Every way a provider can fail maps to one of these, with a stable ``code`` (stored on
job items and shown to users) and whether retrying can help. Messages are written to be
safe to store and display: they never contain credentials or response bodies.
"""

from __future__ import annotations


class ProviderError(Exception):
    code = "provider_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached or answered with a server error (5xx)."""

    code = "provider_unavailable"
    retryable = True


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"
    retryable = True


class RateLimitedError(ProviderError):
    """The provider asked us to slow down (HTTP 429)."""

    code = "rate_limited"
    retryable = True


class AuthenticationError(ProviderError):
    """Credentials are missing, invalid or not allowed to access the resource."""

    code = "authentication_failed"


class InvalidRequestError(ProviderError):
    """The provider rejected the request itself (unknown series, bad parameter, 4xx)."""

    code = "invalid_request"


class MalformedResponseError(ProviderError):
    """The response could not be understood: not JSON, wrong shape, or too large."""

    code = "malformed_response"


class ImportFileError(ProviderError):
    """A file offered for import cannot be read as the declared format."""

    code = "invalid_file"
