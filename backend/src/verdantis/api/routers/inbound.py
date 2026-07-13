"""Public, unauthenticated inbound-submission endpoint — the embeddable
form's backend. Rate-limited per IP since it has no auth. Persists the raw
submission fast (`ingest_submission`) so the HTTP response can return
immediately, then schedules the rest of intake (normalize -> verify ->
score -> route -> dispatch -> ack) as a background task through the
compiled inbound graph, per the scope doc: "Runs synchronously enough for a
fast acknowledgement; verification enrichment can complete async."

No business logic here beyond that orchestration — normalization, scoring,
verification, and dispatch all live in agents/inbound/ and core/.
"""

from __future__ import annotations

import logging

import sentry_sdk
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.agents.inbound.graph import build_inbound_graph
from verdantis.agents.inbound.nodes import ingest_submission
from verdantis.agents.inbound.runtime import build_inbound_services
from verdantis.agents.inbound.state import InboundState
from verdantis.agents.shared.checkpointer import get_checkpointer
from verdantis.agents.shared.run_config import build_run_config
from verdantis.api.deps import get_db
from verdantis.api.rate_limit import enforce_rate_limit
from verdantis.api.schemas.inbound import (
    InboundSubmissionRequest,
    InboundSubmissionResponse,
)
from verdantis.core.security.encryption import EncryptionNotConfiguredError
from verdantis.db.models import Tenant
from verdantis.db.redis import get_redis, get_redis_client
from verdantis.db.session import session_scope
from verdantis.models.tenant_config import TenantConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/inbound", tags=["inbound"])

_RATE_LIMIT = 10
_RATE_LIMIT_WINDOW_SECONDS = 60


@router.post(
    "/submissions",
    response_model=InboundSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_inbound_lead(
    tenant_slug: str,
    payload: InboundSubmissionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> InboundSubmissionResponse:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        redis,
        key=f"inbound:ratelimit:{tenant_slug}:{client_ip}",
        limit=_RATE_LIMIT,
        window_seconds=_RATE_LIMIT_WINDOW_SECONDS,
    )

    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found"
        )

    try:
        company_id, lead_id = await ingest_submission(
            session,
            tenant_id=tenant.id,
            legal_name=payload.legal_name,
            country=payload.country,
            contact_name=payload.contact_name,
            contact_email=payload.contact_email,
            requested_commodity=payload.requested_commodity,
            requested_volume=payload.requested_volume,
            incoterm_raw=payload.incoterm,
            payment_terms_raw=payload.payment_terms,
            message=payload.message,
        )
    except EncryptionNotConfiguredError as exc:
        # PII encryption is mandatory, not best-effort — fail the request
        # rather than silently persist an unencrypted contact name/email.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service temporarily unavailable",
        ) from exc

    tenant_config = TenantConfig.from_raw(tenant.config)
    # contact_name/contact_email deliberately do not flow into InboundState —
    # see agents/inbound/state.py's docstring: the checkpointer durably
    # persists this state, so PII carried here would leak in plaintext
    # regardless of Lead.intake being encrypted. Nodes that need the
    # contact decrypt it on demand from the Lead row instead.
    state = InboundState(
        tenant_id=tenant.id,
        company_id=company_id,
        lead_id=lead_id,
        legal_name=payload.legal_name,
        country=payload.country,
        requested_commodity=payload.requested_commodity,
        requested_volume=payload.requested_volume,
        incoterm_raw=payload.incoterm,
        payment_terms_raw=payload.payment_terms,
        message=payload.message,
        fit_threshold=tenant_config.inbound_fit_threshold,
    )

    background_tasks.add_task(_run_inbound_graph, state, tenant_config)

    return InboundSubmissionResponse(lead_id=lead_id)


async def _run_inbound_graph(state: InboundState, tenant_config: TenantConfig) -> None:
    """Runs after the HTTP response is sent, on its own fresh session — a
    request-scoped session must never be held open across a background
    task of indeterminate length (same rule the outbound graph follows)."""
    try:
        async with session_scope() as session:
            services = build_inbound_services(
                session, redis=get_redis_client(), tenant_config=tenant_config
            )
            async with get_checkpointer() as checkpointer:
                app = build_inbound_graph().compile(checkpointer=checkpointer)
                config = build_run_config(
                    tenant_id=state.tenant_id,
                    capability="inbound",
                    thread_id=str(state.lead_id),
                    services=services,
                )
                await app.ainvoke(state, config=config)
    except Exception:
        logger.exception(
            "inbound graph background run failed for lead %s", state.lead_id
        )
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("capability", "inbound")
            scope.set_tag("tenant_id", str(state.tenant_id))
            sentry_sdk.capture_exception()
