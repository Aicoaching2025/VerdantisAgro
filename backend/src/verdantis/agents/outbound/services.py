"""Dependency bundle injected via RunnableConfig.configurable.

Session, adapters, and providers a graph run needs — built once per
invocation by the caller, never baked into the compiled graph or into
state. Production injects real Postgres sessions and configured providers;
tests inject fakes. This is also where tenant scoping flows through, per
CLAUDE.md: never read tenant config from globals inside a node.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.core.adapters.base import TradeDataAdapter
from verdantis.core.crm.hubspot import CrmSyncClient
from verdantis.core.enrichment.base import EnrichmentProvider
from verdantis.core.llm.client import LLMClient
from verdantis.core.verification.engine import VerificationEngine


@dataclass
class OutboundServices:
    session: AsyncSession
    trade_data_adapter: TradeDataAdapter
    verification_engine: VerificationEngine
    scoring_client: LLMClient
    drafting_client: LLMClient
    enrichment_provider: EnrichmentProvider | None = None
    crm_client: CrmSyncClient | None = None


class ServicesNotInjectedError(Exception):
    """Raised when a node runs without OutboundServices in configurable."""


def get_services(config: RunnableConfig) -> OutboundServices:
    services = config.get("configurable", {}).get("services")
    if services is None:
        raise ServicesNotInjectedError(
            "OutboundServices not found in RunnableConfig.configurable — "
            "the caller must inject it when invoking the graph"
        )
    if not isinstance(services, OutboundServices):
        raise TypeError(
            f"configurable['services'] must be OutboundServices, got {type(services)}"
        )
    return services
