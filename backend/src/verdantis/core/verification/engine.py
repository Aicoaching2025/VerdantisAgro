"""Verification engine: orchestrates sanctions, corporate existence, and
trade-activity checks and persists each verdict via db.provenance.

Sanctions runs FIRST, always, and gates everything else — rule 4 is a hard
requirement, not a UX nicety. The gate check is written as "anything other
than an explicit PASS blocks" rather than "FAIL blocks", so a future verdict
value this code doesn't yet know about fails closed instead of silently
sliding through.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.core.scoring.credibility import compute_credibility_score
from verdantis.core.verification.activity import assess_trade_activity
from verdantis.core.verification.base import (
    CorporateExistenceProvider,
    SanctionsProvider,
)
from verdantis.db.enums import CheckType, Verdict
from verdantis.db.models import Company, TradeSignal
from verdantis.db.provenance import record_verification_result


@dataclass(frozen=True)
class VerificationSummary:
    company_id: uuid.UUID
    sanctions_verdict: Verdict
    corporate_verdict: Verdict | None
    activity_verdict: Verdict | None
    is_sanctioned: bool
    blocked: bool


class VerificationEngine:
    def __init__(
        self,
        *,
        session: AsyncSession,
        sanctions_provider: SanctionsProvider,
        corporate_provider: CorporateExistenceProvider,
    ) -> None:
        self._session = session
        self._sanctions_provider = sanctions_provider
        self._corporate_provider = corporate_provider

    async def verify(
        self, *, tenant_id: uuid.UUID, company_id: uuid.UUID
    ) -> VerificationSummary:
        company = (
            await self._session.execute(
                select(Company).where(
                    Company.id == company_id, Company.tenant_id == tenant_id
                )
            )
        ).scalar_one()

        sanctions_outcome = await self._sanctions_provider.check(
            legal_name=company.legal_name, country=company.country
        )
        await record_verification_result(
            self._session,
            tenant_id=tenant_id,
            company_id=company_id,
            check_type=CheckType.SANCTIONS_AML,
            verdict=sanctions_outcome.verdict,
            provenance=sanctions_outcome.provenance,
            evidence=sanctions_outcome.evidence,
        )

        if sanctions_outcome.verdict is not Verdict.PASS:
            # Hard gate: don't run the other checks, don't let anything
            # downstream infer a clean bill of health from their absence.
            summary = VerificationSummary(
                company_id=company_id,
                sanctions_verdict=sanctions_outcome.verdict,
                corporate_verdict=None,
                activity_verdict=None,
                is_sanctioned=company.is_sanctioned,
                blocked=True,
            )
            await self._record_credibility_score(company, summary)
            return summary

        corporate_outcome = await self._corporate_provider.check(
            legal_name=company.legal_name, country=company.country
        )
        await record_verification_result(
            self._session,
            tenant_id=tenant_id,
            company_id=company_id,
            check_type=CheckType.CORPORATE_EXISTENCE,
            verdict=corporate_outcome.verdict,
            provenance=corporate_outcome.provenance,
            evidence=corporate_outcome.evidence,
        )

        existing_signals = (
            (
                await self._session.execute(
                    select(TradeSignal).where(TradeSignal.company_id == company_id)
                )
            )
            .scalars()
            .all()
        )
        activity_outcome = assess_trade_activity(list(existing_signals))
        await record_verification_result(
            self._session,
            tenant_id=tenant_id,
            company_id=company_id,
            check_type=CheckType.TRADE_ACTIVITY,
            verdict=activity_outcome.verdict,
            provenance=activity_outcome.provenance,
            evidence=activity_outcome.evidence,
        )

        summary = VerificationSummary(
            company_id=company_id,
            sanctions_verdict=sanctions_outcome.verdict,
            corporate_verdict=corporate_outcome.verdict,
            activity_verdict=activity_outcome.verdict,
            is_sanctioned=company.is_sanctioned,
            blocked=False,
        )
        await self._record_credibility_score(company, summary)
        return summary

    async def _record_credibility_score(
        self, company: Company, summary: VerificationSummary
    ) -> None:
        # Denormalized rollup of already-provenanced verdicts (see
        # core.scoring.credibility) -- not a new signal, so no separate
        # provenance write.
        company.credibility_score = compute_credibility_score(summary)
        company.credibility_computed_at = datetime.now(UTC)
        await self._session.flush()
