"""Review state, campaign configuration, and fit decision history

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-19 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("decision_currency", sa.String(length=32), nullable=False, server_default="current"),
    )
    op.add_column(
        "leads",
        sa.Column("decision_currency_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "leads",
        sa.Column("new_evidence_available", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_leads_decision_currency", "leads", ["decision_currency"])

    # Map the pre-v2 fit statuses to the v2 vocabulary.
    op.execute("UPDATE leads SET fit_status = 'shortlisted' WHERE fit_status = 'approved'")
    op.execute("UPDATE leads SET fit_status = 'research_more' WHERE fit_status = 'needs_evidence'")

    op.create_table(
        "campaigns",
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_topics", sa.Text(), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("follower_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("follower_max", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("campaign_id"),
    )
    op.create_index("ix_campaigns_is_active", "campaigns", ["is_active"])

    op.create_table(
        "fit_decisions",
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("fit_status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("decision_currency", sa.String(length=32), nullable=False, server_default="current"),
        sa.Column("evidence_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criteria_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.lead_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index("ix_fit_decisions_lead_id", "fit_decisions", ["lead_id"])
    op.create_index("ix_fit_decisions_created_at", "fit_decisions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_fit_decisions_created_at", table_name="fit_decisions")
    op.drop_index("ix_fit_decisions_lead_id", table_name="fit_decisions")
    op.drop_table("fit_decisions")
    op.drop_index("ix_campaigns_is_active", table_name="campaigns")
    op.drop_table("campaigns")
    op.execute("UPDATE leads SET fit_status = 'approved' WHERE fit_status = 'shortlisted'")
    op.execute("UPDATE leads SET fit_status = 'needs_evidence' WHERE fit_status = 'research_more'")
    op.drop_index("ix_leads_decision_currency", table_name="leads")
    op.drop_column("leads", "new_evidence_available")
    op.drop_column("leads", "decision_currency_reason")
    op.drop_column("leads", "decision_currency")
