"""Add V3 AI conversation memory and sanitized execution traces.

Revision ID: 20260817_0038
Revises: 20260814_0037
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260817_0038"
down_revision = "20260814_0037"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.add_column("chat_conversations", sa.Column("memory_state", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("chat_conversations", sa.Column("memory_summary", sa.Text()))
    op.add_column("chat_conversations", sa.Column("memory_summary_through_message_id", UUID))
    op.add_column("chat_conversations", sa.Column("memory_version", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "ai_execution_traces",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("conversation_id", UUID),
        sa.Column("turn_id", UUID),
        sa.Column("trace_version", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("route", sa.String(60), nullable=False, server_default="business"),
        sa.Column("planner_kind", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("planner_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cache_status", sa.String(30), nullable=False, server_default="miss"),
        sa.Column("stage_durations_ms", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("model_rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_event_latency_ms", sa.Integer()),
        sa.Column("total_latency_ms", sa.Integer()),
        sa.Column("verification_outcome", sa.String(40), nullable=False, server_default="not_required"),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_category", sa.String(80)),
        sa.Column("zero_credit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["turn_id"], ["chat_turns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "user_id", "conversation_id", "turn_id", "route", "planner_kind", "cache_status", "verification_outcome", "error_category", "zero_credit"):
        op.create_index(f"ix_ai_execution_traces_{column}", "ai_execution_traces", [column])
    op.create_index(
        "ix_ai_execution_trace_org_created",
        "ai_execution_traces",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("ai_execution_traces")
    op.drop_column("chat_conversations", "memory_version")
    op.drop_column("chat_conversations", "memory_summary_through_message_id")
    op.drop_column("chat_conversations", "memory_summary")
    op.drop_column("chat_conversations", "memory_state")
