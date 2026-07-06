"""Roles, permissions, and access scopes (RBAC + ABAC)."""
from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class Permission(TimestampMixin, Base):
    """Platform-wide catalogue of permissions. Tenant admins can also add tenant-scoped permissions."""

    __tablename__ = "permissions"

    id: Mapped[str] = uuid_pk()
    code: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    module: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )


class Role(TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_role_org_name"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[str] = uuid_pk()
    role_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)


class UserPermissionOverride(TimestampMixin, Base):
    """User-level override; wins over role permissions. `granted=False` denies."""

    __tablename__ = "user_permission_overrides"
    __table_args__ = (UniqueConstraint("user_id", "permission_id", name="uq_user_perm_override"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AccessScope(TimestampMixin, Base):
    """ABAC scopes: WHICH data a user can act on."""

    __tablename__ = "access_scopes"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False)  # campus/department/class/section/subject/batch
    scope_value: Mapped[str] = mapped_column(String(200), nullable=False)  # id or slug of target
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)
