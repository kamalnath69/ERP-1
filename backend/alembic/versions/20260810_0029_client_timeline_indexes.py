"""Add indexes for normalized client activity timelines.

Revision ID: 20260810_0029
Revises: 20260810_0028
"""
from alembic import op


revision = "20260810_0029"
down_revision = "20260810_0028"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_appointments_org_client_starts_id", "appointments", ["organization_id", "client_id", "starts_at", "id"]),
    ("ix_sale_invoices_org_client_created_id", "sale_invoices", ["organization_id", "client_id", "created_at", "id"]),
    ("ix_sale_payments_org_created_invoice_id", "sale_payments", ["organization_id", "created_at", "invoice_id", "id"]),
    ("ix_gym_check_ins_org_client_checked_id", "gym_check_ins", ["organization_id", "client_id", "checked_in_at", "id"]),
    ("ix_memberships_org_client_created_id", "memberships", ["organization_id", "client_id", "created_at", "id"]),
    ("ix_audit_logs_org_resource_created_id", "audit_logs", ["organization_id", "resource_id", "created_at", "id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
