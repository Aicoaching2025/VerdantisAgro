"""Tests for the outbound run-trigger + approvals API.

The graph's own interrupt/resume mechanics are already exhaustively tested
in tests/agents/outbound/test_graph.py — these tests focus on the API
surface: the trigger endpoint's synchronous validation/response, and the
approvals endpoints reading/resuming a *real* interrupted thread through a
checkpointer + services the router is monkeypatched to use (production uses
the real Postgres checkpointer and real providers; here fakes and an
in-memory checkpointer keep the test self-contained and fast, same as
tests/agents/outbound/test_graph.py's own fakes).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import verdantis.api.routers.outbound as outbound_router
from verdantis.agents.outbound.graph import build_outbound_graph
from verdantis.agents.outbound.services import OutboundServices
from verdantis.agents.outbound.state import OutboundState
from verdantis.agents.shared.run_config import build_run_config
from verdantis.api.deps import get_current_user, get_db
from verdantis.api.main import app
from verdantis.core.adapters.base import TradeSignalRecord
from verdantis.core.auth.clerk import ClerkUser
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
from verdantis.db.redis import get_redis


class _FakeTradeDataAdapter:
    async def fetch_signals(
        self, *, commodities: list[str], regions: list[str] | None = None
    ) -> list[TradeSignalRecord]:
        return [
            TradeSignalRecord(
                company_legal_name="Acme Trading Ltd",
                company_country="DE",
                signal_type=SignalType.SHIPMENT_VOLUME,
                commodity=commodities[0],
                band=SignalBand.HIGH,
                numeric_value=25000,
                provenance=Provenance(
                    source="fake",
                    retrieved_at=datetime.now(UTC),
                    confidence=0.9,
                    method=ProvenanceMethod.DERIVED,
                ),
            )
        ]


class _FakeVerificationProvider(SanctionsProvider, CorporateExistenceProvider):
    async def check(
        self, *, legal_name: str, country: str | None
    ) -> VerificationOutcome:
        return VerificationOutcome(
            verdict=Verdict.PASS,
            evidence={"fake": True},
            provenance=Provenance(
                source="fake",
                retrieved_at=datetime.now(UTC),
                confidence=1.0,
                method=ProvenanceMethod.MANUAL,
            ),
        )


class _FakeScoringClient:
    async def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        return json.dumps({"score": 0.9, "reasons": ["fake reason"]})


class _FakeDraftingClient:
    async def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        return "Fake draft body."


def _fake_services(session: AsyncSession) -> OutboundServices:
    return OutboundServices(
        session=session,
        trade_data_adapter=_FakeTradeDataAdapter(),
        verification_engine=VerificationEngine(
            session=session,
            sanctions_provider=_FakeVerificationProvider(),
            corporate_provider=_FakeVerificationProvider(),
        ),
        scoring_client=_FakeScoringClient(),
        drafting_client=_FakeDraftingClient(),
    )


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(
        name="Verdantis",
        slug=f"verdantis-{uuid.uuid4().hex[:8]}",
        config={"commodities": ["cocoa"]},
    )
    session.add(tenant)
    await session.commit()
    return tenant


async def _seed_pending_approval(
    session: AsyncSession, tenant: Tenant, saver: InMemorySaver
) -> tuple[Lead, str]:
    """Runs the real outbound graph against fakes up to the interrupt — the
    same graph, same nodes, same PENDING_APPROVAL side effects a real run
    would produce, just with a fake trade-data/scoring/drafting stack."""
    thread_id = str(uuid.uuid4())
    services = _fake_services(session)
    compiled = build_outbound_graph().compile(checkpointer=saver)
    config = build_run_config(
        tenant_id=tenant.id,
        capability="outbound",
        thread_id=thread_id,
        services=services,
    )
    state = OutboundState(tenant_id=tenant.id, commodities=["cocoa"])
    result = await compiled.ainvoke(state, config=config)
    assert "__interrupt__" in result

    lead = (
        await session.execute(select(Lead).where(Lead.tenant_id == tenant.id))
    ).scalar_one()
    assert lead.status is LeadStatus.PENDING_APPROVAL
    assert lead.thread_id == thread_id
    return lead, thread_id


@pytest.fixture
def _memory_checkpointer() -> tuple[Any, InMemorySaver]:
    saver = InMemorySaver()

    @asynccontextmanager
    async def _get_checkpointer(
        *, use_memory: bool = False
    ) -> AsyncIterator[InMemorySaver]:
        yield saver

    return _get_checkpointer, saver


@pytest.fixture
def _client(
    db_session: AsyncSession, redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> AsyncClient:
    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_redis() -> AsyncIterator[Redis]:
        yield redis_client

    async def _override_user() -> ClerkUser:
        return ClerkUser(user_id="user_test", claims={})

    @asynccontextmanager
    async def _override_session_scope() -> AsyncIterator[AsyncSession]:
        # Background tasks must see the same test-transaction session, not a
        # fresh one against the real dev database.
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis
    app.dependency_overrides[get_current_user] = _override_user
    monkeypatch.setattr(outbound_router, "session_scope", _override_session_scope)
    monkeypatch.setattr(outbound_router, "get_redis_client", lambda: redis_client)

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _cleanup_overrides() -> AsyncIterator[None]:
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_current_user, None)


async def test_trigger_run_rejects_tenant_with_no_commodities(
    _client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(outbound_router, "_run_outbound_graph", _noop)
    tenant = Tenant(
        name="Verdantis", slug=f"verdantis-{uuid.uuid4().hex[:8]}", config={}
    )
    db_session.add(tenant)
    await db_session.commit()

    async with _client as client:
        response = await client.post(
            f"/tenants/{tenant.slug}/outbound/runs",
            files={"export_file": ("export.csv", b"col1,col2\n", "text/csv")},
        )

    assert response.status_code == 400


async def test_trigger_run_accepted_with_commodities_configured(
    _client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []

    async def _capture(*args: Any, **kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(outbound_router, "_run_outbound_graph", _capture)
    tenant = await _make_tenant(db_session)

    async with _client as client:
        response = await client.post(
            f"/tenants/{tenant.slug}/outbound/runs",
            files={"export_file": ("export.csv", b"col1,col2\n", "text/csv")},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    uuid.UUID(body["thread_id"])  # valid UUID
    assert len(calls) == 1


async def test_missing_auth_returns_401(_client: AsyncClient) -> None:
    app.dependency_overrides.pop(get_current_user, None)
    async with _client as client:
        response = await client.get("/tenants/whatever/outbound/approvals")
    assert response.status_code == 401


async def test_approvals_list_and_approve_decision_end_to_end(
    _client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    _memory_checkpointer: tuple[Any, InMemorySaver],
) -> None:
    get_checkpointer_fn, saver = _memory_checkpointer
    monkeypatch.setattr(outbound_router, "get_checkpointer", get_checkpointer_fn)
    monkeypatch.setattr(
        outbound_router,
        "build_outbound_services",
        lambda session, **kwargs: _fake_services(session),
    )

    tenant = await _make_tenant(db_session)
    lead, thread_id = await _seed_pending_approval(db_session, tenant, saver)

    async with _client as client:
        list_response = await client.get(f"/tenants/{tenant.slug}/outbound/approvals")
        assert list_response.status_code == 200
        items = list_response.json()
        assert len(items) == 1
        assert items[0]["lead_id"] == str(lead.id)
        assert items[0]["legal_name"] == "Acme Trading Ltd"
        assert items[0]["fit_score"] == 0.9
        assert items[0]["draft_body"] == "Fake draft body."

        decide_response = await client.post(
            f"/tenants/{tenant.slug}/outbound/approvals/{lead.id}/decision",
            json={"action": "approve"},
        )
        assert decide_response.status_code == 202

    # The background resume ran inline under ASGITransport -> assert its effect.
    await db_session.refresh(lead)
    assert lead.status is LeadStatus.ROUTED


async def test_decision_on_non_pending_lead_returns_409(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    lead = Lead(
        tenant_id=tenant.id,
        source="OUTBOUND_DISCOVERY",
        status=LeadStatus.NEW,
    )
    db_session.add(lead)
    await db_session.commit()

    async with _client as client:
        response = await client.post(
            f"/tenants/{tenant.slug}/outbound/approvals/{lead.id}/decision",
            json={"action": "approve"},
        )

    assert response.status_code == 409
