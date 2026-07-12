"""Tests for the tenant admin/settings config endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.api.deps import get_current_user, get_db
from verdantis.api.main import app
from verdantis.core.auth.clerk import ClerkUser
from verdantis.db.models import Tenant


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(
        name="Verdantis",
        slug=f"verdantis-{uuid.uuid4().hex[:8]}",
        config={"commodities": ["cocoa"], "outbound_fit_threshold": 0.7},
    )
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
        response = await client.get("/tenants/whatever/config")
    assert response.status_code == 401


async def test_get_config_returns_typed_view(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    async with _client as client:
        response = await client.get(f"/tenants/{tenant.slug}/config")

    assert response.status_code == 200
    body = response.json()
    assert body["commodities"] == ["cocoa"]
    assert body["outbound_fit_threshold"] == 0.7


async def test_get_config_for_unknown_tenant_returns_404(
    _client: AsyncClient,
) -> None:
    async with _client as client:
        response = await client.get("/tenants/does-not-exist/config")
    assert response.status_code == 404


async def test_put_config_replaces_and_persists(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    new_config = {
        "commodities": ["cocoa", "cashew"],
        "regions": ["EU"],
        "outbound_fit_threshold": 0.65,
        "inbound_fit_threshold": 0.4,
        "default_routing_target": "SALES",
        "ack_from_name": "Verdantis Sales",
    }

    async with _client as client:
        put_response = await client.put(
            f"/tenants/{tenant.slug}/config", json=new_config
        )
        assert put_response.status_code == 200
        assert put_response.json()["commodities"] == ["cocoa", "cashew"]

        get_response = await client.get(f"/tenants/{tenant.slug}/config")

    assert get_response.json()["ack_from_name"] == "Verdantis Sales"
    assert get_response.json()["inbound_fit_threshold"] == 0.4


async def test_put_config_rejects_invalid_threshold(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    async with _client as client:
        response = await client.put(
            f"/tenants/{tenant.slug}/config",
            json={"outbound_fit_threshold": 1.5},
        )
    assert response.status_code == 422
