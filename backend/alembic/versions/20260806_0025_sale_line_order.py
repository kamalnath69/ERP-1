"""Preserve invoice line order.

Revision ID: 20260806_0025
Revises: 20260806_0024
"""
from alembic import op
import sqlalchemy as sa


revision = "20260806_0025"
down_revision = "20260806_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sale_lines",
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_sale_lines_invoice_order", "sale_lines", ["invoice_id", "display_order"])


def downgrade() -> None:
    op.drop_index("ix_sale_lines_invoice_order", table_name="sale_lines")
    op.drop_column("sale_lines", "display_order")
