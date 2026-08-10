"""Normalize unique constraints and indexes with SQLAlchemy metadata.

Revision ID: 20260730_0007
Revises: 20260730_0006
"""
from alembic import op

revision = "20260730_0007"
down_revision = "20260730_0006"
branch_labels = None
depends_on = None


def upgrade():
    for table, old_name, new_name, column in (
        ("ai_wallets", "ai_wallets_organization_id_key", "uq_ai_wallet_org", "organization_id"),
        ("billing_profiles", "billing_profiles_organization_id_key", "uq_billing_profile_org", "organization_id"),
        ("platform_mfa_devices", "platform_mfa_devices_user_id_key", "uq_platform_mfa_user", "user_id"),
    ):
        op.drop_constraint(old_name, table, type_="unique")
        op.create_unique_constraint(new_name, table, [column])

    for table, constraint, index, column in (
        ("customer_media", "customer_media_document_id_key", "ix_customer_media_document_id", "document_id"),
        ("feature_definitions", "feature_definitions_code_key", "ix_feature_definitions_code", "code"),
        ("invoices", "uq_invoices_invoice_number", "ix_invoices_invoice_number", "invoice_number"),
        ("payment_events", "uq_payment_events_provider_event_id", "ix_payment_events_provider_event_id", "provider_event_id"),
        ("plan_definitions", "plan_definitions_slug_key", "ix_plan_definitions_slug", "slug"),
        ("platform_payments", "platform_payments_provider_payment_id_key", "ix_platform_payments_provider_payment_id", "provider_payment_id"),
        ("platform_permissions", "platform_permissions_code_key", "ix_platform_permissions_code", "code"),
    ):
        op.drop_constraint(constraint, table, type_="unique")
        op.drop_index(index, table_name=table)
        op.create_index(index, table, [column], unique=True)


def downgrade():
    for table, constraint, index, column in (
        ("customer_media", "customer_media_document_id_key", "ix_customer_media_document_id", "document_id"),
        ("feature_definitions", "feature_definitions_code_key", "ix_feature_definitions_code", "code"),
        ("invoices", "uq_invoices_invoice_number", "ix_invoices_invoice_number", "invoice_number"),
        ("payment_events", "uq_payment_events_provider_event_id", "ix_payment_events_provider_event_id", "provider_event_id"),
        ("plan_definitions", "plan_definitions_slug_key", "ix_plan_definitions_slug", "slug"),
        ("platform_payments", "platform_payments_provider_payment_id_key", "ix_platform_payments_provider_payment_id", "provider_payment_id"),
        ("platform_permissions", "platform_permissions_code_key", "ix_platform_permissions_code", "code"),
    ):
        op.drop_index(index, table_name=table)
        op.create_index(index, table, [column], unique=False)
        op.create_unique_constraint(constraint, table, [column])
    for table, old_name, new_name, column in (
        ("ai_wallets", "ai_wallets_organization_id_key", "uq_ai_wallet_org", "organization_id"),
        ("billing_profiles", "billing_profiles_organization_id_key", "uq_billing_profile_org", "organization_id"),
        ("platform_mfa_devices", "platform_mfa_devices_user_id_key", "uq_platform_mfa_user", "user_id"),
    ):
        op.drop_constraint(new_name, table, type_="unique")
        op.create_unique_constraint(old_name, table, [column])
