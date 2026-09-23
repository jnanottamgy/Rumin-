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
from app.core.logging import request_id_ctx

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


class RequestContextMiddleware:
    """Assigns a request ID, adds security headers, logs access and catches crashes.

    * The request ID is taken from an incoming ``X-Request-ID`` header when it is safe
      to log, otherwise generated. It is echoed in the response and in every log line.
    * Any unhandled exception is logged with its traceback and converted into a generic
      500 response in the standard error envelope — internals never reach the client.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        path: str = scope.get("path", "")
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
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("Unhandled error while processing %s %s", scope["method"], path)
            if response_started:
                raise  # Too late to send an error response; let the server close it.
            response = JSONResponse(
                error_payload(500, "An unexpected error occurred. The error has been logged."),
                status_code=500,
            )
            await response(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info("%s %s -> %d (%.1f ms)", scope["method"], path, status_code, duration_ms)
            request_id_ctx.reset(token)


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
