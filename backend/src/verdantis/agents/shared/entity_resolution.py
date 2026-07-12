"""Company entity resolution, shared by the outbound and inbound graphs.

Simple exact-match strategy on a normalized legal name — fuzzy matching
across name variants and jurisdictions is explicitly deferred, per Phase 1's
dossier design notes. Both graphs resolve-or-create through the same
function so a buyer discovered outbound and later submitted inbound (or vice
versa) lands on one Company row, not two.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.db.models import Company


def normalize_match_key(legal_name: str) -> str:
    return " ".join(legal_name.strip().lower().split())


async def resolve_or_create_company(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    legal_name: str,
    country: str | None,
    match_key: str | None = None,
) -> uuid.UUID:
    key = match_key or normalize_match_key(legal_name)
    existing = (
        await session.execute(
            select(Company).where(
                Company.tenant_id == tenant_id, Company.match_key == key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    company = Company(
        tenant_id=tenant_id, legal_name=legal_name, country=country, match_key=key
    )
    session.add(company)
    await session.flush()
    return company.id
