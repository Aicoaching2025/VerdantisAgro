"""Tests for the suppression-list admin endpoints."""

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
    tenant = Tenant(name="Verdantis", slug=f"verdantis-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.commit()
    return tenant


@pytest.fixture
def _client(db_session: AsyncSession) -> AsyncClient:
    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_user() -> ClerkUser:
        return ClerkUser(user_id="user_admin_1", claims={})

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
        response = await client.get("/tenants/whatever/suppression")
    assert response.status_code == 401


async def test_add_list_and_remove_round_trip(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)

    async with _client as client:
        add_response = await client.post(
            f"/tenants/{tenant.slug}/suppression",
            json={"email": "jane@example.com", "reason": "unsubscribed"},
        )
        assert add_response.status_code == 201
        body = add_response.json()
        assert body["email"] == "jane@example.com"
        assert body["reason"] == "unsubscribed"
        assert body["added_by"] == "user_admin_1"
        entry_id = body["id"]

        list_response = await client.get(f"/tenants/{tenant.slug}/suppression")
        assert list_response.status_code == 200
        items = list_response.json()
        assert len(items) == 1
        assert items[0]["id"] == entry_id

        delete_response = await client.delete(
            f"/tenants/{tenant.slug}/suppression/{entry_id}"
        )
        assert delete_response.status_code == 204

        list_after_response = await client.get(f"/tenants/{tenant.slug}/suppression")
        assert list_after_response.json() == []


async def test_add_is_idempotent_via_api(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)

    async with _client as client:
        first = await client.post(
            f"/tenants/{tenant.slug}/suppression", json={"email": "jane@example.com"}
        )
        second = await client.post(
            f"/tenants/{tenant.slug}/suppression", json={"email": "jane@example.com"}
        )

    assert first.json()["id"] == second.json()["id"]


async def test_remove_unknown_entry_returns_404(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    async with _client as client:
        response = await client.delete(
            f"/tenants/{tenant.slug}/suppression/{uuid.uuid4()}"
        )
    assert response.status_code == 404


async def test_invalid_email_returns_422(
    _client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await _make_tenant(db_session)
    async with _client as client:
        response = await client.post(
            f"/tenants/{tenant.slug}/suppression", json={"email": "not-an-email"}
        )
    assert response.status_code == 422
