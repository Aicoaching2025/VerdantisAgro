"""Tenant-scoped configuration, per CLAUDE.md rule 7: commodity set, regions,
ICP thresholds, and routing rules live in the tenant-scoped config object,
never hardcoded. Backed by `Tenant.config` (JSONB) — this model is just the
typed, validated view of it. One tenant today; every field defaults so an
empty `{}` config (the DB's server_default) still parses.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from verdantis.db.enums import RoutingTarget


class TenantConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    inbound_fit_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    default_routing_target: RoutingTarget = RoutingTarget.SALES
    slack_webhook_url: str | None = None
    ack_from_email: str | None = None
    ack_from_name: str = "Verdantis Agro Produce"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TenantConfig:
        return cls.model_validate(raw)
