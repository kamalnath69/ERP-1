"""AI Access Scopes API — create/list/delete configurable access scopes per user."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permissions
from app.models import AccessScope, User
from app.services.scopes import get_implicit_scopes, scope_catalog, KNOWN_TYPES

router = APIRouter(prefix="", tags=["access-scopes"])


# ---------- pydantic ---------- #

class ScopeIn(BaseModel):
    scope_type: str = Field(min_length=1, max_length=50)
    scope_value: str = Field(min_length=1, max_length=200)
    meta: dict | None = None


class ScopeOut(BaseModel):
    id: str | None
    user_id: str
    scope_type: str
    scope_value: str
    meta: dict | None = None
    is_known_type: bool
    is_implicit: bool = False
    source: str | None = None

    model_config = {"from_attributes": True}


# ---------- utility: 'can manage scopes for this user' ---------- #

def _can_manage_scopes(actor: User, target: User) -> bool:
    # actor must be in same tenant as target (unless super admin)
    if not actor.is_super_admin and actor.organization_id != target.organization_id:
        return False
    return True


def _require_manager(current_user: User, db: Session):
    """Guard: user must have roles.manage OR ai.scopes.manage."""
    from app.services.rbac import user_has_permissions
    if current_user.is_super_admin:
        return
    if user_has_permissions(db, current_user, ["ai.scopes.manage"]):
        return
    if user_has_permissions(db, current_user, ["roles.manage"]):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail="Requires ai.scopes.manage or roles.manage permission",
    )


# ---------- endpoints ---------- #

@router.get("/users/{user_id}/scopes", response_model=list[ScopeOut])
def list_user_scopes(
    user_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Return explicit + implicit scopes. Implicit rows carry is_implicit=true and cannot be deleted."""
    target = db.get(User, user_id)
    if not target or not _can_manage_scopes(current_user, target):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # 1) explicit
    explicit = db.execute(
        select(AccessScope).where(AccessScope.user_id == user_id).order_by(AccessScope.scope_type)
    ).scalars().all()
    out: list[ScopeOut] = [
        ScopeOut(
            id=r.id, user_id=r.user_id, scope_type=r.scope_type,
            scope_value=r.scope_value, meta=r.meta,
            is_known_type=r.scope_type in KNOWN_TYPES,
            is_implicit=False, source="explicit",
        )
        for r in explicit
    ]

    # 2) implicit (faculty assignments, section advisorship). De-dupe against explicit.
    explicit_keys = {(r.scope_type, r.scope_value) for r in explicit}
    for imp in get_implicit_scopes(db, target):
        key = (imp["scope_type"], imp["scope_value"])
        if key in explicit_keys:
            continue
        out.append(ScopeOut(
            id=None, user_id=user_id, scope_type=imp["scope_type"],
            scope_value=imp["scope_value"], meta=imp.get("meta") or {},
            is_known_type=imp["scope_type"] in KNOWN_TYPES,
            is_implicit=True, source=imp["source"],
        ))
    return out


@router.post("/users/{user_id}/scopes", response_model=ScopeOut, status_code=status.HTTP_201_CREATED)
def add_user_scope(
    user_id: str,
    body: ScopeIn,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target or not _can_manage_scopes(current_user, target):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    _require_manager(current_user, db)

    # Enforce tenant on the scope
    if not target.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot attach scope to a platform user")

    dup = db.execute(
        select(AccessScope).where(
            AccessScope.user_id == user_id,
            AccessScope.scope_type == body.scope_type,
            AccessScope.scope_value == body.scope_value,
        )
    ).scalar_one_or_none()
    if dup:
        return ScopeOut(
            id=dup.id, user_id=dup.user_id, scope_type=dup.scope_type,
            scope_value=dup.scope_value, meta=dup.meta,
            is_known_type=dup.scope_type in KNOWN_TYPES,
            is_implicit=False, source="explicit",
        )

    row = AccessScope(
        organization_id=target.organization_id,
        user_id=user_id,
        scope_type=body.scope_type.strip(),
        scope_value=body.scope_value.strip(),
        meta=body.meta or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ScopeOut(
        id=row.id, user_id=row.user_id, scope_type=row.scope_type,
        scope_value=row.scope_value, meta=row.meta,
        is_known_type=row.scope_type in KNOWN_TYPES,
        is_implicit=False, source="explicit",
    )


@router.delete("/scopes/{scope_id}")
def delete_scope(
    scope_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    try:
        row = db.get(AccessScope, scope_id)
    except Exception:
        row = None
    if not row or (not current_user.is_super_admin and row.organization_id != current_user.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scope not found")
    _require_manager(current_user, db)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/scopes/catalog")
def get_scope_catalog(current_user: CurrentUser, db: Session = Depends(get_db)):
    """Suggestions to power the UI: known scope types, tenant-defined types, and value pickers."""
    if not current_user.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No organization context")
    return scope_catalog(db, current_user.organization_id)
