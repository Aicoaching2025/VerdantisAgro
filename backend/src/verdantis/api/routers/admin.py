"""Tenant admin/settings: read and replace the tenant-scoped config object
(CLAUDE.md rule 7 — commodity set, regions, ICP thresholds, routing rules).
Requires Clerk auth (see api/main.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.api.deps import get_db
from verdantis.db.models import Tenant
from verdantis.models.tenant_config import TenantConfig

router = APIRouter(prefix="/tenants/{tenant_slug}/config", tags=["admin"])


async def _get_tenant(session: AsyncSession, tenant_slug: str) -> Tenant:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found"
        )
    return tenant


@router.get("", response_model=TenantConfig)
async def get_tenant_config(
    tenant_slug: str, session: AsyncSession = Depends(get_db)
) -> TenantConfig:
    tenant = await _get_tenant(session, tenant_slug)
    return TenantConfig.from_raw(tenant.config)


@router.put("", response_model=TenantConfig)
async def replace_tenant_config(
    tenant_slug: str,
    payload: TenantConfig,
    session: AsyncSession = Depends(get_db),
) -> TenantConfig:
    tenant = await _get_tenant(session, tenant_slug)
    tenant.config = payload.model_dump(mode="json")
    await session.commit()
    return payload
