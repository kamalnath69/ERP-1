"""Roles & permissions management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import Permission, Role, RolePermission, User
from app.schemas import PermissionOut, RoleCreate, RoleOut, RoleUpdate

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(user: User = Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    stmt = select(Permission).where(
        (Permission.organization_id == user.organization_id) | (Permission.organization_id.is_(None))
    ).order_by(Permission.module, Permission.code)
    return [
        p
        for p in db.execute(stmt).scalars().all()
        if p.module not in {"notifications"} and p.code != "audit.view"
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
    }


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreate, user: User = Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    role = Role(
        organization_id=user.organization_id,
        name=body.name,
        slug=body.name.lower().replace(" ", "-"),
        description=body.description,
        is_system=False,
        is_active=True,
    )
    db.add(role)
    db.flush()
    for pid in body.permission_ids:
        db.add(RolePermission(role_id=role.id, permission_id=pid))
    db.commit()
    db.refresh(role)
    return role


@router.patch("/{role_id}", response_model=RoleOut)
def update_role(role_id: str, body: RoleUpdate, user: User = Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role or role.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    data = body.model_dump(exclude_none=True)
    if "name" in data:
        role.name = data["name"]
        role.slug = data["name"].lower().replace(" ", "-")
    if "description" in data:
        role.description = data["description"]
    if "is_active" in data:
        role.is_active = data["is_active"]
    if body.permission_ids is not None:
        db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
        for pid in body.permission_ids:
            db.add(RolePermission(role_id=role.id, permission_id=pid))
    db.commit()
    db.refresh(role)
    return role


@router.delete("/{role_id}")
def delete_role(role_id: str, user: User = Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role or role.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.is_system:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "System roles cannot be deleted")
    db.delete(role)
    db.commit()
    return {"ok": True}
