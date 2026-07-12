"""Request/response DTOs for the suppression-list admin endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class SuppressionEntryRequest(BaseModel):
    email: EmailStr
    reason: str | None = None


class SuppressionEntryResponse(BaseModel):
    id: uuid.UUID
    email: str
    reason: str | None
    added_by: str
    created_at: datetime
