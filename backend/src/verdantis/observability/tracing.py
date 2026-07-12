"""LangSmith tracing toggle.

Actual instrumentation (per-node tracing, the `traceable` decorator) lives
alongside the LangGraph agents once they exist (Phase 2+) — there's nothing
to trace yet. This module only centralizes the standard LangChain/LangSmith
env vars that langgraph/langchain read automatically, gated by
LANGSMITH_TRACING, so no module reaches into os.environ directly.
"""

from __future__ import annotations

import os

from verdantis.config.settings import get_settings


def configure_tracing() -> None:
    settings = get_settings()
    if not settings.langsmith_tracing:
        return
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
