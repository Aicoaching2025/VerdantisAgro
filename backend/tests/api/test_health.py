from __future__ import annotations

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.api.deps import get_db
from verdantis.api.main import app


async def test_healthz_returns_ok(db_session: AsyncSession) -> None:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-correlation-id" in response.headers
