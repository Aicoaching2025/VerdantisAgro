"""Dossier assembly service.

Fetches Company + TradeSignal + VerificationResult from the db/ repository
layer and converts to DB-agnostic Pydantic domain models. This is the only
place SQLAlchemy dossier-related objects get read above db/ — they never
leave this module as ORM objects (see models/dossier.py).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.db.models import Company, TradeSignal, VerificationResult
from verdantis.models.dossier import (
    CompanyDossier,
    TradeSignalView,
    VerificationVerdictView,
)


class CompanyNotFoundError(LookupError):
    def __init__(self, *, tenant_id: uuid.UUID, company_id: uuid.UUID) -> None:
        super().__init__(f"company {company_id} not found for tenant {tenant_id}")
        self.tenant_id = tenant_id
        self.company_id = company_id


async def get_dossier(
    session: AsyncSession, *, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> CompanyDossier:
    company = (
        await session.execute(
            select(Company).where(
                Company.id == company_id, Company.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if company is None:
        raise CompanyNotFoundError(tenant_id=tenant_id, company_id=company_id)

    signals = (
        (
            await session.execute(
                select(TradeSignal).where(TradeSignal.company_id == company_id)
            )
        )
        .scalars()
        .all()
    )
    results = (
        (
            await session.execute(
                select(VerificationResult).where(
                    VerificationResult.company_id == company_id
                )
            )
        )
        .scalars()
        .all()
    )

    return CompanyDossier(
        company_id=company.id,
        tenant_id=company.tenant_id,
        legal_name=company.legal_name,
        display_name=company.display_name,
        country=company.country,
        vat_number=company.vat_number,
        eori_number=company.eori_number,
        duns_number=company.duns_number,
        is_sanctioned=company.is_sanctioned,
        sanctions_review_suggested=company.sanctions_review_suggested,
        credibility_score=company.credibility_score,
        trade_signals=[
            TradeSignalView(
                signal_type=s.signal_type,
                commodity=s.commodity,
                band=s.band,
                numeric_value=s.numeric_value,
                period_start=s.period_start,
                period_end=s.period_end,
                details=s.details,
                source=s.source,
                retrieved_at=s.retrieved_at,
                confidence=s.confidence,
            )
            for s in signals
        ],
        verification_results=[
            VerificationVerdictView(
                check_type=r.check_type,
                verdict=r.verdict,
                evidence=r.evidence,
                source=r.source,
                retrieved_at=r.retrieved_at,
                confidence=r.confidence,
            )
            for r in results
        ],
    )
