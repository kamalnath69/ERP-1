"""Roles, permissions, and access scopes (RBAC + ABAC)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


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
    """ABAC scopes for locations and assigned business entities."""

    __tablename__ = "access_scopes"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False)  # location/client/employee/assigned
    scope_value: Mapped[str] = mapped_column(String(200), nullable=False)  # id or slug of target
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class AccessPolicy(TimestampMixin, Base):
    """Versioned, fail-closed data reach for one organization user."""

    __tablename__ = "access_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_access_policy_org_user"),
        Index("ix_access_policies_org_status_user", "organization_id", "status", "user_id"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending_review", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    domain_levels: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(500))


class AccessPolicyScope(TimestampMixin, Base):
    """Include-only roots. `domain_key='*'` is the user's maximum reach."""

    __tablename__ = "access_policy_scopes"
    __table_args__ = (
        UniqueConstraint(
            "policy_id", "domain_key", "scope_type", "scope_value",
            name="uq_access_policy_scope_root",
        ),
        Index(
            "ix_access_policy_scopes_policy_domain_type",
            "policy_id", "domain_key", "scope_type",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    policy_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("access_policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain_key: Mapped[str] = mapped_column(String(50), default="*", nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(200), nullable=False)


class AccessDelegation(TimestampMixin, Base):
    """Owner-controlled ceiling for an Access Admin."""

    __tablename__ = "access_delegations"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_access_delegation_org_user"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    domain_levels: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sensitive_capabilities: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_by_user_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class AccessDelegationScope(TimestampMixin, Base):
    __tablename__ = "access_delegation_scopes"
    __table_args__ = (
        UniqueConstraint(
            "delegation_id", "scope_type", "scope_value",
            name="uq_access_delegation_scope_root",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    delegation_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("access_delegations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(200), nullable=False)
