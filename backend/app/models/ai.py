"""AI chat conversations and messages."""
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class ChatConversation(TimestampMixin, Base):
    __tablename__ = "chat_conversations"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), default="New chat")
    provider: Mapped[str] = mapped_column(String(30), default="openai")
    model: Mapped[str] = mapped_column(String(80), default="gpt-5.4")


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    conversation_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant / tool / system
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[dict | None] = mapped_column(JSONB)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
