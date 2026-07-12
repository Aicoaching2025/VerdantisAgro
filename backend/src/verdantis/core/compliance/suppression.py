"""Suppression list: checked before any send (scope doc Section 8:
"Maintain a suppression list checked before any send"). Exact-match lookup
via a SHA-256 hash of the normalized email — membership checks never
require decrypting every row; `email_encrypted` exists for admin display
only.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.core.security.encryption import encrypt_pii
from verdantis.db.models import SuppressionEntry


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_email(email: str) -> str:
    return hashlib.sha256(_normalize_email(email).encode("utf-8")).hexdigest()


async def is_suppressed(
    session: AsyncSession, *, tenant_id: uuid.UUID, email: str
) -> bool:
    existing = (
        await session.execute(
            select(SuppressionEntry.id).where(
                SuppressionEntry.tenant_id == tenant_id,
                SuppressionEntry.email_hash == _hash_email(email),
            )
        )
    ).scalar_one_or_none()
    return existing is not None


async def add_to_suppression_list(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    email: str,
    added_by: str,
    reason: str | None = None,
) -> SuppressionEntry:
    """Idempotent: re-adding an already-suppressed email returns the
    existing entry rather than raising a unique-constraint violation."""
    email_hash = _hash_email(email)
    existing = (
        await session.execute(
            select(SuppressionEntry).where(
                SuppressionEntry.tenant_id == tenant_id,
                SuppressionEntry.email_hash == email_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    entry = SuppressionEntry(
        tenant_id=tenant_id,
        email_hash=email_hash,
        email_encrypted=encrypt_pii(_normalize_email(email)),
        reason=reason,
        added_by=added_by,
    )
    session.add(entry)
    await session.flush()
    return entry


async def remove_from_suppression_list(
    session: AsyncSession, *, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> bool:
    entry = await session.get(SuppressionEntry, entry_id)
    if entry is None or entry.tenant_id != tenant_id:
        return False
    await session.delete(entry)
    await session.flush()
    return True
