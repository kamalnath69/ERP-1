"""User and refresh token models."""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_user_org_email"),)

    id: Mapped[str] = uuid_pk()
    # tenant_id is NULLABLE only for platform Super Admin
    organization_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(300), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    # Data-URI base64 avatar (client-side resized to <= ~256px, ~40-60KB max).
    avatar_base64: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    designation: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    action_preferences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    access_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    replaced_by_token_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("refresh_tokens.id", ondelete="SET NULL"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip_address: Mapped[str | None] = mapped_column(String(60))


class AuthCode(TimestampMixin, Base):
    __tablename__ = "auth_codes"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    request_ip: Mapped[str | None] = mapped_column(String(60), index=True)


class AuthAttempt(TimestampMixin, Base):
    __tablename__ = "auth_attempts"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    identifier_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(60), index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UserPreference(TimestampMixin, Base):
    """Cross-device presentation preferences without mixing them into identity."""

    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", "namespace", name="uq_user_preference_namespace"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class UserMFADevice(TimestampMixin, Base):
    __tablename__ = "user_mfa_devices"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_mfa_device"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)


class UserRecoveryCode(TimestampMixin, Base):
    __tablename__ = "user_recovery_codes"
    __table_args__ = (UniqueConstraint("user_id", "code_hash", name="uq_user_recovery_code"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
