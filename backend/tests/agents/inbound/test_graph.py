"""End-to-end tests of the inbound graph's compliance-critical path: the
sanctions gate short-circuits before scoring/dispatch, and auto-dispatch vs.
human triage is decided by the fit-score threshold with no interrupt() gate
(CLAUDE.md rule 1's inbound exception).

Uses the in-memory checkpointer, real Postgres for persistence, and fakes
for every external provider (already contract-tested separately).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.agents.inbound.graph import build_inbound_graph
from verdantis.agents.inbound.nodes import ingest_submission
from verdantis.agents.inbound.services import InboundServices
from verdantis.agents.inbound.state import InboundState
from verdantis.core.compliance.suppression import add_to_suppression_list
from verdantis.core.crm.hubspot import HubSpotSyncResult
from verdantis.core.notify.email import EmailSendResult
from verdantis.core.verification.base import (
    CorporateExistenceProvider,
    SanctionsProvider,
    VerificationOutcome,
)
from verdantis.core.verification.engine import VerificationEngine
from verdantis.db.enums import LeadStatus, ProvenanceMethod, RoutingTarget, Verdict
from verdantis.db.models import Lead, Tenant
from verdantis.db.provenance import Provenance
from verdantis.models.tenant_config import TenantConfig


class _FakeVerificationProvider(SanctionsProvider, CorporateExistenceProvider):
    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict

    async def check(
        self, *, legal_name: str, country: str | None
    ) -> VerificationOutcome:
        return VerificationOutcome(
            verdict=self.verdict,
            evidence={"fake": True},
            provenance=Provenance(
                source="fake",
                retrieved_at=datetime.now(UTC),
                confidence=1.0,
                method=ProvenanceMethod.MANUAL,
            ),
        )


class _FakeScoringClient:
    def __init__(self, score: float) -> None:
        self.score = score

    async def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        return json.dumps({"score": self.score, "reasons": ["fake reason"]})


class _FakeCrmClient:
    def __init__(self) -> None:
        self.upsert_company_calls: list[dict[str, object]] = []
        self.upsert_contact_calls: list[dict[str, object]] = []

    async def upsert_company(
        self, *, legal_name: str, properties: dict[str, object]
    ) -> HubSpotSyncResult:
        self.upsert_company_calls.append(
            {"legal_name": legal_name, "properties": properties}
        )
        return HubSpotSyncResult(object_type="company", hubspot_id="fake-company-1")

    async def upsert_contact(
        self, *, email: str, properties: dict[str, object]
    ) -> HubSpotSyncResult:
        self.upsert_contact_calls.append({"email": email, "properties": properties})
        return HubSpotSyncResult(object_type="contact", hubspot_id="fake-contact-1")


class _FakeSlackNotifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def notify_new_lead(
        self,
        *,
        legal_name: str,
        country: str | None,
        requested_commodity: str,
        fit_score: float,
    ) -> None:
        self.calls.append(
            {
                "legal_name": legal_name,
                "country": country,
                "requested_commodity": requested_commodity,
                "fit_score": fit_score,
            }
        )


class _FakeEmailSender:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send(
        self, *, to: str, from_email: str, from_name: str, subject: str, body: str
    ) -> EmailSendResult:
        self.calls.append(
            {
                "to": to,
                "from_email": from_email,
                "from_name": from_name,
                "subject": subject,
                "body": body,
            }
        )
        return EmailSendResult(message_id="fake-msg-1")


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Verdantis", slug=f"verdantis-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.commit()
    return tenant


def _build_services(
    session: AsyncSession,
    *,
    sanctions_verdict: Verdict,
    crm: _FakeCrmClient | None,
    slack: _FakeSlackNotifier | None,
    email: _FakeEmailSender | None,
    fit_score: float,
) -> InboundServices:
    sanctions = _FakeVerificationProvider(sanctions_verdict)
    corporate = _FakeVerificationProvider(Verdict.PASS)
    return InboundServices(
        session=session,
        verification_engine=VerificationEngine(
            session=session, sanctions_provider=sanctions, corporate_provider=corporate
        ),
        scoring_client=_FakeScoringClient(fit_score),
        tenant_config=TenantConfig(
            ack_from_email="leads@verdantisagro.com",
            ack_from_name="Verdantis Agro Produce",
        ),
        crm_client=crm,
        slack_notifier=slack,
        email_sender=email,
    )


async def _ingest(session: AsyncSession, tenant: Tenant) -> InboundState:
    company_id, lead_id = await ingest_submission(
        session,
        tenant_id=tenant.id,
        legal_name="Acme Trading Ltd",
        country="DE",
        contact_name="Jane Buyer",
        contact_email="jane@example.com",
        requested_commodity="cocoa",
        requested_volume="1 container",
        incoterm_raw="FOB",
        payment_terms_raw="letter of credit",
        message="Interested in a trial order",
    )
    return InboundState(
        tenant_id=tenant.id,
        company_id=company_id,
        lead_id=lead_id,
        legal_name="Acme Trading Ltd",
        country="DE",
        requested_commodity="cocoa",
        requested_volume="1 container",
        incoterm_raw="FOB",
        payment_terms_raw="letter of credit",
        message="Interested in a trial order",
        fit_threshold=0.5,
    )


async def test_sanctions_fail_discards_before_scoring_or_dispatch(
    db_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(db_session)
    state = await _ingest(db_session, tenant)
    crm, slack, email = _FakeCrmClient(), _FakeSlackNotifier(), _FakeEmailSender()
    services = _build_services(
        db_session,
        sanctions_verdict=Verdict.FAIL,
        crm=crm,
        slack=slack,
        email=email,
        fit_score=0.9,
    )
    app = build_inbound_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4()), "services": services}}

    result = await app.ainvoke(state, config=config)

    assert result["outcome"] == "discarded_sanctions"
    assert crm.upsert_company_calls == []
    assert slack.calls == []
    assert email.calls == []  # discard skips the ack entirely

    lead = await db_session.get(Lead, state.lead_id)
    assert lead is not None
    assert lead.status is LeadStatus.DISCARDED
    assert lead.routed_to is None


async def test_high_fit_auto_dispatches_with_crm_slack_and_ack(
    db_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(db_session)
    state = await _ingest(db_session, tenant)
    crm, slack, email = _FakeCrmClient(), _FakeSlackNotifier(), _FakeEmailSender()
    services = _build_services(
        db_session,
        sanctions_verdict=Verdict.PASS,
        crm=crm,
        slack=slack,
        email=email,
        fit_score=0.9,
    )
    app = build_inbound_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4()), "services": services}}

    result = await app.ainvoke(state, config=config)

    assert result["outcome"] == "dispatched"
    assert len(crm.upsert_company_calls) == 1
    assert len(crm.upsert_contact_calls) == 1
    assert len(slack.calls) == 1
    assert slack.calls[0]["fit_score"] == 0.9
    assert len(email.calls) == 1
    assert email.calls[0]["to"] == "jane@example.com"
    assert "received your inquiry" in str(email.calls[0]["subject"]).lower()

    lead = await db_session.get(Lead, state.lead_id)
    assert lead is not None
    assert lead.status is LeadStatus.ROUTED
    assert lead.routed_to is RoutingTarget.SALES
    assert lead.incoterm is not None
    assert lead.payment_terms is not None


async def test_low_fit_routes_to_triage_without_crm_or_slack_but_still_acks(
    db_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(db_session)
    state = await _ingest(db_session, tenant)
    crm, slack, email = _FakeCrmClient(), _FakeSlackNotifier(), _FakeEmailSender()
    services = _build_services(
        db_session,
        sanctions_verdict=Verdict.PASS,
        crm=crm,
        slack=slack,
        email=email,
        fit_score=0.1,
    )
    app = build_inbound_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4()), "services": services}}

    result = await app.ainvoke(state, config=config)

    assert result["outcome"] == "needs_triage"
    assert crm.upsert_company_calls == []
    assert slack.calls == []
    assert len(email.calls) == 1  # still gets a receipt confirmation

    lead = await db_session.get(Lead, state.lead_id)
    assert lead is not None
    assert lead.status is LeadStatus.ROUTED
    assert lead.routed_to is RoutingTarget.TRIAGE


async def test_no_interrupt_ever_raised_by_inbound_graph(
    db_session: AsyncSession,
) -> None:
    """Rule 1's inbound exception: this graph never pauses for human
    approval, unlike the outbound graph."""
    tenant = await _make_tenant(db_session)
    state = await _ingest(db_session, tenant)
    services = _build_services(
        db_session,
        sanctions_verdict=Verdict.PASS,
        crm=None,
        slack=None,
        email=None,
        fit_score=0.9,
    )
    app = build_inbound_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4()), "services": services}}

    result = await app.ainvoke(state, config=config)

    assert "__interrupt__" not in result


async def test_suppressed_contact_still_dispatches_but_skips_the_ack_email(
    db_session: AsyncSession,
) -> None:
    """Scope doc Section 8: "Maintain a suppression list checked before any
    send." The suppression list gates the external email specifically —
    CRM sync, Slack notification, and routing all still happen normally."""
    tenant = await _make_tenant(db_session)
    await add_to_suppression_list(
        db_session,
        tenant_id=tenant.id,
        email="jane@example.com",
        added_by="user_admin",
        reason="unsubscribed",
    )
    await db_session.commit()

    state = await _ingest(db_session, tenant)
    crm, slack, email = _FakeCrmClient(), _FakeSlackNotifier(), _FakeEmailSender()
    services = _build_services(
        db_session,
        sanctions_verdict=Verdict.PASS,
        crm=crm,
        slack=slack,
        email=email,
        fit_score=0.9,
    )
    app = build_inbound_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4()), "services": services}}

    result = await app.ainvoke(state, config=config)

    assert result["outcome"] == "dispatched"
    assert len(crm.upsert_company_calls) == 1
    assert len(crm.upsert_contact_calls) == 1
    assert len(slack.calls) == 1
    assert email.calls == []  # the only thing suppression blocks

    lead = await db_session.get(Lead, state.lead_id)
    assert lead is not None
    assert lead.status is LeadStatus.ROUTED
    assert lead.routed_to is RoutingTarget.SALES
