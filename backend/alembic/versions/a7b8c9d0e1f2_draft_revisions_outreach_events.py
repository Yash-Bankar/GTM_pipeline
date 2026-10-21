"""Draft revisions and manual outreach event history (V2-07)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-21 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- draft_revisions: immutable saved content versions -------------------
    op.create_table(
        "draft_revisions",
        sa.Column("revision_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("username_normalized", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("subject", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("dm_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="needs_review"),
        sa.Column("method", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("parent_revision_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("contact_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("evidence_scope", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("edited_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.lead_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("revision_id"),
    )
    op.create_index("ix_draft_revisions_lead_id", "draft_revisions", ["lead_id"])
    op.create_index("ix_draft_revisions_status", "draft_revisions", ["status"])
    op.create_index("ix_draft_revisions_method", "draft_revisions", ["method"])
    op.create_index(
        "ix_draft_revisions_parent_revision_id", "draft_revisions", ["parent_revision_id"]
    )

    # --- outreach_events: append-only manual log history --------------------
    op.create_table(
        "outreach_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False, server_default="sent"),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("revision_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manually_logged"),
        sa.Column("corrects_event_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("sent_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("logged_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.lead_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_outreach_events_lead_id", "outreach_events", ["lead_id"])
    op.create_index("ix_outreach_events_outcome", "outreach_events", ["outcome"])
    op.create_index("ix_outreach_events_source", "outreach_events", ["source"])
    op.create_index("ix_outreach_events_revision_id", "outreach_events", ["revision_id"])
    op.create_index(
        "ix_outreach_events_corrects_event_id", "outreach_events", ["corrects_event_id"]
    )

    # --- outreach_revisions: link a generation request to its result --------
    op.add_column(
        "outreach_revisions",
        sa.Column("result_revision_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "outreach_revisions",
        sa.Column("parent_revision_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "outreach_revisions",
        sa.Column("job_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "outreach_revisions",
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_outreach_revisions_result_revision_id",
        "outreach_revisions",
        ["result_revision_id"],
    )

    # Legacy draft rows become the first revision of their lead, so existing
    # content stays visible and is never silently discarded.
    op.execute(
        """
        INSERT INTO draft_revisions (
            revision_id, lead_id, username, username_normalized, channel,
            subject, body, dm_body, status, method, model, parent_revision_id,
            contact_id, request_id, evidence_scope, note, edited_at,
            created_at, updated_at
        )
        SELECT
            'dr_legacy_' || d.lead_id,
            d.lead_id,
            d.username,
            d.username_normalized,
            d.channel,
            d.subject,
            d.body,
            d.dm_body,
            CASE
                WHEN upper(d.status) = 'APPROVED' THEN 'reviewed'
                ELSE 'needs_review'
            END,
            CASE
                WHEN d.model <> '' THEN 'ai'
                ELSE 'manual'
            END,
            d.model,
            '', '', '', '', '',
            d.updated_at,
            d.created_at,
            d.updated_at
        FROM outreach_drafts d
        WHERE d.subject <> '' OR d.body <> '' OR d.dm_body <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_outreach_revisions_result_revision_id", table_name="outreach_revisions")
    op.drop_column("outreach_revisions", "error")
    op.drop_column("outreach_revisions", "job_id")
    op.drop_column("outreach_revisions", "parent_revision_id")
    op.drop_column("outreach_revisions", "result_revision_id")

    op.drop_index("ix_outreach_events_corrects_event_id", table_name="outreach_events")
    op.drop_index("ix_outreach_events_revision_id", table_name="outreach_events")
    op.drop_index("ix_outreach_events_source", table_name="outreach_events")
    op.drop_index("ix_outreach_events_outcome", table_name="outreach_events")
    op.drop_index("ix_outreach_events_lead_id", table_name="outreach_events")
    op.drop_table("outreach_events")

    op.drop_index("ix_draft_revisions_parent_revision_id", table_name="draft_revisions")
    op.drop_index("ix_draft_revisions_method", table_name="draft_revisions")
    op.drop_index("ix_draft_revisions_status", table_name="draft_revisions")
    op.drop_index("ix_draft_revisions_lead_id", table_name="draft_revisions")
    op.drop_table("draft_revisions")
