"""Structured JSON logging with correlation-id propagation.

`configure_logging()` runs once at process startup (app factory / graph
entrypoint). Every log record picks up the current correlation_id from
context, so one request/run is followable end to end across API -> graph ->
adapter without threading an id through every function signature.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter

from verdantis.config.settings import get_settings

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


class _CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


def configure_logging() -> None:
    settings = get_settings()

    handler = logging.StreamHandler()
    handler.addFilter(_CorrelationIdFilter())
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(correlation_id)s %(message)s"
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(
        logging.DEBUG if settings.environment == "development" else logging.INFO
    )
