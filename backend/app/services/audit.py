"""Audit logging helper."""
from contextvars import ContextVar
from sqlalchemy.orm import Session

from app.models import AuditLog

platform_audit_context: ContextVar[dict | None] = ContextVar("platform_audit_context", default=None)


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
    changes: dict | None = None,
) -> None:
    support_context = platform_audit_context.get() or {}
    merged_meta = {**(meta or {}), **support_context, **({"changes": changes} if changes is not None else {})}
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
        meta=merged_meta,
    )
    db.add(entry)
    db.flush()
