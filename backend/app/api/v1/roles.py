"""Roles & permissions management."""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_entitlements, require_permissions
from app.models import Permission, Role, RolePermission, User, UserRole
from app.schemas import PermissionOut, RoleCreate, RoleOut, RoleUpdate
from app.services.audit import log_action
from app.services.rbac import get_user_permissions

router = APIRouter(prefix="/roles", tags=["roles"])


def _normalized_name(value: str) -> str:
    name = " ".join(value.split()).strip()
    if len(name) < 2 or len(name) > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Role name must be between 2 and 100 characters")
    return name


def _ensure_unique_name(db: Session, user: User, name: str, exclude_id: str | None = None) -> None:
    statement = select(Role.id).where(Role.organization_id == user.organization_id, func.lower(Role.name) == name.casefold())
    if exclude_id:
        statement = statement.where(Role.id != exclude_id)
    if db.execute(statement).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "A role with this name already exists")


def _slug(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return value or "custom-role"


def _validate_permission_grant(db: Session, actor: User, permission_ids: list[str]):
    rows = db.execute(select(Permission.id, Permission.code, Permission.organization_id).where(Permission.id.in_(permission_ids))).all() if permission_ids else []
    if len(rows) != len(set(permission_ids)) or any(org_id not in {None, actor.organization_id} for _, _, org_id in rows):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more permissions are invalid")
    actor_codes = get_user_permissions(db, actor)
    excessive = [code for _, code, _ in rows if code not in actor_codes]
    if excessive and not actor.is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot grant permissions you do not have")


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(user: User = Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    allowed_codes = get_user_permissions(db, user)
    stmt = select(Permission).where(
        (Permission.organization_id == user.organization_id) | (Permission.organization_id.is_(None))
    ).order_by(Permission.module, Permission.code)
    return [
        p
        for p in db.execute(stmt).scalars().all()
        if p.code in allowed_codes
    ]


@router.get("", response_model=list[RoleOut])
def list_roles(user: User = Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    stmt = select(Role).where(Role.organization_id == user.organization_id).order_by(Role.created_at.asc())
    return db.execute(stmt).scalars().all()


@router.get("/{role_id}")
def get_role(role_id: str, user: User = Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role or role.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    perm_ids = db.execute(
        select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
    ).scalars().all()
    return {
        "role": RoleOut.model_validate(role).model_dump(),
        "permission_ids": list(perm_ids),
        "user_count": int(db.scalar(select(func.count(UserRole.id)).where(UserRole.role_id == role.id)) or 0),
    }


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreate, user: User = Depends(require_permissions("roles.manage")), _plan=Depends(require_entitlements("access.custom_roles")), db: Session = Depends(get_db)):
    _validate_permission_grant(db, user, body.permission_ids)
    name = _normalized_name(body.name)
    _ensure_unique_name(db, user, name)
    role = Role(
        organization_id=user.organization_id,
        name=name,
        slug=_slug(name),
        description=body.description,
        is_system=False,
        is_active=True,
    )
    db.add(role)
    db.flush()
    for pid in body.permission_ids:
        db.add(RolePermission(role_id=role.id, permission_id=pid))
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="role.created", resource_type="role", resource_id=role.id, permission="roles.manage", meta={"summary": f"Created role {role.name}", "permission_count": len(body.permission_ids)})
    db.commit()
    db.refresh(role)
    return role


@router.patch("/{role_id}", response_model=RoleOut)
def update_role(role_id: str, body: RoleUpdate, user: User = Depends(require_permissions("roles.manage")), _plan=Depends(require_entitlements("access.custom_roles")), db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role or role.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.is_system:
        raise HTTPException(status.HTTP_409_CONFLICT, "Built-in role templates cannot be edited. Duplicate this role to customize it.")
    if body.version is not None and body.version != role.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "This role changed on another screen. Refresh before saving.")
    data = body.model_dump(exclude_none=True)
    if "name" in data:
        name = _normalized_name(data["name"])
        _ensure_unique_name(db, user, name, role.id)
        role.name = name
        role.slug = _slug(name)
    if "description" in data:
        role.description = data["description"]
    if "is_active" in data:
        role.is_active = data["is_active"]
    if body.permission_ids is not None:
        _validate_permission_grant(db, user, body.permission_ids)
        db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
        for pid in body.permission_ids:
            db.add(RolePermission(role_id=role.id, permission_id=pid))
    role.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="role.updated", resource_type="role", resource_id=role.id, permission="roles.manage", meta={"summary": f"Updated role {role.name}", "permission_count": len(body.permission_ids) if body.permission_ids is not None else None})
    db.commit()
    db.refresh(role)
    return role


@router.delete("/{role_id}")
def delete_role(role_id: str, user: User = Depends(require_permissions("roles.manage")), _plan=Depends(require_entitlements("access.custom_roles")), db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role or role.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.is_system:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "System roles cannot be deleted")
    assigned = int(db.scalar(select(func.count(UserRole.id)).where(UserRole.role_id == role.id)) or 0)
    if assigned:
        raise HTTPException(status.HTTP_409_CONFLICT, "This role is assigned to team members. Deactivate it after moving those people to another role.")
    role_name = role.name
    db.delete(role)
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="role.deleted", resource_type="role", resource_id=role.id, permission="roles.manage", meta={"summary": f"Deleted role {role_name}"})
    db.commit()
    return {"ok": True}


@router.post("/{role_id}/duplicate", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def duplicate_role(role_id: str, body: RoleCreate, user: User = Depends(require_permissions("roles.manage")), _plan=Depends(require_entitlements("access.custom_roles")), db: Session = Depends(get_db)):
    source = db.get(Role, role_id)
    if not source or source.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    permission_ids = body.permission_ids or list(db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == source.id)).scalars())
    name = _normalized_name(body.name)
    _ensure_unique_name(db, user, name)
    _validate_permission_grant(db, user, permission_ids)
    role = Role(organization_id=user.organization_id, name=name, slug=_slug(name), description=body.description or f"Customized from {source.name}", is_system=False, is_active=True)
    db.add(role)
    db.flush()
    for permission_id in permission_ids:
        db.add(RolePermission(role_id=role.id, permission_id=permission_id))
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="role.duplicated", resource_type="role", resource_id=role.id, permission="roles.manage", meta={"summary": f"Duplicated {source.name} as {role.name}", "source_role_id": source.id})
    db.commit()
    db.refresh(role)
    return role
