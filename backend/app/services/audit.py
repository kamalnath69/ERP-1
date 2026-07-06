"""Audit logging helper."""
from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(
    db: Session,
    *,
    organization_id: str | None,
    user_id: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    tool: str | None = None,
    permission: str | None = None,
    question: str | None = None,
    ip_address: str | None = None,
    device: str | None = None,
    duration_ms: int | None = None,
    meta: dict | None = None,
    rows_affected: int | None = None,
) -> None:
    entry = AuditLog(
        organization_id=organization_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        tool=tool,
        permission=permission,
        question=question,
        ip_address=ip_address,
        device=device,
        duration_ms=duration_ms,
        rows_affected=rows_affected,
        meta=meta or {},
    )
    db.add(entry)
    db.flush()
