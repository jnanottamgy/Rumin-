"""Logging configuration.

Every log line carries the current request ID (see ``RequestContextMiddleware``) so a
single request can be traced across log statements. Only the ``app`` logger hierarchy
is configured, which leaves uvicorn's own loggers untouched.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())

    app_logger = logging.getLogger("app")
    app_logger.handlers[:] = [handler]
    app_logger.setLevel(level)
    app_logger.propagate = False
