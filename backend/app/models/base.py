"""Common SQLAlchemy base mixins."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base  # noqa: F401 re-export

UUID_STR = UUID(as_uuid=False)


def uuid_pk() -> Mapped[str]:
    return mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid.uuid4()))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TenantMixin:
    """Every business table has an organization_id column referencing organizations.id."""

    @classmethod
    def _tenant_column(cls):
        return mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def tenant_fk() -> Mapped[str]:
    return mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
