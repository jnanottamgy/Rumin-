"""ASGI middleware: request context, security headers and request-size limits.

These are written as plain ASGI middleware (rather than ``BaseHTTPMiddleware``) so they
work with streaming bodies and add negligible overhead.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_payload
from app.core.logging import printable, request_id_ctx
from app.core.metrics import Metrics

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Interactive API docs load Swagger UI / ReDoc assets, so they cannot use the strict
# Content-Security-Policy applied to JSON responses.
_DOCS_PATHS = ("/docs", "/redoc")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
_API_CSP = "default-src 'none'; frame-ancestors 'none'"

# A client chooses the method; a label must not multiply with every token it invents.
_KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def _method(scope: Scope) -> str:
    method: str = scope.get("method", "")
    return method if method in _KNOWN_METHODS else "OTHER"


class RequestContextMiddleware:
    """Assigns a request ID, adds security headers, logs access and catches crashes.

    * The request ID is taken from an incoming ``X-Request-ID`` header when it is safe
      to log, otherwise generated. It is echoed in the response and in every log line.
    * Any unhandled exception is logged with its traceback and converted into a generic
      500 response in the standard error envelope — internals never reach the client.
    """

    def __init__(self, app: ASGIApp, metrics: Metrics | None = None) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.metrics is not None:
            self.metrics.in_flight.add(1)
        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        path: str = scope.get("path", "")
        method = _method(scope)
        logged_path = printable(path)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                for name, value in _SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if not path.startswith(_DOCS_PATHS):
                    headers.setdefault("Content-Security-Policy", _API_CSP)
                if path.startswith("/api/"):
                    # People, the audit trail and conversations must not stay in a shared
                    # browser's cache.
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("Unhandled error while processing %s %s", method, logged_path)
            if response_started:
                raise  # Too late to send an error response; let the server close it.
            response = JSONResponse(
                error_payload(500, "An unexpected error occurred. The error has been logged."),
                status_code=500,
            )
            await response(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            duration_ms = elapsed * 1000
            logger.info(
                "%s %s -> %d (%.1f ms)",
                method,
                logged_path,
                status_code,
                duration_ms,
                extra={
                    "http": {
                        "method": method,
                        "path": logged_path,
                        "status": status_code,
                        "duration_ms": round(duration_ms, 1),
                    }
                },
            )
            if self.metrics is not None:
                route = _route_template(scope)
                self.metrics.requests.inc(method, route, str(status_code))
                self.metrics.durations.observe(elapsed, method, route)
                self.metrics.in_flight.add(-1)
            request_id_ctx.reset(token)


def _route_template(scope: Scope) -> str:
    """The matched route's template (``/api/v1/scenarios/{scenario_id}``), never the raw
    path: a label must not multiply with every identifier a client sends.

    Routes of an included router know only their own part (``/scenarios/{scenario_id}``);
    the router's prefix is what precedes the part of the path the route matched — fixed
    text, since the route matched only below that prefix."""
    route = scope.get("route")
    template = getattr(route, "path_format", None)
    regex = getattr(route, "path_regex", None)
    if not isinstance(template, str) or not template or regex is None:
        return "unmatched"
    path: str = scope.get("path", "")
    for index, character in enumerate(path):
        if character == "/" and regex.match(path[index:]):
            return path[:index] + template
    return template


class BodySizeLimitMiddleware:
    """Rejects request bodies larger than ``max_bytes`` with HTTP 413.

    The declared ``Content-Length`` is checked first; bodies without one (chunked
    transfer encoding) are counted while being read, so the limit cannot be bypassed.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        chunks: list[bytes] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return  # Client went away before sending the full body.
            chunk = message.get("body", b"")
            received += len(chunk)
            if received > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()  # Lets the app observe client disconnects.

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            error_payload(413, f"The request body exceeds the limit of {self.max_bytes} bytes."),
            status_code=413,
        )
        await response(scope, receive, send)


_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CrossSiteRequestMiddleware:
    """Refuses state-changing API requests that a browser sends from another site (CSRF).

    Sessions live in a cookie, so a page on another site could make a signed-in browser
    send a request. For ``POST``, ``PUT``, ``PATCH`` and ``DELETE`` under ``/api/`` this
    refuses (403) a request whose Fetch-Metadata says ``cross-site`` or whose ``Origin`` is
    neither this server's own origin nor one of the configured CORS origins. Requests with
    neither header come from programs rather than browsers, which hold no ambient cookies,
    and pass. The session cookie is also ``SameSite=Lax``; this is the second defence.
    """

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed = {origin.rstrip("/") for origin in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in _UNSAFE_METHODS
            or not scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        own = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
        cross_site = headers.get("sec-fetch-site") == "cross-site"
        foreign = origin is not None and origin.rstrip("/") not in self.allowed | {own}
        if cross_site or foreign:
            logger.warning(
                "Refused a cross-site %s %s (origin %s)",
                scope["method"],
                printable(scope["path"]),
                printable(origin or "none"),
            )
            response = JSONResponse(
                error_payload(403, "Requests that change data must come from RUMIN's own pages."),
                status_code=403,
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
