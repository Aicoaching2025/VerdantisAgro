"""initial core schema: tenants, companies, trade_signals, verification_results, leads

Revision ID: 0001_initial_core
Revises:
Create Date: Phase 0/1 starter

This migration is the schema source of truth. Enum types are created explicitly
via `enum.create(bind, checkfirst=True)` below, and each ENUM is declared with
create_type=False so op.create_table doesn't ALSO try to create the type
implicitly when the enum is used as a column type (that double-create is a
DuplicateObject error against Postgres — verified against a live instance).
EMBEDDING_DIM is imported from the app so the vector column width has a single
source of truth — set it correctly BEFORE running this migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from verdantis.config.constants import EMBEDDING_DIM

# revision identifiers, used by Alembic.
revision = "0001_initial_core"
down_revision = None
branch_labels = None
depends_on = None


# --- enum type definitions (created once, referenced by tables) ---------------
# create_type=False on every one of these: the explicit enum.create(...) loop
# in upgrade() is the sole creation path. Without this flag, SQLAlchemy also
# emits its own CREATE TYPE the moment the enum is used as a column type in
# op.create_table, colliding with the explicit create and aborting the
# migration on the very first table that references a custom enum.
PROVENANCE_METHOD = postgresql.ENUM(
    "API",
    "DERIVED",
    "ENRICHMENT",
    "MANUAL",
    name="provenance_method",
    create_type=False,
)
SIGNAL_TYPE = postgresql.ENUM(
    "COMMODITY_MATCH",
    "SHIPMENT_VOLUME",
    "SHIPMENT_FREQUENCY",
    "RECENCY",
    "TREND",
    name="signal_type",
    create_type=False,
)
SIGNAL_BAND = postgresql.ENUM(
    "LOW", "MEDIUM", "HIGH", "VERY_HIGH", name="signal_band", create_type=False
)
CHECK_TYPE = postgresql.ENUM(
    "CORPORATE_EXISTENCE",
    "SANCTIONS_AML",
    "TRADE_ACTIVITY",
    name="check_type",
    create_type=False,
)
VERDICT = postgresql.ENUM(
    "PASS", "FAIL", "INCONCLUSIVE", name="verdict", create_type=False
)
LEAD_SOURCE = postgresql.ENUM(
    "OUTBOUND_DISCOVERY", "INBOUND_FORM", name="lead_source", create_type=False
)
LEAD_STATUS = postgresql.ENUM(
    "NEW",
    "VERIFYING",
    "QUALIFIED",
    "DISQUALIFIED",
    "PENDING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "ROUTED",
    "DISCARDED",
    name="lead_status",
    create_type=False,
)
ROUTING_TARGET = postgresql.ENUM(
    "SALES", "ORGANICA", "SUPPORT", "TRIAGE", name="routing_target", create_type=False
)
INCOTERM = postgresql.ENUM(
    "EXW",
    "FCA",
    "FAS",
    "FOB",
    "CFR",
    "CIF",
    "CPT",
    "CIP",
    "DAP",
    "DPU",
    "DDP",
    name="incoterm",
    create_type=False,
)
PAYMENT_TERMS = postgresql.ENUM(
    "LC",
    "TT",
    "DP",
    "DA",
    "OPEN_ACCOUNT",
    "ADVANCE",
    "OTHER",
    name="payment_terms",
    create_type=False,
)

_ALL_ENUMS = [
    PROVENANCE_METHOD,
    SIGNAL_TYPE,
    SIGNAL_BAND,
    CHECK_TYPE,
    VERDICT,
    LEAD_SOURCE,
    LEAD_STATUS,
    ROUTING_TARGET,
    INCOTERM,
    PAYMENT_TERMS,
]


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for enum in _ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    # --- tenants --------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "config",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # --- companies ------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("legal_name", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("vat_number", sa.String(64), nullable=True),
        sa.Column("eori_number", sa.String(64), nullable=True),
        sa.Column("duns_number", sa.String(16), nullable=True),
        sa.Column("match_key", sa.String(512), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "is_sanctioned", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("sanctions_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "sanctions_review_suggested",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("credibility_score", sa.Float, nullable=True),
        sa.Column("credibility_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "credibility_score IS NULL OR (credibility_score >= 0 AND credibility_score <= 1)",
            name="ck_companies_credibility_range",
        ),
    )
    op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"])
    op.create_index(
        "ix_companies_tenant_match_key", "companies", ["tenant_id", "match_key"]
    )
    op.create_index(
        "ix_companies_tenant_country", "companies", ["tenant_id", "country"]
    )
    op.create_index(
        "uq_companies_tenant_duns",
        "companies",
        ["tenant_id", "duns_number"],
        unique=True,
        postgresql_where=sa.text("duns_number IS NOT NULL"),
    )
    op.create_index(
        "uq_companies_tenant_vat",
        "companies",
        ["tenant_id", "vat_number"],
        unique=True,
        postgresql_where=sa.text("vat_number IS NOT NULL"),
    )
    op.create_index(
        "uq_companies_tenant_eori",
        "companies",
        ["tenant_id", "eori_number"],
        unique=True,
        postgresql_where=sa.text("eori_number IS NOT NULL"),
    )
    # HNSW ANN index for semantic dedup (cosine). Requires pgvector >= 0.5.
    op.execute(
        "CREATE INDEX ix_companies_embedding_hnsw ON companies "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # --- trade_signals --------------------------------------------------------
    op.create_table(
        "trade_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_type", SIGNAL_TYPE, nullable=False),
        sa.Column("commodity", sa.String(128), nullable=True),
        sa.Column("band", SIGNAL_BAND, nullable=True),
        sa.Column("numeric_value", sa.Float, nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
        # embedded provenance
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("method", PROVENANCE_METHOD, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_trade_signals_confidence_range",
        ),
    )
    op.create_index("ix_trade_signals_tenant_id", "trade_signals", ["tenant_id"])
    op.create_index(
        "ix_trade_signals_company_type", "trade_signals", ["company_id", "signal_type"]
    )
    op.create_index(
        "ix_trade_signals_company_commodity",
        "trade_signals",
        ["company_id", "commodity"],
    )

    # --- verification_results -------------------------------------------------
    op.create_table(
        "verification_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("check_type", CHECK_TYPE, nullable=False),
        sa.Column("verdict", VERDICT, nullable=False),
        sa.Column("evidence", postgresql.JSONB, nullable=True),
        # embedded provenance
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("method", PROVENANCE_METHOD, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_verification_results_confidence_range",
        ),
    )
    op.create_index(
        "ix_verification_results_tenant_id", "verification_results", ["tenant_id"]
    )
    op.create_index(
        "ix_verification_results_company_check",
        "verification_results",
        ["company_id", "check_type"],
    )

    # --- leads ----------------------------------------------------------------
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", LEAD_SOURCE, nullable=False),
        sa.Column("status", LEAD_STATUS, nullable=False, server_default="NEW"),
        sa.Column("fit_score", sa.Float, nullable=True),
        sa.Column("routed_to", ROUTING_TARGET, nullable=True),
        sa.Column("routed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("incoterm", INCOTERM, nullable=True),
        sa.Column("payment_terms", PAYMENT_TERMS, nullable=True),
        sa.Column("requested_commodity", sa.String(128), nullable=True),
        sa.Column("intake", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fit_score IS NULL OR (fit_score >= 0 AND fit_score <= 1)",
            name="ck_leads_fit_score_range",
        ),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_index("ix_leads_tenant_status", "leads", ["tenant_id", "status"])
    op.create_index("ix_leads_company", "leads", ["company_id"])


def downgrade() -> None:
    op.drop_table("leads")
    op.drop_table("verification_results")
    op.drop_table("trade_signals")
    op.execute("DROP INDEX IF EXISTS ix_companies_embedding_hnsw")
    op.drop_table("companies")
    op.drop_table("tenants")
    bind = op.get_bind()
    for enum in reversed(_ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
    # Note: `vector` extension is intentionally left installed.
