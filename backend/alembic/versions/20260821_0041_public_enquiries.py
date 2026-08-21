"""Add public enquiry types and optional project organizations.

Revision ID: 20260821_0041
Revises: 20260817_0040
"""
from alembic import op
import sqlalchemy as sa


revision = "20260821_0041"
down_revision = "20260817_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "demo_requests",
        sa.Column("inquiry_type", sa.String(32), nullable=False, server_default="product_demo"),
    )
    op.alter_column(
        "demo_requests", "organization_name", existing_type=sa.String(200), nullable=True
    )
    op.create_index(
        "ix_demo_request_type_status_time",
        "demo_requests",
        ["inquiry_type", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_demo_request_type_status_time", table_name="demo_requests")
    op.execute("UPDATE demo_requests SET organization_name = 'Not provided' WHERE organization_name IS NULL")
    op.alter_column(
        "demo_requests", "organization_name", existing_type=sa.String(200), nullable=False
    )
    op.drop_column("demo_requests", "inquiry_type")
