"""Tests for the public inbound-submission endpoint's synchronous behavior:
tenant resolution, rate limiting, and the fast-ack response. The graph
execution itself (normalize/verify/score/route/dispatch/ack) is already
covered end-to-end in tests/agents/inbound/test_graph.py — here the
background task is stubbed out so these tests don't depend on production
Settings pointing at a reachable database/Redis.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

import verdantis.api.routers.inbound as inbound_router
from verdantis.api.deps import get_db
from verdantis.api.main import app
from verdantis.core.security.pii import decrypt_intake_pii
from verdantis.db.enums import LeadSource
from verdantis.db.models import Lead, Tenant
from verdantis.db.redis import get_redis

_SUBMISSION = {
    "legal_name": "Acme Trading Ltd",
    "country": "DE",
    "contact_name": "Jane Buyer",
    "contact_email": "jane@example.com",
    "requested_commodity": "cocoa",
    "incoterm": "FOB",
    "payment_terms": "letter of credit",
    "message": "Interested in a trial order",
}


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Verdantis", slug=f"verdantis-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.commit()
    return tenant


@pytest.fixture
def _client(
    db_session: AsyncSession, redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> tuple[AsyncClient, AsyncSession]:
    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_redis() -> AsyncIterator[Redis]:
        yield redis_client

    async def _noop_background(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(inbound_router, "_run_inbound_graph", _noop_background)
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return client, db_session


@pytest.fixture(autouse=True)
def _cleanup_overrides() -> AsyncIterator[None]:
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis, None)


async def test_unknown_tenant_returns_404(
    _client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, _ = _client
    async with client:
        response = await client.post(
            "/tenants/does-not-exist/inbound/submissions", json=_SUBMISSION
        )
    assert response.status_code == 404


async def test_valid_submission_returns_202_and_persists_lead(
    _client: tuple[AsyncClient, AsyncSession],
    db_session: AsyncSession,
) -> None:
    client, _ = _client
    tenant = await _make_tenant(db_session)

    async with client:
        response = await client.post(
            f"/tenants/{tenant.slug}/inbound/submissions", json=_SUBMISSION
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "received"
    lead_id = uuid.UUID(body["lead_id"])

    lead = await db_session.get(Lead, lead_id)
    assert lead is not None
    assert lead.tenant_id == tenant.id
    assert lead.source is LeadSource.INBOUND_FORM
    assert lead.requested_commodity == "cocoa"
    assert lead.intake is not None
    # PII is encrypted at rest -> the raw column never holds the plaintext.
    assert lead.intake["contact_email"] != "jane@example.com"
    assert decrypt_intake_pii(lead.intake)["contact_email"] == "jane@example.com"


async def test_invalid_email_returns_422(
    _client: tuple[AsyncClient, AsyncSession],
    db_session: AsyncSession,
) -> None:
    client, _ = _client
    tenant = await _make_tenant(db_session)
    bad_submission = {**_SUBMISSION, "contact_email": "not-an-email"}

    async with client:
        response = await client.post(
            f"/tenants/{tenant.slug}/inbound/submissions", json=bad_submission
        )

    assert response.status_code == 422


async def test_rate_limit_returns_429_after_limit_exceeded(
    _client: tuple[AsyncClient, AsyncSession],
    db_session: AsyncSession,
) -> None:
    client, _ = _client
    tenant = await _make_tenant(db_session)

    async with client:
        statuses = []
        for _ in range(inbound_router._RATE_LIMIT + 1):
            response = await client.post(
                f"/tenants/{tenant.slug}/inbound/submissions", json=_SUBMISSION
            )
            statuses.append(response.status_code)

    assert statuses[: inbound_router._RATE_LIMIT] == [202] * inbound_router._RATE_LIMIT
    assert statuses[-1] == 429
