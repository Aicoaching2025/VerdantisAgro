"""Inbound intake graph nodes.

`ingest_submission` is deliberately NOT one of the compiled graph's nodes —
it's a plain function the API router calls directly, synchronously, with its
own short-lived session, so it can mint a real lead_id fast enough for the
HTTP response (the scope doc: "Runs synchronously enough for a fast
acknowledgement"). The compiled graph (agents/inbound/graph.py) picks up
from `normalize_fields` onward as a background task, once company_id/lead_id
already exist in state.

Every other node is `async def node(state, config) -> dict`, matching the
outbound graph's convention. Dependencies come from
`RunnableConfig.configurable` via `get_services`, never from globals.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.agents.inbound.services import InboundServices, get_services
from verdantis.agents.inbound.state import InboundState
from verdantis.agents.shared.entity_resolution import (
    normalize_match_key,
    resolve_or_create_company,
)
from verdantis.core.compliance.suppression import is_suppressed
from verdantis.core.dossier.service import get_dossier
from verdantis.core.intake.normalize import normalize_incoterm, normalize_payment_terms
from verdantis.core.notify.email import render_inquiry_ack
from verdantis.core.scoring.fit import FitScoreParseError
from verdantis.core.scoring.lead import score_lead
from verdantis.core.security.pii import decrypt_intake_pii, encrypt_intake_pii
from verdantis.db.enums import LeadSource, LeadStatus, PaymentTerms, RoutingTarget
from verdantis.db.models import Lead


async def ingest_submission(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    legal_name: str,
    country: str | None,
    contact_name: str,
    contact_email: str,
    requested_commodity: str,
    requested_volume: str | None,
    incoterm_raw: str | None,
    payment_terms_raw: str | None,
    message: str | None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Resolve/create the Company and create the Lead. Not a graph node —
    see module docstring. Returns (company_id, lead_id)."""
    company_id = await resolve_or_create_company(
        session,
        tenant_id=tenant_id,
        legal_name=legal_name,
        country=country,
        match_key=normalize_match_key(legal_name),
    )
    lead = Lead(
        tenant_id=tenant_id,
        company_id=company_id,
        source=LeadSource.INBOUND_FORM,
        requested_commodity=requested_commodity,
        # contact_name/contact_email are PII -> encrypted before they ever
        # touch the database (core.security.pii). Raises
        # EncryptionNotConfiguredError if no key is set; the caller (the API
        # router) must fail the request rather than let that propagate into
        # a silent plaintext write.
        intake=encrypt_intake_pii(
            {
                "contact_name": contact_name,
                "contact_email": contact_email,
                "requested_volume": requested_volume,
                "incoterm_raw": incoterm_raw,
                "payment_terms_raw": payment_terms_raw,
                "message": message,
            }
        ),
    )
    session.add(lead)
    await session.commit()
    return company_id, lead.id


async def normalize_fields(
    state: InboundState, config: RunnableConfig
) -> dict[str, Any]:
    services = get_services(config)
    incoterm = normalize_incoterm(state.incoterm_raw)
    payment_terms = normalize_payment_terms(state.payment_terms_raw)

    lead = await services.session.get(Lead, state.lead_id)
    if lead is not None:
        lead.incoterm = incoterm
        lead.payment_terms = payment_terms
        lead.status = LeadStatus.VERIFYING
        await services.session.commit()

    return {"incoterm": incoterm, "payment_terms": payment_terms}


async def verify(state: InboundState, config: RunnableConfig) -> dict[str, Any]:
    services = get_services(config)
    summary = await services.verification_engine.verify(
        tenant_id=state.tenant_id, company_id=state.company_id
    )
    return {"blocked": summary.blocked}


async def score_lead_node(
    state: InboundState, config: RunnableConfig
) -> dict[str, Any]:
    services = get_services(config)
    dossier = await get_dossier(
        services.session, tenant_id=state.tenant_id, company_id=state.company_id
    )
    try:
        result = await score_lead(
            services.scoring_client,
            dossier,
            requested_commodity=state.requested_commodity,
            requested_volume=state.requested_volume,
            incoterm=state.incoterm,
            payment_terms=state.payment_terms or PaymentTerms.OTHER,
            message=state.message,
        )
    except FitScoreParseError:
        # Can't score reliably -> fail closed to human triage, never
        # auto-dispatch on an unparseable score.
        return {
            "fit_score": 0.0,
            "fit_reasons": ["lead score unparseable; routed to triage"],
        }
    return {"fit_score": result.score, "fit_reasons": result.reasons}


async def dispatch_node(state: InboundState, config: RunnableConfig) -> dict[str, Any]:
    services = get_services(config)
    routing_target = services.tenant_config.default_routing_target

    if services.crm_client is not None:
        dossier = await get_dossier(
            services.session, tenant_id=state.tenant_id, company_id=state.company_id
        )
        await services.crm_client.upsert_company(
            legal_name=dossier.legal_name,
            properties={
                "verdantis_lead_source": "inbound",
                "verdantis_fit_score": str(state.fit_score or ""),
            },
        )
        contact = await _load_decrypted_contact(services.session, state.lead_id)
        if contact is not None:
            _, contact_email = contact
            await services.crm_client.upsert_contact(
                email=contact_email,
                properties={
                    "company": dossier.legal_name,
                    "requested_commodity": state.requested_commodity,
                },
            )

    if services.slack_notifier is not None:
        await services.slack_notifier.notify_new_lead(
            legal_name=state.legal_name,
            country=state.country,
            requested_commodity=state.requested_commodity,
            fit_score=state.fit_score or 0.0,
        )

    await _send_ack(state, services)
    await _route_lead(services.session, state.lead_id, routing_target)
    return {"routing_target": routing_target, "outcome": "dispatched"}


async def triage_node(state: InboundState, config: RunnableConfig) -> dict[str, Any]:
    services = get_services(config)
    await _send_ack(state, services)
    await _route_lead(services.session, state.lead_id, RoutingTarget.TRIAGE)
    return {"routing_target": RoutingTarget.TRIAGE, "outcome": "needs_triage"}


async def discard_node(state: InboundState, config: RunnableConfig) -> dict[str, Any]:
    """Sanctions hit. Nothing further happens: no CRM sync, no Slack, no ack
    email — discard means discard (CLAUDE.md rule 4 / rule 1's inbound
    exception explicitly carves this out)."""
    services = get_services(config)
    lead = await services.session.get(Lead, state.lead_id)
    if lead is not None:
        lead.status = LeadStatus.DISCARDED
        await services.session.commit()
    return {"outcome": "discarded_sanctions"}


async def _send_ack(state: InboundState, services: InboundServices) -> None:
    if services.email_sender is None:
        return
    from_email = services.tenant_config.ack_from_email
    if not from_email:
        return  # no configured from-address -> skip rather than guess one

    contact = await _load_decrypted_contact(services.session, state.lead_id)
    if contact is None:
        return
    contact_name, contact_email = contact

    if await is_suppressed(
        services.session, tenant_id=state.tenant_id, email=contact_email
    ):
        # Do-not-contact -> skip only the send. Routing/CRM/Slack already
        # happened (or will, for the triage path); the suppression list
        # gates the external message, not the internal record-keeping.
        return

    subject, body = render_inquiry_ack(
        contact_name=contact_name, legal_name=state.legal_name
    )
    await services.email_sender.send(
        to=contact_email,
        from_email=from_email,
        from_name=services.tenant_config.ack_from_name,
        subject=subject,
        body=body,
    )


async def _load_decrypted_contact(
    session: AsyncSession, lead_id: uuid.UUID
) -> tuple[str, str] | None:
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.intake is None:
        return None
    decrypted = decrypt_intake_pii(lead.intake)
    contact_name = decrypted.get("contact_name")
    contact_email = decrypted.get("contact_email")
    if not contact_name or not contact_email:
        return None
    return contact_name, contact_email


async def _route_lead(
    session: AsyncSession, lead_id: uuid.UUID, target: RoutingTarget
) -> None:
    lead = await session.get(Lead, lead_id)
    if lead is not None:
        lead.status = LeadStatus.ROUTED
        lead.routed_to = target
        lead.routed_at = datetime.now(UTC)
        await session.commit()
