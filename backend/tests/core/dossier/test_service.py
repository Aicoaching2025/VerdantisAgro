from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.core.dossier.service import CompanyNotFoundError, get_dossier
from verdantis.db.enums import CheckType, ProvenanceMethod, SignalType, Verdict
from verdantis.db.models import Company, Tenant
from verdantis.db.provenance import (
    Provenance,
    record_trade_signal,
    record_verification_result,
)


async def _provenance(confidence: float = 0.9) -> Provenance:
    return Provenance(
        source="test",
        retrieved_at=datetime.now(UTC),
        confidence=confidence,
        method=ProvenanceMethod.API,
    )


async def test_assembles_dossier_with_signals_and_verdicts(
    db_session: AsyncSession,
) -> None:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    other_tenant = Tenant(name="Tenant B", slug="tenant-b")
    db_session.add_all([tenant, other_tenant])
    await db_session.flush()

    company = Company(
        tenant_id=tenant.id, legal_name="Acme Trading Ltd", match_key="acme-trading-ltd"
    )
    db_session.add(company)
    await db_session.flush()

    await record_trade_signal(
        db_session,
        tenant_id=tenant.id,
        company_id=company.id,
        signal_type=SignalType.COMMODITY_MATCH,
        commodity="cocoa",
        provenance=await _provenance(),
    )
    await record_verification_result(
        db_session,
        tenant_id=tenant.id,
        company_id=company.id,
        check_type=CheckType.CORPORATE_EXISTENCE,
        verdict=Verdict.PASS,
        provenance=await _provenance(0.85),
    )
    await db_session.commit()

    dossier = await get_dossier(db_session, tenant_id=tenant.id, company_id=company.id)

    assert dossier.legal_name == "Acme Trading Ltd"
    assert dossier.is_sanctioned is False
    assert len(dossier.trade_signals) == 1
    assert dossier.trade_signals[0].signal_type is SignalType.COMMODITY_MATCH
    assert dossier.trade_signals[0].commodity == "cocoa"
    assert len(dossier.verification_results) == 1

    latest = dossier.latest_verdict_by_check
    assert latest[CheckType.CORPORATE_EXISTENCE].verdict is Verdict.PASS


async def test_latest_verdict_by_check_picks_most_recent(
    db_session: AsyncSession,
) -> None:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db_session.add(tenant)
    await db_session.flush()
    company = Company(
        tenant_id=tenant.id, legal_name="Acme Trading Ltd", match_key="acme-trading-ltd"
    )
    db_session.add(company)
    await db_session.flush()

    await record_verification_result(
        db_session,
        tenant_id=tenant.id,
        company_id=company.id,
        check_type=CheckType.CORPORATE_EXISTENCE,
        verdict=Verdict.INCONCLUSIVE,
        provenance=Provenance(
            source="test",
            retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
            confidence=0.5,
            method=ProvenanceMethod.API,
        ),
    )
    await record_verification_result(
        db_session,
        tenant_id=tenant.id,
        company_id=company.id,
        check_type=CheckType.CORPORATE_EXISTENCE,
        verdict=Verdict.PASS,
        provenance=Provenance(
            source="test",
            retrieved_at=datetime(2025, 6, 1, tzinfo=UTC),
            confidence=0.85,
            method=ProvenanceMethod.API,
        ),
    )
    await db_session.commit()

    dossier = await get_dossier(db_session, tenant_id=tenant.id, company_id=company.id)
    assert len(dossier.verification_results) == 2
    assert (
        dossier.latest_verdict_by_check[CheckType.CORPORATE_EXISTENCE].verdict
        is Verdict.PASS
    )


async def test_missing_company_raises(db_session: AsyncSession) -> None:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db_session.add(tenant)
    await db_session.commit()

    with pytest.raises(CompanyNotFoundError):
        await get_dossier(db_session, tenant_id=tenant.id, company_id=uuid.uuid4())


async def test_cross_tenant_company_raises(db_session: AsyncSession) -> None:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    db_session.add_all([tenant_a, tenant_b])
    await db_session.flush()
    company = Company(
        tenant_id=tenant_a.id,
        legal_name="Acme Trading Ltd",
        match_key="acme-trading-ltd",
    )
    db_session.add(company)
    await db_session.commit()

    with pytest.raises(CompanyNotFoundError):
        await get_dossier(db_session, tenant_id=tenant_b.id, company_id=company.id)
