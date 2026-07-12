"""Request/response DTOs for the public inbound-submission endpoint."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class InboundSubmissionRequest(BaseModel):
    legal_name: str = Field(min_length=1, max_length=255)
    country: str | None = Field(default=None, max_length=2)
    contact_name: str = Field(min_length=1, max_length=255)
    contact_email: EmailStr
    requested_commodity: str = Field(min_length=1, max_length=128)
    requested_volume: str | None = Field(default=None, max_length=128)
    incoterm: str | None = Field(default=None, max_length=64)
    payment_terms: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=4000)


class InboundSubmissionResponse(BaseModel):
    lead_id: uuid.UUID
    status: str = "received"
