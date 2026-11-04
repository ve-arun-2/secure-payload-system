"""Structured JSON logging with per-request context.

Every log line is a single JSON object. Fields bound through `bind_log_context`
(request_id, partner_id, transaction_id, event_publish_status, ...) are attached
automatically to all records emitted while the request is being handled.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.security import mask_sensitive

# A mutable dict per request: services mutate it, the request-context middleware
# reads it when writing the access log line.
_log_context: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)

_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


def init_log_context() -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    _log_context.set(ctx)
    return ctx


def bind_log_context(**fields: Any) -> None:
    ctx = _log_context.get()
    if ctx is not None:
        ctx.update(fields)


def get_log_context() -> dict[str, Any]:
    return dict(_log_context.get() or {})


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str, environment: str) -> None:
        super().__init__()
        self._service = service_name
        self._env = environment

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service,
            "env": self._env,
        }
        entry.update(get_log_context())
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS:
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(mask_sensitive(entry), default=str)


class _StdoutHandler(logging.StreamHandler):
    """StreamHandler that looks up sys.stdout on every emit (survives stdout redirection)."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def stream(self):  # type: ignore[override]
        return sys.stdout

    @stream.setter
    def stream(self, _value) -> None:
        pass


def configure_logging(level: str, service_name: str, environment: str) -> None:
    handler = _StdoutHandler()
    handler.setFormatter(JsonFormatter(service_name, environment))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn's own access log would duplicate (and not mask) ours.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
