"""Notification sending (in-app + email skeleton)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import Notification, Role, User, UserRole

router = APIRouter(prefix="/notifications-send", tags=["notifications"])


class SendIn(BaseModel):
    title: str
    body: str | None = None
    kind: str = "info"
    link: str | None = None
    user_ids: list[str] | None = None       # explicit recipients
    role_slug: str | None = None            # OR everyone with this role
    all_users: bool = False                 # OR broadcast to whole tenant


@router.post("", status_code=status.HTTP_201_CREATED)
def send_notification(body: SendIn, user: User = Depends(require_permissions("notifications.send")), db: Session = Depends(get_db)):
    if not (body.user_ids or body.role_slug or body.all_users):
        raise HTTPException(400, "Provide user_ids, role_slug, or set all_users=true")

    recipients: list[str] = []
    if body.all_users:
        rows = db.execute(select(User.id).where(User.organization_id == user.organization_id, User.is_active.is_(True))).scalars().all()
        recipients.extend(rows)
    if body.role_slug:
        role = db.execute(select(Role).where(Role.organization_id == user.organization_id, Role.slug == body.role_slug)).scalar_one_or_none()
        if role:
            rows = db.execute(select(UserRole.user_id).where(UserRole.role_id == role.id)).scalars().all()
            recipients.extend(rows)
    if body.user_ids:
        recipients.extend(body.user_ids)

    recipients = list(set(recipients))
    count = 0
    for uid in recipients:
        n = Notification(
            organization_id=user.organization_id,
            user_id=uid,
            title=body.title,
            body=body.body,
            kind=body.kind,
            link=body.link,
        )
        db.add(n)
        count += 1
    db.commit()
    return {"ok": True, "sent": count}
