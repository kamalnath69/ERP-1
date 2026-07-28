"""Feature flag and lightweight system routes."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import FeatureFlag, User

router = APIRouter(tags=["misc"])


@router.get("/feature-flags")
def feature_flags(user: User = Depends(require_permissions("settings.manage")), db: Session = Depends(get_db)):
    stmt = select(FeatureFlag).where(FeatureFlag.organization_id == user.organization_id)
    return [{"id": f.id, "flag": f.flag, "enabled": f.enabled} for f in db.execute(stmt).scalars().all()]


@router.post("/feature-flags/{flag_id}/toggle")
def toggle_flag(flag_id: str, user: User = Depends(require_permissions("settings.manage")), db: Session = Depends(get_db)):
    f = db.get(FeatureFlag, flag_id)
    if f and f.organization_id == user.organization_id:
        f.enabled = not f.enabled
        db.commit()
    return {"ok": True, "enabled": f.enabled if f else False}
