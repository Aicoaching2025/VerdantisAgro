from verdantis.observability.logging import (
    configure_logging,
    get_correlation_id,
    set_correlation_id,
)
from verdantis.observability.sentry import configure_sentry
from verdantis.observability.tracing import configure_tracing


def configure_observability() -> None:
    configure_logging()
    configure_sentry()
    configure_tracing()


__all__ = [
    "configure_observability",
    "get_correlation_id",
    "set_correlation_id",
]
