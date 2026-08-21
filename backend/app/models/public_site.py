"""Public-site legal publication, consent evidence, and demo enquiries."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk


class LegalDocument(TimestampMixin, Base):
    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint("document_type", "version", name="uq_legal_document_type_version"),
        Index("ix_legal_document_type_status", "document_type", "status"),
        Index(
            "uq_legal_document_current",
            "document_type",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
    )

    id: Mapped[str] = uuid_pk()
    document_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    version: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    version_lock: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )


class LegalAcceptance(TimestampMixin, Base):
    __tablename__ = "legal_acceptances"
    __table_args__ = (
        Index("ix_legal_acceptance_org_time", "organization_id", "accepted_at"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    signup_checkout_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("signup_checkouts.id", ondelete="SET NULL"), unique=True, index=True
    )
    subject_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    terms_document_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False
    )
    privacy_document_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False
    )
    refund_document_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False
    )
    document_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(80))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(40), nullable=False)


class DemoRequest(TimestampMixin, Base):
    __tablename__ = "demo_requests"
    __table_args__ = (
        Index("ix_demo_request_status_time", "status", "created_at"),
        Index("ix_demo_request_ip_time", "ip_hash", "created_at"),
    )

    id: Mapped[str] = uuid_pk()
    inquiry_type: Mapped[str] = mapped_column(
        String(32), default="product_demo", server_default="product_demo", nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    work_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    organization_name: Mapped[str | None] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(40), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="new", nullable=False, index=True)
    privacy_document_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False
    )
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
