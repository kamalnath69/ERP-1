"""Add browser-bound signup email verification.

Revision ID: 20260814_0037
Revises: 20260813_0036
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260814_0037"
down_revision = "20260813_0036"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "signup_email_challenges",
        sa.Column("id", UUID, nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("email_hash", sa.String(128), nullable=False),
        sa.Column("browser_token_hash", sa.String(128), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("proof_hash", sa.String(128)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_ip", sa.String(64)),
        sa.Column("resend_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("proof_expires_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signup_email_challenges_status", "signup_email_challenges", ["status"])
    op.create_index("ix_signup_email_challenges_expires_at", "signup_email_challenges", ["expires_at"])
    op.create_index(
        "ix_signup_email_challenges_email_created",
        "signup_email_challenges",
        ["email_hash", "created_at"],
    )
    op.create_index(
        "ix_signup_email_challenges_ip_created",
        "signup_email_challenges",
        ["request_ip", "created_at"],
    )
    op.create_index(
        "ix_signup_email_challenges_status_expiry",
        "signup_email_challenges",
        ["status", "expires_at"],
    )
    op.add_column("signup_checkouts", sa.Column("email_challenge_id", UUID))
    op.create_foreign_key(
        "fk_signup_checkouts_email_challenge",
        "signup_checkouts",
        "signup_email_challenges",
        ["email_challenge_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_signup_checkouts_email_challenge_id",
        "signup_checkouts",
        ["email_challenge_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_signup_checkouts_email_challenge_id", table_name="signup_checkouts")
    op.drop_constraint("fk_signup_checkouts_email_challenge", "signup_checkouts", type_="foreignkey")
    op.drop_column("signup_checkouts", "email_challenge_id")
    op.drop_table("signup_email_challenges")
