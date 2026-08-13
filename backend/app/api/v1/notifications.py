"""Personal, tenant-safe operational notifications."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Notification, Organization
from app.services.access_policy import policy_v2_enabled, resolve_policy_context
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size
from app.services.entity_resolution import validate_entity_ref


router = APIRouter(prefix="/notifications", tags=["notifications"])
ALLOWED_ROUTES = {
    "home", "clients", "calendar", "sales", "catalog", "inventory", "gym",
    "salon", "clinic", "college", "team", "reports", "documents", "billing", "settings",
}
ALLOWED_KINDS = {"client", "employee", "catalog"}
PATH_ROUTES = {
    "/app": "home", "/app/clients": "clients", "/app/calendar": "calendar",
    "/app/sales": "sales", "/app/catalog": "catalog", "/app/inventory": "inventory",
    "/app/gym": "gym", "/app/salon": "salon", "/app/clinic": "clinic", "/app/college": "college",
    "/app/team": "team", "/app/reports": "reports", "/app/documents": "documents",
    "/app/billing": "billing", "/app/settings": "settings",
}


def _destination(row: Notification) -> dict | None:
    value = row.destination or {}
    if value.get("kind") in ALLOWED_KINDS and value.get("id"):
        return {"kind": value["kind"], "id": str(value["id"])}
    if value.get("route") in ALLOWED_ROUTES:
        return {key: item for key, item in value.items() if key == "route" or isinstance(item, (str, int, bool))}
    legacy = (row.link or "").split("?", 1)[0].rstrip("/") or "/app"
    for prefix, kind in (("/app/clients/", "client"), ("/app/team/", "employee"), ("/app/catalog/", "catalog")):
        if legacy.startswith(prefix):
            identifier = legacy[len(prefix):].split("/", 1)[0]
            return {"kind": kind, "id": identifier} if identifier else None
    route = PATH_ROUTES.get(legacy)
    return {"route": route} if route else None


def _serialize(row: Notification) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "body": row.body,
        "kind": row.kind,
        "category": row.category,
        "is_read": row.is_read,
        "destination": _destination(row),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _notification_visible(db: Session, user, row: Notification) -> bool:
    organization = db.get(Organization, user.organization_id) if user.organization_id else None
    if (
        not organization
        or getattr(organization.industry, "value", organization.industry) != "college"
        or not policy_v2_enabled(db, user.organization_id)
    ):
        return True
    context = resolve_policy_context(db, user)
    if not context.active:
        return False
    if context.maximum_scope.unrestricted:
        return True

    destination = _destination(row)
    if destination and destination.get("kind"):
        return bool(validate_entity_ref(db, user, destination["kind"], destination["id"]))

    route = destination.get("route") if destination else None
    if route in {"settings", "team"}:
        return True
    if route == "clients":
        return context.level("students") != "none"
    if route in {"sales", "billing"}:
        return context.level("clearance") != "none" and context.has_sensitive("college.fees.view")

    # Aggregate notifications can contain counts from the scope that existed
    # when they were generated. Only show them when they carry the same policy
    # snapshot; direct-record notifications are revalidated above.
    snapshot = row.destination or {}
    if route in {"home", "college", "reports", "documents"}:
        if int(snapshot.get("policy_version") or -1) != context.policy_version:
            return False
        domain = {"reports": "reports", "documents": "documents"}.get(route)
        return not domain or context.level(domain) != "none"

    # Account and security notices are data-neutral. Unlinked operational
    # notices fail closed because their underlying student scope is unknown.
    return row.category in {"account", "security", "system"}


def _visible_rows(db: Session, user, statement, limit: int | None) -> list[Notification]:
    visible: list[Notification] = []
    stream = db.execute(statement.order_by(Notification.created_at.desc(), Notification.id.desc())).scalars()
    for row in stream:
        if _notification_visible(db, user, row):
            visible.append(row)
            if limit is not None and len(visible) >= limit:
                break
    return visible


@router.get("")
def list_notifications(
    status: str = Query("all", pattern="^(all|unread|action_required|delivery_issues)$"),
    unread_only: bool = False,
    limit: int = Query(100, ge=1, le=200),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(Notification).where(
        Notification.organization_id == user.organization_id,
        Notification.user_id == user.id,
    )
    if unread_only or status == "unread":
        statement = statement.where(Notification.is_read.is_(False))
    elif status == "action_required":
        statement = statement.where(Notification.category == "action_required")
    elif status == "delivery_issues":
        statement = statement.where(Notification.category == "delivery_issue")
    rows = _visible_rows(db, user, statement, limit)
    return [_serialize(row) for row in rows]


@router.get("/page")
def notification_page(
    status: str = Query("all", pattern="^(all|unread|action_required|delivery_issues)$"),
    q: str | None = Query(default=None, max_length=120),
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = {"status": status, "q": q}
    values = decode_cursor(cursor, scope="notifications.page", organization_id=user.organization_id, filters=filters)
    statement = select(Notification).where(
        Notification.organization_id == user.organization_id,
        Notification.user_id == user.id,
    )
    if status == "unread":
        statement = statement.where(Notification.is_read.is_(False))
    elif status == "action_required":
        statement = statement.where(Notification.category == "action_required")
    elif status == "delivery_issues":
        statement = statement.where(Notification.category == "delivery_issue")
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(or_(func.lower(Notification.title).like(term), func.lower(Notification.body).like(term)))
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            Notification.created_at < pivot_at,
            and_(Notification.created_at == pivot_at, Notification.id < values["id"]),
        ))
    size = page_size(limit)
    rows = _visible_rows(db, user, statement, size + 1)
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="notifications.page",
        organization_id=user.organization_id,
        filters=filters,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    return {"items": [_serialize(row) for row in rows], "next_cursor": next_cursor, "has_more": has_more}


@router.get("/summary")
def notification_summary(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = _visible_rows(db, user, select(Notification).where(
        Notification.organization_id == user.organization_id,
        Notification.user_id == user.id,
    ), None)
    return {
        "unread": sum(not row.is_read for row in rows),
        "action_required": sum(row.category == "action_required" for row in rows),
        "delivery_issues": sum(row.category == "delivery_issue" for row in rows),
        "total": len(rows),
    }


@router.post("/{notification_id}/read")
def read_notification(notification_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.execute(select(Notification).where(
        Notification.id == notification_id,
        Notification.organization_id == user.organization_id,
        Notification.user_id == user.id,
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Notification not found")
    if not _notification_visible(db, user, row):
        raise HTTPException(404, "Notification not found")
    row.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def read_all_notifications(user=Depends(get_current_user), db: Session = Depends(get_db)):
    visible_ids = [row.id for row in _visible_rows(db, user, select(Notification).where(
        Notification.organization_id == user.organization_id,
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    ), None)]
    if not visible_ids:
        return {"ok": True, "updated": 0}
    result = db.execute(
        update(Notification)
        .where(
            Notification.organization_id == user.organization_id,
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.id.in_(visible_ids),
        )
        .values(is_read=True)
    )
    db.commit()
    return {"ok": True, "updated": result.rowcount}
