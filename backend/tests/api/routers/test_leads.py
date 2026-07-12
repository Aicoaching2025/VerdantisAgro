"""Tests for the lead inbox + dossier detail endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.api.deps import get_current_user, get_db
from verdantis.api.main import app
from verdantis.core.auth.clerk import ClerkUser
from verdantis.db.enums import LeadSource, LeadStatus
from verdantis.db.models import Company, Lead, Tenant


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Verdantis", slug=f"verdantis-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.commit()
    return tenant


@pytest.fixture
def _client(db_session: AsyncSession) -> AsyncClient:
    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_user() -> ClerkUser:
        return ClerkUser(user_id="user_test", claims={})

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _cleanup_overrides() -> AsyncIterator[None]:
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


async def test_missing_auth_returns_401(_client: AsyncClient) -> None:
    app.dependency_overrides.pop(get_current_user, None)
    async with _client as client:
        response = await client.get("/tenants/whatever/leads")
    assert response.status_code == 401


async def test_list_leads_filters_by_status_and_source(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    db_session.add_all(
        [
            Lead(
                tenant_id=tenant.id,
                source=LeadSource.OUTBOUND_DISCOVERY,
                status=LeadStatus.NEW,
            ),
            Lead(
                tenant_id=tenant.id,
                source=LeadSource.INBOUND_FORM,
                status=LeadStatus.ROUTED,
                requested_commodity="cocoa",
            ),
            Lead(
                tenant_id=tenant.id,
                source=LeadSource.INBOUND_FORM,
                status=LeadStatus.DISCARDED,
                requested_commodity="coffee",
            ),
        ]
    )
    await db_session.commit()

    async with _client as client:
        all_response = await client.get(f"/tenants/{tenant.slug}/leads")
        assert all_response.status_code == 200
        assert all_response.json()["total"] == 3

        inbound_response = await client.get(
            f"/tenants/{tenant.slug}/leads", params={"source": "INBOUND_FORM"}
        )
        assert inbound_response.json()["total"] == 2

        routed_response = await client.get(
            f"/tenants/{tenant.slug}/leads", params={"status": "ROUTED"}
        )
        body = routed_response.json()
        assert body["total"] == 1
        assert body["items"][0]["requested_commodity"] == "cocoa"


async def test_list_leads_paginates(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    db_session.add_all(
        [
            Lead(
                tenant_id=tenant.id,
                source=LeadSource.INBOUND_FORM,
                status=LeadStatus.NEW,
            )
            for _ in range(5)
        ]
    )
    await db_session.commit()

    async with _client as client:
        response = await client.get(
            f"/tenants/{tenant.slug}/leads", params={"limit": 2, "offset": 0}
        )

    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


async def test_get_lead_includes_dossier(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    company = Company(
        tenant_id=tenant.id,
        legal_name="Acme Trading Ltd",
        country="DE",
        match_key="acme trading ltd",
    )
    db_session.add(company)
    await db_session.flush()
    lead = Lead(
        tenant_id=tenant.id,
        company_id=company.id,
        source=LeadSource.INBOUND_FORM,
        status=LeadStatus.NEW,
        requested_commodity="cocoa",
        intake={"contact_email": "jane@example.com"},
    )
    db_session.add(lead)
    await db_session.commit()

    async with _client as client:
        response = await client.get(f"/tenants/{tenant.slug}/leads/{lead.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["lead"]["id"] == str(lead.id)
    assert body["intake"]["contact_email"] == "jane@example.com"
    assert body["dossier"]["legal_name"] == "Acme Trading Ltd"


async def test_get_lead_without_company_has_no_dossier(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    lead = Lead(
        tenant_id=tenant.id,
        source=LeadSource.INBOUND_FORM,
        status=LeadStatus.NEW,
    )
    db_session.add(lead)
    await db_session.commit()

    async with _client as client:
        response = await client.get(f"/tenants/{tenant.slug}/leads/{lead.id}")

    assert response.status_code == 200
    assert response.json()["dossier"] is None


async def test_get_unknown_lead_returns_404(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    async with _client as client:
        response = await client.get(f"/tenants/{tenant.slug}/leads/{uuid.uuid4()}")
    assert response.status_code == 404
