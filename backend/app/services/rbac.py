"""Authorization service: role/permission resolution and enforcement."""
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserPermissionOverride,
    UserRole,
)

OWNER_SYSTEM_KEY = "owner"


def get_system_role_id(db: Session, organization_id: str, system_key: str) -> str | None:
    """Resolve a built-in role by its immutable machine identity."""
    cache = db.info.setdefault("edvatiq.system_role_ids", {})
    cache_key = (str(organization_id), system_key)
    if cache_key not in cache:
        cache[cache_key] = db.execute(select(Role.id).where(
            Role.organization_id == organization_id,
            Role.system_key == system_key,
            Role.is_system.is_(True),
            Role.is_active.is_(True),
        )).scalar_one_or_none()
    return cache[cache_key]


def is_system_owner(db: Session, user: User) -> bool:
    """Return whether an active tenant user holds the active system Owner role."""
    if not user.is_active or not user.organization_id or user.is_super_admin:
        return False
    owner_role_id = get_system_role_id(db, user.organization_id, OWNER_SYSTEM_KEY)
    if not owner_role_id:
        return False
    return db.execute(select(UserRole.id).where(
        UserRole.user_id == user.id,
        UserRole.role_id == owner_role_id,
    )).scalar_one_or_none() is not None


def active_owner_count(db: Session, organization_id: str) -> int:
    """Count active users holding the organization's active system Owner role."""
    owner_role_id = get_system_role_id(db, organization_id, OWNER_SYSTEM_KEY)
    if not owner_role_id:
        return 0
    return int(db.scalar(select(func.count(User.id)).join(
        UserRole, UserRole.user_id == User.id,
    ).where(
        User.organization_id == organization_id,
        User.is_active.is_(True),
        UserRole.role_id == owner_role_id,
    )) or 0)


def owner_invariant_health(db: Session) -> dict:
    """Report tenant organizations without a fully provisioned active Owner."""
    from app.models import AccessPolicy, AccessPolicyScope, Organization

    unhealthy = []
    organizations = list(db.execute(select(Organization.id, Organization.industry)).all())
    global_permission_count = int(db.scalar(select(func.count(Permission.id)).where(
        Permission.organization_id.is_(None),
    )) or 0)
    for organization_id, industry in organizations:
        role_id = get_system_role_id(db, organization_id, OWNER_SYSTEM_KEY)
        active_count = active_owner_count(db, organization_id)
        reasons = []
        if not role_id:
            reasons.append("missing_owner_role")
        if active_count < 1:
            reasons.append("missing_active_owner")
        if role_id:
            grant_count = int(db.scalar(select(func.count(RolePermission.id)).where(
                RolePermission.role_id == role_id,
            )) or 0)
            tenant_permission_count = int(db.scalar(select(func.count(Permission.id)).where(
                Permission.organization_id == organization_id,
            )) or 0)
            if grant_count < global_permission_count + tenant_permission_count:
                reasons.append("owner_grants_need_repair")
        if getattr(industry, "value", industry) == "college" and role_id:
            owner_ids = list(db.execute(select(User.id).join(
                UserRole, UserRole.user_id == User.id,
            ).where(
                UserRole.role_id == role_id,
                User.is_active.is_(True),
            )).scalars())
            provisioned = int(db.scalar(select(func.count(AccessPolicy.id)).where(
                AccessPolicy.user_id.in_(owner_ids),
                AccessPolicy.status == "active",
            )) or 0) if owner_ids else 0
            scoped = int(db.scalar(select(func.count(AccessPolicyScope.id)).join(
                AccessPolicy, AccessPolicy.id == AccessPolicyScope.policy_id,
            ).where(
                AccessPolicy.user_id.in_(owner_ids),
                AccessPolicyScope.domain_key == "*",
                AccessPolicyScope.scope_type == "organization",
                AccessPolicyScope.scope_value == "*",
            )) or 0) if owner_ids else 0
            if provisioned < len(owner_ids) or scoped < len(owner_ids):
                reasons.append("owner_policy_needs_repair")
        if reasons:
            unhealthy.append({"organization_id": organization_id, "reasons": reasons})
    return {
        "healthy": not unhealthy,
        "organizations_checked": len(organizations),
        "unhealthy": unhealthy,
    }


def get_user_permissions(db: Session, user: User) -> set[str]:
    """Resolve effective permission codes for a user.

    - Start with permissions granted by roles.
    - Apply per-user overrides last: granted=True adds, granted=False removes.
    """
    if user.is_super_admin:
        # Super admin: return every catalogue code
        return set(db.execute(select(Permission.code)).scalars().all())

    # Owner is a runtime invariant rather than a seed-time permission bundle.
    # This automatically includes future catalogue entries and intentionally
    # ignores per-user deny overrides, while retaining the tenant boundary.
    if is_system_owner(db, user):
        return set(db.execute(select(Permission.code).where(or_(
            Permission.organization_id.is_(None),
            Permission.organization_id == user.organization_id,
        ))).scalars().all())

    cache = db.info.setdefault("edvatiq.user_permissions", {})
    cache_key = (str(user.id), int(user.access_version or 0), bool(user.is_active))
    cached = cache.get(cache_key)
    if cached is not None:
        return set(cached)

    # Role permissions
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id, Role.is_active.is_(True))
    )
    codes = set(db.execute(stmt).scalars().all())

    # Overrides
    override_stmt = (
        select(Permission.code, UserPermissionOverride.granted)
        .join(Permission, Permission.id == UserPermissionOverride.permission_id)
        .where(UserPermissionOverride.user_id == user.id)
    )
    for code, granted in db.execute(override_stmt).all():
        if granted:
            codes.add(code)
        else:
            codes.discard(code)

    resolved = frozenset(codes)
    cache[cache_key] = resolved
    return set(resolved)


def user_has_permissions(db: Session, user: User, required: list[str]) -> bool:
    have = get_user_permissions(db, user)
    return all(code in have for code in required)


def get_user_roles(db: Session, user: User) -> list[Role]:
    cache = db.info.setdefault("edvatiq.user_roles", {})
    cache_key = (str(user.id), int(user.access_version or 0))
    cached = cache.get(cache_key)
    if cached is not None:
        return list(cached)
    stmt = select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id, Role.is_active.is_(True))
    roles = tuple(db.execute(stmt).scalars().all())
    cache[cache_key] = roles
    return list(roles)
