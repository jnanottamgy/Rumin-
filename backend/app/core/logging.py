"""Logging configuration.

Every log line carries the current request ID (see ``RequestContextMiddleware``) so a
single request can be traced across log statements. Only the ``app`` logger hierarchy
is configured in text mode, which leaves uvicorn's own loggers untouched.

``json`` writes one JSON object per line for log collectors (Phase 10): time (UTC), level,
logger, request ID, message, the structured ``http`` fields of access lines and any
exception. It also takes over uvicorn's loggers, so every line of the process has the same
shape. Nothing secret is logged: request bodies, cookies and passwords never are.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Literal

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"

LogFormat = Literal["text", "json"]


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per record."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        http = getattr(record, "http", None)
        if isinstance(http, dict):
            entry["http"] = http
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str, log_format: LogFormat = "text") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if log_format == "json" else logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())

    app_logger = logging.getLogger("app")
    app_logger.handlers[:] = [handler]
    app_logger.setLevel(level)
    app_logger.propagate = False

    if log_format == "json":
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            server_logger = logging.getLogger(name)
            server_logger.handlers[:] = [handler]
            server_logger.propagate = False
