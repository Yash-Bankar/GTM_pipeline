"""Add capture snapshot + request id to leads

Revision ID: a1b2c3d4e5f6
Revises: d556f1834724
Create Date: 2026-10-19 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d556f1834724"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("profile_snapshot", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "leads",
        sa.Column("request_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_leads_request_id", "leads", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_leads_request_id", table_name="leads")
    op.drop_column("leads", "request_id")
    op.drop_column("leads", "profile_snapshot")
