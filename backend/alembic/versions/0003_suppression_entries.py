"""add suppression entries

Revision ID: 0003_suppression_entries
Revises: 0002_lead_thread_id
Create Date: 2026-07-12 19:34:16.897761
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0003_suppression_entries"
down_revision: Union[str, None] = "0002_lead_thread_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "suppression_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("email_encrypted", sa.String(length=512), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("added_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "email_hash", name="uq_suppression_tenant_email_hash"
        ),
    )
    op.create_index(
        "ix_suppression_entries_tenant_id", "suppression_entries", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_suppression_entries_tenant_id", table_name="suppression_entries")
    op.drop_table("suppression_entries")
