"""Analytics and dashboard endpoints."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    Department,
    Faculty,
    Section,
    Student,
    Subject,
    User,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard")
def dashboard(user: User = Depends(require_permissions("analytics.view")), db: Session = Depends(get_db)):
    org_id = user.organization_id
    students = db.execute(select(func.count(Student.id)).where(Student.organization_id == org_id)).scalar()
    faculty = db.execute(select(func.count(Faculty.id)).where(Faculty.organization_id == org_id)).scalar()
    subjects = db.execute(select(func.count(Subject.id)).where(Subject.organization_id == org_id)).scalar()
    sections = db.execute(select(func.count(Section.id)).where(Section.organization_id == org_id)).scalar()
    departments = db.execute(select(func.count(Department.id)).where(Department.organization_id == org_id)).scalar()

    cutoff = date.today() - timedelta(days=30)
    att_rows = db.execute(
        select(AttendanceRecord.status, func.count(AttendanceRecord.id))
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(
            AttendanceRecord.organization_id == org_id,
            AttendanceSession.session_date >= cutoff,
        )
        .group_by(AttendanceRecord.status)
    ).all()
    att_counts = {r[0].value: r[1] for r in att_rows}
    att_total = sum(att_counts.values())
    att_present = att_counts.get("present", 0) + att_counts.get("late", 0)
    att_pct = round((att_present / att_total) * 100, 2) if att_total else 0.0

    # Attendance trend last 14 days
    trend = []
    for i in range(13, -1, -1):
        d = date.today() - timedelta(days=i)
        rows = db.execute(
            select(AttendanceRecord.status, func.count(AttendanceRecord.id))
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .where(
                AttendanceRecord.organization_id == org_id,
                AttendanceSession.session_date == d,
            )
            .group_by(AttendanceRecord.status)
        ).all()
        c = {r[0].value: r[1] for r in rows}
        t = sum(c.values())
        p = c.get("present", 0) + c.get("late", 0)
        trend.append({"date": d.isoformat(), "attendance_percent": round(p / t * 100, 1) if t else 0.0})

    # Department distribution
    dept_dist = db.execute(
        select(Department.name, func.count(Student.id))
        .outerjoin(Student, Student.department_id == Department.id)
        .where(Department.organization_id == org_id)
        .group_by(Department.name)
    ).all()

    return {
        "kpis": {
            "students": students,
            "faculty": faculty,
            "subjects": subjects,
            "sections": sections,
            "departments": departments,
            "avg_attendance_30d": att_pct,
        },
        "attendance_trend": trend,
        "department_distribution": [{"name": n, "students": c} for n, c in dept_dist],
    }
