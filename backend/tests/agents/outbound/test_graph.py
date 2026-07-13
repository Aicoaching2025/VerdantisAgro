"""End-to-end tests of the outbound graph's compliance-critical path: the
sanctions gate and the human-approval interrupt (rule 1).

Uses the in-memory checkpointer per CLAUDE.md's graph-testing convention,
real Postgres for persistence (Company/Lead/TradeSignal/VerificationResult),
and fakes for every external provider (already contract-tested separately
in tests/core/).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import verdantis.agents.outbound.nodes as nodes_module
import verdantis.core.evals.feedback as feedback_module
from verdantis.agents.outbound.graph import build_outbound_graph
from verdantis.agents.outbound.services import OutboundServices
from verdantis.agents.outbound.state import OutboundState
from verdantis.config.settings import Settings
from verdantis.core.adapters.base import TradeDataAdapter, TradeSignalRecord
from verdantis.core.crm.hubspot import HubSpotSyncResult
from verdantis.core.verification.base import (
    CorporateExistenceProvider,
    SanctionsProvider,
    VerificationOutcome,
)
from verdantis.core.verification.engine import VerificationEngine
from verdantis.db.enums import (
    LeadStatus,
    ProvenanceMethod,
    SignalBand,
    SignalType,
    Verdict,
)
from verdantis.db.models import Lead, Tenant
from verdantis.db.provenance import Provenance


class _FakeTradeDataAdapter(TradeDataAdapter):
    def __init__(self, legal_name: str = "Acme Trading Ltd") -> None:
        self.legal_name = legal_name

    async def fetch_signals(
        self, *, commodities: list[str], regions: list[str] | None = None
    ) -> list[TradeSignalRecord]:
        provenance = Provenance(
            source="fake",
            retrieved_at=datetime.now(UTC),
            confidence=0.9,
            method=ProvenanceMethod.DERIVED,
        )
        return [
            TradeSignalRecord(
                company_legal_name=self.legal_name,
                company_country="DE",
                signal_type=SignalType.SHIPMENT_VOLUME,
                commodity=commodities[0],
                band=SignalBand.HIGH,
                numeric_value=25000,
                provenance=provenance,
            ),
            TradeSignalRecord(
                company_legal_name=self.legal_name,
                company_country="DE",
                signal_type=SignalType.RECENCY,
                commodity=commodities[0],
                band=SignalBand.HIGH,
                numeric_value=10,
                provenance=provenance,
            ),
        ]


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


class _FakeDraftingClient:
    async def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        return "Fake outreach draft body."


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


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Verdantis", slug=f"verdantis-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.commit()
    return tenant


def _build_services(
    session: AsyncSession,
    *,
    sanctions_verdict: Verdict,
    fit_score: float,
    crm_client: _FakeCrmClient | None,
) -> OutboundServices:
    sanctions = _FakeVerificationProvider(sanctions_verdict)
    corporate = _FakeVerificationProvider(Verdict.PASS)
    return OutboundServices(
        session=session,
        trade_data_adapter=_FakeTradeDataAdapter(),
        verification_engine=VerificationEngine(
            session=session, sanctions_provider=sanctions, corporate_provider=corporate
        ),
        scoring_client=_FakeScoringClient(fit_score),
        drafting_client=_FakeDraftingClient(),
        enrichment_provider=None,
        crm_client=crm_client,
    )


async def test_sanctions_fail_never_reaches_interrupt(db_session: AsyncSession) -> None:
    tenant = await _make_tenant(db_session)
    services = _build_services(
        db_session, sanctions_verdict=Verdict.FAIL, fit_score=0.9, crm_client=None
    )
    app = build_outbound_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4()), "services": services}}

    result = await app.ainvoke(
        OutboundState(tenant_id=tenant.id, commodities=["cocoa"]), config=config
    )

    assert "__interrupt__" not in result
    assert result["outcomes"] == {next(iter(result["outcomes"])): "discarded_sanctions"}

    leads = (
        (await db_session.execute(select(Lead).where(Lead.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    assert len(leads) == 1
    assert leads[0].status is LeadStatus.DISCARDED


async def test_low_fit_never_reaches_interrupt(db_session: AsyncSession) -> None:
    tenant = await _make_tenant(db_session)
    services = _build_services(
        db_session, sanctions_verdict=Verdict.PASS, fit_score=0.1, crm_client=None
    )
    app = build_outbound_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4()), "services": services}}

    result = await app.ainvoke(
        OutboundState(tenant_id=tenant.id, commodities=["cocoa"], fit_threshold=0.6),
        config=config,
    )

    assert "__interrupt__" not in result
    assert result["outcomes"] == {next(iter(result["outcomes"])): "discarded_low_fit"}

    leads = (
        (await db_session.execute(select(Lead).where(Lead.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    assert leads[0].status is LeadStatus.DISCARDED


async def test_approval_gate_pauses_with_correct_payload_then_resumes_approved(
    db_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(db_session)
    crm = _FakeCrmClient()
    services = _build_services(
        db_session, sanctions_verdict=Verdict.PASS, fit_score=0.9, crm_client=crm
    )
    app = build_outbound_graph().compile(checkpointer=InMemorySaver())
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id, "services": services}}

    result = await app.ainvoke(
        OutboundState(tenant_id=tenant.id, commodities=["cocoa"], fit_threshold=0.6),
        config=config,
    )

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["legal_name"] == "Acme Trading Ltd"
    assert payload["fit_score"] == 0.9
    assert payload["fit_reasons"] == ["fake reason"]
    assert payload["draft_body"] == "Fake outreach draft body."
    assert payload["credibility"]["SANCTIONS_AML"] == "PASS"

    leads = (
        (await db_session.execute(select(Lead).where(Lead.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    assert leads[0].status is LeadStatus.PENDING_APPROVAL
    assert crm.upsert_company_calls == []  # must not sync before approval
    # LangSmith tracing is off in tests -> no run id generated, and
    # record_decision_node's feedback call below is a no-op, not an error.
    assert leads[0].fit_score_run_id is None

    final = await app.ainvoke(Command(resume={"action": "approve"}), config=config)

    assert "__interrupt__" not in final
    assert final["outcomes"] == {str(leads[0].company_id): "approved"}
    assert len(crm.upsert_company_calls) == 1
    assert crm.upsert_company_calls[0]["legal_name"] == "Acme Trading Ltd"

    await db_session.refresh(leads[0])
    assert leads[0].status is LeadStatus.ROUTED


async def test_approval_gate_resumes_rejected_without_crm_sync(
    db_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(db_session)
    crm = _FakeCrmClient()
    services = _build_services(
        db_session, sanctions_verdict=Verdict.PASS, fit_score=0.9, crm_client=crm
    )
    app = build_outbound_graph().compile(checkpointer=InMemorySaver())
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id, "services": services}}

    result = await app.ainvoke(
        OutboundState(tenant_id=tenant.id, commodities=["cocoa"], fit_threshold=0.6),
        config=config,
    )
    assert "__interrupt__" in result

    final = await app.ainvoke(Command(resume={"action": "reject"}), config=config)

    assert "__interrupt__" not in final
    assert final["outcomes"] == {next(iter(final["outcomes"])): "rejected"}
    assert crm.upsert_company_calls == []  # rejection must never sync to CRM

    leads = (
        (await db_session.execute(select(Lead).where(Lead.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    assert leads[0].status is LeadStatus.REJECTED


async def test_approval_decision_feeds_back_to_langsmith_when_tracing_enabled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With tracing on, score_fit_node must mint a run id and persist it on
    the lead, and record_decision_node must submit it as eval feedback --
    the actual "approve/reject decisions feed back as labels" loop CLAUDE.md
    asks for. LangSmith's Client is mocked; nothing here reaches the network."""
    tracing_settings = Settings(langsmith_tracing=True, langsmith_api_key="test-key")
    monkeypatch.setattr(nodes_module, "get_settings", lambda: tracing_settings)
    monkeypatch.setattr(feedback_module, "get_settings", lambda: tracing_settings)
    fake_langsmith_client = MagicMock()
    monkeypatch.setattr(feedback_module, "Client", lambda **_: fake_langsmith_client)

    tenant = await _make_tenant(db_session)
    services = _build_services(
        db_session, sanctions_verdict=Verdict.PASS, fit_score=0.9, crm_client=None
    )
    app = build_outbound_graph().compile(checkpointer=InMemorySaver())
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id, "services": services}}

    await app.ainvoke(
        OutboundState(tenant_id=tenant.id, commodities=["cocoa"], fit_threshold=0.6),
        config=config,
    )

    leads = (
        (await db_session.execute(select(Lead).where(Lead.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    run_id = leads[0].fit_score_run_id
    assert run_id is not None
    fake_langsmith_client.create_feedback.assert_not_called()  # not yet decided

    await app.ainvoke(Command(resume={"action": "approve"}), config=config)

    fake_langsmith_client.create_feedback.assert_called_once_with(
        run_id, key="human_decision", score=1.0, value="approve"
    )
