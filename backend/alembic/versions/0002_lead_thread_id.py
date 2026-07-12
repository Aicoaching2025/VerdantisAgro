"""add lead thread_id

Revision ID: 0002_lead_thread_id
Revises: 0001_initial_core
Create Date: 2026-07-12 19:12:52.168479
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_lead_thread_id"
down_revision: Union[str, None] = "0001_initial_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("thread_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "thread_id")
