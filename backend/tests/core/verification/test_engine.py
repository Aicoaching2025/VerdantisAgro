"""VerificationEngine orchestration against real Postgres, with fake
providers standing in for the HTTP-backed ones (already contract-tested
separately). This is where the sanctions-blocks-routing gate itself gets
verified end to end.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.core.verification.base import (
    CorporateExistenceProvider,
    SanctionsProvider,
    VerificationOutcome,
)
from verdantis.core.verification.engine import VerificationEngine
from verdantis.db.enums import CheckType, ProvenanceMethod, Verdict
from verdantis.db.models import Company, Tenant, VerificationResult
from verdantis.db.provenance import Provenance


class _FakeProvider(SanctionsProvider, CorporateExistenceProvider):
    """Stands in for either ABC — returns a fixed verdict, counts calls."""

    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict
        self.call_count = 0

    async def check(
        self, *, legal_name: str, country: str | None
    ) -> VerificationOutcome:
        self.call_count += 1
        return VerificationOutcome(
            verdict=self.verdict,
            evidence={"fake": True},
            provenance=Provenance(
                source="fake",
                retrieved_at=datetime.now(UTC),
                confidence=1.0,
                method=ProvenanceMethod.MANUAL,
            ),
        )


async def _make_company(session: AsyncSession) -> tuple[Tenant, Company]:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    session.add(tenant)
    await session.flush()
    company = Company(
        tenant_id=tenant.id, legal_name="Acme Trading Ltd", match_key="acme-trading-ltd"
    )
    session.add(company)
    await session.commit()
    return tenant, company


async def test_sanctions_fail_blocks_downstream_checks(
    db_session: AsyncSession,
) -> None:
    tenant, company = await _make_company(db_session)
    sanctions = _FakeProvider(Verdict.FAIL)
    corporate = _FakeProvider(Verdict.PASS)
    engine = VerificationEngine(
        session=db_session, sanctions_provider=sanctions, corporate_provider=corporate
    )

    summary = await engine.verify(tenant_id=tenant.id, company_id=company.id)
    await db_session.commit()

    assert summary.blocked is True
    assert summary.sanctions_verdict is Verdict.FAIL
    assert summary.corporate_verdict is None
    assert summary.activity_verdict is None
    assert summary.is_sanctioned is True
    assert corporate.call_count == 0  # the gate must prevent this from ever running

    results = (
        (
            await db_session.execute(
                select(VerificationResult).where(
                    VerificationResult.company_id == company.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert {r.check_type for r in results} == {CheckType.SANCTIONS_AML}

    await db_session.refresh(company)
    assert company.is_sanctioned is True
    assert company.credibility_score == 0.0
    assert company.credibility_computed_at is not None


async def test_sanctions_pass_runs_all_checks(db_session: AsyncSession) -> None:
    tenant, company = await _make_company(db_session)
    sanctions = _FakeProvider(Verdict.PASS)
    corporate = _FakeProvider(Verdict.PASS)
    engine = VerificationEngine(
        session=db_session, sanctions_provider=sanctions, corporate_provider=corporate
    )

    summary = await engine.verify(tenant_id=tenant.id, company_id=company.id)
    await db_session.commit()

    assert summary.blocked is False
    assert summary.sanctions_verdict is Verdict.PASS
    assert summary.corporate_verdict is Verdict.PASS
    assert summary.activity_verdict is Verdict.FAIL  # no trade signals exist yet
    assert summary.is_sanctioned is False
    assert corporate.call_count == 1

    results = (
        (
            await db_session.execute(
                select(VerificationResult).where(
                    VerificationResult.company_id == company.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert {r.check_type for r in results} == {
        CheckType.SANCTIONS_AML,
        CheckType.CORPORATE_EXISTENCE,
        CheckType.TRADE_ACTIVITY,
    }

    await db_session.refresh(company)
    # corporate PASS (1.0) + activity FAIL (0.0), averaged.
    assert company.credibility_score == 0.5
    assert company.credibility_computed_at is not None
