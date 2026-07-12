"""Sentry error tracking init, gated by SENTRY_DSN. A no-op locally when unset."""

from __future__ import annotations

import sentry_sdk

from verdantis.config.settings import get_settings


def configure_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
    )
