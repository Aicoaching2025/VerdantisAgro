"""Provenance-by-construction write path.

This module is the ONLY sanctioned way to persist a derived trade signal or a
verification verdict. Both functions require a `Provenance` value with no
default, so it is structurally impossible to write a signal without
source / retrieved_at / confidence / method. The DB backs this with NOT NULL
columns; this layer backs it with the type system.

Rules enforced here in addition to provenance:
  - Every write is scoped to the (tenant_id, company_id) pair actually owning
    the row — a company_id that doesn't belong to tenant_id is rejected rather
    than silently written or flagged, since this module is the one chokepoint
    tenant isolation for these writes actually depends on.
  - Recording a SANCTIONS_AML verdict of FAIL flips the company's denormalized
    `is_sanctioned` blocking flag. The routing gate reads that flag; it is
    never set by hand elsewhere. The flag is STICKY: record_verification_result
    never clears it, even on a later PASS — a PASS on an already-flagged
    company instead sets `sanctions_review_suggested` so the mismatch surfaces
    for human review. The only way to clear `is_sanctioned` is the separate,
    audited `clear_sanctions_flag()` below, which requires a reviewer and a
    reason and writes its own record of the override.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.db.enums import (
    CheckType,
    ProvenanceMethod,
    SignalBand,
    SignalType,
    Verdict,
)
from verdantis.db.models import Company, TradeSignal, VerificationResult


class CompanyTenantMismatchError(LookupError):
    """Raised when company_id does not resolve under the given tenant_id."""

    def __init__(self, *, tenant_id: uuid.UUID, company_id: uuid.UUID) -> None:
        super().__init__(f"company {company_id} not found for tenant {tenant_id}")
        self.tenant_id = tenant_id
        self.company_id = company_id


class Provenance(BaseModel):
    """Immutable provenance stamp attached to every derived datum."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1, max_length=128)
    retrieved_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    method: ProvenanceMethod

    @field_validator("retrieved_at")
    @classmethod
    def _must_be_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return v


async def _get_company_or_raise(
    session: AsyncSession, *, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> Company:
    """Load a company, scoped to its owning tenant.

    This is the enforcement point for tenant isolation on provenance writes:
    a company_id that exists but belongs to a different tenant is treated the
    same as a company_id that doesn't exist at all.
    """
    company = (
        await session.execute(
            select(Company).where(
                Company.id == company_id, Company.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if company is None:
        raise CompanyTenantMismatchError(tenant_id=tenant_id, company_id=company_id)
    return company


async def record_trade_signal(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    signal_type: SignalType,
    provenance: Provenance,
    commodity: str | None = None,
    band: SignalBand | None = None,
    numeric_value: float | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    details: dict[str, Any] | None = None,
) -> TradeSignal:
    """Persist one derived trade signal. `provenance` is required by signature.

    `details` must contain DERIVED extras only — never verbatim licensed records.
    """
    await _get_company_or_raise(session, tenant_id=tenant_id, company_id=company_id)

    signal = TradeSignal(
        tenant_id=tenant_id,
        company_id=company_id,
        signal_type=signal_type,
        commodity=commodity,
        band=band,
        numeric_value=numeric_value,
        period_start=period_start,
        period_end=period_end,
        details=details,
        source=provenance.source,
        retrieved_at=provenance.retrieved_at,
        confidence=provenance.confidence,
        method=provenance.method,
    )
    session.add(signal)
    await session.flush()
    return signal


async def record_verification_result(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    check_type: CheckType,
    verdict: Verdict,
    provenance: Provenance,
    evidence: dict[str, Any] | None = None,
) -> VerificationResult:
    """Persist one verification verdict. `provenance` is required by signature.

    Side effect: a SANCTIONS_AML FAIL flips the company's blocking flag so the
    routing gate can short-circuit without re-querying the check history. A
    subsequent PASS never clears it (see module docstring) — instead, a PASS
    on an already-flagged company sets `sanctions_review_suggested` so the
    conflict surfaces for human review rather than resolving itself silently.
    """
    company = await _get_company_or_raise(
        session, tenant_id=tenant_id, company_id=company_id
    )

    result = VerificationResult(
        tenant_id=tenant_id,
        company_id=company_id,
        check_type=check_type,
        verdict=verdict,
        evidence=evidence,
        source=provenance.source,
        retrieved_at=provenance.retrieved_at,
        confidence=provenance.confidence,
        method=provenance.method,
    )
    session.add(result)

    if check_type is CheckType.SANCTIONS_AML:
        company.sanctions_checked_at = provenance.retrieved_at
        if verdict is Verdict.FAIL:
            company.is_sanctioned = True
        elif verdict is Verdict.PASS and company.is_sanctioned:
            # Sticky flag conflicts with this rescreen — flag for review
            # rather than auto-clearing. is_sanctioned itself is untouched.
            company.sanctions_review_suggested = True
        # INCONCLUSIVE, or PASS on an already-clean company: no flag change.

    await session.flush()
    return result


async def clear_sanctions_flag(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    reviewed_by: str,
    reason: str,
) -> VerificationResult:
    """Explicitly clear a company's sticky is_sanctioned flag after human review.

    This is the ONLY path that unsets is_sanctioned once a FAIL has set it.
    It writes its own audited VerificationResult (method=MANUAL, evidence
    carries reviewed_by/reason) rather than reusing record_verification_result,
    so the override is distinguishable in history from an automated rescreen.
    """
    if not reviewed_by.strip():
        raise ValueError("reviewed_by is required")
    if not reason.strip():
        raise ValueError("reason is required")

    company = await _get_company_or_raise(
        session, tenant_id=tenant_id, company_id=company_id
    )

    reviewed_at = datetime.now(UTC)
    result = VerificationResult(
        tenant_id=tenant_id,
        company_id=company_id,
        check_type=CheckType.SANCTIONS_AML,
        verdict=Verdict.PASS,
        evidence={
            "action": "manual_clear",
            "reviewed_by": reviewed_by,
            "reason": reason,
        },
        source=reviewed_by,
        retrieved_at=reviewed_at,
        confidence=1.0,
        method=ProvenanceMethod.MANUAL,
    )
    session.add(result)

    company.is_sanctioned = False
    company.sanctions_review_suggested = False
    company.sanctions_checked_at = reviewed_at

    await session.flush()
    return result
