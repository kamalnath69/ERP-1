"""AI conversations, metering, and safely staged actions."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    model: Mapped[str] = mapped_column(String(80), default="configured")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context_state: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    memory_state: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    memory_summary: Mapped[str | None] = mapped_column(Text)
    memory_summary_through_message_id: Mapped[str | None] = mapped_column(UUID_STR)
    memory_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ChatTurn(TimestampMixin, Base):
    __tablename__ = "chat_turns"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "request_key", name="uq_chat_turn_request"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    conversation_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    request_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="processing", nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    conversation_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("chat_turns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant / tool / system
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[dict | None] = mapped_column(JSONB)
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    response_schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    blocks: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class AIAction(TimestampMixin, Base):
    __tablename__ = "ai_actions"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_ai_action_org_key"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("chat_conversations.id", ondelete="SET NULL"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    preview: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_confirmation", nullable=False, index=True)
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(100))
    confirmation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    required_permission: Mapped[str | None] = mapped_column(String(100))
    policy_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    undo_payload: Mapped[dict | None] = mapped_column(JSONB)
    undo_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AIUsage(TimestampMixin, Base):
    __tablename__ = "ai_usage"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_cost_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_version: Mapped[str] = mapped_column(String(60), default="legacy", nullable=False)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    route: Mapped[str] = mapped_column(String(40), default="business", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="completed", nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AIExecutionTrace(TimestampMixin, Base):
    """Sanitized execution telemetry for both free and provider-backed turns."""

    __tablename__ = "ai_execution_traces"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("chat_conversations.id", ondelete="SET NULL"), index=True
    )
    turn_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("chat_turns.id", ondelete="SET NULL"), index=True
    )
    trace_version: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    route: Mapped[str] = mapped_column(String(60), default="business", nullable=False, index=True)
    planner_kind: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False, index=True)
    planner_confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    cache_status: Mapped[str] = mapped_column(String(30), default="miss", nullable=False, index=True)
    stage_durations_ms: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    model_rounds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_event_latency_ms: Mapped[int | None] = mapped_column(Integer)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer)
    verification_outcome: Mapped[str] = mapped_column(String(40), default="not_required", nullable=False, index=True)
    policy_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(80), index=True)
    zero_credit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AIIntentResolution(TimestampMixin, Base):
    __tablename__ = "ai_intent_resolutions"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("chat_conversations.id", ondelete="SET NULL"), index=True
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(100), index=True)
    subject: Mapped[str | None] = mapped_column(String(60), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AIResultSession(TimestampMixin, Base):
    __tablename__ = "ai_result_sessions"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    query_spec: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result_type: Mapped[str] = mapped_column(String(50), nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class AISavedView(TimestampMixin, Base):
    __tablename__ = "ai_saved_views"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    owner_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    query_spec: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    layout: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AIMessageFeedback(TimestampMixin, Base):
    __tablename__ = "ai_message_feedback"
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_ai_feedback_message_user"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    message_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
