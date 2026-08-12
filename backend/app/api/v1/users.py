"""User management endpoints (tenant admin) + self profile + permission overrides."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permissions
from app.core.security import hash_password, verify_password
from app.schemas.validation import RequestModel
from app.models import (
    Permission,
    Role,
    RolePermission,
    RefreshToken, User, UserPreference,
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
from app.models import AccessScope, Location
from app.services.auth_security import clear_auth_cookies
from app.services.auth_security import create_auth_code
from app.services.email import send_auth_code_email
from app.services.audit import log_action
from app.ai.personalization import normalize_assistant_preferences

router = APIRouter(prefix="/users", tags=["users"])


class PreferenceUpdate(RequestModel):
    value: dict
    version: int | None = Field(default=None, ge=1)


PREFERENCE_NAMESPACES = {"appearance", "assistant", "dashboard", "navigation", "notifications"}


class MFAStartBody(RequestModel):
    current_password: str = Field(min_length=1, max_length=128)


class MFACodeBody(RequestModel):
    code: str = Field(min_length=6, max_length=64)


class MFASensitiveBody(MFACodeBody):
    current_password: str = Field(min_length=1, max_length=128)


# ---------- Self profile (no explicit permission required) ---------- #

@router.get("/me/profile", response_model=UserOut)
def my_profile(user: CurrentUser):
    return user


@router.patch("/me/profile", response_model=UserOut)
def update_my_profile(body: ProfileUpdate, user: CurrentUser, db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me/preferences")
def my_preferences(user: CurrentUser, db: Session = Depends(get_db)):
    rows = db.execute(select(UserPreference).where(UserPreference.user_id == user.id)).scalars().all()
    return {row.namespace: {"value": row.value, "version": row.version, "updated_at": row.updated_at} for row in rows}


@router.put("/me/preferences/{namespace}")
def save_my_preference(namespace: str, body: PreferenceUpdate, user: CurrentUser, db: Session = Depends(get_db)):
    if namespace not in PREFERENCE_NAMESPACES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This preference cannot be changed")
    value = body.value
    if namespace == "assistant":
        try:
            value = normalize_assistant_preferences(value)
        except ValidationError as exc:
            message = exc.errors()[0].get("msg", "Assistant preferences are invalid")
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, message) from exc
    row = db.execute(select(UserPreference).where(
        UserPreference.user_id == user.id, UserPreference.namespace == namespace,
    ).with_for_update()).scalar_one_or_none()
    if row:
        if body.version is not None and body.version != row.version:
            raise HTTPException(status.HTTP_409_CONFLICT, "Your preferences changed on another device")
        row.value = value
        row.version += 1
    else:
        row = UserPreference(
            organization_id=user.organization_id, user_id=user.id,
            namespace=namespace, value=value,
        )
        db.add(row)
    db.flush()
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="user.preference.update",
        resource_type="user_preference",
        resource_id=row.id,
        meta={"namespace": namespace, "version": row.version},
    )
    db.commit()
    db.refresh(row)
    return {"namespace": namespace, "value": row.value, "version": row.version, "updated_at": row.updated_at}


@router.post("/me/password")
def change_my_password(body: PasswordChange, response: Response, user: CurrentUser, db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    user.session_version += 1
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False)).update({RefreshToken.revoked: True})
    db.commit()
    clear_auth_cookies(response)
    return {"ok": True, "reauthenticate": True}


@router.get("/me/security")
def my_security(user: CurrentUser, db: Session = Depends(get_db)):
    from app.services.user_security import mfa_requirement, recovery_codes_remaining
    state = mfa_requirement(db, user)
    return {
        "mfa": {
            **state,
            "recovery_codes_remaining": recovery_codes_remaining(db, user) if state["enabled"] else 0,
        },
        "email_verified": user.email_verified,
    }


@router.post("/me/mfa/start")
def start_my_mfa(body: MFAStartBody, user: CurrentUser, db: Session = Depends(get_db)):
    from app.services.audit import log_action
    from app.services.user_security import begin_mfa_enrollment
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    try:
        enrollment = begin_mfa_enrollment(db, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="auth.mfa_enrollment_started", resource_type="user", resource_id=user.id)
    db.commit()
    return enrollment


@router.post("/me/mfa/verify")
def verify_my_mfa(body: MFACodeBody, user: CurrentUser, db: Session = Depends(get_db)):
    from app.services.audit import log_action
    from app.services.user_security import complete_mfa_enrollment
    try:
        recovery_codes = complete_mfa_enrollment(db, user, body.code)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="auth.mfa_enabled", resource_type="user", resource_id=user.id)
    db.commit()
    return {"ok": True, "recovery_codes": recovery_codes, "reauthenticate": True}


@router.post("/me/mfa/recovery-codes")
def regenerate_my_recovery_codes(body: MFASensitiveBody, user: CurrentUser, db: Session = Depends(get_db)):
    from app.services.audit import log_action
    from app.services.user_security import replace_recovery_codes, verify_user_mfa_or_recovery
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if not verify_user_mfa_or_recovery(db, user, body.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication code is invalid")
    recovery_codes = replace_recovery_codes(db, user)
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="auth.mfa_recovery_codes_replaced", resource_type="user", resource_id=user.id)
    db.commit()
    return {"recovery_codes": recovery_codes}


@router.post("/me/mfa/disable")
def disable_my_mfa(body: MFASensitiveBody, user: CurrentUser, db: Session = Depends(get_db)):
    from app.services.audit import log_action
    from app.services.user_security import disable_user_mfa, mfa_requirement, verify_user_mfa_or_recovery
    if mfa_requirement(db, user)["required"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your organization requires authenticator security for this account")
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if not verify_user_mfa_or_recovery(db, user, body.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication code is invalid")
    disable_user_mfa(db, user)
    user.session_version += 1
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False)).update({RefreshToken.revoked: True})
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="auth.mfa_disabled", resource_type="user", resource_id=user.id)
    db.commit()
    return {"ok": True, "reauthenticate": True}


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
def create_user(body: UserCreate, request: Request, user: User = Depends(require_permissions("users.manage")), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.execute(select(User).where(User.email == email, User.organization_id == user.organization_id)).scalar_one_or_none():
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
    if body.role_ids:
        valid_role_ids = set(db.execute(select(Role.id).where(Role.organization_id == user.organization_id, Role.id.in_(body.role_ids))).scalars().all())
        if valid_role_ids != set(body.role_ids):
            db.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more roles are invalid")
    for rid in body.role_ids:
        db.add(UserRole(user_id=new_user.id, role_id=rid))
    valid_locations = set(db.execute(select(Location.id).where(Location.organization_id == user.organization_id, Location.id.in_(body.location_ids))).scalars())
    if valid_locations != set(body.location_ids):
        db.rollback(); raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more locations are invalid")
    for location_id in valid_locations:
        db.add(AccessScope(organization_id=user.organization_id, user_id=new_user.id, scope_type="location", scope_value=location_id, meta={}))
    code = create_auth_code(db, new_user, "email_verification", request)
    db.commit()
    db.refresh(new_user)
    try:
        send_auth_code_email(new_user.email, code, "email_verification", new_user.first_name)
    except Exception:
        pass
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
    valid = set(db.execute(select(Role.id).where(Role.organization_id == user.organization_id, Role.id.in_(body.role_ids))).scalars())
    if valid != set(body.role_ids): raise HTTPException(422, "One or more roles are invalid")
    actor_codes = get_user_permissions(db, user)
    for role_id in valid:
        codes = set(db.execute(select(Permission.code).join(RolePermission, RolePermission.permission_id == Permission.id).where(RolePermission.role_id == role_id)).scalars())
        if not codes.issubset(actor_codes): raise HTTPException(403, "Cannot assign a role with permissions you do not have")
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
    if target.id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Use another administrator to change your own permission overrides")

    # Validate every permission_id
    if body.overrides:
        perm_ids = [o.permission_id for o in body.overrides]
        found = db.execute(select(Permission.id, Permission.code, Permission.organization_id).where(Permission.id.in_(perm_ids))).all()
        missing = set(perm_ids) - {row[0] for row in found}
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown permission ids: {sorted(missing)}")
        if any(org_id not in {None, user.organization_id} for _, _, org_id in found):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant permission grant blocked")
        actor_codes = get_user_permissions(db, user)
        if any(code not in actor_codes for _, code, _ in found) and not user.is_super_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot grant a permission you do not have")

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
    if target.id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Use another administrator to change your own permission overrides")
    n = db.query(UserPermissionOverride).filter(UserPermissionOverride.user_id == user_id).delete()
    db.commit()
    return {"ok": True, "deleted": n}
