"""Structured ingestion events: one line per event, ``event=… key=value …``.

Lines are easy to read and to grep (``event=ingestion.failed``), and the request-ID filter
from ``app.core.logging`` still applies. Callers pass only safe values — URLs are
redacted before they get here and response bodies are never logged.
"""

from __future__ import annotations

import logging


def _format_value(value: object) -> str:
    text = str(value)
    if not text or any(ch.isspace() for ch in text) or '"' in text or "=" in text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def format_event(event: str, fields: dict[str, object]) -> str:
    parts = [f"event={event}"]
    parts += [f"{key}={_format_value(value)}" for key, value in fields.items() if value is not None]
    return " ".join(parts)


def log_event(
    logger: logging.Logger, event: str, level: int = logging.INFO, **fields: object
) -> None:
    if logger.isEnabledFor(level):
        logger.log(level, "%s", format_event(event, fields))
