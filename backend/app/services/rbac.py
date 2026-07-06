"""Authorization service: role/permission resolution and enforcement."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserPermissionOverride,
    UserRole,
)


def get_user_permissions(db: Session, user: User) -> set[str]:
    """Resolve effective permission codes for a user.

    - Start with permissions granted by roles.
    - Apply per-user overrides last: granted=True adds, granted=False removes.
    """
    if user.is_super_admin:
        # Super admin: return every catalogue code
        codes = db.execute(select(Permission.code)).scalars().all()
        return set(codes)

    # Role permissions
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id)
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

    return codes


def user_has_permissions(db: Session, user: User, required: list[str]) -> bool:
    have = get_user_permissions(db, user)
    return all(code in have for code in required)


def get_user_roles(db: Session, user: User) -> list[Role]:
    stmt = select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
    return list(db.execute(stmt).scalars().all())
