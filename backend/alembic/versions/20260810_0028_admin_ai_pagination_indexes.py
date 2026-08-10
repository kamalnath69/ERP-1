"""Add indexes for administration, billing, and AI history pages.

Revision ID: 20260810_0028
Revises: 20260810_0027
"""
from alembic import op


revision = "20260810_0028"
down_revision = "20260810_0027"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_invoices_org_created_id", "invoices", ["organization_id", "created_at", "id"]),
    ("ix_users_org_active_name_id", "users", ["organization_id", "is_active", "first_name", "last_name", "id"]),
    ("ix_clients_org_name_id", "clients", ["organization_id", "first_name", "last_name", "id"]),
    (
        "ix_chat_conversations_org_user_archive_pin_updated_id",
        "chat_conversations",
        ["organization_id", "user_id", "archived_at", "pinned_at", "updated_at", "id"],
    ),
    ("ix_chat_messages_conversation_created_id", "chat_messages", ["conversation_id", "created_at", "id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
