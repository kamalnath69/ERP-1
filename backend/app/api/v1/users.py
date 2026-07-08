"""User management endpoints (tenant admin) + self profile + permission overrides."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permissions
from app.core.security import hash_password, verify_password
from app.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserPermissionOverride,
    UserRole,
)
from app.schemas import (
    AssignRolesRequest,
    PasswordChange,
    ProfileUpdate,
    UserCreate,
    UserOut,
    UserOverridesUpdate,
    UserUpdate,
)
from app.services.rbac import get_user_permissions

router = APIRouter(prefix="/users", tags=["users"])


# ---------- Self profile (no explicit permission required) ---------- #

@router.get("/me/profile", response_model=UserOut)
def my_profile(user: CurrentUser):
    return user


@router.patch("/me/profile", response_model=UserOut)
def update_my_profile(body: ProfileUpdate, user: CurrentUser, db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/password")
def change_my_password(body: PasswordChange, user: CurrentUser, db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


# ---------- Tenant admin: list / create / read / update ---------- #

@router.get("", response_model=list[UserOut])
def list_users(
    user: User = Depends(require_permissions("users.view")),
    db: Session = Depends(get_db),
    q: str | None = None,
):
    stmt = select(User).where(User.organization_id == user.organization_id).order_by(User.created_at.desc())
    if q:
        like = f"%{q.lower()}%"
        from sqlalchemy import func, or_

        stmt = stmt.where(
            or_(
                func.lower(User.first_name).like(like),
                func.lower(User.last_name).like(like),
                func.lower(User.email).like(like),
            )
        )
    return db.execute(stmt.limit(200)).scalars().all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, user: User = Depends(require_permissions("users.manage")), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    new_user = User(
        organization_id=user.organization_id,
        email=email,
        hashed_password=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        is_active=True,
    )
    db.add(new_user)
    db.flush()
    for rid in body.role_ids:
        db.add(UserRole(user_id=new_user.id, role_id=rid))
    db.commit()
    db.refresh(new_user)
    return new_user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str, user: User = Depends(require_permissions("users.view")), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target or target.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return target


@router.get("/{user_id}/detail")
def get_user_detail(
    user_id: str,
    user: User = Depends(require_permissions("users.view")),
    db: Session = Depends(get_db),
):
    """Rich profile: user + roles + effective permissions."""
    target = db.get(User, user_id)
    if not target or target.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    role_rows = db.execute(
        select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    ).scalars().all()
    role_ids = [r.id for r in role_rows]

    # Role-granted permission ids
    role_perm_ids: set[str] = set()
    if role_ids:
        role_perm_ids = set(
            db.execute(
                select(RolePermission.permission_id).where(RolePermission.role_id.in_(role_ids))
            ).scalars().all()
        )

    override_rows = db.execute(
        select(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id)
    ).scalars().all()
    overrides = {o.permission_id: o.granted for o in override_rows}

    effective_codes = sorted(get_user_permissions(db, target))

    return {
        "user": UserOut.model_validate(target).model_dump(),
        "roles": [{"id": r.id, "name": r.name, "slug": r.slug, "is_system": r.is_system} for r in role_rows],
        "role_permission_ids": sorted(role_perm_ids),
        "overrides": [{"permission_id": pid, "granted": g} for pid, g in overrides.items()],
        "effective_permission_codes": effective_codes,
    }


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    user: User = Depends(require_permissions("users.manage")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target or target.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(target, k, v)
    db.commit()
    db.refresh(target)
    return target


@router.post("/{user_id}/roles")
def assign_roles(
    user_id: str,
    body: AssignRolesRequest,
    user: User = Depends(require_permissions("users.manage")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target or target.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    for rid in body.role_ids:
        db.add(UserRole(user_id=user_id, role_id=rid))
    db.commit()
    return {"ok": True, "role_count": len(body.role_ids)}


# ---------- User-level permission overrides ---------- #

@router.get("/{user_id}/overrides")
def list_user_overrides(
    user_id: str,
    user: User = Depends(require_permissions("users.view")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target or target.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    rows = db.execute(
        select(UserPermissionOverride).where(UserPermissionOverride.user_id == user_id)
    ).scalars().all()
    return {
        "user_id": user_id,
        "overrides": [{"permission_id": r.permission_id, "granted": r.granted} for r in rows],
    }


@router.put("/{user_id}/overrides")
def set_user_overrides(
    user_id: str,
    body: UserOverridesUpdate,
    user: User = Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target or target.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Validate every permission_id
    if body.overrides:
        perm_ids = [o.permission_id for o in body.overrides]
        found = db.execute(select(Permission.id).where(Permission.id.in_(perm_ids))).scalars().all()
        missing = set(perm_ids) - set(found)
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown permission ids: {sorted(missing)}")

    db.query(UserPermissionOverride).filter(UserPermissionOverride.user_id == user_id).delete()
    for o in body.overrides:
        db.add(UserPermissionOverride(user_id=user_id, permission_id=o.permission_id, granted=o.granted))
    db.commit()
    return {"ok": True, "override_count": len(body.overrides)}


@router.delete("/{user_id}/overrides")
def clear_user_overrides(
    user_id: str,
    user: User = Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target or target.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    n = db.query(UserPermissionOverride).filter(UserPermissionOverride.user_id == user_id).delete()
    db.commit()
    return {"ok": True, "deleted": n}
