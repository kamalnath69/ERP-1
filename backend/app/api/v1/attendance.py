"""Attendance endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatusConfig,
    AttendanceStatusEnum,
    User,
)
from app.schemas import AttendanceSessionCreate, AttendanceSessionOut

router = APIRouter(prefix="/attendance", tags=["attendance"])

# Default fallback statuses used when the tenant has NOT configured a catalogue.
_DEFAULT_STATUS_CODES = {s.value for s in AttendanceStatusEnum}


def _validate_status_code(db: Session, org_id: str, code: str) -> str:
    """Validate & normalise an incoming attendance status code."""
    code = (code or "present").strip()
    # 1) Tenant catalogue takes precedence
    tenant_codes = db.execute(
        select(AttendanceStatusConfig.code).where(
            AttendanceStatusConfig.organization_id == org_id,
            AttendanceStatusConfig.is_active.is_(True),
        )
    ).scalars().all()
    if tenant_codes:
        # Case-insensitive lookup, but store the exact code as configured.
        lower_map = {c.lower(): c for c in tenant_codes}
        if code.lower() in lower_map:
            return lower_map[code.lower()]
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"status '{code}' is not in this organisation's attendance catalogue: {sorted(tenant_codes)}. "
                   "Add it under Academic Config → Attendance Statuses first.",
        )
    # 2) Fallback to default enum values
    if code.lower() in _DEFAULT_STATUS_CODES:
        return code.lower()
    return "present"


@router.post("/sessions", response_model=AttendanceSessionOut, status_code=status.HTTP_201_CREATED)
def create_attendance_session(
    body: AttendanceSessionCreate,
    user: User = Depends(require_permissions("attendance.mark")),
    db: Session = Depends(get_db),
):
    try:
        sess_date = date.fromisoformat(body.session_date)
    except ValueError:
        raise HTTPException(400, "session_date must be YYYY-MM-DD")

    sess = AttendanceSession(
        organization_id=user.organization_id,
        section_id=body.section_id,
        subject_id=body.subject_id,
        faculty_user_id=user.id,
        session_date=sess_date,
        topic=body.topic,
    )
    db.add(sess)
    db.flush()
    for rec in body.records:
        status_code = _validate_status_code(db, user.organization_id, rec.get("status", "present"))
        db.add(
            AttendanceRecord(
                organization_id=user.organization_id,
                session_id=sess.id,
                student_id=rec["student_id"],
                status=status_code,
                remarks=rec.get("remarks"),
            )
        )
    db.commit()
    db.refresh(sess)
    return sess


@router.get("/sessions")
def list_sessions(
    section_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: User = Depends(require_permissions("attendance.view")),
    db: Session = Depends(get_db),
):
    stmt = select(AttendanceSession).where(AttendanceSession.organization_id == user.organization_id)
    if section_id:
        stmt = stmt.where(AttendanceSession.section_id == section_id)
    if date_from:
        stmt = stmt.where(AttendanceSession.session_date >= date.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(AttendanceSession.session_date <= date.fromisoformat(date_to))
    stmt = stmt.order_by(AttendanceSession.session_date.desc()).limit(200)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": r.id,
            "section_id": r.section_id,
            "subject_id": r.subject_id,
            "session_date": r.session_date.isoformat(),
            "topic": r.topic,
            "faculty_user_id": r.faculty_user_id,
        }
        for r in rows
    ]


@router.get("/sessions/{session_id}/records")
def get_session_records(
    session_id: str,
    user: User = Depends(require_permissions("attendance.view")),
    db: Session = Depends(get_db),
):
    sess = db.get(AttendanceSession, session_id)
    if not sess or sess.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    records = db.execute(
        select(AttendanceRecord).where(AttendanceRecord.session_id == session_id)
    ).scalars().all()
    return [
        {"id": r.id, "student_id": r.student_id, "status": r.status.value, "remarks": r.remarks}
        for r in records
    ]


@router.get("/summary")
def attendance_summary(
    section_id: str,
    days: int = 30,
    user: User = Depends(require_permissions("attendance.view")),
    db: Session = Depends(get_db),
):
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=days)
    stmt = (
        select(AttendanceRecord.status, func.count(AttendanceRecord.id))
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(
            AttendanceRecord.organization_id == user.organization_id,
            AttendanceSession.section_id == section_id,
            AttendanceSession.session_date >= cutoff,
        )
        .group_by(AttendanceRecord.status)
    )
    counts = {r[0].value: r[1] for r in db.execute(stmt).all()}
    total = sum(counts.values())
    present = counts.get("present", 0) + counts.get("late", 0)
    return {"counts": counts, "total": total, "attendance_percent": round(present / total * 100, 2) if total else 0.0}
