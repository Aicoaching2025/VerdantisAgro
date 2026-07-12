"""Formalizes the manual smoke tests run during code review into real pytest:
cross-tenant rejection, the sticky sanctions flag, sanctions_review_suggested
on a conflicting PASS, and the audited clear_sanctions_flag override path.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.db.enums import CheckType, ProvenanceMethod, Verdict
from verdantis.db.models import Company, Tenant
from verdantis.db.provenance import (
    CompanyTenantMismatchError,
    Provenance,
    clear_sanctions_flag,
    record_verification_result,
)


def _provenance(confidence: float = 0.9) -> Provenance:
    return Provenance(
        source="opensanctions",
        retrieved_at=datetime.now(UTC),
        confidence=confidence,
        method=ProvenanceMethod.API,
    )


@pytest_asyncio.fixture
async def two_tenants_with_company(
    db_session: AsyncSession,
) -> tuple[Tenant, Tenant, Company]:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    db_session.add_all([tenant_a, tenant_b])
    await db_session.flush()

    company = Company(
        tenant_id=tenant_a.id, legal_name="Acme Trading", match_key="acme-trading"
    )
    db_session.add(company)
    await db_session.commit()
    return tenant_a, tenant_b, company


async def test_cross_tenant_write_is_rejected(
    db_session: AsyncSession,
    two_tenants_with_company: tuple[Tenant, Tenant, Company],
) -> None:
    _tenant_a, tenant_b, company = two_tenants_with_company
    with pytest.raises(CompanyTenantMismatchError):
        await record_verification_result(
            db_session,
            tenant_id=tenant_b.id,
            company_id=company.id,
            check_type=CheckType.SANCTIONS_AML,
            verdict=Verdict.FAIL,
            provenance=_provenance(),
        )


async def test_fail_verdict_sets_is_sanctioned(
    db_session: AsyncSession,
    two_tenants_with_company: tuple[Tenant, Tenant, Company],
) -> None:
    tenant_a, _tenant_b, company = two_tenants_with_company
    await record_verification_result(
        db_session,
        tenant_id=tenant_a.id,
        company_id=company.id,
        check_type=CheckType.SANCTIONS_AML,
        verdict=Verdict.FAIL,
        provenance=_provenance(),
    )
    await db_session.commit()
    await db_session.refresh(company)

    assert company.is_sanctioned is True
    assert company.sanctions_review_suggested is False


async def test_later_pass_does_not_clear_sticky_flag(
    db_session: AsyncSession,
    two_tenants_with_company: tuple[Tenant, Tenant, Company],
) -> None:
    tenant_a, _tenant_b, company = two_tenants_with_company
    await record_verification_result(
        db_session,
        tenant_id=tenant_a.id,
        company_id=company.id,
        check_type=CheckType.SANCTIONS_AML,
        verdict=Verdict.FAIL,
        provenance=_provenance(),
    )
    await db_session.commit()

    await record_verification_result(
        db_session,
        tenant_id=tenant_a.id,
        company_id=company.id,
        check_type=CheckType.SANCTIONS_AML,
        verdict=Verdict.PASS,
        provenance=_provenance(0.99),
    )
    await db_session.commit()
    await db_session.refresh(company)

    assert company.is_sanctioned is True
    assert company.sanctions_review_suggested is True


async def test_clear_sanctions_flag_requires_reviewer_and_reason(
    db_session: AsyncSession,
    two_tenants_with_company: tuple[Tenant, Tenant, Company],
) -> None:
    tenant_a, _tenant_b, company = two_tenants_with_company
    with pytest.raises(ValueError):
        await clear_sanctions_flag(
            db_session,
            tenant_id=tenant_a.id,
            company_id=company.id,
            reviewed_by="",
            reason="false positive",
        )
    with pytest.raises(ValueError):
        await clear_sanctions_flag(
            db_session,
            tenant_id=tenant_a.id,
            company_id=company.id,
            reviewed_by="compliance@verdantis.example",
            reason="",
        )


async def test_clear_sanctions_flag_clears_and_audits(
    db_session: AsyncSession,
    two_tenants_with_company: tuple[Tenant, Tenant, Company],
) -> None:
    tenant_a, _tenant_b, company = two_tenants_with_company
    await record_verification_result(
        db_session,
        tenant_id=tenant_a.id,
        company_id=company.id,
        check_type=CheckType.SANCTIONS_AML,
        verdict=Verdict.FAIL,
        provenance=_provenance(),
    )
    await db_session.commit()

    audit = await clear_sanctions_flag(
        db_session,
        tenant_id=tenant_a.id,
        company_id=company.id,
        reviewed_by="compliance@verdantis.example",
        reason="name-match false positive, confirmed via registry lookup",
    )
    await db_session.commit()
    await db_session.refresh(company)

    assert company.is_sanctioned is False
    assert company.sanctions_review_suggested is False
    assert audit.method is ProvenanceMethod.MANUAL
    assert audit.evidence is not None
    assert audit.evidence["reviewed_by"] == "compliance@verdantis.example"
