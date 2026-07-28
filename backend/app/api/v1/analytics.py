"""Analytics and dashboard endpoints."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    Department,
    Exam,
    Faculty,
    Mark,
    Section,
    Student,
    Subject,
    User,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _status_key(value) -> str:
    return str(value.value if hasattr(value, "value") else value)


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
    att_counts = {_status_key(r[0]): r[1] for r in att_rows}
    att_total = sum(att_counts.values())
    att_present = att_counts.get("present", 0) + att_counts.get("late", 0)
    att_pct = round((att_present / att_total) * 100, 2) if att_total else 0.0

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
      c = {_status_key(r[0]): r[1] for r in rows}
      t = sum(c.values())
      p = c.get("present", 0) + c.get("late", 0)
      trend.append({"date": d.isoformat(), "attendance_percent": round(p / t * 100, 1) if t else 0.0})

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


@router.get("/widgets")
def enterprise_widgets(user: User = Depends(require_permissions("analytics.view")), db: Session = Depends(get_db)):
    org_id = user.organization_id

    students = db.execute(select(func.count(Student.id)).where(Student.organization_id == org_id)).scalar() or 0
    faculty = db.execute(select(func.count(Faculty.id)).where(Faculty.organization_id == org_id)).scalar() or 0
    subjects = db.execute(select(func.count(Subject.id)).where(Subject.organization_id == org_id)).scalar() or 0
    sections = db.execute(select(func.count(Section.id)).where(Section.organization_id == org_id)).scalar() or 0
    departments = db.execute(select(func.count(Department.id)).where(Department.organization_id == org_id)).scalar() or 0

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
    att_counts = {_status_key(r[0]): r[1] for r in att_rows}
    att_total = sum(att_counts.values())
    att_present = att_counts.get("present", 0) + att_counts.get("late", 0)
    att_pct = round((att_present / att_total) * 100, 2) if att_total else 0.0

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
        c = {_status_key(r[0]): r[1] for r in rows}
        t = sum(c.values())
        p = c.get("present", 0) + c.get("late", 0)
        trend.append({"date": d.isoformat(), "attendance_percent": round(p / t * 100, 1) if t else 0.0})

    dept_dist = db.execute(
        select(Department.name, func.count(Student.id))
        .outerjoin(Student, Student.department_id == Department.id)
        .where(Department.organization_id == org_id)
        .group_by(Department.name)
    ).all()

    at_risk_rows = db.execute(
        select(
            Student.id,
            Student.first_name,
            Student.last_name,
            Student.roll_number,
            func.count(AttendanceRecord.id).label("total"),
            func.sum(
                case(
                    (AttendanceRecord.status == "present", 1),
                    (AttendanceRecord.status == "late", 1),
                    (AttendanceRecord.status == "P", 1),
                    (AttendanceRecord.status == "L", 1),
                    (AttendanceRecord.status == "OD", 1),
                    else_=0,
                )
            ).label("present"),
        )
        .join(AttendanceRecord, AttendanceRecord.student_id == Student.id)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(
            Student.organization_id == org_id,
            AttendanceSession.session_date >= cutoff,
        )
        .group_by(Student.id, Student.first_name, Student.last_name, Student.roll_number)
        .having(func.count(AttendanceRecord.id) >= 5)
    ).all()
    at_risk = []
    for r in at_risk_rows:
        total = r.total or 0
        present = r.present or 0
        pct = round((present / total) * 100, 1) if total else 0.0
        if pct < 75:
            at_risk.append(
                {
                    "student_id": r.id,
                    "name": f"{r.first_name} {r.last_name}".strip(),
                    "roll_no": r.roll_number,
                    "attendance_pct": pct,
                    "sessions": total,
                }
            )
    at_risk.sort(key=lambda x: x["attendance_pct"])
    at_risk = at_risk[:10]

    top_rows = db.execute(
        select(
            Student.id,
            Student.first_name,
            Student.last_name,
            Student.roll_number,
            func.avg((Mark.obtained / Exam.max_marks) * 100).label("avg_pct"),
            func.count(Mark.id).label("exams"),
        )
        .join(Mark, Mark.student_id == Student.id)
        .join(Exam, Exam.id == Mark.exam_id)
        .where(
            Student.organization_id == org_id,
            Exam.is_published.is_(True),
        )
        .group_by(Student.id, Student.first_name, Student.last_name, Student.roll_number)
        .having(func.count(Mark.id) >= 1)
        .order_by(func.avg((Mark.obtained / Exam.max_marks) * 100).desc())
        .limit(8)
    ).all()
    top_performers = [
        {
            "student_id": r.id,
            "name": f"{r.first_name} {r.last_name}".strip(),
            "roll_no": r.roll_number,
            "avg_pct": round(float(r.avg_pct or 0), 1),
            "exams": r.exams,
        }
        for r in top_rows
    ]

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
        "at_risk": at_risk,
        "top_performers": top_performers,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
