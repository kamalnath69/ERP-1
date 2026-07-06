"""User management endpoints (tenant admin)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions, require_tenant
from app.core.security import hash_password
from app.models import User, UserRole
from app.schemas import UserCreate, UserOut, UserUpdate, AssignRolesRequest

router = APIRouter(prefix="/users", tags=["users"])


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
    # Remove existing roles for this user
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    for rid in body.role_ids:
        db.add(UserRole(user_id=user_id, role_id=rid))
    db.commit()
    return {"ok": True, "role_count": len(body.role_ids)}
