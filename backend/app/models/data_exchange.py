"""Tenant-scoped import, export, and template run records."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class DataExchangeRun(TimestampMixin, Base):
    __tablename__ = "data_exchange_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_data_exchange_org_idempotency"),
        Index(
            "ix_data_exchange_runs_org_created_id",
            "organization_id", "created_at", "id",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    resource_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    file_format: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="uploaded", nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(40), default="1", nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_import_run_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("college_import_runs.id", ondelete="SET NULL"), index=True,
    )
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    create_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    update_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    committed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    initiated_by_user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    correction_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class DataExchangeRow(TimestampMixin, Base):
    __tablename__ = "data_exchange_rows"
    __table_args__ = (
        UniqueConstraint("run_id", "row_number", name="uq_data_exchange_row_number"),
        Index("ix_data_exchange_rows_run_status_row", "run_id", "status", "row_number", "id"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    run_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("data_exchange_runs.id", ondelete="CASCADE"), index=True,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(24), default="validate", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    natural_key: Mapped[str | None] = mapped_column(String(300), index=True)
    record_id: Mapped[str | None] = mapped_column(UUID_STR, index=True)
    record_version: Mapped[int | None] = mapped_column(Integer)
    values: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    current_values: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    changes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class DataExchangeArtifact(TimestampMixin, Base):
    __tablename__ = "data_exchange_artifacts"
    __table_args__ = (
        UniqueConstraint("run_id", "kind", name="uq_data_exchange_artifact_kind"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    run_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("data_exchange_runs.id", ondelete="CASCADE"), index=True,
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
