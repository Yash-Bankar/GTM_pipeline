"""Fit decision, contact/draft requests, and worker heartbeat

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-19 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("fit_status", sa.String(length=32), nullable=False, server_default="not_reviewed"),
    )
    op.add_column(
        "leads",
        sa.Column("fit_note", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "leads",
        sa.Column("fit_decided_at", sa.String(length=40), nullable=False, server_default=""),
    )
    op.create_index("ix_leads_fit_status", "leads", ["fit_status"])

    op.create_table(
        "contact_requests",
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="requested"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.lead_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index("ix_contact_requests_lead_id", "contact_requests", ["lead_id"])
    op.create_index("ix_contact_requests_status", "contact_requests", ["status"])

    op.create_table(
        "outreach_revisions",
        sa.Column("revision_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="requested"),
        sa.Column("subject", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("dm_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.lead_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("revision_id"),
    )
    op.create_index("ix_outreach_revisions_lead_id", "outreach_revisions", ["lead_id"])
    op.create_index("ix_outreach_revisions_status", "outreach_revisions", ["status"])

    op.create_table(
        "worker_heartbeat",
        sa.Column("heartbeat_id", sa.String(length=64), nullable=False),
        sa.Column("worker_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("beat_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("heartbeat_id"),
    )
    op.create_index("ix_worker_heartbeat_beat_at", "worker_heartbeat", ["beat_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeat_beat_at", table_name="worker_heartbeat")
    op.drop_table("worker_heartbeat")
    op.drop_index("ix_outreach_revisions_status", table_name="outreach_revisions")
    op.drop_index("ix_outreach_revisions_lead_id", table_name="outreach_revisions")
    op.drop_table("outreach_revisions")
    op.drop_index("ix_contact_requests_status", table_name="contact_requests")
    op.drop_index("ix_contact_requests_lead_id", table_name="contact_requests")
    op.drop_table("contact_requests")
    op.drop_index("ix_leads_fit_status", table_name="leads")
    op.drop_column("leads", "fit_decided_at")
    op.drop_column("leads", "fit_note")
    op.drop_column("leads", "fit_status")
