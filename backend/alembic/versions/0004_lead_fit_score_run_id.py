"""add lead fit_score_run_id

Revision ID: 0004_lead_fit_score_run_id
Revises: 0003_suppression_entries
Create Date: 2026-07-13 01:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_lead_fit_score_run_id"
down_revision: Union[str, None] = "0003_suppression_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads", sa.Column("fit_score_run_id", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("leads", "fit_score_run_id")
