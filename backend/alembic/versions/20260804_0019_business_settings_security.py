"""Add typed business settings, security foundations, and operational indexes.

Revision ID: 20260804_0019
Revises: 20260804_0018
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260804_0019"
down_revision = "20260804_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column(
        "tax_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
        server_default=sa.text("'{\"prices_include_tax\": false, \"default_tax_rate_bps\": 0}'::jsonb"),
    ))
    op.add_column("organizations", sa.Column(
        "operating_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ))
    op.add_column("organizations", sa.Column(
        "communication_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
        server_default=sa.text("'{\"appointment_reminders\": true, \"payment_reminders\": true}'::jsonb"),
    ))
    op.add_column("organizations", sa.Column(
        "security_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
        server_default=sa.text("'{\"mfa_policy\": \"optional\"}'::jsonb"),
    ))
    op.add_column("organizations", sa.Column(
        "privacy_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
        server_default=sa.text("'{\"conversation_retention_days\": 90}'::jsonb"),
    ))
    op.add_column("organizations", sa.Column("settings_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("locations", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    op.execute("""
        UPDATE clients
        SET client_number = 'CLI-' || substring(client_number FROM 5)
        WHERE client_number LIKE 'CUS-%'
    """)

    op.create_index("ix_clients_org_location_status_created", "clients", ["organization_id", "home_location_id", "status", "created_at"])
    op.create_index("ix_appointments_org_location_start_status", "appointments", ["organization_id", "location_id", "starts_at", "status"])
    op.create_index("ix_sales_org_location_created_status", "sale_invoices", ["organization_id", "location_id", "created_at", "status"])
    op.create_index("ix_memberships_org_location_status_end", "memberships", ["organization_id", "location_id", "status", "ends_on"])
    op.create_index("ix_checkins_org_location_checked_in", "gym_check_ins", ["organization_id", "location_id", "checked_in_at"])
    op.create_index("ix_tasks_org_assignee_status_due", "tasks", ["organization_id", "assigned_to_user_id", "status", "due_at"])
    op.create_index("ix_client_signals_org_location_status_generated", "client_signals", ["organization_id", "location_id", "status", "generated_at"])


def downgrade():
    op.drop_index("ix_client_signals_org_location_status_generated", table_name="client_signals")
    op.drop_index("ix_tasks_org_assignee_status_due", table_name="tasks")
    op.drop_index("ix_checkins_org_location_checked_in", table_name="gym_check_ins")
    op.drop_index("ix_memberships_org_location_status_end", table_name="memberships")
    op.drop_index("ix_sales_org_location_created_status", table_name="sale_invoices")
    op.drop_index("ix_appointments_org_location_start_status", table_name="appointments")
    op.drop_index("ix_clients_org_location_status_created", table_name="clients")
    op.drop_column("locations", "version")
    op.drop_column("organizations", "settings_version")
    op.drop_column("organizations", "privacy_settings")
    op.drop_column("organizations", "security_settings")
    op.drop_column("organizations", "communication_settings")
    op.drop_column("organizations", "operating_settings")
    op.drop_column("organizations", "tax_settings")
