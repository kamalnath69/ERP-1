"""Add local intent telemetry and organization rollout flag.

Revision ID: 20260803_0016
Revises: 20260803_0015
"""
from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260803_0016"
down_revision = "20260803_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_intent_resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("chat_conversations.id", ondelete="SET NULL")),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(40), nullable=False),
        sa.Column("intent", sa.String(100)),
        sa.Column("subject", sa.String(60)),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ["organization_id", "user_id", "conversation_id", "request_hash", "intent", "subject", "outcome"]:
        op.create_index(f"ix_ai_intent_resolutions_{column}", "ai_intent_resolutions", [column])
    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    organizations = connection.execute(sa.text("SELECT id FROM organizations")).scalars().all()
    for organization_id in organizations:
        connection.execute(sa.text("""
            INSERT INTO feature_flags (id, organization_id, flag, enabled, meta, created_at, updated_at)
            VALUES (:id, :organization_id, 'ai.local_intent_v2', true, CAST(:meta AS jsonb), :now, :now)
            ON CONFLICT (organization_id, flag) DO UPDATE
            SET enabled = true, meta = EXCLUDED.meta, updated_at = EXCLUDED.updated_at
        """), {"id": str(uuid.uuid4()), "organization_id": organization_id,
               "meta": json.dumps({"mode": "enabled", "engine_version": "local-intent-v1"}), "now": now})


def downgrade():
    op.execute("DELETE FROM feature_flags WHERE flag = 'ai.local_intent_v2'")
    op.drop_table("ai_intent_resolutions")
