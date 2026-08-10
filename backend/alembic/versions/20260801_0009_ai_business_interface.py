"""Add the secured AI business interface schema.

Revision ID: 20260801_0009
Revises: 20260731_0008
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "20260801_0009"
down_revision = "20260731_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column("documents", sa.Column("visibility", sa.String(30), nullable=False, server_default="team"))
    op.add_column("documents", sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("documents", sa.Column("embedding_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_documents_visibility", "documents", ["visibility"])

    op.add_column("document_chunks", sa.Column("embedding_vector", Vector(1536), nullable=True))
    op.add_column("document_chunks", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True))
    op.add_column("document_chunks", sa.Column("page_number", sa.Integer(), nullable=True))
    op.add_column("document_chunks", sa.Column("section", sa.String(250), nullable=True))
    op.add_column("document_chunks", sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE document_chunks SET search_vector = to_tsvector('simple', content)")
    op.create_index("ix_document_chunks_search_vector", "document_chunks", ["search_vector"], postgresql_using="gin")
    op.execute("CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding_vector vector_cosine_ops)")

    op.add_column("chat_conversations", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_chat_conversations_expires_at", "chat_conversations", ["expires_at"])
    op.add_column("chat_messages", sa.Column("response_schema_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("chat_messages", sa.Column("blocks", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("chat_messages", sa.Column("citations", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))

    for name, column in [
        ("required_permission", sa.Column("required_permission", sa.String(100), nullable=True)),
        ("policy_version", sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1")),
        ("undo_payload", sa.Column("undo_payload", postgresql.JSONB(), nullable=True)),
        ("undo_expires_at", sa.Column("undo_expires_at", sa.DateTime(timezone=True), nullable=True)),
        ("undone_at", sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True)),
        ("version", sa.Column("version", sa.Integer(), nullable=False, server_default="1")),
    ]:
        op.add_column("ai_actions", column)

    op.add_column("ai_usage", sa.Column("route", sa.String(40), nullable=False, server_default="business"))
    op.add_column("ai_usage", sa.Column("status", sa.String(30), nullable=False, server_default="completed"))
    op.add_column("ai_usage", sa.Column("credits_used", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ai_usage", sa.Column("tool_latency_ms", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "ai_result_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("query_spec", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_type", sa.String(50), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_results_org_user", "ai_result_sessions", ["organization_id", "user_id", "expires_at"])

    op.create_table(
        "ai_saved_views",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("query_spec", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("layout", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_saved_views_org_owner", "ai_saved_views", ["organization_id", "owner_user_id"])

    op.create_table(
        "ai_message_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", "user_id", name="uq_ai_feedback_message_user"),
    )


def downgrade():
    op.drop_table("ai_message_feedback")
    op.drop_index("ix_ai_saved_views_org_owner", table_name="ai_saved_views")
    op.drop_table("ai_saved_views")
    op.drop_index("ix_ai_results_org_user", table_name="ai_result_sessions")
    op.drop_table("ai_result_sessions")
    for column in ["tool_latency_ms", "credits_used", "status", "route"]:
        op.drop_column("ai_usage", column)
    for column in ["version", "undone_at", "undo_expires_at", "undo_payload", "policy_version", "required_permission"]:
        op.drop_column("ai_actions", column)
    for column in ["citations", "blocks", "response_schema_version"]:
        op.drop_column("chat_messages", column)
    op.drop_index("ix_chat_conversations_expires_at", table_name="chat_conversations")
    op.drop_column("chat_conversations", "expires_at")
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_index("ix_document_chunks_search_vector", table_name="document_chunks")
    for column in ["token_count", "section", "page_number", "search_vector", "embedding_vector"]:
        op.drop_column("document_chunks", column)
    op.drop_index("ix_documents_visibility", table_name="documents")
    for column in ["embedding_version", "embedding_model", "visibility"]:
        op.drop_column("documents", column)
