"""Audit log viewer, notifications, feature flags."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import AuditLog, FeatureFlag, Notification, User
from app.schemas import NotificationOut

router = APIRouter(tags=["misc"])


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = 100,
    user: User = Depends(require_permissions("audit.view")),
    db: Session = Depends(get_db),
):
    stmt = (
        select(AuditLog)
        .where(AuditLog.organization_id == user.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "user_id": r.user_id,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "tool": r.tool,
            "question": r.question,
            "ip_address": r.ip_address,
        }
        for r in rows
    ]


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(user: User = Depends(require_permissions("notifications.view")), db: Session = Depends(get_db)):
    stmt = (
        select(Notification)
        .where(Notification.organization_id == user.organization_id, Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return db.execute(stmt).scalars().all()


@router.post("/notifications/{nid}/read")
def mark_read(nid: str, user: User = Depends(require_permissions("notifications.view")), db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    if n and n.user_id == user.id:
        n.is_read = True
        db.commit()
    return {"ok": True}


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
