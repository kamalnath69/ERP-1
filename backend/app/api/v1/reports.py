"""Report generation: PDF (ReportLab) + Excel (openpyxl)."""
from datetime import date, timedelta
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    Department,
    Exam,
    Mark,
    Section,
    Student,
    Subject,
    User,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _status_key(value) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _pdf_response(title: str, headers: list[str], rows: list[list[str]], summary: dict | None = None) -> StreamingResponse:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"<b>{title}</b>", styles["Title"]), Spacer(1, 12)]
    if summary:
        for k, v in summary.items():
            story.append(Paragraph(f"<b>{k}</b>: {v}", styles["Normal"]))
        story.append(Spacer(1, 12))
    data = [headers] + rows
    tbl = Table(data, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(tbl)
    doc.build(story)
    buf.seek(0)
    fname = title.lower().replace(" ", "-") + ".pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


def _xlsx_response(title: str, headers: list[str], rows: list[list], summary: dict | None = None) -> StreamingResponse:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    r = 1
    if summary:
        for k, v in summary.items():
            ws.cell(row=r, column=1, value=k).font = Font(bold=True)
            ws.cell(row=r, column=2, value=str(v))
            r += 1
        r += 1
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    r += 1
    for row in rows:
        for c, v in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=v)
        r += 1
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = title.lower().replace(" ", "-") + ".xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ------------------------------------------------------------ students report
def _students_data(db: Session, user: User) -> tuple[list[str], list[list]]:
    stmt = (
        select(Student, Department.name.label("dept"), Section.name.label("sec"))
        .outerjoin(Department, Student.department_id == Department.id)
        .outerjoin(Section, Student.section_id == Section.id)
        .where(Student.organization_id == user.organization_id)
        .order_by(Student.admission_number)
    )
    rows = db.execute(stmt).all()
    headers = ["Admission", "Name", "Email", "Phone", "Section", "Department"]
    out = []
    for s, dept, sec in rows:
        out.append([s.admission_number, f"{s.first_name} {s.last_name}", s.email or "", s.phone or "", sec or "", dept or ""])
    return headers, out


@router.get("/students.pdf")
def students_pdf(user: User = Depends(require_permissions("reports.export")), db: Session = Depends(get_db)):
    h, r = _students_data(db, user)
    return _pdf_response("Students Report", h, r, {"Total students": len(r)})


@router.get("/students.xlsx")
def students_xlsx(user: User = Depends(require_permissions("reports.export")), db: Session = Depends(get_db)):
    h, r = _students_data(db, user)
    return _xlsx_response("Students Report", h, r, {"Total students": len(r)})


# ------------------------------------------------------------ attendance report
def _attendance_data(db: Session, user: User, section_id: str | None, days: int) -> tuple[list[str], list[list], dict]:
    cutoff = date.today() - timedelta(days=days)
    q = (
        select(
            Student.admission_number, Student.first_name, Student.last_name,
            AttendanceRecord.status, func.count(AttendanceRecord.id),
        )
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .join(Student, AttendanceRecord.student_id == Student.id)
        .where(
            AttendanceRecord.organization_id == user.organization_id,
            AttendanceSession.session_date >= cutoff,
        )
        .group_by(Student.admission_number, Student.first_name, Student.last_name, AttendanceRecord.status)
    )
    if section_id:
        q = q.where(AttendanceSession.section_id == section_id)
    per_student: dict = {}
    for adm, fn, ln, st, c in db.execute(q).all():
        key = (adm, f"{fn} {ln}")
        per_student.setdefault(key, {"present": 0, "absent": 0, "late": 0, "excused": 0})
        per_student[key][_status_key(st)] = c
    headers = ["Admission", "Name", "Present", "Absent", "Late", "Excused", "%"]
    rows = []
    total_p, total_all = 0, 0
    for (adm, name), c in per_student.items():
        t = sum(c.values())
        p = c["present"] + c["late"]
        pct = round(p / t * 100, 2) if t else 0
        total_p += p
        total_all += t
        rows.append([adm, name, c["present"], c["absent"], c["late"], c["excused"], f"{pct}%"])
    overall = round(total_p / total_all * 100, 2) if total_all else 0
    return headers, rows, {"Days": days, "Overall": f"{overall}%"}


@router.get("/attendance.pdf")
def attendance_pdf(section_id: str | None = None, days: int = 30, user: User = Depends(require_permissions("reports.export")), db: Session = Depends(get_db)):
    h, r, s = _attendance_data(db, user, section_id, days)
    return _pdf_response("Attendance Report", h, r, s)


@router.get("/attendance.xlsx")
def attendance_xlsx(section_id: str | None = None, days: int = 30, user: User = Depends(require_permissions("reports.export")), db: Session = Depends(get_db)):
    h, r, s = _attendance_data(db, user, section_id, days)
    return _xlsx_response("Attendance Report", h, r, s)


# ------------------------------------------------------------ marks report
def _marks_data(db: Session, user: User, exam_id: str) -> tuple[list[str], list[list], dict]:
    exam = db.get(Exam, exam_id)
    if not exam or exam.organization_id != user.organization_id:
        raise HTTPException(404, "Exam not found")
    subj = db.get(Subject, exam.subject_id)
    stmt = (
        select(Student.admission_number, Student.first_name, Student.last_name, Mark.obtained, Mark.grade)
        .join(Mark, Mark.student_id == Student.id)
        .where(Mark.exam_id == exam_id, Mark.organization_id == user.organization_id)
        .order_by(Student.admission_number)
    )
    rows = []
    total = 0.0
    for adm, fn, ln, obt, grade in db.execute(stmt).all():
        rows.append([adm, f"{fn} {ln}", obt, grade or ""])
        total += obt
    headers = ["Admission", "Name", "Obtained", "Grade"]
    avg = round(total / len(rows), 2) if rows else 0
    summary = {"Exam": exam.name, "Subject": subj.name if subj else "", "Max marks": exam.max_marks, "Average": avg}
    return headers, rows, summary


@router.get("/marks.pdf")
def marks_pdf(exam_id: str, user: User = Depends(require_permissions("reports.export")), db: Session = Depends(get_db)):
    h, r, s = _marks_data(db, user, exam_id)
    return _pdf_response("Marks Report", h, r, s)


@router.get("/marks.xlsx")
def marks_xlsx(exam_id: str, user: User = Depends(require_permissions("reports.export")), db: Session = Depends(get_db)):
    h, r, s = _marks_data(db, user, exam_id)
    return _xlsx_response("Marks Report", h, r, s)
