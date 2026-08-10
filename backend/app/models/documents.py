"""Secure documents, retrieval chunks, outbound messages, and durable jobs."""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    uploaded_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))
    entity_type: Mapped[str | None] = mapped_column(String(50), index=True)
    entity_id: Mapped[str | None] = mapped_column(UUID_STR, index=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    object_key: Mapped[str] = mapped_column(String(600), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(30), default="team", nullable=False, index=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    document_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # JSONB fallback keeps local PostgreSQL usable when the vector extension is unavailable.
    embedding: Mapped[list | None] = mapped_column(JSONB)
    embedding_vector: Mapped[list | None] = mapped_column(Vector(1536))
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(250))
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class OutboundMessage(TimestampMixin, Base):
    __tablename__ = "outbound_messages"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_outbound_org_idempotency"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    recipient: Mapped[str] = mapped_column(String(200), nullable=False)
    template: Mapped[str | None] = mapped_column(String(120))
    template_language: Mapped[str | None] = mapped_column(String(20))
    template_variables: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(250))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_job_org_idempotency"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
