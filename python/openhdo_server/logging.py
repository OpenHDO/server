"""Structured JSON logging without a runtime-specific logging dependency."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import sys
from collections.abc import Mapping


_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


class JsonFormatter(logging.Formatter):
    """Format application records as one parseable JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", {})
        if not isinstance(fields, Mapping):
            fields = {"value": str(fields)}
        return json.dumps(
            {
                "ts": datetime.fromtimestamp(record.created, timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "level": record.levelname.lower(),
                "component": record.name,
                "event": getattr(record, "event_name", record.getMessage()),
                "fields": dict(fields),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def configure_logging(log_level: str) -> logging.Logger:
    """Configure the server logger once and return its application logger."""

    logger = logging.getLogger("openhdo.server")
    logger.setLevel(_LEVELS[log_level])
    logger.propagate = False
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    fields: Mapping[str, object] | None = None,
) -> None:
    """Write a structured application event."""

    logger.log(level, event, extra={"event_name": event, "fields": dict(fields or {})})
