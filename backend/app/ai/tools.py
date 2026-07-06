"""AI tools that the LLM can invoke. Each tool receives (db, user, args) and returns a JSON-serializable dict.

Authorization always happens BEFORE tool execution - the caller supplies the User which
carries organization_id (tenant scope) and permission set.
"""
from datetime import date, timedelta
from typing import Any, Callable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

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


# ---------------------------------------------------------------- tool schemas
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_students",
            "description": "Fuzzy search students by name, admission number, roll number, or email. Returns up to 10 matches. Use this first when the user references a student by name.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Name / admission / roll / email keyword"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "student_profile",
            "description": "Fetch full profile of a student by student_id.",
            "parameters": {"type": "object", "properties": {"student_id": {"type": "string"}}, "required": ["student_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "student_attendance",
            "description": "Attendance summary and recent sessions for a student. Optional date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string"},
                    "days": {"type": "integer", "description": "Lookback window (default 30)"},
                },
                "required": ["student_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "student_marks",
            "description": "All published marks for a student, grouped by subject.",
            "parameters": {"type": "object", "properties": {"student_id": {"type": "string"}}, "required": ["student_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "department_summary",
            "description": "Aggregate counts (students, faculty, subjects) for one department or all departments.",
            "parameters": {"type": "object", "properties": {"department_id": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attendance_report",
            "description": "Aggregate attendance % for a section over the last N days.",
            "parameters": {
                "type": "object",
                "properties": {"section_id": {"type": "string"}, "days": {"type": "integer"}},
                "required": ["section_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "faculty_summary",
            "description": "List faculty with department and workload.",
            "parameters": {"type": "object", "properties": {"department_id": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "risk_prediction",
            "description": "Identify students at risk (low attendance <75% or failing marks) in a section or department.",
            "parameters": {
                "type": "object",
                "properties": {"section_id": {"type": "string"}, "department_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analytics_dashboard",
            "description": "Organization-wide KPIs: total students, faculty, avg attendance, avg marks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ---------------------------------------------------------------- implementations
def _tenant_filter(model, user: User):
    return model.organization_id == user.organization_id


def tool_search_students(db: Session, user: User, query: str) -> dict:
    like = f"%{query.lower()}%"
    stmt = (
        select(Student)
        .where(
            Student.organization_id == user.organization_id,
            or_(
                func.lower(Student.first_name).like(like),
                func.lower(Student.last_name).like(like),
                func.lower(func.concat(Student.first_name, " ", Student.last_name)).like(like),
                func.lower(Student.admission_number).like(like),
                func.lower(Student.roll_number).like(like),
                func.lower(Student.email).like(like),
            ),
        )
        .limit(10)
    )
    rows = db.execute(stmt).scalars().all()
    matches = [
        {
            "id": s.id,
            "name": f"{s.first_name} {s.last_name}",
            "admission_number": s.admission_number,
            "roll_number": s.roll_number,
            "email": s.email,
            "section_id": s.section_id,
        }
        for s in rows
    ]
    return {"count": len(matches), "matches": matches, "ambiguous": len(matches) > 1}


def tool_student_profile(db: Session, user: User, student_id: str) -> dict:
    s = db.execute(
        select(Student).where(Student.id == student_id, _tenant_filter(Student, user))
    ).scalar_one_or_none()
    if not s:
        return {"error": "Student not found"}
    return {
        "id": s.id,
        "name": f"{s.first_name} {s.last_name}",
        "admission_number": s.admission_number,
        "roll_number": s.roll_number,
        "email": s.email,
        "phone": s.phone,
        "section_id": s.section_id,
        "department_id": s.department_id,
        "gender": s.gender,
        "date_of_birth": s.date_of_birth,
        "is_active": s.is_active,
    }


def tool_student_attendance(db: Session, user: User, student_id: str, days: int = 30) -> dict:
    cutoff = date.today() - timedelta(days=days)
    stmt = (
        select(AttendanceRecord.status, func.count(AttendanceRecord.id))
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.organization_id == user.organization_id,
            AttendanceSession.session_date >= cutoff,
        )
        .group_by(AttendanceRecord.status)
    )
    counts = {str(row[0].value if hasattr(row[0], "value") else row[0]): row[1] for row in db.execute(stmt).all()}
    total = sum(counts.values())
    present = counts.get("present", 0) + counts.get("late", 0)
    pct = round((present / total) * 100, 2) if total else 0.0
    return {"student_id": student_id, "days": days, "counts": counts, "total_sessions": total, "attendance_percent": pct}


def tool_student_marks(db: Session, user: User, student_id: str) -> dict:
    stmt = (
        select(Mark, Exam, Subject)
        .join(Exam, Mark.exam_id == Exam.id)
        .join(Subject, Exam.subject_id == Subject.id)
        .where(
            Mark.student_id == student_id,
            Mark.organization_id == user.organization_id,
            Exam.is_published == True,  # noqa: E712
        )
    )
    rows = db.execute(stmt).all()
    items = []
    for m, e, sub in rows:
        items.append(
            {
                "subject": sub.name,
                "subject_code": sub.code,
                "exam": e.name,
                "exam_type": e.exam_type,
                "obtained": m.obtained,
                "max_marks": e.max_marks,
                "percent": round((m.obtained / e.max_marks) * 100, 2) if e.max_marks else 0,
                "grade": m.grade,
            }
        )
    avg = round(sum(i["percent"] for i in items) / len(items), 2) if items else 0.0
    return {"count": len(items), "average_percent": avg, "marks": items}


def tool_department_summary(db: Session, user: User, department_id: str | None = None) -> dict:
    q_students = select(Department.id, Department.name, func.count(Student.id)).outerjoin(
        Student, Student.department_id == Department.id
    ).where(Department.organization_id == user.organization_id).group_by(Department.id, Department.name)
    if department_id:
        q_students = q_students.where(Department.id == department_id)
    depts = [{"id": r[0], "name": r[1], "students": r[2]} for r in db.execute(q_students).all()]
    return {"departments": depts}


def tool_attendance_report(db: Session, user: User, section_id: str, days: int = 30) -> dict:
    cutoff = date.today() - timedelta(days=days)
    stmt = (
        select(AttendanceRecord.status, func.count(AttendanceRecord.id))
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(
            AttendanceSession.section_id == section_id,
            AttendanceRecord.organization_id == user.organization_id,
            AttendanceSession.session_date >= cutoff,
        )
        .group_by(AttendanceRecord.status)
    )
    counts = {str(row[0].value if hasattr(row[0], "value") else row[0]): row[1] for row in db.execute(stmt).all()}
    total = sum(counts.values())
    present = counts.get("present", 0) + counts.get("late", 0)
    pct = round((present / total) * 100, 2) if total else 0.0
    return {"section_id": section_id, "days": days, "counts": counts, "attendance_percent": pct}


def tool_faculty_summary(db: Session, user: User, department_id: str | None = None) -> dict:
    stmt = (
        select(Faculty, User)
        .join(User, Faculty.user_id == User.id)
        .where(Faculty.organization_id == user.organization_id)
    )
    if department_id:
        stmt = stmt.where(Faculty.department_id == department_id)
    rows = db.execute(stmt).all()
    return {
        "count": len(rows),
        "faculty": [
            {
                "id": f.id,
                "name": f"{u.first_name} {u.last_name}",
                "employee_number": f.employee_number,
                "designation": f.designation,
                "department_id": f.department_id,
            }
            for f, u in rows
        ],
    }


def tool_risk_prediction(db: Session, user: User, section_id: str | None = None, department_id: str | None = None) -> dict:
    """Simple heuristic: attendance <75% OR any published mark below pass_marks."""
    q = select(Student).where(Student.organization_id == user.organization_id)
    if section_id:
        q = q.where(Student.section_id == section_id)
    if department_id:
        q = q.where(Student.department_id == department_id)
    students = db.execute(q).scalars().all()

    at_risk = []
    for s in students:
        # attendance
        att = tool_student_attendance(db, user, s.id, days=60)
        # marks
        marks = tool_student_marks(db, user, s.id)
        reasons = []
        if att["total_sessions"] > 0 and att["attendance_percent"] < 75:
            reasons.append(f"Attendance {att['attendance_percent']}%")
        for m in marks["marks"]:
            if m["percent"] < 40:
                reasons.append(f"Failed {m['subject_code']} ({m['percent']}%)")
                break
        if reasons:
            at_risk.append(
                {
                    "student_id": s.id,
                    "name": f"{s.first_name} {s.last_name}",
                    "admission_number": s.admission_number,
                    "reasons": reasons,
                }
            )
    return {"count": len(at_risk), "at_risk": at_risk[:25]}


def tool_analytics_dashboard(db: Session, user: User) -> dict:
    org_id = user.organization_id
    students = db.execute(select(func.count(Student.id)).where(Student.organization_id == org_id)).scalar()
    faculty = db.execute(select(func.count(Faculty.id)).where(Faculty.organization_id == org_id)).scalar()
    subjects = db.execute(select(func.count(Subject.id)).where(Subject.organization_id == org_id)).scalar()
    sections = db.execute(select(func.count(Section.id)).where(Section.organization_id == org_id)).scalar()

    # Avg attendance last 30 days
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
    att_counts = {str(r[0].value if hasattr(r[0], "value") else r[0]): r[1] for r in att_rows}
    att_total = sum(att_counts.values())
    att_present = att_counts.get("present", 0) + att_counts.get("late", 0)
    att_pct = round((att_present / att_total) * 100, 2) if att_total else 0.0

    return {
        "students": students,
        "faculty": faculty,
        "subjects": subjects,
        "sections": sections,
        "avg_attendance_30d": att_pct,
    }


TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "search_students": tool_search_students,
    "student_profile": tool_student_profile,
    "student_attendance": tool_student_attendance,
    "student_marks": tool_student_marks,
    "department_summary": tool_department_summary,
    "attendance_report": tool_attendance_report,
    "faculty_summary": tool_faculty_summary,
    "risk_prediction": tool_risk_prediction,
    "analytics_dashboard": tool_analytics_dashboard,
}


def execute_tool(name: str, db: Session, user: User, arguments: dict) -> dict:
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(db, user, **(arguments or {}))
    except TypeError as exc:
        return {"error": f"Invalid arguments for {name}: {exc}"}
    except Exception as exc:  # keep AI robust
        return {"error": f"Tool {name} failed: {exc}"}
