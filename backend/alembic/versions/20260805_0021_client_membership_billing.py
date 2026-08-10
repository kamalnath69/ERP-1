"""Add authoritative membership billing and cancellation lifecycle fields.

Revision ID: 20260805_0021
Revises: 20260804_0020
"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql


revision = "20260805_0021"
down_revision = "20260804_0020"
branch_labels = None
depends_on = None
UUID = postgresql.UUID(as_uuid=False)


def upgrade():
    op.add_column("memberships", sa.Column("invoice_id", UUID, nullable=True))
    op.add_column("memberships", sa.Column("previous_membership_id", UUID, nullable=True))
    op.add_column("memberships", sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memberships", sa.Column("cancellation_effective_on", sa.Date(), nullable=True))
    op.create_foreign_key(
        "fk_memberships_invoice_id_sale_invoices",
        "memberships",
        "sale_invoices",
        ["invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_memberships_previous_membership_id_memberships",
        "memberships",
        "memberships",
        ["previous_membership_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_memberships_invoice_id", "memberships", ["invoice_id"], unique=True)
    op.create_index("ix_memberships_previous_membership_id", "memberships", ["previous_membership_id"])
    op.create_index("ix_memberships_cancellation_effective_on", "memberships", ["cancellation_effective_on"])

    # Repair the previous early-renewal shape: the valid current term was
    # labelled renewed while its future successor was labelled active.
    op.execute("""
        UPDATE memberships AS current_term
        SET status = 'active', version = current_term.version + 1
        FROM memberships AS future_term
        WHERE current_term.organization_id = future_term.organization_id
          AND current_term.client_id = future_term.client_id
          AND current_term.status = 'renewed'
          AND current_term.starts_on <= CURRENT_DATE
          AND current_term.ends_on >= CURRENT_DATE
          AND future_term.status IN ('active', 'frozen')
          AND future_term.starts_on > CURRENT_DATE
    """)
    op.execute("""
        UPDATE memberships
        SET status = 'scheduled',
            frozen_from = NULL,
            frozen_until = NULL,
            version = version + 1
        WHERE status IN ('active', 'frozen') AND starts_on > CURRENT_DATE
    """)

    # Legacy databases may contain several rows labelled active. Keep the most
    # recent current term and preserve the others as lifecycle history.
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY organization_id, client_id
                       ORDER BY ends_on DESC, created_at DESC, id DESC
                   ) AS position
            FROM memberships
            WHERE status IN ('active', 'frozen')
        )
        UPDATE memberships
        SET status = CASE WHEN memberships.ends_on < CURRENT_DATE THEN 'expired' ELSE 'renewed' END,
            version = version + 1
        FROM ranked
        WHERE memberships.id = ranked.id AND ranked.position > 1
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY organization_id, client_id
                       ORDER BY starts_on ASC, created_at ASC, id ASC
                   ) AS position
            FROM memberships
            WHERE status = 'scheduled'
        )
        UPDATE memberships
        SET status = 'cancelled',
            cancellation_reason = COALESCE(cancellation_reason, 'Duplicate legacy scheduled term'),
            version = version + 1
        FROM ranked
        WHERE memberships.id = ranked.id AND ranked.position > 1
    """)
    op.create_index(
        "uq_memberships_current_per_client",
        "memberships",
        ["organization_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'frozen')"),
    )
    op.create_index(
        "uq_memberships_scheduled_per_client",
        "memberships",
        ["organization_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("status = 'scheduled'"),
    )

    op.add_column(
        "sale_invoices",
        sa.Column(
            "tax_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("sale_invoices", sa.Column("void_reason", sa.Text(), nullable=True))
    op.add_column("sale_invoices", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sale_invoices", sa.Column("voided_by_user_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_sale_invoices_voided_by_user_id_users",
        "sale_invoices",
        "users",
        ["voided_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sale_invoices_voided_by_user_id", "sale_invoices", ["voided_by_user_id"])


def downgrade():
    op.drop_index("ix_sale_invoices_voided_by_user_id", table_name="sale_invoices")
    op.drop_constraint("fk_sale_invoices_voided_by_user_id_users", "sale_invoices", type_="foreignkey")
    op.drop_column("sale_invoices", "voided_by_user_id")
    op.drop_column("sale_invoices", "voided_at")
    op.drop_column("sale_invoices", "void_reason")
    op.drop_column("sale_invoices", "tax_snapshot")

    op.drop_index("uq_memberships_scheduled_per_client", table_name="memberships")
    op.drop_index("uq_memberships_current_per_client", table_name="memberships")
    op.drop_index("ix_memberships_cancellation_effective_on", table_name="memberships")
    op.drop_index("ix_memberships_previous_membership_id", table_name="memberships")
    op.drop_index("ix_memberships_invoice_id", table_name="memberships")
    op.drop_constraint("fk_memberships_previous_membership_id_memberships", "memberships", type_="foreignkey")
    op.drop_constraint("fk_memberships_invoice_id_sale_invoices", "memberships", type_="foreignkey")
    op.drop_column("memberships", "cancellation_effective_on")
    op.drop_column("memberships", "cancellation_requested_at")
    op.drop_column("memberships", "previous_membership_id")
    op.drop_column("memberships", "invoice_id")
