"""professional platform control plane

Revision ID: 20260730_0005
Revises: 20260730_0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260730_0005"
down_revision: Union[str, None] = "20260730_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = sa.UUID(as_uuid=False)
JSON = postgresql.JSONB()


def ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("feature_definitions",
        sa.Column("id", UUID, primary_key=True), sa.Column("code", sa.String(120), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.Text()), sa.Column("value_type", sa.String(30), nullable=False),
        sa.Column("industries", JSON, nullable=False), sa.Column("dependencies", JSON, nullable=False),
        sa.Column("metering", JSON, nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), *ts())
    op.create_index("ix_feature_definitions_code", "feature_definitions", ["code"])
    op.create_index("ix_feature_definitions_category", "feature_definitions", ["category"])

    op.create_table("plan_definitions",
        sa.Column("id", UUID, primary_key=True), sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("display_order", sa.Integer(), nullable=False), sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False), *ts())
    op.create_index("ix_plan_definitions_slug", "plan_definitions", ["slug"])

    op.create_table("plan_versions",
        sa.Column("id", UUID, primary_key=True), sa.Column("plan_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("monthly_price_paise", sa.BigInteger()), sa.Column("annual_price_paise", sa.BigInteger()),
        sa.Column("annual_discount_bps", sa.Integer(), nullable=False), sa.Column("gst_rate_bps", sa.Integer(), nullable=False),
        sa.Column("included_ai_credits", sa.BigInteger(), nullable=False), sa.Column("support_level", sa.String(40), nullable=False),
        sa.Column("ai_tier", sa.String(40), nullable=False), sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("published_by_user_id", UUID),
        sa.Column("version_lock", sa.Integer(), nullable=False), *ts(),
        sa.ForeignKeyConstraint(["plan_id"], ["plan_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("plan_id", "version", name="uq_plan_version"))
    op.create_index("ix_plan_versions_plan_id", "plan_versions", ["plan_id"])
    op.create_index("ix_plan_versions_status", "plan_versions", ["status"])
    op.create_index("ix_plan_versions_effective_from", "plan_versions", ["effective_from"])

    op.create_table("plan_entitlements",
        sa.Column("id", UUID, primary_key=True), sa.Column("plan_version_id", UUID, nullable=False),
        sa.Column("feature_id", UUID, nullable=False), sa.Column("value", JSON, nullable=False),
        sa.ForeignKeyConstraint(["plan_version_id"], ["plan_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_id"], ["feature_definitions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("plan_version_id", "feature_id", name="uq_plan_entitlement"))
    op.create_index("ix_plan_entitlements_plan_version_id", "plan_entitlements", ["plan_version_id"])
    op.create_index("ix_plan_entitlements_feature_id", "plan_entitlements", ["feature_id"])

    op.create_table("organization_entitlement_overrides",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("feature_id", UUID, nullable=False), sa.Column("value", JSON, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("approved_by_user_id", UUID), sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_id"], ["feature_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"))
    for col in ["organization_id", "feature_id", "starts_at", "ends_at"]:
        op.create_index(f"ix_organization_entitlement_overrides_{col}", "organization_entitlement_overrides", [col])

    op.create_table("billing_profiles",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False, unique=True),
        sa.Column("legal_name", sa.String(220)), sa.Column("billing_email", sa.String(200)),
        sa.Column("billing_phone", sa.String(40)), sa.Column("gstin", sa.String(20)), sa.Column("address", sa.Text()),
        sa.Column("city", sa.String(100)), sa.Column("state", sa.String(100)), sa.Column("postal_code", sa.String(12)),
        sa.Column("purchase_order_reference", sa.String(120)), sa.Column("tax_exempt", sa.Boolean(), nullable=False),
        sa.Column("tax_exemption_meta", JSON, nullable=False), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"))
    op.create_index("ix_billing_profiles_organization_id", "billing_profiles", ["organization_id"])

    op.add_column("subscriptions", sa.Column("razorpay_plan_id", sa.String(120)))
    op.add_column("subscriptions", sa.Column("plan_version_id", UUID))
    op.add_column("subscriptions", sa.Column("billing_interval", sa.String(20), server_default="monthly", nullable=False))
    op.add_column("subscriptions", sa.Column("provider", sa.String(30), server_default="razorpay", nullable=False))
    op.add_column("subscriptions", sa.Column("provider_mode", sa.String(20), server_default="test", nullable=False))
    op.add_column("subscriptions", sa.Column("cancel_at_cycle_end", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("subscriptions", sa.Column("scheduled_plan_version_id", UUID))
    op.add_column("subscriptions", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.create_foreign_key("fk_subscriptions_plan_version", "subscriptions", "plan_versions", ["plan_version_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_subscriptions_scheduled_plan_version", "subscriptions", "plan_versions", ["scheduled_plan_version_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_subscriptions_plan_version_id", "subscriptions", ["plan_version_id"])

    op.alter_column("invoices", "amount", new_column_name="amount_paise")
    op.alter_column("invoices", "amount_paise", existing_type=sa.Float(), type_=sa.BigInteger(), postgresql_using="round(amount_paise)::bigint")
    for name, default in [("subtotal_paise", "0"), ("discount_paise", "0"), ("tax_paise", "0"), ("cgst_paise", "0"), ("sgst_paise", "0"), ("igst_paise", "0")]:
        op.add_column("invoices", sa.Column(name, sa.BigInteger(), server_default=default, nullable=False))
    op.add_column("invoices", sa.Column("gst_rate_bps", sa.Integer(), server_default="1800", nullable=False))
    op.add_column("invoices", sa.Column("invoice_number", sa.String(80)))
    op.add_column("invoices", sa.Column("billing_snapshot", JSON, server_default="{}", nullable=False))
    op.add_column("invoices", sa.Column("plan_snapshot", JSON, server_default="{}", nullable=False))
    op.add_column("invoices", sa.Column("due_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("paid_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("reconciled_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.execute("UPDATE invoices SET subtotal_paise = amount_paise WHERE subtotal_paise = 0")
    op.create_unique_constraint("uq_invoices_invoice_number", "invoices", ["invoice_number"])
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])

    op.add_column("payment_events", sa.Column("provider_event_id", sa.String(160)))
    op.add_column("payment_events", sa.Column("provider_mode", sa.String(20), server_default="test", nullable=False))
    op.add_column("payment_events", sa.Column("status", sa.String(30), server_default="processed", nullable=False))
    op.add_column("payment_events", sa.Column("error", sa.Text()))
    op.add_column("payment_events", sa.Column("processed_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_payment_events_provider_event_id", "payment_events", ["provider_event_id"])
    op.create_index("ix_payment_events_provider_event_id", "payment_events", ["provider_event_id"])

    op.create_table("platform_payments",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False), sa.Column("invoice_id", UUID),
        sa.Column("provider", sa.String(30), nullable=False), sa.Column("provider_payment_id", sa.String(140), unique=True),
        sa.Column("provider_order_id", sa.String(140)), sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("method", sa.String(40)),
        sa.Column("captured_at", sa.DateTime(timezone=True)), sa.Column("reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("meta", JSON, nullable=False), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"))
    for col in ["organization_id", "invoice_id", "provider_payment_id", "provider_order_id", "status"]:
        op.create_index(f"ix_platform_payments_{col}", "platform_payments", [col])

    op.create_table("platform_refunds",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("payment_id", UUID, nullable=False), sa.Column("provider_refund_id", sa.String(140), unique=True),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("requested_by_user_id", UUID, nullable=False),
        sa.Column("approved_by_user_id", UUID), sa.Column("idempotency_key", sa.String(120), nullable=False, unique=True), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["platform_payments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"))
    op.create_index("ix_platform_refunds_organization_id", "platform_refunds", ["organization_id"])
    op.create_index("ix_platform_refunds_payment_id", "platform_refunds", ["payment_id"])
    op.create_index("ix_platform_refunds_status", "platform_refunds", ["status"])

    op.create_table("platform_settlements",
        sa.Column("id", UUID, primary_key=True), sa.Column("provider_settlement_id", sa.String(140), unique=True),
        sa.Column("mode", sa.String(20), nullable=False), sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("meta", JSON, nullable=False), *ts())
    op.create_index("ix_platform_settlements_status", "platform_settlements", ["status"])

    op.create_table("ai_wallets",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False, unique=True),
        sa.Column("balance_credits", sa.BigInteger(), nullable=False), sa.Column("reserved_credits", sa.BigInteger(), nullable=False),
        sa.Column("cycle_grant_credits", sa.BigInteger(), nullable=False), sa.Column("cycle_start", sa.DateTime(timezone=True)),
        sa.Column("cycle_end", sa.DateTime(timezone=True)), sa.Column("version", sa.Integer(), nullable=False), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"))
    op.create_index("ix_ai_wallets_organization_id", "ai_wallets", ["organization_id"])
    op.create_index("ix_ai_wallets_cycle_end", "ai_wallets", ["cycle_end"])

    op.create_table("wallet_ledger",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("wallet_id", UUID, nullable=False), sa.Column("entry_type", sa.String(40), nullable=False),
        sa.Column("credits_delta", sa.BigInteger(), nullable=False), sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("reference_type", sa.String(60)), sa.Column("reference_id", sa.String(140)),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True), sa.Column("description", sa.Text()),
        sa.Column("created_by_user_id", UUID), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wallet_id"], ["ai_wallets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"))
    for col in ["organization_id", "wallet_id", "entry_type", "reference_id"]:
        op.create_index(f"ix_wallet_ledger_{col}", "wallet_ledger", [col])

    op.create_table("wallet_reservations",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("wallet_id", UUID, nullable=False), sa.Column("credits", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("settled_credits", sa.BigInteger()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wallet_id"], ["ai_wallets.id"], ondelete="CASCADE"))
    op.create_index("ix_wallet_reservations_organization_id", "wallet_reservations", ["organization_id"])
    op.create_index("ix_wallet_reservations_status", "wallet_reservations", ["status"])
    op.create_index("ix_wallet_reservations_expires_at", "wallet_reservations", ["expires_at"])

    op.create_table("recharge_packs",
        sa.Column("id", UUID, primary_key=True), sa.Column("name", sa.String(100), nullable=False),
        sa.Column("credits", sa.BigInteger(), nullable=False), sa.Column("price_paise", sa.BigInteger(), nullable=False),
        sa.Column("gst_rate_bps", sa.Integer(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False), *ts())

    op.create_table("platform_permissions",
        sa.Column("id", UUID, primary_key=True), sa.Column("code", sa.String(120), nullable=False, unique=True),
        sa.Column("name", sa.String(180), nullable=False), sa.Column("category", sa.String(80), nullable=False), *ts())
    op.create_index("ix_platform_permissions_code", "platform_permissions", ["code"])
    op.create_table("platform_roles",
        sa.Column("id", UUID, primary_key=True), sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("is_system", sa.Boolean(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), *ts())
    op.create_table("platform_role_permissions",
        sa.Column("id", UUID, primary_key=True), sa.Column("role_id", UUID, nullable=False), sa.Column("permission_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["platform_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["platform_permissions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_platform_role_permission"))
    op.create_table("platform_user_roles",
        sa.Column("id", UUID, primary_key=True), sa.Column("user_id", UUID, nullable=False), sa.Column("role_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["platform_roles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_platform_user_role"))
    op.create_index("ix_platform_user_roles_user_id", "platform_user_roles", ["user_id"])

    op.create_table("platform_mfa_devices",
        sa.Column("id", UUID, primary_key=True), sa.Column("user_id", UUID, nullable=False, unique=True),
        sa.Column("secret_encrypted", sa.Text(), nullable=False), sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)), sa.Column("last_used_step", sa.BigInteger()), *ts(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"))
    op.create_index("ix_platform_mfa_devices_user_id", "platform_mfa_devices", ["user_id"])
    op.create_table("platform_recovery_codes",
        sa.Column("id", UUID, primary_key=True), sa.Column("user_id", UUID, nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False), sa.Column("used_at", sa.DateTime(timezone=True)), *ts(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"))
    op.create_index("ix_platform_recovery_codes_user_id", "platform_recovery_codes", ["user_id"])

    op.create_table("approval_requests",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID),
        sa.Column("action_type", sa.String(100), nullable=False), sa.Column("amount_paise", sa.BigInteger()),
        sa.Column("payload", JSON, nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("requested_by_user_id", UUID, nullable=False),
        sa.Column("decided_by_user_id", UUID), sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("version", sa.Integer(), nullable=False), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"))
    for col in ["organization_id", "action_type", "status", "expires_at"]:
        op.create_index(f"ix_approval_requests_{col}", "approval_requests", [col])

    op.create_table("support_sessions",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("target_user_id", UUID, nullable=False), sa.Column("platform_user_id", UUID, nullable=False),
        sa.Column("approval_id", UUID), sa.Column("mode", sa.String(30), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ticket_reference", sa.String(120), nullable=False), sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"], ondelete="SET NULL"))
    for col in ["organization_id", "platform_user_id", "status", "expires_at"]:
        op.create_index(f"ix_support_sessions_{col}", "support_sessions", [col])

    op.create_table("organization_deletion_requests",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID),
        sa.Column("organization_name", sa.String(200), nullable=False), sa.Column("organization_slug", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=False), sa.Column("approved_by_user_id", UUID),
        sa.Column("purge_after", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"))
    op.create_index("ix_organization_deletion_requests_organization_id", "organization_deletion_requests", ["organization_id"])
    op.create_index("ix_organization_deletion_requests_status", "organization_deletion_requests", ["status"])
    op.create_index("ix_organization_deletion_requests_purge_after", "organization_deletion_requests", ["purge_after"])

    op.create_table("retention_archives",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID),
        sa.Column("organization_slug", sa.String(80), nullable=False), sa.Column("record_type", sa.String(80), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False), sa.Column("retention_reason", sa.Text(), nullable=False),
        sa.Column("purge_at", sa.DateTime(timezone=True), nullable=False), sa.Column("purged_at", sa.DateTime(timezone=True)), *ts(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"))
    op.create_index("ix_retention_archives_organization_id", "retention_archives", ["organization_id"])
    op.create_index("ix_retention_archives_purge_at", "retention_archives", ["purge_at"])

    op.create_table("platform_settings",
        sa.Column("id", UUID, primary_key=True), sa.Column("key", sa.String(120), nullable=False, unique=True),
        sa.Column("value", JSON, nullable=False), sa.Column("version", sa.Integer(), nullable=False), *ts())


def downgrade() -> None:
    for table in [
        "platform_settings", "retention_archives", "organization_deletion_requests", "support_sessions",
        "approval_requests", "platform_recovery_codes", "platform_mfa_devices", "platform_user_roles",
        "platform_role_permissions", "platform_roles", "platform_permissions", "recharge_packs",
        "wallet_reservations", "wallet_ledger", "ai_wallets", "platform_settlements", "platform_refunds",
        "platform_payments", "billing_profiles", "organization_entitlement_overrides", "plan_entitlements",
    ]:
        op.drop_table(table)
    op.drop_constraint("fk_subscriptions_scheduled_plan_version", "subscriptions", type_="foreignkey")
    op.drop_constraint("fk_subscriptions_plan_version", "subscriptions", type_="foreignkey")
    for column in ["version", "scheduled_plan_version_id", "cancel_at_cycle_end", "provider_mode", "provider", "billing_interval", "plan_version_id", "razorpay_plan_id"]:
        op.drop_column("subscriptions", column)
    for column in ["version", "reconciled_at", "paid_at", "due_at", "plan_snapshot", "billing_snapshot", "invoice_number", "gst_rate_bps", "igst_paise", "sgst_paise", "cgst_paise", "tax_paise", "discount_paise", "subtotal_paise"]:
        op.drop_column("invoices", column)
    op.alter_column("invoices", "amount_paise", existing_type=sa.BigInteger(), type_=sa.Float(), postgresql_using="amount_paise::double precision")
    op.alter_column("invoices", "amount_paise", new_column_name="amount")
    for column in ["processed_at", "error", "status", "provider_mode", "provider_event_id"]:
        op.drop_column("payment_events", column)
    op.drop_table("plan_versions")
    op.drop_table("plan_definitions")
    op.drop_table("feature_definitions")
