"""Add indexes for high-volume catalog, inventory, document, and audit lists.

Revision ID: 20260810_0027
Revises: 20260810_0026
"""
from alembic import op


revision = "20260810_0027"
down_revision = "20260810_0026"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_catalog_org_active_type_name_id", "catalog_items", ["organization_id", "is_active", "item_type", "name", "id"]),
    ("ix_stock_levels_org_location_updated_id", "stock_levels", ["organization_id", "location_id", "updated_at", "id"]),
    ("ix_stock_movements_org_location_created_id", "stock_movements", ["organization_id", "location_id", "created_at", "id"]),
    ("ix_documents_org_created_id", "documents", ["organization_id", "created_at", "id"]),
    ("ix_notifications_org_user_created_id", "notifications", ["organization_id", "user_id", "created_at", "id"]),
    ("ix_audit_logs_org_created_id", "audit_logs", ["organization_id", "created_at", "id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
