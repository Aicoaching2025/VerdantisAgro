"""Core persistence models for the Verdantis buy-side lead-gen system.

Scope: the STABLE spine only — tenant, company identity, derived trade signals,
verification results, and leads. Outreach threading, eval tables, and full audit
logs are intentionally deferred to their own phases to avoid migration churn.

Hard constraints enforced structurally here (not just in prose):
  - Every derived signal / verdict carries NOT NULL provenance (ProvenanceMixin).
  - No column stores verbatim licensed records; JSONB fields hold DERIVED
    evidence only (matched IDs, list names, computed extras).
  - `Company.is_sanctioned` is a denormalized blocking flag the routing gate
    reads cheaply; it is maintained by the provenance write-path helper.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from verdantis.config.constants import EMBEDDING_DIM
from verdantis.db.base import (
    Base,
    ProvenanceMixin,
    TenantMixin,
    TimestampMixin,
    uuid_pk,
)
from verdantis.db.enums import (
    CheckType,
    Incoterm,
    LeadSource,
    LeadStatus,
    PaymentTerms,
    RoutingTarget,
    SignalBand,
    SignalType,
    Verdict,
)


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Tenant-scoped config: commodity set, target regions, ICP thresholds,
    # routing rules. Kept out of code so generalization is configuration.
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    companies: Mapped[list[Company]] = relationship(back_populates="tenant")


class Company(Base, TenantMixin, TimestampMixin):
    """A buyer / prospect. Identity is deliberately loose: surrogate PK plus
    nullable registry IDs plus a normalized match_key. Entity resolution across
    name variants and jurisdictions is a Phase-1 code problem the schema ENABLES
    but does not pretend to solve with a natural key.
    """

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = uuid_pk()

    legal_name: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(
        String(2), nullable=True
    )  # ISO-3166 alpha-2

    # Registry identifiers (resolved opportunistically; often partial).
    vat_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    eori_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duns_number: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Normalized key for dedup/candidate-matching. NOT unique — resolution is
    # probabilistic and handled in code.
    match_key: Mapped[str] = mapped_column(String(512), nullable=False)

    # Semantic dedup / similarity. Dimension pinned by EMBEDDING_DIM.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    # Denormalized latest verification rollups for cheap filtering / gating.
    # is_sanctioned is STICKY: only clear_sanctions_flag() (an audited, manual
    # override) can unset it — a routine PASS rescreen never does.
    is_sanctioned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sanctions_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when a PASS rescreen arrives on an already-flagged company, so a
    # possible false positive surfaces for human review instead of silently
    # auto-clearing. Cleared alongside is_sanctioned by clear_sanctions_flag().
    sanctions_review_suggested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    credibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    credibility_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tenant: Mapped[Tenant] = relationship(back_populates="companies")
    trade_signals: Mapped[list[TradeSignal]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    verification_results: Mapped[list[VerificationResult]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    leads: Mapped[list[Lead]] = relationship(back_populates="company")

    __table_args__ = (
        CheckConstraint(
            "credibility_score IS NULL OR (credibility_score >= 0 AND credibility_score <= 1)",
            name="ck_companies_credibility_range",
        ),
        Index("ix_companies_tenant_match_key", "tenant_id", "match_key"),
        Index("ix_companies_tenant_country", "tenant_id", "country"),
        # HNSW ANN index for semantic dedup (cosine). Registered on the model
        # (not just raw SQL in the migration) so autogenerate sees it and
        # doesn't propose dropping it as an "extra" index on every diff.
        Index(
            "ix_companies_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Partial uniqueness: a registry ID, when present, is unique per tenant.
        Index(
            "uq_companies_tenant_duns",
            "tenant_id",
            "duns_number",
            unique=True,
            postgresql_where=text("duns_number IS NOT NULL"),
        ),
        Index(
            "uq_companies_tenant_vat",
            "tenant_id",
            "vat_number",
            unique=True,
            postgresql_where=text("vat_number IS NOT NULL"),
        ),
        Index(
            "uq_companies_tenant_eori",
            "tenant_id",
            "eori_number",
            unique=True,
            postgresql_where=text("eori_number IS NOT NULL"),
        ),
    )


class TradeSignal(Base, TenantMixin, TimestampMixin, ProvenanceMixin):
    """A single DERIVED trade signal about a company. One typed table keyed by
    `signal_type`, with typed value columns, rather than a table per kind."""

    __tablename__ = "trade_signals"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    signal_type: Mapped[SignalType] = mapped_column(
        SAEnum(SignalType, name="signal_type", create_type=False), nullable=False
    )
    commodity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    band: Mapped[SignalBand | None] = mapped_column(
        SAEnum(SignalBand, name="signal_band", create_type=False), nullable=True
    )
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    # DERIVED structured extras only (never verbatim licensed records).
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    company: Mapped[Company] = relationship(back_populates="trade_signals")

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_trade_signals_confidence_range",
        ),
        Index("ix_trade_signals_company_type", "company_id", "signal_type"),
        Index("ix_trade_signals_company_commodity", "company_id", "commodity"),
    )


class VerificationResult(Base, TenantMixin, TimestampMixin, ProvenanceMixin):
    """Result of one verification check. History is retained (one row per run);
    Company holds the denormalized latest rollups."""

    __tablename__ = "verification_results"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    check_type: Mapped[CheckType] = mapped_column(
        SAEnum(CheckType, name="check_type", create_type=False), nullable=False
    )
    verdict: Mapped[Verdict] = mapped_column(
        SAEnum(Verdict, name="verdict", create_type=False), nullable=False
    )
    # DERIVED evidence trail: matched registry IDs, sanctions list names,
    # computed activity summary. Powers the "why credible" view.
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    company: Mapped[Company] = relationship(back_populates="verification_results")

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_verification_results_confidence_range",
        ),
        Index("ix_verification_results_company_check", "company_id", "check_type"),
    )


class Lead(Base, TenantMixin, TimestampMixin):
    """A discovered (outbound) or submitted (inbound) opportunity."""

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Inbound leads may arrive before a company is resolved -> nullable.
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )

    source: Mapped[LeadSource] = mapped_column(
        SAEnum(LeadSource, name="lead_source", create_type=False), nullable=False
    )
    status: Mapped[LeadStatus] = mapped_column(
        SAEnum(LeadStatus, name="lead_status", create_type=False),
        nullable=False,
        server_default=LeadStatus.NEW.value,
    )
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # LangGraph checkpointer thread_id for the outbound run that owns this
    # lead — lets the approvals endpoint look up the live interrupt() state
    # for a PENDING_APPROVAL lead. Inbound leads never set this (their graph
    # never interrupts).
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    routed_to: Mapped[RoutingTarget | None] = mapped_column(
        SAEnum(RoutingTarget, name="routing_target", create_type=False),
        nullable=True,
    )
    routed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Normalized inbound qualification fields (the schema Verdantis publishes).
    incoterm: Mapped[Incoterm | None] = mapped_column(
        SAEnum(Incoterm, name="incoterm", create_type=False), nullable=True
    )
    payment_terms: Mapped[PaymentTerms | None] = mapped_column(
        SAEnum(PaymentTerms, name="payment_terms", create_type=False), nullable=True
    )
    requested_commodity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Full normalized intake payload (volume, origin, specs, inspection...).
    intake: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    company: Mapped[Company | None] = relationship(back_populates="leads")

    __table_args__ = (
        CheckConstraint(
            "fit_score IS NULL OR (fit_score >= 0 AND fit_score <= 1)",
            name="ck_leads_fit_score_range",
        ),
        Index("ix_leads_tenant_status", "tenant_id", "status"),
        Index("ix_leads_company", "company_id"),
    )
