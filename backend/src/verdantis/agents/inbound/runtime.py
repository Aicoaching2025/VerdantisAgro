"""Production wiring for InboundServices: builds real providers from
Settings + TenantConfig. Tests construct InboundServices directly with
fakes (see tests/agents/inbound/test_graph.py) — this is the only place
concrete provider classes get instantiated for a real request.

Sanctions and corporate-existence providers are NOT optional: if
`OPENSANCTIONS_API_KEY` isn't configured, `OpenSanctionsProvider` raises
`OpenSanctionsNotConfiguredError` here, and the whole services build fails —
by design (CLAUDE.md rule 4: sanctions screening is a blocking gate, never
bypassed, not even when unconfigured). CRM, Slack, and email are the parts
allowed to be `None` when unconfigured; verification is not.
"""

from __future__ import annotations

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.agents.inbound.services import InboundServices
from verdantis.config.settings import get_settings
from verdantis.core.adapters.resilience import AdapterResilience
from verdantis.core.crm.hubspot import HubSpotClient, HubSpotNotConfiguredError
from verdantis.core.llm.cache import LLMResponseCache
from verdantis.core.llm.client import AnthropicClient
from verdantis.core.notify.email import EmailNotConfiguredError, ResendEmailClient
from verdantis.core.notify.slack import SlackNotConfiguredError, SlackWebhookNotifier
from verdantis.core.verification.corporate import OpenCorporatesProvider
from verdantis.core.verification.engine import VerificationEngine
from verdantis.core.verification.sanctions import OpenSanctionsProvider
from verdantis.models.tenant_config import TenantConfig


def build_inbound_services(
    session: AsyncSession, *, redis: Redis, tenant_config: TenantConfig
) -> InboundServices:
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
        cache=LLMResponseCache(redis),
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

    slack_notifier = None
    try:
        slack_notifier = SlackWebhookNotifier(
            webhook_url=tenant_config.slack_webhook_url,
            resilience=AdapterResilience(redis, provider="slack"),
            client=http_client,
        )
    except SlackNotConfiguredError:
        pass

    email_sender = None
    try:
        email_sender = ResendEmailClient(
            api_key=settings.resend_api_key,
            resilience=AdapterResilience(redis, provider="resend"),
            client=http_client,
        )
    except EmailNotConfiguredError:
        pass

    return InboundServices(
        session=session,
        verification_engine=verification_engine,
        scoring_client=scoring_client,
        tenant_config=tenant_config,
        crm_client=crm_client,
        slack_notifier=slack_notifier,
        email_sender=email_sender,
    )
