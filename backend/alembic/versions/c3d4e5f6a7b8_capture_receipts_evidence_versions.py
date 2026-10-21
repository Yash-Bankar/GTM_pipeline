"""Capture receipts and immutable evidence versions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-19 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("evidence_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "leads",
        sa.Column("evidence_version_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_leads_evidence_version_id", "leads", ["evidence_version_id"])

    op.create_table(
        "capture_receipts",
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("received_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.lead_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index("ix_capture_receipts_lead_id", "capture_receipts", ["lead_id"])

    op.create_table(
        "evidence_versions",
        sa.Column("evidence_version_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("request_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("snapshot_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("captured_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("received_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("parser_version", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("field_provenance", sa.Text(), nullable=False, server_default=""),
        sa.Column("changed_fields", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.lead_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evidence_version_id"),
        sa.UniqueConstraint("lead_id", "version", name="uq_evidence_versions_lead_version"),
    )
    op.create_index("ix_evidence_versions_lead_id", "evidence_versions", ["lead_id"])
    op.create_index("ix_evidence_versions_request_id", "evidence_versions", ["request_id"])
    op.create_index("ix_evidence_versions_received_at", "evidence_versions", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_evidence_versions_received_at", table_name="evidence_versions")
    op.drop_index("ix_evidence_versions_request_id", table_name="evidence_versions")
    op.drop_index("ix_evidence_versions_lead_id", table_name="evidence_versions")
    op.drop_table("evidence_versions")
    op.drop_index("ix_capture_receipts_lead_id", table_name="capture_receipts")
    op.drop_table("capture_receipts")
    op.drop_index("ix_leads_evidence_version_id", table_name="leads")
    op.drop_column("leads", "evidence_version_id")
    op.drop_column("leads", "evidence_version")
