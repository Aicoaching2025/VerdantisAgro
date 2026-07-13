"""Request/response DTOs for the lead inbox + dossier detail endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from verdantis.db.enums import (
    Incoterm,
    LeadSource,
    LeadStatus,
    PaymentTerms,
    RoutingTarget,
)
from verdantis.models.dossier import CompanyDossier


class LeadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    company_legal_name: str | None
    source: LeadSource
    status: LeadStatus
    fit_score: float | None
    routed_to: RoutingTarget | None
    requested_commodity: str | None
    created_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadSummary]
    total: int


class LeadDetailResponse(BaseModel):
    lead: LeadSummary
    incoterm: Incoterm | None
    payment_terms: PaymentTerms | None
    intake: dict[str, Any] | None
    dossier: CompanyDossier | None
