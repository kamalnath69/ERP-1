"""Add durable AI turns and conversation follow-up context.

Revision ID: 20260801_0012
Revises: 20260801_0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260801_0012"
down_revision = "20260801_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chat_conversations", sa.Column(
        "context_state", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ))
    op.create_table(
        "chat_turns",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="processing"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("organization_id", "user_id", "request_key", name="uq_chat_turn_request"),
    )
    op.create_index("ix_chat_turns_organization_id", "chat_turns", ["organization_id"])
    op.create_index("ix_chat_turns_conversation_id", "chat_turns", ["conversation_id"])
    op.create_index("ix_chat_turns_user_id", "chat_turns", ["user_id"])
    op.create_index("ix_chat_turns_status", "chat_turns", ["status"])

    # Start with one turn per historical message, then pair each assistant with
    # the closest preceding user message in the same conversation.
    op.execute("""
        INSERT INTO chat_turns
            (id, organization_id, conversation_id, user_id, request_key, status,
             completed_at, error_code, created_at, updated_at)
        SELECT m.id, m.organization_id, m.conversation_id, c.user_id,
               'legacy:' || m.id::text,
               CASE WHEN m.role = 'assistant' THEN 'completed' ELSE 'failed' END,
               CASE WHEN m.role = 'assistant' THEN m.created_at ELSE NULL END,
               CASE WHEN m.role = 'assistant' THEN NULL ELSE 'legacy_incomplete' END,
               m.created_at, m.updated_at
        FROM chat_messages m
        JOIN chat_conversations c ON c.id = m.conversation_id
    """)
    op.add_column("chat_messages", sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.execute("UPDATE chat_messages SET turn_id = id")
    op.execute("""
        UPDATE chat_messages assistant
        SET turn_id = COALESCE((
            SELECT user_message.id
            FROM chat_messages user_message
            WHERE user_message.conversation_id = assistant.conversation_id
              AND user_message.role = 'user'
              AND user_message.created_at <= assistant.created_at
            ORDER BY user_message.created_at DESC, user_message.id DESC
            LIMIT 1
        ), assistant.id)
        WHERE assistant.role = 'assistant'
    """)
    op.execute("""
        UPDATE chat_turns turn_row
        SET status = 'completed', completed_at = answer.created_at, error_code = NULL
        FROM chat_messages answer
        WHERE answer.turn_id = turn_row.id AND answer.role = 'assistant'
    """)
    op.execute("DELETE FROM chat_turns t WHERE NOT EXISTS (SELECT 1 FROM chat_messages m WHERE m.turn_id = t.id)")
    op.create_foreign_key("fk_chat_messages_turn", "chat_messages", "chat_turns", ["turn_id"], ["id"], ondelete="CASCADE")
    op.alter_column("chat_messages", "turn_id", nullable=False)
    op.create_index("ix_chat_messages_turn_id", "chat_messages", ["turn_id"])


def downgrade():
    op.drop_index("ix_chat_messages_turn_id", table_name="chat_messages")
    op.drop_constraint("fk_chat_messages_turn", "chat_messages", type_="foreignkey")
    op.drop_column("chat_messages", "turn_id")
    op.drop_table("chat_turns")
    op.drop_column("chat_conversations", "context_state")
