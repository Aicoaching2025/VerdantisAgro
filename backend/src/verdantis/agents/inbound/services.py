"""Dependency bundle injected via RunnableConfig.configurable, same pattern
as agents.outbound.services.OutboundServices. A fresh InboundServices (fresh
session) is built once per invocation by the caller — production builds one
per background task, tests inject fakes.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.core.crm.hubspot import CrmSyncClient
from verdantis.core.llm.client import LLMClient
from verdantis.core.notify.email import EmailSender
from verdantis.core.notify.slack import SlackNotifier
from verdantis.core.verification.engine import VerificationEngine
from verdantis.models.tenant_config import TenantConfig


@dataclass
class InboundServices:
    session: AsyncSession
    verification_engine: VerificationEngine
    scoring_client: LLMClient
    tenant_config: TenantConfig
    crm_client: CrmSyncClient | None = None
    slack_notifier: SlackNotifier | None = None
    email_sender: EmailSender | None = None


class ServicesNotInjectedError(Exception):
    """Raised when a node runs without InboundServices in configurable."""


def get_services(config: RunnableConfig) -> InboundServices:
    services = config.get("configurable", {}).get("services")
    if services is None:
        raise ServicesNotInjectedError(
            "InboundServices not found in RunnableConfig.configurable — "
            "the caller must inject it when invoking the graph"
        )
    if not isinstance(services, InboundServices):
        raise TypeError(
            f"configurable['services'] must be InboundServices, got {type(services)}"
        )
    return services
