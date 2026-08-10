"""Add chat organization metadata for the personalized AI workspace.

Revision ID: 20260806_0022
Revises: 20260805_0021
"""
from alembic import op
import sqlalchemy as sa


revision = "20260806_0022"
down_revision = "20260805_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chat_conversations", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chat_conversations", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_chat_conversations_user_archive_pin",
        "chat_conversations",
        ["organization_id", "user_id", "archived_at", "pinned_at", "updated_at"],
    )


def downgrade():
    op.drop_index("ix_chat_conversations_user_archive_pin", table_name="chat_conversations")
    op.drop_column("chat_conversations", "archived_at")
    op.drop_column("chat_conversations", "pinned_at")
