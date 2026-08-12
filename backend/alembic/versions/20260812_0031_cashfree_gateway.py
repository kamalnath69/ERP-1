"""Add provider-neutral payment gateway fields and Cashfree selection.

Revision ID: 20260812_0031
Revises: 20260810_0030
"""
import uuid

from alembic import op
import sqlalchemy as sa


revision = "20260812_0031"
down_revision = "20260810_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("provider", sa.String(30), nullable=False, server_default="razorpay"))
    op.add_column("invoices", sa.Column("provider_order_id", sa.String(140)))
    op.add_column("invoices", sa.Column("provider_payment_id", sa.String(140)))
    op.add_column("invoices", sa.Column("provider_session_id", sa.Text()))
    op.execute("UPDATE invoices SET provider_order_id = razorpay_order_id, provider_payment_id = razorpay_payment_id")
    op.create_index("uq_invoice_provider_order", "invoices", ["provider", "provider_order_id"], unique=True, postgresql_where=sa.text("provider_order_id IS NOT NULL"))
    op.create_index("uq_invoice_provider_payment", "invoices", ["provider", "provider_payment_id"], unique=True, postgresql_where=sa.text("provider_payment_id IS NOT NULL"))

    op.add_column("payment_events", sa.Column("provider", sa.String(30), nullable=False, server_default="razorpay"))
    op.create_index("ix_payment_events_provider_mode", "payment_events", ["provider", "provider_mode"])

    op.add_column("billing_checkout_attempts", sa.Column("provider", sa.String(30), nullable=False, server_default="razorpay"))
    op.create_index("ix_billing_checkout_provider_status", "billing_checkout_attempts", ["provider", "status"])

    op.add_column("provider_plan_mappings", sa.Column("provider", sa.String(30), nullable=False, server_default="razorpay"))
    op.drop_constraint("uq_provider_plan_price", "provider_plan_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_provider_plan_price",
        "provider_plan_mappings",
        ["plan_version_id", "billing_interval", "provider", "provider_mode", "amount_paise"],
    )

    op.add_column("signup_checkouts", sa.Column("provider", sa.String(30), nullable=False, server_default="razorpay"))
    op.add_column("signup_checkouts", sa.Column("provider_session_id", sa.Text()))
    op.add_column("signup_checkouts", sa.Column("admin_phone", sa.String(40)))
    op.create_index("ix_signup_checkout_provider_status", "signup_checkouts", ["provider", "provider_mode", "status"])

    setting_id = str(uuid.uuid4())
    op.execute(sa.text(f"""
        INSERT INTO platform_settings (id, key, value, version, created_at, updated_at)
        SELECT '{setting_id}', 'payment_gateway', '{{"provider":"razorpay"}}'::jsonb, 1, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM platform_settings WHERE key = 'payment_gateway')
    """))


def downgrade() -> None:
    op.drop_index("ix_signup_checkout_provider_status", table_name="signup_checkouts")
    op.drop_column("signup_checkouts", "admin_phone")
    op.drop_column("signup_checkouts", "provider_session_id")
    op.drop_column("signup_checkouts", "provider")

    op.drop_constraint("uq_provider_plan_price", "provider_plan_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_provider_plan_price",
        "provider_plan_mappings",
        ["plan_version_id", "billing_interval", "provider_mode", "amount_paise"],
    )
    op.drop_column("provider_plan_mappings", "provider")

    op.drop_index("ix_billing_checkout_provider_status", table_name="billing_checkout_attempts")
    op.drop_column("billing_checkout_attempts", "provider")
    op.drop_index("ix_payment_events_provider_mode", table_name="payment_events")
    op.drop_column("payment_events", "provider")

    op.drop_index("uq_invoice_provider_payment", table_name="invoices")
    op.drop_index("uq_invoice_provider_order", table_name="invoices")
    op.drop_column("invoices", "provider_session_id")
    op.drop_column("invoices", "provider_payment_id")
    op.drop_column("invoices", "provider_order_id")
    op.drop_column("invoices", "provider")
