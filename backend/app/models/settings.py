"""Feature flags, per-org settings, notifications."""
from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class Setting(TimestampMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_setting_org_key"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)


class FeatureFlag(TimestampMixin, Base):
    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("organization_id", "flag", name="uq_flag_org_key"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    flag: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(60), default="info")  # info / warning / success / error
    link: Mapped[str | None] = mapped_column(String(500))
