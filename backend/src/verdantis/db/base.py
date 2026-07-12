"""Declarative base and reusable mixins.

Design decisions encoded here:
  - Surrogate UUID PKs everywhere (entity resolution is a code concern, not a
    natural-key assumption).
  - `tenant_id` on every domain row from day one (multi-tenant seam). RLS is
    deferred; the column is present so enabling RLS later is a policy change,
    not a schema migration.
  - Provenance is an embedded mixin, not a separate table: each derived signal
    is single-sourced, so source/retrieved_at/confidence/method live inline and
    are NOT NULL. This is how "provenance by construction" becomes enforceable.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from verdantis.db.enums import ProvenanceMethod


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class ProvenanceMixin:
    """Embedded provenance. Every derived signal/verdict MUST carry these.

    The accompanying CHECK on `confidence` is added per-table in each model's
    __table_args__ (see models.py) to keep constraint names explicit.
    """

    source: Mapped[str] = mapped_column(String(128), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[ProvenanceMethod] = mapped_column(
        SAEnum(ProvenanceMethod, name="provenance_method", create_type=False),
        nullable=False,
    )
