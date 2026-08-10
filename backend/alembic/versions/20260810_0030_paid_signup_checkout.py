"""Add payment-first signup checkouts.

Revision ID: 20260810_0030
Revises: 20260810_0029
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260810_0030"
down_revision = "20260810_0029"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)
JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "signup_checkouts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("access_token_hash", sa.String(128), nullable=False),
        sa.Column("organization_name", sa.String(200), nullable=False),
        sa.Column("organization_slug", sa.String(80), nullable=False),
        sa.Column("industry", sa.String(30), nullable=False),
        sa.Column("admin_email", sa.String(200), nullable=False),
        sa.Column("admin_password_hash", sa.String(300)),
        sa.Column("admin_first_name", sa.String(100), nullable=False),
        sa.Column("admin_last_name", sa.String(100), nullable=False),
        sa.Column("location_name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(100)),
        sa.Column("plan_version_id", UUID, sa.ForeignKey("plan_versions.id", ondelete="SET NULL")),
        sa.Column("plan_snapshot", JSON, nullable=False),
        sa.Column("billing_interval", sa.String(20), nullable=False),
        sa.Column("subtotal_paise", sa.BigInteger(), nullable=False),
        sa.Column("tax_paise", sa.BigInteger(), nullable=False),
        sa.Column("total_paise", sa.BigInteger(), nullable=False),
        sa.Column("tax_enabled", sa.Boolean(), nullable=False),
        sa.Column("gst_rate_bps", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("provider_mode", sa.String(20), nullable=False),
        sa.Column("provider_order_id", sa.String(140)),
        sa.Column("provider_payment_id", sa.String(140)),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("verification_sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(240)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("provider_order_id"),
        sa.UniqueConstraint("provider_payment_id"),
    )
    op.create_index("ix_signup_checkouts_status", "signup_checkouts", ["status"])
    op.create_index("ix_signup_checkouts_admin_email", "signup_checkouts", ["admin_email"])
    op.create_index("ix_signup_checkouts_plan_version_id", "signup_checkouts", ["plan_version_id"])
    op.create_index("ix_signup_checkouts_provider_order_id", "signup_checkouts", ["provider_order_id"])
    op.create_index("ix_signup_checkouts_provider_payment_id", "signup_checkouts", ["provider_payment_id"])
    op.create_index("ix_signup_checkouts_organization_id", "signup_checkouts", ["organization_id"])
    op.create_index("ix_signup_checkouts_expires_at", "signup_checkouts", ["expires_at"])
    op.create_index(
        "ix_signup_checkouts_slug_status_expiry",
        "signup_checkouts",
        ["organization_slug", "status", "expires_at"],
    )
    op.create_index("ix_signup_checkouts_status_expiry", "signup_checkouts", ["status", "expires_at"])


def downgrade() -> None:
    op.drop_table("signup_checkouts")
