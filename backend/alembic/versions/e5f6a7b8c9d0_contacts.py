"""Evidence-backed public contacts + legacy contact backfill

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-19 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("contact_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False, server_default="email"),
        sa.Column("value", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("observed_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("method", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("validation_state", sa.String(length=32), nullable=False, server_default="unverified"),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.lead_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("contact_id"),
    )
    op.create_index("ix_contacts_lead_id", "contacts", ["lead_id"])
    op.create_index("ix_contacts_type", "contacts", ["type"])

    # Preserve existing public contact fields as legacy evidence. Provenance is
    # explicitly unknown; do not invent a source or validation claim.
    op.execute(
        """
        INSERT INTO contacts
            (contact_id, lead_id, type, value, source_url, observed_at,
             method, validation_state, created_at, updated_at)
        SELECT
            'ct_' || substr(md5(lead_id || '|email|' || lower(business_email) || '|'), 1, 20),
            lead_id, 'email', business_email, '',
            COALESCE(NULLIF(updated_at, ''), created_at),
            'legacy', 'unverified', created_at, updated_at
        FROM leads
        WHERE business_email <> ''
        ON CONFLICT (contact_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO contacts
            (contact_id, lead_id, type, value, source_url, observed_at,
             method, validation_state, created_at, updated_at)
        SELECT
            'ct_' || substr(md5(lead_id || '|phone|' || business_phone_number || '|'), 1, 20),
            lead_id, 'phone', business_phone_number, '',
            COALESCE(NULLIF(updated_at, ''), created_at),
            'legacy', 'unverified', created_at, updated_at
        FROM leads
        WHERE business_phone_number <> ''
        ON CONFLICT (contact_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_contacts_type", table_name="contacts")
    op.drop_index("ix_contacts_lead_id", table_name="contacts")
    op.drop_table("contacts")
