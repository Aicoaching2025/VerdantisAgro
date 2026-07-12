"""Production wiring for OutboundServices, mirroring
agents/inbound/runtime.py. Tests construct OutboundServices directly with
fakes; this is the only place concrete provider classes get instantiated
for a real request.

Sanctions and corporate-existence providers are NOT optional — same
fail-closed rule as inbound (CLAUDE.md rule 4). `enrichment_provider` stays
`None`: no Clay/PDL key exists in this environment, per the user's Phase 2
answer to build the interface only.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.agents.outbound.services import OutboundServices
from verdantis.config.settings import get_settings
from verdantis.core.adapters.manual_export import ManualExportAdapter
from verdantis.core.adapters.resilience import AdapterResilience
from verdantis.core.crm.hubspot import HubSpotClient, HubSpotNotConfiguredError
from verdantis.core.llm.client import AnthropicClient
from verdantis.core.verification.corporate import OpenCorporatesProvider
from verdantis.core.verification.engine import VerificationEngine
from verdantis.core.verification.sanctions import OpenSanctionsProvider


def build_outbound_services(
    session: AsyncSession,
    *,
    redis: Redis,
    csv_file: io.TextIOBase,
    csv_source: str,
) -> OutboundServices:
    settings = get_settings()
    http_client = httpx.AsyncClient()

    verification_engine = VerificationEngine(
        session=session,
        sanctions_provider=OpenSanctionsProvider(
            api_url=settings.opensanctions_api_url,
            api_key=settings.opensanctions_api_key,
            resilience=AdapterResilience(redis, provider="opensanctions"),
            client=http_client,
        ),
        corporate_provider=OpenCorporatesProvider(
            api_token=settings.opencorporates_api_key,
            resilience=AdapterResilience(redis, provider="opencorporates"),
            client=http_client,
        ),
    )

    scoring_client = AnthropicClient(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_scoring_model,
        resilience=AdapterResilience(redis, provider="anthropic-scoring"),
    )
    drafting_client = AnthropicClient(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_drafting_model,
        resilience=AdapterResilience(redis, provider="anthropic-drafting"),
    )

    crm_client = None
    try:
        crm_client = HubSpotClient(
            access_token=settings.hubspot_access_token,
            resilience=AdapterResilience(redis, provider="hubspot"),
            client=http_client,
        )
    except HubSpotNotConfiguredError:
        pass

    return OutboundServices(
        session=session,
        trade_data_adapter=ManualExportAdapter(
            csv_file, source=csv_source, export_retrieved_at=datetime.now(UTC)
        ),
        verification_engine=verification_engine,
        scoring_client=scoring_client,
        drafting_client=drafting_client,
        enrichment_provider=None,
        crm_client=crm_client,
    )
