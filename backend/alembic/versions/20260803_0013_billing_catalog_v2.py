"""Add production billing catalog, tax controls, and durable fulfillment.

Revision ID: 20260803_0013
Revises: 20260801_0012
"""
from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260803_0013"
down_revision = "20260801_0012"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)
JSON = postgresql.JSONB()


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade():
    op.add_column("plan_versions", sa.Column("tax_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("recharge_packs", sa.Column("tax_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("invoices", sa.Column("tax_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("invoices", sa.Column("purchase_type", sa.String(30), nullable=False, server_default="plan"))
    op.add_column("invoices", sa.Column("billing_interval", sa.String(20), nullable=True))
    op.add_column("invoices", sa.Column("fulfillment_status", sa.String(30), nullable=False, server_default="pending"))
    op.add_column("invoices", sa.Column("provider_mode", sa.String(20), nullable=False, server_default="test"))
    op.create_index("ix_invoices_purchase_type", "invoices", ["purchase_type"])
    op.create_index("ix_invoices_fulfillment_status", "invoices", ["fulfillment_status"])
    op.execute("UPDATE invoices SET tax_enabled = (tax_paise > 0), fulfillment_status = CASE WHEN status = 'paid' THEN 'fulfilled' ELSE 'pending' END")

    op.create_table(
        "provider_plan_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plan_version_id", UUID, nullable=False),
        sa.Column("billing_interval", sa.String(20), nullable=False),
        sa.Column("provider_mode", sa.String(20), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("provider_plan_id", sa.String(140)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["plan_version_id"], ["plan_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("plan_version_id", "billing_interval", "provider_mode", "amount_paise", name="uq_provider_plan_price"),
    )
    for column in ("plan_version_id", "provider_plan_id", "status"):
        op.create_index(f"ix_provider_plan_mappings_{column}", "provider_plan_mappings", [column])

    op.create_table(
        "billing_checkout_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("invoice_id", UUID),
        sa.Column("subscription_id", UUID),
        sa.Column("purchase_type", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("provider_mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="creating"),
        sa.Column("provider_reference", sa.String(140)),
        sa.Column("error_code", sa.String(100)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_billing_checkout_key"),
    )
    for column in ("organization_id", "invoice_id", "subscription_id", "status", "provider_reference"):
        op.create_index(f"ix_billing_checkout_attempts_{column}", "billing_checkout_attempts", [column])

    op.create_table(
        "subscription_schedules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("subscription_id", UUID, nullable=False),
        sa.Column("target_plan_version_id", UUID),
        sa.Column("billing_interval", sa.String(20)),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="scheduled"),
        sa.Column("provider_reference", sa.String(140)),
        sa.Column("reason", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_plan_version_id"], ["plan_versions.id"], ondelete="SET NULL"),
    )
    for column in ("organization_id", "subscription_id", "target_plan_version_id", "effective_at", "status"):
        op.create_index(f"ix_subscription_schedules_{column}", "subscription_schedules", [column])
    op.create_index("uq_subscription_schedule_active", "subscription_schedules", ["subscription_id"], unique=True, postgresql_where=sa.text("status = 'scheduled'"))

    op.create_table(
        "wallet_credit_grants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("wallet_id", UUID, nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(140)),
        sa.Column("granted_credits", sa.BigInteger(), nullable=False),
        sa.Column("remaining_credits", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wallet_id"], ["ai_wallets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key", name="uq_wallet_credit_grant_key"),
    )
    for column in ("organization_id", "wallet_id", "source_type", "source_id", "expires_at"):
        op.create_index(f"ix_wallet_credit_grants_{column}", "wallet_credit_grants", [column])

    _seed_catalog_v2()
    connection = op.get_bind()
    wallets = connection.execute(sa.text("""
        SELECT id, organization_id, balance_credits, cycle_end FROM ai_wallets
        WHERE balance_credits > 0 AND cycle_end IS NOT NULL
    """)).mappings()
    for wallet in wallets:
        connection.execute(sa.text("""
            INSERT INTO wallet_credit_grants
                (id, organization_id, wallet_id, source_type, source_id, granted_credits,
                 remaining_credits, expires_at, idempotency_key, created_at, updated_at)
            VALUES (:id, :organization_id, :wallet_id, 'legacy_balance', :source_id,
                    :credits, :credits, :expires_at, :key, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (idempotency_key) DO NOTHING
        """), {
            "id": str(uuid.uuid4()), "organization_id": wallet["organization_id"],
            "wallet_id": wallet["id"], "source_id": str(wallet["id"]),
            "credits": wallet["balance_credits"], "expires_at": wallet["cycle_end"],
            "key": f"legacy-wallet:{wallet['id']}",
        })


def _seed_catalog_v2():
    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    feature_specs = {
        "reports.exports": ("Report exports", "Capabilities"),
        "documents.knowledge": ("Document knowledge", "Capabilities"),
        "communications.send": ("Direct customer communication", "Capabilities"),
        "communications.automations": ("Communication automation", "Capabilities"),
        "access.custom_roles": ("Custom roles", "Capabilities"),
        "ai.views.share": ("Shared AI views", "AI"),
    }
    for code, (name, category) in feature_specs.items():
        connection.execute(sa.text("""
            INSERT INTO feature_definitions
                (id, code, name, category, description, value_type, industries,
                 dependencies, metering, is_active, created_at, updated_at)
            VALUES (:id, :code, :name, :category, :description, 'boolean',
                    '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, true, :now, :now)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category,
                description = EXCLUDED.description, is_active = true, updated_at = EXCLUDED.updated_at
        """), {"id": str(uuid.uuid4()), "code": code, "name": name, "category": category, "description": f"Controls {name.lower()} availability", "now": now})

    specs = {
        "trial": (0, None, 5, 100, 1, 250, 100, "basic", "self-service", False),
        "starter": (99900, 999000, 5, 500, 1, 1024, 500, "basic", "standard", True),
        "growth": (249900, 2499000, 15, 2000, 3, 10240, 2500, "advanced", "priority", True),
        "business": (599900, 5999000, 50, 10000, 10, 51200, 10000, "actions", "priority", True),
        "enterprise": (None, None, None, None, None, None, 50000, "enterprise", "dedicated", True),
    }
    modules = ["customers", "employees", "catalog", "inventory", "sales", "appointments", "documents", "reports", "notifications", "ai", "gym", "salon", "clinic"]
    for slug, spec in specs.items():
        plan_id = connection.execute(sa.text("SELECT id FROM plan_definitions WHERE slug = :slug"), {"slug": slug}).scalar()
        if not plan_id:
            continue
        version_id = connection.execute(sa.text("SELECT id FROM plan_versions WHERE plan_id = :plan_id AND version = 2"), {"plan_id": plan_id}).scalar()
        if not version_id:
            version_id = str(uuid.uuid4())
            connection.execute(sa.text("""
                INSERT INTO plan_versions
                    (id, plan_id, version, status, monthly_price_paise, annual_price_paise,
                     annual_discount_bps, tax_enabled, gst_rate_bps, included_ai_credits,
                     support_level, ai_tier, effective_from, published_at, version_lock,
                     created_at, updated_at)
                VALUES (:id, :plan_id, 2, 'published', :monthly, :annual, 1667, :tax_enabled,
                        1800, :credits, :support, :tier, :now, :now, 1, :now, :now)
            """), {"id": version_id, "plan_id": plan_id, "monthly": spec[0], "annual": spec[1], "tax_enabled": spec[9], "credits": spec[6], "support": spec[8], "tier": spec[7], "now": now})
        growth = slug in {"growth", "business", "enterprise"}
        business = slug in {"business", "enterprise"}
        values = {
            "limits.employees": spec[2], "limits.customers": spec[3],
            "limits.locations": spec[4], "limits.storage_mb": spec[5],
            "reports.exports": growth, "documents.knowledge": growth,
            "communications.send": growth, "access.custom_roles": growth,
            "communications.automations": business, "ai.actions": business,
            "ai.views.share": business,
            **{f"module.{module}": True for module in modules},
        }
        for code, value in values.items():
            feature_id = connection.execute(sa.text("SELECT id FROM feature_definitions WHERE code = :code"), {"code": code}).scalar()
            if not feature_id:
                continue
            connection.execute(sa.text("""
                INSERT INTO plan_entitlements (id, plan_version_id, feature_id, value)
                VALUES (:id, :version_id, :feature_id, CAST(:value AS jsonb))
                ON CONFLICT (plan_version_id, feature_id) DO UPDATE SET value = EXCLUDED.value
            """), {"id": str(uuid.uuid4()), "version_id": version_id, "feature_id": feature_id, "value": json.dumps({"value": value})})
        connection.execute(sa.text("UPDATE plan_versions SET status = 'retired' WHERE plan_id = :plan_id AND version < 2 AND status = 'published'"), {"plan_id": plan_id})
        connection.execute(sa.text("""
            UPDATE subscriptions SET plan_version_id = :version_id
            WHERE plan = :slug AND (plan_version_id IS NULL OR plan_version_id <> :version_id)
        """), {"version_id": version_id, "slug": slug})


def downgrade():
    op.drop_table("wallet_credit_grants")
    op.drop_index("uq_subscription_schedule_active", table_name="subscription_schedules")
    op.drop_table("subscription_schedules")
    op.drop_table("billing_checkout_attempts")
    op.drop_table("provider_plan_mappings")
    op.drop_index("ix_invoices_fulfillment_status", table_name="invoices")
    op.drop_index("ix_invoices_purchase_type", table_name="invoices")
    for column in ("provider_mode", "fulfillment_status", "billing_interval", "purchase_type", "tax_enabled"):
        op.drop_column("invoices", column)
    op.drop_column("recharge_packs", "tax_enabled")
    op.drop_column("plan_versions", "tax_enabled")
