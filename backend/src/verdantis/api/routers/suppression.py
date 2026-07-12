"""Suppression list admin: view, add, and remove do-not-contact entries
(scope doc Section 8: "Maintain a suppression list checked before any
send"). The actual check happens in agents/inbound/nodes.py::_send_ack;
this router is only the human-facing management surface. Requires Clerk
auth (see api/main.py).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.api.deps import get_current_user, get_db
from verdantis.api.schemas.suppression import (
    SuppressionEntryRequest,
    SuppressionEntryResponse,
)
from verdantis.core.auth.clerk import ClerkUser
from verdantis.core.compliance.suppression import (
    add_to_suppression_list,
    remove_from_suppression_list,
)
from verdantis.core.security.encryption import decrypt_pii
from verdantis.db.models import SuppressionEntry, Tenant

router = APIRouter(prefix="/tenants/{tenant_slug}/suppression", tags=["suppression"])


async def _get_tenant(session: AsyncSession, tenant_slug: str) -> Tenant:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found"
        )
    return tenant


def _to_response(entry: SuppressionEntry) -> SuppressionEntryResponse:
    return SuppressionEntryResponse(
        id=entry.id,
        email=decrypt_pii(entry.email_encrypted),
        reason=entry.reason,
        added_by=entry.added_by,
        created_at=entry.created_at,
    )


@router.get("", response_model=list[SuppressionEntryResponse])
async def list_suppression_entries(
    tenant_slug: str, session: AsyncSession = Depends(get_db)
) -> list[SuppressionEntryResponse]:
    tenant = await _get_tenant(session, tenant_slug)
    rows = (
        (
            await session.execute(
                select(SuppressionEntry)
                .where(SuppressionEntry.tenant_id == tenant.id)
                .order_by(SuppressionEntry.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_response(entry) for entry in rows]


@router.post(
    "", response_model=SuppressionEntryResponse, status_code=status.HTTP_201_CREATED
)
async def add_suppression_entry(
    tenant_slug: str,
    payload: SuppressionEntryRequest,
    session: AsyncSession = Depends(get_db),
    current_user: ClerkUser = Depends(get_current_user),
) -> SuppressionEntryResponse:
    tenant = await _get_tenant(session, tenant_slug)
    entry = await add_to_suppression_list(
        session,
        tenant_id=tenant.id,
        email=payload.email,
        added_by=current_user.user_id,
        reason=payload.reason,
    )
    await session.commit()
    return _to_response(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_suppression_entry(
    tenant_slug: str,
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    tenant = await _get_tenant(session, tenant_slug)
    removed = await remove_from_suppression_list(
        session, tenant_id=tenant.id, entry_id=entry_id
    )
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="entry not found"
        )
    await session.commit()
