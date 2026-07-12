"""Dossier domain models — Pydantic, DB-agnostic.

What agents/api consume; never a SQLAlchemy object. This is the boundary
CLAUDE.md's repository-layer rule protects: `core/dossier/service.py` is the
only place that reads SQLAlchemy dossier-related models above `db/`, and it
converts to these before returning anything.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from verdantis.db.enums import CheckType, SignalBand, SignalType, Verdict


class TradeSignalView(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_type: SignalType
    commodity: str | None
    band: SignalBand | None
    numeric_value: float | None
    period_start: date | None
    period_end: date | None
    details: dict[str, Any] | None
    source: str
    retrieved_at: datetime
    confidence: float


class VerificationVerdictView(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_type: CheckType
    verdict: Verdict
    evidence: dict[str, Any] | None
    source: str
    retrieved_at: datetime
    confidence: float


class CompanyDossier(BaseModel):
    """The assembled, DB-agnostic view of everything known about a company."""

    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    tenant_id: uuid.UUID
    legal_name: str
    display_name: str | None
    country: str | None
    vat_number: str | None
    eori_number: str | None
    duns_number: str | None

    is_sanctioned: bool
    sanctions_review_suggested: bool
    credibility_score: float | None

    trade_signals: list[TradeSignalView]
    verification_results: list[VerificationVerdictView]

    @property
    def latest_verdict_by_check(self) -> dict[CheckType, VerificationVerdictView]:
        """Most recent verdict per check_type, by retrieved_at."""
        latest: dict[CheckType, VerificationVerdictView] = {}
        for v in self.verification_results:
            current = latest.get(v.check_type)
            if current is None or v.retrieved_at > current.retrieved_at:
                latest[v.check_type] = v
        return latest
