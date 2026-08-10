"""secure cookie sessions and one-time authentication codes

Revision ID: 20260730_0003
Revises: 20260730_0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260730_0003"
down_revision: Union[str, None] = "20260730_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = sa.UUID(as_uuid=False)


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("family_id", sa.String(64), nullable=True))
    op.add_column("refresh_tokens", sa.Column("replaced_by_token_id", UUID, nullable=True))
    op.add_column("refresh_tokens", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE refresh_tokens SET family_id = id::text WHERE family_id IS NULL")
    op.alter_column("refresh_tokens", "family_id", nullable=False)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_foreign_key("fk_refresh_replaced_by", "refresh_tokens", "refresh_tokens", ["replaced_by_token_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "auth_codes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("request_ip", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ["organization_id", "user_id", "purpose", "expires_at", "request_ip"]:
        op.create_index(f"ix_auth_codes_{column}", "auth_codes", [column])

    op.create_table(
        "auth_attempts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("identifier_hash", sa.String(128), nullable=False),
        sa.Column("ip_address", sa.String(60), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("succeeded", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ["organization_id", "user_id", "identifier_hash", "ip_address", "kind"]:
        op.create_index(f"ix_auth_attempts_{column}", "auth_attempts", [column])


def downgrade() -> None:
    op.drop_table("auth_attempts")
    op.drop_table("auth_codes")
    op.drop_constraint("fk_refresh_replaced_by", "refresh_tokens", type_="foreignkey")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("refresh_tokens", "replaced_by_token_id")
    op.drop_column("refresh_tokens", "family_id")
