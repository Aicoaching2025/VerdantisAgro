"""build_run_config tags every run with tenant + capability, per CLAUDE.md's
observability convention ("Tag runs with tenant + capability")."""

from __future__ import annotations

import uuid

from verdantis.agents.shared.run_config import build_run_config


def test_build_run_config_tags_tenant_and_capability() -> None:
    tenant_id = uuid.uuid4()
    services = object()

    config = build_run_config(
        tenant_id=tenant_id,
        capability="outbound",
        thread_id="thread-123",
        services=services,
    )

    assert config["configurable"] == {"thread_id": "thread-123", "services": services}
    assert config["tags"] == ["outbound", f"tenant:{tenant_id}"]
    assert config["metadata"] == {
        "tenant_id": str(tenant_id),
        "capability": "outbound",
    }
