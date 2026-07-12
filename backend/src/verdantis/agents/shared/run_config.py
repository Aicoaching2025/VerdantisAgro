"""Builds a correctly-tagged RunnableConfig for a graph invocation.

Every graph run should carry a thread_id, its services bundle, and tracing
tags for tenant + capability (CLAUDE.md: "Tag runs with tenant + capability")
— callers should build config through here rather than hand-rolling the
dict, so the tagging convention can't drift between call sites.
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig


def build_run_config(
    *, tenant_id: uuid.UUID, capability: str, thread_id: str, services: Any
) -> RunnableConfig:
    return {
        "configurable": {"thread_id": thread_id, "services": services},
        "tags": [capability, f"tenant:{tenant_id}"],
        "metadata": {"tenant_id": str(tenant_id), "capability": capability},
    }
