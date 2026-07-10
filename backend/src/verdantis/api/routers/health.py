"""Health check. No business logic — just proves the API is up and can reach Postgres."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.api.deps import get_db
from verdantis.api.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz(session: AsyncSession = Depends(get_db)) -> HealthResponse:
    await session.execute(text("SELECT 1"))
    return HealthResponse(status="ok")
