"""immediate JWT session revocation

Revision ID: 20260730_0004
Revises: 20260730_0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260730_0004"
down_revision: Union[str, None] = "20260730_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("session_version", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "session_version")
