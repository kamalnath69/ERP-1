"""Joined, permission-ready College workspace reads."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Client, CollegeAssessment, CollegeAssessmentScore, CollegeAttendanceRecord,
    CollegeAttendanceSession, CollegeCohort, CollegeCourse, CollegeCourseOffering,
    CollegeDepartment, CollegeFeePlan, CollegeProgram, CollegeStudentFee,
    CollegeStudentProfile, CollegeTerm, Employee, Organization, SaleInvoice, User,
)
from app.services.business_access import ensure_location, organization_for
from app.services.college_placement import fee_clearance_by_student
from app.services.rbac import get_user_permissions


def require_college(db: Session, user: User) -> Organization:
    organization = organization_for(db, user)
    if organization.industry.value != "college":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "College workspace is unavailable")
    return organization


def tenant_row(db: Session, model, row_id: str, user: User, label: str | None = None):
    row = db.execute(select(model).where(
        model.id == row_id,
        model.organization_id == user.organization_id,
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label or model.__name__} not found")
    return row


def serialize(row) -> dict:
    data = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, Decimal):
            value = float(value)
        elif hasattr(value, "value"):
            value = value.value
        data[column.name] = value
    return data


def college_workspace(db: Session, user: User, location_id: str | None, days: int = 30) -> dict:
    require_college(db, user)
    if location_id:
        ensure_location(db, user, location_id)
    permissions = get_user_permissions(db, user)
    can_view_students = bool({"college.students.view", "college.students.manage"} & permissions)
    can_work_with_students = can_view_students or bool({
        "college.attendance.mark", "college.assessments.manage", "college.fees.manage",
    } & permissions)
    can_view_attendance = bool({"college.attendance.view", "college.attendance.mark"} & permissions)
    can_view_assessments = bool({"college.assessments.view", "college.assessments.manage"} & permissions)
    can_view_fees = bool({"college.fees.view", "college.fees.manage"} & permissions)
    can_manage_academics = "college.academics.manage" in permissions
    cutoff = date.today() - timedelta(days=max(1, min(days, 90)) - 1)
    current_term = db.execute(select(CollegeTerm).where(
        CollegeTerm.organization_id == user.organization_id,
        CollegeTerm.is_current.is_(True),
    ).order_by(CollegeTerm.starts_on.desc())).scalars().first()

    department_stmt = select(CollegeDepartment).where(CollegeDepartment.organization_id == user.organization_id)
    if location_id:
        department_stmt = department_stmt.where(or_(
            CollegeDepartment.location_id == location_id,
            CollegeDepartment.location_id.is_(None),
        ))
    departments = list(db.execute(department_stmt.order_by(CollegeDepartment.name)).scalars())
    department_ids = {row.id for row in departments}

    programs = list(db.execute(select(CollegeProgram).where(
        CollegeProgram.organization_id == user.organization_id,
        CollegeProgram.department_id.in_(department_ids) if department_ids else CollegeProgram.department_id.in_([]),
    ).order_by(CollegeProgram.name)).scalars())
    program_ids = {row.id for row in programs}
    cohorts = list(db.execute(select(CollegeCohort).where(
        CollegeCohort.organization_id == user.organization_id,
        CollegeCohort.program_id.in_(program_ids) if program_ids else CollegeCohort.program_id.in_([]),
    ).order_by(CollegeCohort.admission_year.desc(), CollegeCohort.name)).scalars())
    cohort_ids = {row.id for row in cohorts}
    courses = list(db.execute(select(CollegeCourse).where(
        CollegeCourse.organization_id == user.organization_id,
        CollegeCourse.department_id.in_(department_ids) if department_ids else CollegeCourse.department_id.in_([]),
    ).order_by(CollegeCourse.code)).scalars())
    course_ids = {row.id for row in courses}
    terms = list(db.execute(select(CollegeTerm).where(
        CollegeTerm.organization_id == user.organization_id,
    ).order_by(CollegeTerm.starts_on.desc()).limit(20)).scalars())

    offering_stmt = select(CollegeCourseOffering).where(
        CollegeCourseOffering.organization_id == user.organization_id,
        CollegeCourseOffering.course_id.in_(course_ids) if course_ids else CollegeCourseOffering.course_id.in_([]),
        CollegeCourseOffering.cohort_id.in_(cohort_ids) if cohort_ids else CollegeCourseOffering.cohort_id.in_([]),
    )
    if current_term:
        offering_stmt = offering_stmt.where(CollegeCourseOffering.term_id == current_term.id)
    offerings = list(db.execute(offering_stmt.order_by(CollegeCourseOffering.created_at.desc()).limit(250)).scalars())
    offering_ids = {row.id for row in offerings}

    student_stmt = (
        select(CollegeStudentProfile, Client)
        .join(Client, Client.id == CollegeStudentProfile.client_id)
        .where(
            CollegeStudentProfile.organization_id == user.organization_id,
            CollegeStudentProfile.cohort_id.in_(cohort_ids) if cohort_ids else CollegeStudentProfile.cohort_id.in_([]),
        )
    )
    if location_id:
        student_stmt = student_stmt.where(Client.home_location_id == location_id)
    student_pairs = db.execute(student_stmt.order_by(Client.first_name, Client.last_name).limit(250)).all() if can_work_with_students else []
    student_count_stmt = select(
        CollegeStudentProfile.program_id,
        CollegeStudentProfile.cohort_id,
        func.count(CollegeStudentProfile.id),
    ).join(Client, Client.id == CollegeStudentProfile.client_id).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.cohort_id.in_(cohort_ids) if cohort_ids else CollegeStudentProfile.cohort_id.in_([]),
    )
    if location_id:
        student_count_stmt = student_count_stmt.where(Client.home_location_id == location_id)
    student_counts = db.execute(student_count_stmt.group_by(
        CollegeStudentProfile.program_id,
        CollegeStudentProfile.cohort_id,
    )).all()
    program_student_counts: dict[str, int] = defaultdict(int)
    cohort_student_counts: dict[str, int] = {}
    for program_id, cohort_id, count in student_counts:
        program_student_counts[program_id] += int(count)
        cohort_student_counts[cohort_id] = int(count)

    sessions = list(db.execute(select(CollegeAttendanceSession).where(
        CollegeAttendanceSession.organization_id == user.organization_id,
        CollegeAttendanceSession.offering_id.in_(offering_ids) if offering_ids else CollegeAttendanceSession.offering_id.in_([]),
    ).order_by(CollegeAttendanceSession.held_on.desc(), CollegeAttendanceSession.starts_at.desc()).limit(100)).scalars()) if can_view_attendance else []
    session_ids = {row.id for row in sessions}
    attendance_counts = {
        session_id: {"total": int(total), "present": int(present or 0)}
        for session_id, total, present in db.execute(select(
            CollegeAttendanceRecord.session_id,
            func.count(CollegeAttendanceRecord.id),
            func.sum(case((CollegeAttendanceRecord.status.in_(["present", "late"]), 1), else_=0)),
        ).where(
            CollegeAttendanceRecord.organization_id == user.organization_id,
            CollegeAttendanceRecord.session_id.in_(session_ids) if session_ids else CollegeAttendanceRecord.session_id.in_([]),
        ).group_by(CollegeAttendanceRecord.session_id))
    }

    assessments = list(db.execute(select(CollegeAssessment).where(
        CollegeAssessment.organization_id == user.organization_id,
        CollegeAssessment.offering_id.in_(offering_ids) if offering_ids else CollegeAssessment.offering_id.in_([]),
    ).order_by(CollegeAssessment.due_on.asc().nullslast(), CollegeAssessment.created_at.desc()).limit(100)).scalars()) if can_view_assessments else []
    assessment_ids = {row.id for row in assessments}
    score_counts = dict(db.execute(select(
        CollegeAssessmentScore.assessment_id,
        func.count(CollegeAssessmentScore.id),
    ).where(
        CollegeAssessmentScore.assessment_id.in_(assessment_ids) if assessment_ids else CollegeAssessmentScore.assessment_id.in_([]),
    ).group_by(CollegeAssessmentScore.assessment_id)).all())

    fee_plan_stmt = select(CollegeFeePlan).where(
        CollegeFeePlan.organization_id == user.organization_id,
    )
    if location_id:
        fee_plan_stmt = fee_plan_stmt.where(
            or_(CollegeFeePlan.program_id.is_(None), CollegeFeePlan.program_id.in_(program_ids)),
            or_(CollegeFeePlan.cohort_id.is_(None), CollegeFeePlan.cohort_id.in_(cohort_ids)),
        )
    fee_plans = list(db.execute(
        fee_plan_stmt.order_by(CollegeFeePlan.due_on.desc().nullslast()).limit(100),
    ).scalars()) if can_view_fees else []
    student_fee_stmt = select(CollegeStudentFee, SaleInvoice, Client).join(
        CollegeStudentProfile, CollegeStudentProfile.id == CollegeStudentFee.student_profile_id,
    ).join(
        Client, Client.id == CollegeStudentProfile.client_id,
    ).outerjoin(
        SaleInvoice, SaleInvoice.id == CollegeStudentFee.invoice_id,
    ).where(
        CollegeStudentFee.organization_id == user.organization_id,
        CollegeStudentProfile.cohort_id.in_(cohort_ids) if cohort_ids else CollegeStudentProfile.cohort_id.in_([]),
    )
    if location_id:
        student_fee_stmt = student_fee_stmt.where(Client.home_location_id == location_id)
    student_fees = db.execute(
        student_fee_stmt.order_by(CollegeStudentFee.created_at.desc()).limit(100),
    ).all() if can_view_fees else []

    employees = list(db.execute(select(Employee).where(
        Employee.organization_id == user.organization_id,
        Employee.status == "active",
    ).order_by(Employee.first_name, Employee.last_name).limit(250)).scalars()) if can_manage_academics else []

    program_by_id = {row.id: row for row in programs}
    department_by_id = {row.id: row for row in departments}
    cohort_by_id = {row.id: row for row in cohorts}
    course_by_id = {row.id: row for row in courses}
    term_by_id = {row.id: row for row in terms}
    employee_by_id = {row.id: row for row in employees}
    offering_by_id = {row.id: row for row in offerings}
    fee_plan_by_id = {row.id: row for row in fee_plans}
    fee_clearance = fee_clearance_by_student(
        db,
        user.organization_id,
        [profile.id for profile, _client in student_pairs],
    ) if can_view_fees else {}

    attendance_total, attendance_present = (0, 0)
    if can_view_attendance:
        attendance_total, attendance_present = db.execute(select(
            func.count(CollegeAttendanceRecord.id),
            func.sum(case((CollegeAttendanceRecord.status.in_(["present", "late"]), 1), else_=0)),
        ).join(
            CollegeAttendanceSession, CollegeAttendanceSession.id == CollegeAttendanceRecord.session_id,
        ).where(
            CollegeAttendanceRecord.organization_id == user.organization_id,
            CollegeAttendanceSession.held_on >= cutoff,
            CollegeAttendanceSession.offering_id.in_(offering_ids) if offering_ids else CollegeAttendanceSession.offering_id.in_([]),
        )).one()
    outstanding = None
    if can_view_fees:
        outstanding_stmt = select(func.coalesce(func.sum(SaleInvoice.total_paise - SaleInvoice.paid_paise), 0)).select_from(
            CollegeStudentFee,
        ).join(
            SaleInvoice, SaleInvoice.id == CollegeStudentFee.invoice_id,
        ).join(
            CollegeStudentProfile, CollegeStudentProfile.id == CollegeStudentFee.student_profile_id,
        ).join(
            Client, Client.id == CollegeStudentProfile.client_id,
        ).where(
            CollegeStudentFee.organization_id == user.organization_id,
            CollegeStudentProfile.cohort_id.in_(cohort_ids) if cohort_ids else CollegeStudentProfile.cohort_id.in_([]),
            SaleInvoice.status.in_(["issued", "partially_paid", "overdue"]),
        )
        if location_id:
            outstanding_stmt = outstanding_stmt.where(Client.home_location_id == location_id)
        outstanding = int(db.scalar(outstanding_stmt) or 0)
    active_students_stmt = select(func.count(CollegeStudentProfile.id)).join(
        Client, Client.id == CollegeStudentProfile.client_id,
    ).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.status == "active",
        CollegeStudentProfile.cohort_id.in_(cohort_ids) if cohort_ids else CollegeStudentProfile.cohort_id.in_([]),
    )
    if location_id:
        active_students_stmt = active_students_stmt.where(Client.home_location_id == location_id)
    active_students = db.scalar(active_students_stmt) or 0
    faculty_assigned = db.scalar(select(func.count(func.distinct(CollegeCourseOffering.faculty_employee_id))).where(
        CollegeCourseOffering.organization_id == user.organization_id,
        CollegeCourseOffering.id.in_(offering_ids) if offering_ids else CollegeCourseOffering.id.in_([]),
        CollegeCourseOffering.faculty_employee_id.is_not(None),
    )) or 0
    due_assessments = 0
    if can_view_assessments:
        due_assessments = db.scalar(select(func.count(CollegeAssessment.id)).where(
            CollegeAssessment.organization_id == user.organization_id,
            CollegeAssessment.status.in_(["draft", "published"]),
            CollegeAssessment.due_on.between(date.today(), date.today() + timedelta(days=14)),
            CollegeAssessment.offering_id.in_(offering_ids) if offering_ids else CollegeAssessment.offering_id.in_([]),
        )) or 0

    def offering_payload(row):
        course = course_by_id.get(row.course_id)
        cohort = cohort_by_id.get(row.cohort_id)
        faculty = employee_by_id.get(row.faculty_employee_id)
        return {
            **serialize(row),
            "course_name": course.name if course else None,
            "course_code": course.code if course else None,
            "cohort_name": cohort.name if cohort else None,
            "term_name": term_by_id.get(row.term_id).name if term_by_id.get(row.term_id) else None,
            "faculty_name": f"{faculty.first_name} {faculty.last_name}".strip() if faculty else None,
        }

    return {
        "summary": {
            "active_students": int(active_students),
            "active_programs": sum(1 for row in programs if row.is_active),
            "faculty_assigned": int(faculty_assigned),
            "attendance_percent": round(int(attendance_present or 0) * 100 / int(attendance_total or 1), 1) if attendance_total else None,
            "classes_today": sum(1 for row in sessions if row.held_on == date.today()),
            "assessments_due": int(due_assessments),
            "fees_outstanding_paise": outstanding,
        },
        "current_term": serialize(current_term) if current_term else None,
        "departments": [{**serialize(row), "program_count": sum(1 for item in programs if item.department_id == row.id)} for row in departments],
        "programs": [{**serialize(row), "department_name": department_by_id.get(row.department_id).name if department_by_id.get(row.department_id) else None, "student_count": program_student_counts.get(row.id, 0)} for row in programs],
        "terms": [serialize(row) for row in terms],
        "cohorts": [{**serialize(row), "program_name": program_by_id.get(row.program_id).name if program_by_id.get(row.program_id) else None, "student_count": cohort_student_counts.get(row.id, 0)} for row in cohorts],
        "courses": [{**serialize(row), "department_name": department_by_id.get(row.department_id).name if department_by_id.get(row.department_id) else None} for row in courses],
        "offerings": [offering_payload(row) for row in offerings],
        "students": [{
            **serialize(profile), "client_id": client.id,
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "phone": client.phone, "email": client.email,
            "program_name": program_by_id.get(profile.program_id).name if program_by_id.get(profile.program_id) else None,
            "cohort_name": cohort_by_id.get(profile.cohort_id).name if cohort_by_id.get(profile.cohort_id) else None,
            "fee_clearance_status": fee_clearance.get(profile.id, {}).get("status"),
            "fee_outstanding_paise": fee_clearance.get(profile.id, {}).get("outstanding_paise"),
        } for profile, client in student_pairs] if can_work_with_students else [],
        "attendance_sessions": [{
            **serialize(row),
            "offering": offering_payload(offering_by_id[row.offering_id]) if row.offering_id in offering_by_id else None,
            "record_count": attendance_counts.get(row.id, {}).get("total", 0),
            "present_count": attendance_counts.get(row.id, {}).get("present", 0),
        } for row in sessions],
        "assessments": [{
            **serialize(row),
            "offering": offering_payload(offering_by_id[row.offering_id]) if row.offering_id in offering_by_id else None,
            "score_count": int(score_counts.get(row.id, 0)),
        } for row in assessments],
        "fee_plans": [{
            **serialize(row),
            "program_name": program_by_id.get(row.program_id).name if row.program_id and program_by_id.get(row.program_id) else None,
            "cohort_name": cohort_by_id.get(row.cohort_id).name if row.cohort_id and cohort_by_id.get(row.cohort_id) else None,
        } for row in fee_plans],
        "student_fees": [{
            **serialize(fee),
            "student_name": f"{client.first_name} {client.last_name}".strip(),
            "fee_plan_name": fee_plan_by_id.get(fee.fee_plan_id).name if fee_plan_by_id.get(fee.fee_plan_id) else None,
            "invoice_number": invoice.invoice_number if invoice else None,
            "invoice_status": invoice.status if invoice else None,
            "paid_paise": int(invoice.paid_paise) if invoice else 0,
            "outstanding_paise": max(0, int(invoice.total_paise) - int(invoice.paid_paise)) if invoice else max(0, int(fee.amount_paise) - int(fee.concession_paise)),
        } for fee, invoice, client in student_fees],
        "employees": [{"id": row.id, "display_name": f"{row.first_name} {row.last_name}".strip(), "designation": row.designation} for row in employees],
    }
