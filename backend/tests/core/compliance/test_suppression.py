from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.core.compliance.suppression import (
    add_to_suppression_list,
    is_suppressed,
    remove_from_suppression_list,
)
from verdantis.core.security.encryption import decrypt_pii
from verdantis.db.models import Tenant


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Verdantis", slug=f"verdantis-{uuid.uuid4().hex[:8]}")
    session.add(tenant)
    await session.commit()
    return tenant


async def test_is_suppressed_false_when_absent(db_session: AsyncSession) -> None:
    tenant = await _make_tenant(db_session)
    assert not await is_suppressed(
        db_session, tenant_id=tenant.id, email="jane@example.com"
    )


async def test_add_then_is_suppressed_true(db_session: AsyncSession) -> None:
    tenant = await _make_tenant(db_session)
    await add_to_suppression_list(
        db_session,
        tenant_id=tenant.id,
        email="Jane@Example.com",
        added_by="user_admin",
        reason="unsubscribed",
    )
    await db_session.commit()

    assert await is_suppressed(
        db_session, tenant_id=tenant.id, email="jane@example.com"
    )
    # Case/whitespace insensitive normalization.
    assert await is_suppressed(
        db_session, tenant_id=tenant.id, email="  JANE@EXAMPLE.COM  "
    )


async def test_add_is_idempotent(db_session: AsyncSession) -> None:
    tenant = await _make_tenant(db_session)
    first = await add_to_suppression_list(
        db_session, tenant_id=tenant.id, email="jane@example.com", added_by="user_a"
    )
    second = await add_to_suppression_list(
        db_session, tenant_id=tenant.id, email="jane@example.com", added_by="user_b"
    )
    await db_session.commit()

    assert first.id == second.id


async def test_add_stores_encrypted_email_not_plaintext(
    db_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(db_session)
    entry = await add_to_suppression_list(
        db_session, tenant_id=tenant.id, email="jane@example.com", added_by="user_a"
    )
    await db_session.commit()

    assert entry.email_encrypted != "jane@example.com"
    assert decrypt_pii(entry.email_encrypted) == "jane@example.com"


async def test_suppression_is_tenant_scoped(db_session: AsyncSession) -> None:
    tenant_a = await _make_tenant(db_session)
    tenant_b = await _make_tenant(db_session)
    await add_to_suppression_list(
        db_session, tenant_id=tenant_a.id, email="jane@example.com", added_by="user_a"
    )
    await db_session.commit()

    assert await is_suppressed(
        db_session, tenant_id=tenant_a.id, email="jane@example.com"
    )
    assert not await is_suppressed(
        db_session, tenant_id=tenant_b.id, email="jane@example.com"
    )


async def test_remove_from_suppression_list(db_session: AsyncSession) -> None:
    tenant = await _make_tenant(db_session)
    entry = await add_to_suppression_list(
        db_session, tenant_id=tenant.id, email="jane@example.com", added_by="user_a"
    )
    await db_session.commit()

    removed = await remove_from_suppression_list(
        db_session, tenant_id=tenant.id, entry_id=entry.id
    )
    await db_session.commit()

    assert removed
    assert not await is_suppressed(
        db_session, tenant_id=tenant.id, email="jane@example.com"
    )


async def test_remove_unknown_entry_returns_false(db_session: AsyncSession) -> None:
    tenant = await _make_tenant(db_session)
    removed = await remove_from_suppression_list(
        db_session, tenant_id=tenant.id, entry_id=uuid.uuid4()
    )
    assert not removed


async def test_remove_wrong_tenant_returns_false(db_session: AsyncSession) -> None:
    tenant_a = await _make_tenant(db_session)
    tenant_b = await _make_tenant(db_session)
    entry = await add_to_suppression_list(
        db_session, tenant_id=tenant_a.id, email="jane@example.com", added_by="user_a"
    )
    await db_session.commit()

    removed = await remove_from_suppression_list(
        db_session, tenant_id=tenant_b.id, entry_id=entry.id
    )
    assert not removed
