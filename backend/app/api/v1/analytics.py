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
    AuditLog,
    CalendarEvent,
    Department,
    Exam,
    Faculty,
    FeeInvoice,
    Mark,
    Notification,
    PlacementOffer,
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


@router.get("/widgets")
def enterprise_widgets(user: User = Depends(require_permissions("analytics.view")), db: Session = Depends(get_db)):
    """Aggregated data for the enterprise dashboard (8+ widgets)."""
    org_id = user.organization_id

    # --- KPIs ---
    students = db.execute(select(func.count(Student.id)).where(Student.organization_id == org_id)).scalar() or 0
    faculty = db.execute(select(func.count(Faculty.id)).where(Faculty.organization_id == org_id)).scalar() or 0
    subjects = db.execute(select(func.count(Subject.id)).where(Subject.organization_id == org_id)).scalar() or 0
    sections = db.execute(select(func.count(Section.id)).where(Section.organization_id == org_id)).scalar() or 0
    departments = db.execute(select(func.count(Department.id)).where(Department.organization_id == org_id)).scalar() or 0

    # --- 30d avg attendance ---
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

    # --- Attendance trend (14 days) ---
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

    # --- Department distribution ---
    dept_dist = db.execute(
        select(Department.name, func.count(Student.id))
        .outerjoin(Student, Student.department_id == Department.id)
        .where(Department.organization_id == org_id)
        .group_by(Department.name)
    ).all()

    # --- At-risk students (attendance < 75% last 30d) ---
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

    # --- Top performers (highest average across published exams) ---
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

    # --- Fees summary ---
    fee_rows = db.execute(
        select(FeeInvoice.status, func.sum(FeeInvoice.amount), func.sum(FeeInvoice.amount_paid), func.count(FeeInvoice.id))
        .where(FeeInvoice.organization_id == org_id)
        .group_by(FeeInvoice.status)
    ).all()
    fee_summary = {
        "billed": 0.0,
        "collected": 0.0,
        "pending": 0.0,
        "invoices": 0,
        "by_status": [],
    }
    for status_val, billed, paid, cnt in fee_rows:
        billed_f = float(billed or 0)
        paid_f = float(paid or 0)
        fee_summary["billed"] += billed_f
        fee_summary["collected"] += paid_f
        fee_summary["invoices"] += cnt or 0
        fee_summary["by_status"].append(
            {"status": status_val, "billed": billed_f, "collected": paid_f, "count": cnt or 0}
        )
    fee_summary["pending"] = round(fee_summary["billed"] - fee_summary["collected"], 2)
    fee_summary["billed"] = round(fee_summary["billed"], 2)
    fee_summary["collected"] = round(fee_summary["collected"], 2)
    fee_summary["collection_rate"] = round(
        (fee_summary["collected"] / fee_summary["billed"] * 100) if fee_summary["billed"] else 0, 1
    )

    # --- Placement stats ---
    placement_rows = db.execute(
        select(
            func.count(PlacementOffer.id),
            func.avg(PlacementOffer.package_lpa),
            func.max(PlacementOffer.package_lpa),
        ).where(PlacementOffer.organization_id == org_id)
    ).one()
    accepted = db.execute(
        select(func.count(PlacementOffer.id)).where(
            PlacementOffer.organization_id == org_id, PlacementOffer.status == "accepted"
        )
    ).scalar() or 0
    placement_stats = {
        "offers": placement_rows[0] or 0,
        "accepted": accepted,
        "avg_lpa": round(float(placement_rows[1] or 0), 2),
        "max_lpa": round(float(placement_rows[2] or 0), 2),
        "placement_rate": round((accepted / students * 100) if students else 0, 1),
    }

    # --- Upcoming calendar events (next 30 days) ---
    today = date.today().isoformat()
    max_d = (date.today() + timedelta(days=30)).isoformat()
    events = db.execute(
        select(CalendarEvent)
        .where(
            CalendarEvent.organization_id == org_id,
            CalendarEvent.event_date >= today,
            CalendarEvent.event_date <= max_d,
        )
        .order_by(CalendarEvent.event_date.asc())
        .limit(8)
    ).scalars().all()
    calendar_events = [
        {
            "id": e.id,
            "title": e.title,
            "event_date": e.event_date,
            "kind": e.kind,
            "color": e.color,
        }
        for e in events
    ]

    # --- Recent activity (audit logs, last 12) ---
    audit_rows = db.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc())
        .limit(12)
    ).all()
    activity = []
    for log, u in audit_rows:
        activity.append(
            {
                "id": log.id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "user_name": (f"{u.first_name} {u.last_name}".strip() if u else "System"),
                "created_at": (log.created_at.isoformat() if log.created_at else None),
            }
        )

    # --- Notifications preview for current user (unread first, latest 6) ---
    notif_rows = db.execute(
        select(Notification)
        .where(Notification.organization_id == org_id, Notification.user_id == user.id)
        .order_by(Notification.is_read.asc(), Notification.created_at.desc())
        .limit(6)
    ).scalars().all()
    notifications = [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "kind": n.kind,
            "is_read": n.is_read,
            "link": n.link,
            "created_at": (n.created_at.isoformat() if n.created_at else None),
        }
        for n in notif_rows
    ]
    unread_total = db.execute(
        select(func.count(Notification.id)).where(
            Notification.organization_id == org_id,
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
        )
    ).scalar() or 0

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
        "fees": fee_summary,
        "placements": placement_stats,
        "calendar": calendar_events,
        "activity": activity,
        "notifications": {"unread": unread_total, "recent": notifications},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

