"""Outbound discovery graph nodes.

Each node is `async def node(state, config) -> dict` returning a partial
state update, per CLAUDE.md's LangGraph conventions. Dependencies (session,
adapters, providers) come from `RunnableConfig.configurable` via
`get_services`, never from globals — a fresh `OutboundServices` (fresh
session) is expected on every invocation, including resumes after an
interrupt, since a session must never be held open across a human-approval
pause of indeterminate length.

Nodes call db.provenance / core.verification / core.dossier — never touch
SQLAlchemy models beyond what those already expose, and never leak ORM
objects into state.
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.agents.outbound.services import get_services
from verdantis.agents.outbound.state import Outcome, OutboundState
from verdantis.agents.shared.entity_resolution import (
    normalize_match_key,
    resolve_or_create_company,
)
from verdantis.core.dossier.service import get_dossier
from verdantis.core.outreach.draft import draft_outreach
from verdantis.core.scoring.fit import FitScoreParseError, score_fit
from verdantis.db.enums import LeadSource, LeadStatus
from verdantis.db.models import Lead
from verdantis.db.provenance import record_trade_signal


async def fetch_signals(state: OutboundState, config: RunnableConfig) -> dict[str, Any]:
    services = get_services(config)
    records = await services.trade_data_adapter.fetch_signals(
        commodities=state.commodities, regions=state.regions
    )
    return {"fetched_signals": records}


async def persist_signals(
    state: OutboundState, config: RunnableConfig
) -> dict[str, Any]:
    services = get_services(config)
    company_ids: list[uuid.UUID] = []
    seen_keys: dict[str, uuid.UUID] = {}

    for record in state.fetched_signals:
        match_key = normalize_match_key(record.company_legal_name)
        company_id = seen_keys.get(match_key)
        if company_id is None:
            company_id = await resolve_or_create_company(
                services.session,
                tenant_id=state.tenant_id,
                legal_name=record.company_legal_name,
                country=record.company_country,
                match_key=match_key,
            )
            seen_keys[match_key] = company_id
            if company_id not in company_ids:
                company_ids.append(company_id)

        await record_trade_signal(
            services.session,
            tenant_id=state.tenant_id,
            company_id=company_id,
            signal_type=record.signal_type,
            commodity=record.commodity,
            band=record.band,
            numeric_value=record.numeric_value,
            period_start=record.period_start,
            period_end=record.period_end,
            details=record.details,
            provenance=record.provenance,
        )

    await services.session.commit()
    return {"fetched_signals": [], "pending_company_ids": company_ids}


# Deliberately excludes current_lead_id: next_company always sets that
# explicitly to the newly created lead's id, and unpacking this dict *after*
# that key in the same literal would silently overwrite it back to None.
_RESET_CURRENT_FIELDS: dict[str, Any] = {
    "current_blocked": False,
    "current_fit_score": None,
    "current_fit_reasons": [],
    "current_decision_maker_email": None,
    "current_draft_body": None,
    "current_approval_decision": None,
    "current_outcome": None,
}


async def next_company(state: OutboundState, config: RunnableConfig) -> dict[str, Any]:
    if not state.pending_company_ids:
        return {"current_company_id": None}

    services = get_services(config)
    remaining = list(state.pending_company_ids)
    company_id = remaining.pop(0)

    lead = Lead(
        tenant_id=state.tenant_id,
        company_id=company_id,
        source=LeadSource.OUTBOUND_DISCOVERY,
        # Lets the approvals API look up this lead's live interrupt() state
        # from the checkpointer once it reaches PENDING_APPROVAL.
        thread_id=config.get("configurable", {}).get("thread_id"),
    )
    services.session.add(lead)
    await services.session.commit()

    return {
        "pending_company_ids": remaining,
        "current_company_id": company_id,
        "current_lead_id": lead.id,
        **_RESET_CURRENT_FIELDS,
    }


async def verify(state: OutboundState, config: RunnableConfig) -> dict[str, Any]:
    services = get_services(config)
    assert state.current_company_id is not None
    summary = await services.verification_engine.verify(
        tenant_id=state.tenant_id, company_id=state.current_company_id
    )
    await _set_lead_status(
        services.session,
        state.current_lead_id,
        LeadStatus.DISQUALIFIED if summary.blocked else LeadStatus.VERIFYING,
    )
    return {"current_blocked": summary.blocked}


async def score_fit_node(
    state: OutboundState, config: RunnableConfig
) -> dict[str, Any]:
    services = get_services(config)
    assert state.current_company_id is not None
    dossier = await get_dossier(
        services.session, tenant_id=state.tenant_id, company_id=state.current_company_id
    )
    try:
        result = await score_fit(services.scoring_client, dossier)
    except FitScoreParseError:
        # Can't score reliably -> treat as no-fit rather than guess a score.
        return {
            "current_fit_score": 0.0,
            "current_fit_reasons": ["fit score unparseable; treated as no-fit"],
        }
    return {"current_fit_score": result.score, "current_fit_reasons": result.reasons}


async def resolve_decision_maker_node(
    state: OutboundState, config: RunnableConfig
) -> dict[str, Any]:
    services = get_services(config)
    if services.enrichment_provider is None:
        return {"current_decision_maker_email": None}
    assert state.current_company_id is not None
    dossier = await get_dossier(
        services.session, tenant_id=state.tenant_id, company_id=state.current_company_id
    )
    contact = await services.enrichment_provider.resolve_decision_maker(
        company_legal_name=dossier.legal_name, country=dossier.country
    )
    return {"current_decision_maker_email": contact.email if contact else None}


async def draft_outreach_node(
    state: OutboundState, config: RunnableConfig
) -> dict[str, Any]:
    services = get_services(config)
    assert state.current_company_id is not None
    dossier = await get_dossier(
        services.session, tenant_id=state.tenant_id, company_id=state.current_company_id
    )
    draft = await draft_outreach(
        services.drafting_client, dossier, fit_reasons=state.current_fit_reasons
    )
    if state.current_lead_id is not None:
        lead = await services.session.get(Lead, state.current_lead_id)
        if lead is not None:
            lead.status = LeadStatus.PENDING_APPROVAL
            lead.fit_score = state.current_fit_score
            await services.session.commit()
    return {"current_draft_body": draft.body}


async def human_approval_node(
    state: OutboundState, config: RunnableConfig
) -> dict[str, Any]:
    """The rule-1 gate. Nothing before this node can send anything; nothing
    after it runs without an explicit human decision captured here."""
    services = get_services(config)
    assert state.current_company_id is not None
    dossier = await get_dossier(
        services.session, tenant_id=state.tenant_id, company_id=state.current_company_id
    )
    payload = {
        "company_id": str(state.current_company_id),
        "legal_name": dossier.legal_name,
        "country": dossier.country,
        "fit_score": state.current_fit_score,
        "fit_reasons": state.current_fit_reasons,
        "credibility": {
            check_type.value: verdict.verdict.value
            for check_type, verdict in dossier.latest_verdict_by_check.items()
        },
        "decision_maker_email": state.current_decision_maker_email,
        "draft_body": state.current_draft_body,
    }
    decision = interrupt(payload)
    if not isinstance(decision, dict) or decision.get("action") not in (
        "approve",
        "reject",
    ):
        raise ValueError(f"invalid human approval decision: {decision!r}")
    return {
        "current_approval_decision": "approved"
        if decision["action"] == "approve"
        else "rejected"
    }


async def record_decision_node(
    state: OutboundState, config: RunnableConfig
) -> dict[str, Any]:
    services = get_services(config)
    assert state.current_lead_id is not None
    outcome: Outcome
    if state.current_approval_decision == "approved":
        status, outcome = LeadStatus.APPROVED, "approved"
    else:
        status, outcome = LeadStatus.REJECTED, "rejected"
    await _set_lead_status(services.session, state.current_lead_id, status)
    return _finish_company(state, outcome)


async def sync_crm_node(state: OutboundState, config: RunnableConfig) -> dict[str, Any]:
    services = get_services(config)
    if services.crm_client is not None:
        assert state.current_company_id is not None
        dossier = await get_dossier(
            services.session,
            tenant_id=state.tenant_id,
            company_id=state.current_company_id,
        )
        await services.crm_client.upsert_company(
            legal_name=dossier.legal_name,
            properties={"verdantis_fit_score": str(state.current_fit_score or "")},
        )
        if state.current_decision_maker_email:
            await services.crm_client.upsert_contact(
                email=state.current_decision_maker_email,
                properties={"company": dossier.legal_name},
            )
    await _set_lead_status(services.session, state.current_lead_id, LeadStatus.ROUTED)
    return {}


async def discard_node(state: OutboundState, config: RunnableConfig) -> dict[str, Any]:
    services = get_services(config)
    outcome: Outcome = (
        "discarded_sanctions" if state.current_blocked else "discarded_low_fit"
    )
    await _set_lead_status(
        services.session, state.current_lead_id, LeadStatus.DISCARDED
    )
    return _finish_company(state, outcome)


async def _set_lead_status(
    session: AsyncSession, lead_id: uuid.UUID | None, status: LeadStatus
) -> None:
    if lead_id is None:
        return
    lead = await session.get(Lead, lead_id)
    if lead is not None:
        lead.status = status
        await session.commit()


def _finish_company(state: OutboundState, outcome: Outcome) -> dict[str, Any]:
    key = str(state.current_company_id)
    return {
        "current_outcome": outcome,
        "outcomes": {**state.outcomes, key: outcome},
        "processed_company_ids": [
            *state.processed_company_ids,
            state.current_company_id,
        ],
    }
