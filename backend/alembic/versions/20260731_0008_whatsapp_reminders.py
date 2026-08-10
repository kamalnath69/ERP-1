"""Add WhatsApp consent evidence and template metadata.

Revision ID: 20260731_0008
Revises: 20260730_0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260731_0008"
down_revision = "20260730_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("whatsapp_consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customers", sa.Column("whatsapp_consent_source", sa.String(length=50), nullable=True))
    op.add_column("outbound_messages", sa.Column("template_language", sa.String(length=20), nullable=True))
    op.add_column("outbound_messages", sa.Column("template_variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade():
    op.drop_column("outbound_messages", "template_variables")
    op.drop_column("outbound_messages", "template_language")
    op.drop_column("customers", "whatsapp_consent_source")
    op.drop_column("customers", "whatsapp_consent_at")
