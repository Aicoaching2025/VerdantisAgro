"""Lead inbox + dossier/evidence detail. Read-only — the only writes to a
Lead happen inside the outbound/inbound graphs, never from a dashboard GET.
Requires Clerk auth (see api/main.py).

The scope doc's separate "intake view" dashboard section is just this same
listing filtered to `source=INBOUND_FORM` — no separate endpoint needed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.api.deps import get_db
from verdantis.api.schemas.leads import (
    LeadDetailResponse,
    LeadListResponse,
    LeadSummary,
)
from verdantis.core.dossier.service import CompanyNotFoundError, get_dossier
from verdantis.db.enums import LeadSource, LeadStatus
from verdantis.db.models import Lead, Tenant

router = APIRouter(prefix="/tenants/{tenant_slug}/leads", tags=["leads"])


async def _get_tenant(session: AsyncSession, tenant_slug: str) -> Tenant:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found"
        )
    return tenant


@router.get("", response_model=LeadListResponse)
async def list_leads(
    tenant_slug: str,
    lead_status: LeadStatus | None = Query(default=None, alias="status"),
    source: LeadSource | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> LeadListResponse:
    tenant = await _get_tenant(session, tenant_slug)

    filters = [Lead.tenant_id == tenant.id]
    if lead_status is not None:
        filters.append(Lead.status == lead_status)
    if source is not None:
        filters.append(Lead.source == source)

    total = (
        await session.execute(select(func.count()).select_from(Lead).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(Lead)
                .where(*filters)
                .order_by(Lead.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return LeadListResponse(
        items=[LeadSummary.model_validate(lead) for lead in rows], total=total
    )


@router.get("/{lead_id}", response_model=LeadDetailResponse)
async def get_lead(
    tenant_slug: str,
    lead_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> LeadDetailResponse:
    tenant = await _get_tenant(session, tenant_slug)
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="lead not found"
        )

    dossier = None
    if lead.company_id is not None:
        try:
            dossier = await get_dossier(
                session, tenant_id=tenant.id, company_id=lead.company_id
            )
        except CompanyNotFoundError:
            dossier = None

    return LeadDetailResponse(
        lead=LeadSummary.model_validate(lead),
        incoterm=lead.incoterm,
        payment_terms=lead.payment_terms,
        intake=lead.intake,
        dossier=dossier,
    )
