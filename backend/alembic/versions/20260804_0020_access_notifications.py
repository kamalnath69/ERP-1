"""Add optimistic access versions and structured notifications.

Revision ID: 20260804_0020
Revises: 20260804_0019
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260804_0020"
down_revision = "20260804_0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("roles", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("users", sa.Column("access_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("notifications", sa.Column("category", sa.String(length=40), nullable=False, server_default="general"))
    op.add_column(
        "notifications",
        sa.Column("destination", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_notifications_user_category_created",
        "notifications",
        ["organization_id", "user_id", "category", "created_at"],
    )


def downgrade():
    op.drop_index("ix_notifications_user_category_created", table_name="notifications")
    op.drop_column("notifications", "destination")
    op.drop_column("notifications", "category")
    op.drop_column("users", "access_version")
    op.drop_column("roles", "version")
