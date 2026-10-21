"""Explicit contact discovery request lifecycle

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-19 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contact_requests",
        sa.Column("evidence_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "contact_requests",
        sa.Column("searched_scope", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "contact_requests",
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "contact_requests",
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "contact_requests",
        sa.Column("started_at", sa.String(length=40), nullable=False, server_default=""),
    )
    op.add_column(
        "contact_requests",
        sa.Column("completed_at", sa.String(length=40), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_contact_requests_lead_version",
        "contact_requests",
        ["lead_id", "evidence_version"],
    )

    # Old request rows were recorded but never scheduled. Preserve them and make
    # the missing work explicit instead of silently bulk-running discovery.
    op.execute(
        """
        UPDATE contact_requests
        SET status = 'failed',
            error = 'Legacy request not scheduled'
        WHERE status = 'requested'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_contact_requests_lead_version", table_name="contact_requests")
    op.drop_column("contact_requests", "completed_at")
    op.drop_column("contact_requests", "started_at")
    op.drop_column("contact_requests", "error")
    op.drop_column("contact_requests", "result_count")
    op.drop_column("contact_requests", "searched_scope")
    op.drop_column("contact_requests", "evidence_version")
