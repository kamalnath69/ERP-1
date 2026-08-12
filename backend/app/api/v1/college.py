"""College workspace, academic structure, attendance, assessment, and fee APIs."""
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import EmailStr, Field, model_validator
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.validation import RequestModel
from app.core.deps import require_entitlements, require_permissions
from app.models import (
    Client, CollegeAssessment, CollegeAssessmentScore, CollegeAttendanceRecord,
    CollegeAttendanceSession, CollegeCohort, CollegeCourse, CollegeCourseOffering,
    CollegeAttendanceSnapshot, CollegeDepartment, CollegeFeePlan, CollegeProgram,
    CollegeStudentFee, CollegeStudentProfile, CollegeTerm, CollegeTermResult,
    Employee, Location, SaleInvoice, SaleLine, User,
)
from app.services.audit import log_action
from app.services.business_access import enforce_plan_limit, ensure_location, organization_for
from app.services.college import college_workspace, require_college, serialize, tenant_row
from app.services.college_access import resolve_college_access, validate_college_filters
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_response, page_size


router = APIRouter(
    prefix="/college",
    tags=["college"],
    dependencies=[Depends(require_entitlements("module.college"))],
)


class DepartmentBody(RequestModel):
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=2, max_length=30)
    location_id: str | None = None
    hod_employee_id: str | None = None
    description: str | None = Field(default=None, max_length=1000)


class ProgramBody(RequestModel):
    department_id: str
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=40)
    degree_type: Literal["undergraduate", "postgraduate", "diploma", "certificate"] = "undergraduate"
    duration_semesters: int = Field(default=6, ge=1, le=16)


class TermBody(RequestModel):
    name: str = Field(min_length=2, max_length=80)
    academic_year: str = Field(min_length=4, max_length=20)
    term_number: int = Field(ge=1, le=16)
    starts_on: date
    ends_on: date
    status: Literal["planned", "active", "closed"] = "planned"
    is_current: bool = False

    @model_validator(mode="after")
    def valid_dates(self):
        if self.ends_on <= self.starts_on:
            raise ValueError("Term end date must be after its start date")
        return self


class CohortBody(RequestModel):
    program_id: str
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=50)
    admission_year: int = Field(ge=2000, le=2200)
    current_semester: int = Field(default=1, ge=1, le=16)
    section: str | None = Field(default=None, max_length=20)
    advisor_employee_id: str | None = None


class CourseBody(RequestModel):
    department_id: str
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=40)
    credits: int = Field(default=3, ge=0, le=30)
    course_type: Literal["core", "elective", "lab", "project", "audit"] = "core"


class ScheduleSlot(RequestModel):
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    room: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def valid_time(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Class end time must be after its start time")
        return self


class OfferingBody(RequestModel):
    term_id: str
    course_id: str
    cohort_id: str
    faculty_employee_id: str | None = None
    room: str | None = Field(default=None, max_length=60)
    weekly_schedule: list[ScheduleSlot] = Field(default_factory=list, max_length=14)

    @model_validator(mode="after")
    def unique_slots(self):
        slots = {(row.weekday, row.starts_at) for row in self.weekly_schedule}
        if len(slots) != len(self.weekly_schedule):
            raise ValueError("The weekly schedule contains a duplicate start time")
        return self


class StudentBody(RequestModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=1000)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    home_location_id: str | None = None
    admission_number: str = Field(min_length=2, max_length=40)
    roll_number: str | None = Field(default=None, max_length=60)
    program_id: str
    cohort_id: str
    current_semester: int = Field(default=1, ge=1, le=16)
    admitted_on: date = Field(default_factory=date.today)
    category: str | None = Field(default=None, max_length=40)
    guardian: dict = Field(default_factory=dict)


AttendanceStatus = Literal["present", "absent", "late", "excused"]


class AttendanceRecordBody(RequestModel):
    student_profile_id: str
    status: AttendanceStatus = "present"
    note: str | None = Field(default=None, max_length=300)


class AttendanceSessionBody(RequestModel):
    offering_id: str
    held_on: date = Field(default_factory=date.today)
    starts_at: time | None = None
    ends_at: time | None = None
    topic: str | None = Field(default=None, max_length=300)
    records: list[AttendanceRecordBody] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_time(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("Session end time must be after its start time")
        if len({row.student_profile_id for row in self.records}) != len(self.records):
            raise ValueError("A student can appear only once in an attendance session")
        return self


class AttendanceRecordsBody(RequestModel):
    records: list[AttendanceRecordBody] = Field(min_length=1)


class AssessmentBody(RequestModel):
    offering_id: str
    title: str = Field(min_length=2, max_length=180)
    assessment_type: Literal["internal", "assignment", "quiz", "practical", "project", "semester"] = "internal"
    max_marks: Decimal = Field(default=Decimal("100"), gt=0, max_digits=8, decimal_places=2)
    weightage_bps: int = Field(default=0, ge=0, le=10000)
    due_on: date | None = None
    status: Literal["draft", "published", "closed"] = "draft"


class ScoreBody(RequestModel):
    student_profile_id: str
    marks_awarded: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    grade: str | None = Field(default=None, max_length=12)
    feedback: str | None = Field(default=None, max_length=2000)


class ScoresBody(RequestModel):
    scores: list[ScoreBody] = Field(min_length=1)
    publish: bool = False


class FeeLineBody(RequestModel):
    name: str = Field(min_length=2, max_length=180)
    amount_paise: int = Field(gt=0)


class FeePlanBody(RequestModel):
    name: str = Field(min_length=2, max_length=180)
    program_id: str | None = None
    cohort_id: str | None = None
    term_id: str | None = None
    amount_paise: int = Field(gt=0)
    due_on: date | None = None
    line_items: list[FeeLineBody] = Field(default_factory=list, max_length=25)

    @model_validator(mode="after")
    def valid_total(self):
        if self.line_items and sum(row.amount_paise for row in self.line_items) != self.amount_paise:
            raise ValueError("Fee line items must add up to the plan total")
        return self


class StudentFeeBody(RequestModel):
    student_profile_id: str
    fee_plan_id: str
    concession_paise: int = Field(default=0, ge=0)
    idempotency_key: str = Field(min_length=8, max_length=120)


def _normalized_code(value: str) -> str:
    return value.strip().upper().replace(" ", "-")


def _employee(db: Session, user: User, employee_id: str | None) -> Employee | None:
    if not employee_id:
        return None
    row = tenant_row(db, Employee, employee_id, user, "Faculty member")
    if row.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "Faculty member is not active")
    return row


def _commit(db: Session, row, user: User, action: str, permission: str, changes: dict | None = None):
    try:
        db.flush()
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action=action, resource_type=row.__tablename__, resource_id=row.id,
            permission=permission, changes=changes or {},
        )
        db.commit()
        db.refresh(row)
        return serialize(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A record with this code or identifier already exists") from exc


@router.get("/workspace")
def workspace(
    location_id: str | None = None,
    range_days: int = Query(default=30, alias="range", ge=7, le=90),
    user: User = Depends(require_permissions("college.view")),
    db: Session = Depends(get_db),
):
    return college_workspace(db, user, location_id, range_days)


def _name_cursor(statement, model, values: dict | None):
    if not values:
        return statement
    name = str(values.get("name") or "")
    row_id = str(values.get("id") or "")
    return statement.where(or_(
        func.lower(model.name) > name,
        and_(func.lower(model.name) == name, model.id > row_id),
    ))


def _dated_cursor(statement, model, values: dict | None, field="created_at"):
    if not values:
        return statement
    value = values.get("at")
    row_id = str(values.get("id") or "")
    if not value:
        return statement
    pivot = datetime.fromisoformat(str(value)) if "T" in str(value) else date.fromisoformat(str(value))
    column = getattr(model, field)
    return statement.where(or_(column < pivot, and_(column == pivot, model.id < row_id)))


@router.get("/references")
def college_references(
    user: User = Depends(require_permissions("college.view")),
    db: Session = Depends(get_db),
):
    """Small academic configuration lists used by forms and filters."""
    require_college(db, user)
    access = resolve_college_access(db, user)
    departments = select(CollegeDepartment).where(CollegeDepartment.organization_id == user.organization_id)
    programs = select(CollegeProgram).where(CollegeProgram.organization_id == user.organization_id)
    cohorts = select(CollegeCohort).where(CollegeCohort.organization_id == user.organization_id)
    offerings = select(CollegeCourseOffering).where(CollegeCourseOffering.organization_id == user.organization_id)
    if not access.unrestricted:
        departments = departments.where(CollegeDepartment.id.in_(access.department_ids))
        programs = programs.where(CollegeProgram.id.in_(access.program_ids))
        cohorts = cohorts.where(CollegeCohort.id.in_(access.cohort_ids))
        offerings = offerings.where(CollegeCourseOffering.cohort_id.in_(access.cohort_ids))
    return {
        "departments": [serialize(row) for row in db.execute(departments.order_by(CollegeDepartment.name)).scalars()],
        "programs": [serialize(row) for row in db.execute(programs.order_by(CollegeProgram.name)).scalars()],
        "terms": [serialize(row) for row in db.execute(select(CollegeTerm).where(
            CollegeTerm.organization_id == user.organization_id,
        ).order_by(CollegeTerm.starts_on.desc())).scalars()],
        "cohorts": [serialize(row) for row in db.execute(cohorts.order_by(CollegeCohort.name)).scalars()],
        "courses": [serialize(row) for row in db.execute(select(CollegeCourse).where(
            CollegeCourse.organization_id == user.organization_id,
        ).order_by(CollegeCourse.name)).scalars()],
        "offerings": [serialize(row) for row in db.execute(offerings.order_by(CollegeCourseOffering.created_at.desc())).scalars()],
        "employees": [{
            "id": row.id,
            "display_name": f"{row.first_name} {row.last_name}".strip(),
            "designation": row.designation,
        } for row in db.execute(select(Employee).where(
            Employee.organization_id == user.organization_id,
            Employee.status == "active",
        ).order_by(Employee.first_name, Employee.last_name)).scalars()],
    }


@router.get("/cohorts/page")
def cohort_page(
    q: str | None = None,
    program_id: str | None = None,
    active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.students.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user)
    validate_college_filters(access, program_id=program_id)
    filters = {"q": q, "program_id": program_id, "active": active}
    values = decode_cursor(cursor, scope="college.cohorts", organization_id=user.organization_id, filters=filters)
    counts = select(
        CollegeStudentProfile.cohort_id,
        func.count(CollegeStudentProfile.id).label("student_count"),
    ).where(CollegeStudentProfile.organization_id == user.organization_id).group_by(CollegeStudentProfile.cohort_id).subquery()
    statement = select(
        CollegeCohort,
        CollegeProgram.name.label("program_name"),
        func.coalesce(counts.c.student_count, 0).label("student_count"),
    ).join(CollegeProgram, CollegeProgram.id == CollegeCohort.program_id).outerjoin(
        counts, counts.c.cohort_id == CollegeCohort.id,
    ).where(CollegeCohort.organization_id == user.organization_id)
    if not access.unrestricted:
        statement = statement.where(CollegeCohort.id.in_(access.cohort_ids))
    if program_id:
        statement = statement.where(CollegeCohort.program_id == program_id)
    if active is not None:
        statement = statement.where(CollegeCohort.is_active.is_(active))
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(or_(func.lower(CollegeCohort.name).like(term), func.lower(CollegeCohort.code).like(term)))
    statement = _name_cursor(statement, CollegeCohort, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(func.lower(CollegeCohort.name), CollegeCohort.id).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{**serialize(row[0]), "program_name": row.program_name, "student_count": int(row.student_count)} for row in rows]
    next_cursor = encode_cursor(
        scope="college.cohorts", organization_id=user.organization_id, filters=filters,
        values={"name": rows[-1][0].name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.get("/academic-evidence/page")
def academic_evidence_page(
    kind: Literal["term_results", "attendance"] = "term_results",
    q: str | None = None,
    cohort_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user)
    validate_college_filters(access, cohort_id=cohort_id)
    filters = {"kind": kind, "q": q, "cohort_id": cohort_id}
    model = CollegeTermResult if kind == "term_results" else CollegeAttendanceSnapshot
    values = decode_cursor(cursor, scope="college.academic-evidence", organization_id=user.organization_id, filters=filters)
    statement = select(model, CollegeStudentProfile, Client, CollegeProgram, CollegeCohort).join(
        CollegeStudentProfile, CollegeStudentProfile.id == model.student_profile_id,
    ).join(Client, Client.id == CollegeStudentProfile.client_id).join(
        CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id,
    ).join(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id).where(
        model.organization_id == user.organization_id,
    )
    if not access.unrestricted:
        statement = statement.where(CollegeStudentProfile.id.in_(access.student_ids))
    if cohort_id:
        statement = statement.where(CollegeStudentProfile.cohort_id == cohort_id)
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(func.lower(func.concat_ws(" ", Client.first_name, Client.last_name, CollegeStudentProfile.admission_number, CollegeStudentProfile.roll_number)).like(term))
    statement = _dated_cursor(statement, model, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(model.created_at.desc(), model.id.desc()).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = []
    for evidence, student, client, program, cohort in rows:
        items.append({
            **serialize(evidence),
            "kind": kind,
            "student_profile_id": student.id,
            "client_id": client.id,
            "student_name": f"{client.first_name} {client.last_name}".strip(),
            "admission_number": student.admission_number,
            "program_name": program.name,
            "cohort_name": cohort.name,
        })
    next_cursor = encode_cursor(
        scope="college.academic-evidence", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1][0].created_at.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.get("/attendance/sessions/page")
def attendance_session_page(
    cohort_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.attendance.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user)
    validate_college_filters(access, cohort_id=cohort_id)
    filters = {"cohort_id": cohort_id}
    values = decode_cursor(cursor, scope="college.attendance-sessions", organization_id=user.organization_id, filters=filters)
    counts = select(
        CollegeAttendanceRecord.session_id,
        func.count(CollegeAttendanceRecord.id).label("record_count"),
        func.sum(case((CollegeAttendanceRecord.status == "present", 1), else_=0)).label("present_count"),
    ).where(CollegeAttendanceRecord.organization_id == user.organization_id).group_by(CollegeAttendanceRecord.session_id).subquery()
    statement = select(
        CollegeAttendanceSession, CollegeCourseOffering, CollegeCourse, CollegeCohort,
        func.coalesce(counts.c.record_count, 0).label("record_count"),
        func.coalesce(counts.c.present_count, 0).label("present_count"),
    ).join(CollegeCourseOffering, CollegeCourseOffering.id == CollegeAttendanceSession.offering_id).join(
        CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id,
    ).join(CollegeCohort, CollegeCohort.id == CollegeCourseOffering.cohort_id).outerjoin(
        counts, counts.c.session_id == CollegeAttendanceSession.id,
    ).where(CollegeAttendanceSession.organization_id == user.organization_id)
    if not access.unrestricted:
        statement = statement.where(CollegeCourseOffering.cohort_id.in_(access.cohort_ids))
    if cohort_id:
        statement = statement.where(CollegeCourseOffering.cohort_id == cohort_id)
    statement = _dated_cursor(statement, CollegeAttendanceSession, values, "held_on")
    size = page_size(limit)
    rows = db.execute(statement.order_by(CollegeAttendanceSession.held_on.desc(), CollegeAttendanceSession.id.desc()).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]), "course_name": row[2].name, "course_code": row[2].code,
        "cohort_name": row[3].name, "cohort_id": row[3].id,
        "record_count": int(row.record_count), "present_count": int(row.present_count),
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.attendance-sessions", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1][0].held_on.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.get("/assessments/page")
def assessment_page(
    cohort_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.assessments.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user)
    validate_college_filters(access, cohort_id=cohort_id)
    filters = {"cohort_id": cohort_id}
    values = decode_cursor(cursor, scope="college.assessments", organization_id=user.organization_id, filters=filters)
    score_counts = select(
        CollegeAssessmentScore.assessment_id,
        func.count(CollegeAssessmentScore.id).label("score_count"),
    ).where(CollegeAssessmentScore.organization_id == user.organization_id).group_by(CollegeAssessmentScore.assessment_id).subquery()
    statement = select(
        CollegeAssessment, CollegeCourse, CollegeCohort,
        func.coalesce(score_counts.c.score_count, 0).label("score_count"),
    ).join(CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id).join(
        CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id,
    ).join(CollegeCohort, CollegeCohort.id == CollegeCourseOffering.cohort_id).outerjoin(
        score_counts, score_counts.c.assessment_id == CollegeAssessment.id,
    ).where(CollegeAssessment.organization_id == user.organization_id)
    if not access.unrestricted:
        statement = statement.where(CollegeCourseOffering.cohort_id.in_(access.cohort_ids))
    if cohort_id:
        statement = statement.where(CollegeCourseOffering.cohort_id == cohort_id)
    statement = _dated_cursor(statement, CollegeAssessment, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(CollegeAssessment.created_at.desc(), CollegeAssessment.id.desc()).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]), "course_name": row[1].name, "course_code": row[1].code,
        "cohort_name": row[2].name, "cohort_id": row[2].id, "score_count": int(row.score_count),
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.assessments", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1][0].created_at.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.post("/departments", status_code=201)
def create_department(body: DepartmentBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    if body.location_id:
        ensure_location(db, user, body.location_id)
    _employee(db, user, body.hod_employee_id)
    row = CollegeDepartment(
        organization_id=user.organization_id, name=body.name.strip(), code=_normalized_code(body.code),
        location_id=body.location_id, hod_employee_id=body.hod_employee_id,
        description=body.description,
    )
    db.add(row)
    return _commit(db, row, user, "college.department.create", "college.academics.manage")


@router.post("/programs", status_code=201)
def create_program(body: ProgramBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    tenant_row(db, CollegeDepartment, body.department_id, user, "Department")
    row = CollegeProgram(
        organization_id=user.organization_id, department_id=body.department_id,
        name=body.name.strip(), code=_normalized_code(body.code),
        degree_type=body.degree_type, duration_semesters=body.duration_semesters,
    )
    db.add(row)
    return _commit(db, row, user, "college.program.create", "college.academics.manage")


@router.post("/terms", status_code=201)
def create_term(body: TermBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    if body.is_current:
        for row in db.execute(select(CollegeTerm).where(
            CollegeTerm.organization_id == user.organization_id,
            CollegeTerm.is_current.is_(True),
        ).with_for_update()).scalars():
            row.is_current = False
            if row.status == "active":
                row.status = "closed"
    row = CollegeTerm(organization_id=user.organization_id, **body.model_dump())
    if row.is_current:
        row.status = "active"
    db.add(row)
    return _commit(db, row, user, "college.term.create", "college.academics.manage")


@router.post("/cohorts", status_code=201)
def create_cohort(body: CohortBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    program = tenant_row(db, CollegeProgram, body.program_id, user, "Program")
    if body.current_semester > program.duration_semesters:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Semester exceeds the program duration")
    _employee(db, user, body.advisor_employee_id)
    row = CollegeCohort(
        organization_id=user.organization_id, **body.model_dump(exclude={"code"}),
        code=_normalized_code(body.code),
    )
    db.add(row)
    return _commit(db, row, user, "college.cohort.create", "college.academics.manage")


@router.post("/courses", status_code=201)
def create_course(body: CourseBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    tenant_row(db, CollegeDepartment, body.department_id, user, "Department")
    row = CollegeCourse(
        organization_id=user.organization_id, **body.model_dump(exclude={"code"}),
        code=_normalized_code(body.code),
    )
    db.add(row)
    return _commit(db, row, user, "college.course.create", "college.academics.manage")


@router.post("/offerings", status_code=201)
def create_offering(body: OfferingBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    tenant_row(db, CollegeTerm, body.term_id, user, "Term")
    tenant_row(db, CollegeCourse, body.course_id, user, "Course")
    tenant_row(db, CollegeCohort, body.cohort_id, user, "Cohort")
    _employee(db, user, body.faculty_employee_id)
    values = body.model_dump(mode="json")
    row = CollegeCourseOffering(organization_id=user.organization_id, **values)
    db.add(row)
    return _commit(db, row, user, "college.offering.create", "college.academics.manage")


@router.post("/students", status_code=201)
def admit_student(body: StudentBody, user: User = Depends(require_permissions("college.students.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    program = tenant_row(db, CollegeProgram, body.program_id, user, "Program")
    cohort = tenant_row(db, CollegeCohort, body.cohort_id, user, "Cohort")
    if cohort.program_id != program.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cohort does not belong to the selected program")
    if body.current_semester > program.duration_semesters:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Semester exceeds the program duration")
    if body.home_location_id:
        ensure_location(db, user, body.home_location_id)
    count = db.scalar(select(func.count(Client.id)).where(Client.organization_id == user.organization_id)) or 0
    enforce_plan_limit(db, user, "clients", count)
    admission = _normalized_code(body.admission_number)
    client = Client(
        organization_id=user.organization_id,
        home_location_id=body.home_location_id,
        client_number=f"STU-{admission}",
        first_name=body.first_name.strip(), last_name=body.last_name.strip(),
        email=str(body.email).lower() if body.email else None, phone=body.phone,
        address=body.address, date_of_birth=body.date_of_birth, gender=body.gender,
        joined_on=body.admitted_on, tags=["student"], status="active",
    )
    db.add(client)
    try:
        db.flush()
        profile = CollegeStudentProfile(
            organization_id=user.organization_id, client_id=client.id,
            admission_number=admission,
            roll_number=_normalized_code(body.roll_number) if body.roll_number else None,
            program_id=program.id, cohort_id=cohort.id,
            current_semester=body.current_semester, admitted_on=body.admitted_on,
            guardian=body.guardian, category=body.category,
        )
        db.add(profile)
        db.flush()
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action="college.student.admit", resource_type="college_student_profiles",
            resource_id=profile.id, permission="college.students.manage",
            changes={"client_id": client.id, "program_id": program.id, "cohort_id": cohort.id},
        )
        db.commit()
        return {**serialize(profile), "client_id": client.id, "display_name": f"{client.first_name} {client.last_name}".strip()}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Admission number, roll number, or student record already exists") from exc


def _validate_attendance_students(db: Session, user: User, offering: CollegeCourseOffering, records: list[AttendanceRecordBody]):
    if not records:
        return {}
    ids = {row.student_profile_id for row in records}
    students = {row.id: row for row in db.execute(select(CollegeStudentProfile).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.id.in_(ids),
    )).scalars()}
    if len(students) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more students are unavailable")
    if any(row.cohort_id != offering.cohort_id for row in students.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Attendance can only include students from the offering cohort")
    return students


@router.post("/attendance", status_code=201)
def create_attendance(body: AttendanceSessionBody, user: User = Depends(require_permissions("college.attendance.mark")), db: Session = Depends(get_db)):
    require_college(db, user)
    offering = tenant_row(db, CollegeCourseOffering, body.offering_id, user, "Course offering")
    _validate_attendance_students(db, user, offering, body.records)
    session = CollegeAttendanceSession(
        organization_id=user.organization_id, offering_id=offering.id,
        held_on=body.held_on, starts_at=body.starts_at, ends_at=body.ends_at,
        topic=body.topic, status="submitted" if body.records else "draft",
        recorded_by_user_id=user.id,
    )
    db.add(session)
    db.flush()
    for item in body.records:
        db.add(CollegeAttendanceRecord(
            organization_id=user.organization_id, session_id=session.id,
            student_profile_id=item.student_profile_id, status=item.status, note=item.note,
        ))
    return _commit(db, session, user, "college.attendance.create", "college.attendance.mark", {"record_count": len(body.records)})


@router.put("/attendance/{session_id}/records")
def save_attendance(session_id: str, body: AttendanceRecordsBody, user: User = Depends(require_permissions("college.attendance.mark")), db: Session = Depends(get_db)):
    require_college(db, user)
    session = tenant_row(db, CollegeAttendanceSession, session_id, user, "Attendance session")
    offering = tenant_row(db, CollegeCourseOffering, session.offering_id, user, "Course offering")
    _validate_attendance_students(db, user, offering, body.records)
    existing = {row.student_profile_id: row for row in db.execute(select(CollegeAttendanceRecord).where(
        CollegeAttendanceRecord.session_id == session.id,
        CollegeAttendanceRecord.organization_id == user.organization_id,
    )).scalars()}
    for item in body.records:
        row = existing.get(item.student_profile_id)
        if row:
            row.status = item.status
            row.note = item.note
        else:
            db.add(CollegeAttendanceRecord(
                organization_id=user.organization_id, session_id=session.id,
                student_profile_id=item.student_profile_id, status=item.status, note=item.note,
            ))
    session.status = "submitted"
    return _commit(db, session, user, "college.attendance.update", "college.attendance.mark", {"record_count": len(body.records)})


@router.get("/attendance/{session_id}/records")
def attendance_records(session_id: str, user: User = Depends(require_permissions("college.attendance.view")), db: Session = Depends(get_db)):
    require_college(db, user)
    tenant_row(db, CollegeAttendanceSession, session_id, user, "Attendance session")
    rows = db.execute(select(CollegeAttendanceRecord, CollegeStudentProfile, Client).join(
        CollegeStudentProfile, CollegeStudentProfile.id == CollegeAttendanceRecord.student_profile_id,
    ).join(Client, Client.id == CollegeStudentProfile.client_id).where(
        CollegeAttendanceRecord.organization_id == user.organization_id,
        CollegeAttendanceRecord.session_id == session_id,
    ).order_by(Client.first_name, Client.last_name)).all()
    return [{**serialize(record), "student_name": f"{client.first_name} {client.last_name}".strip(), "roll_number": profile.roll_number} for record, profile, client in rows]


@router.get("/attendance/{session_id}/register")
def attendance_register(
    session_id: str,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_permissions("college.attendance.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    session = tenant_row(db, CollegeAttendanceSession, session_id, user, "Attendance session")
    offering = tenant_row(db, CollegeCourseOffering, session.offering_id, user, "Course offering")
    access = resolve_college_access(db, user)
    validate_college_filters(access, cohort_id=offering.cohort_id)
    filters = {"session_id": session_id, "q": q}
    values = decode_cursor(cursor, scope="college.attendance-register", organization_id=user.organization_id, filters=filters)
    statement = select(CollegeStudentProfile, Client, CollegeAttendanceRecord).join(
        Client, Client.id == CollegeStudentProfile.client_id,
    ).outerjoin(CollegeAttendanceRecord, and_(
        CollegeAttendanceRecord.session_id == session.id,
        CollegeAttendanceRecord.student_profile_id == CollegeStudentProfile.id,
    )).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.cohort_id == offering.cohort_id,
        CollegeStudentProfile.status == "active",
    )
    if not access.unrestricted:
        statement = statement.where(CollegeStudentProfile.id.in_(access.student_ids))
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(func.lower(func.concat_ws(
            " ", Client.first_name, Client.last_name,
            CollegeStudentProfile.admission_number, CollegeStudentProfile.roll_number,
        )).like(term))
    if values:
        first = str(values.get("first") or "")
        last = str(values.get("last") or "")
        row_id = str(values.get("id") or "")
        statement = statement.where(or_(
            func.lower(Client.first_name) > first,
            and_(func.lower(Client.first_name) == first, func.lower(Client.last_name) > last),
            and_(func.lower(Client.first_name) == first, func.lower(Client.last_name) == last, CollegeStudentProfile.id > row_id),
        ))
    size = page_size(limit, default=50)
    rows = db.execute(statement.order_by(
        func.lower(Client.first_name), func.lower(Client.last_name), CollegeStudentProfile.id,
    ).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    total = db.scalar(select(func.count(CollegeStudentProfile.id)).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.cohort_id == offering.cohort_id,
        CollegeStudentProfile.status == "active",
        CollegeStudentProfile.id.in_(access.student_ids) if not access.unrestricted else CollegeStudentProfile.id.is_not(None),
    )) or 0
    recorded = db.scalar(select(func.count(CollegeAttendanceRecord.id)).where(
        CollegeAttendanceRecord.organization_id == user.organization_id,
        CollegeAttendanceRecord.session_id == session.id,
    )) or 0
    items = [{
        "student_profile_id": profile.id,
        "client_id": client.id,
        "student_name": f"{client.first_name} {client.last_name}".strip(),
        "admission_number": profile.admission_number,
        "roll_number": profile.roll_number,
        "record_id": record.id if record else None,
        "status": record.status if record else "unrecorded",
        "note": record.note if record else None,
    } for profile, client, record in rows]
    next_cursor = encode_cursor(
        scope="college.attendance-register", organization_id=user.organization_id, filters=filters,
        values={"first": rows[-1][1].first_name.casefold(), "last": rows[-1][1].last_name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return {
        **page_response(items, next_cursor),
        "session": serialize(session),
        "summary": {"total": int(total), "recorded": int(recorded), "unrecorded": max(0, int(total) - int(recorded))},
    }


@router.post("/assessments", status_code=201)
def create_assessment(body: AssessmentBody, user: User = Depends(require_permissions("college.assessments.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    tenant_row(db, CollegeCourseOffering, body.offering_id, user, "Course offering")
    row = CollegeAssessment(
        organization_id=user.organization_id, **body.model_dump(),
        published_at=datetime.now(timezone.utc) if body.status == "published" else None,
    )
    db.add(row)
    return _commit(db, row, user, "college.assessment.create", "college.assessments.manage")


@router.put("/assessments/{assessment_id}/scores")
def save_scores(assessment_id: str, body: ScoresBody, user: User = Depends(require_permissions("college.assessments.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    assessment = tenant_row(db, CollegeAssessment, assessment_id, user, "Assessment")
    offering = tenant_row(db, CollegeCourseOffering, assessment.offering_id, user, "Course offering")
    ids = {item.student_profile_id for item in body.scores}
    if len(ids) != len(body.scores):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A student can appear only once")
    students = {row.id: row for row in db.execute(select(CollegeStudentProfile).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.id.in_(ids),
    )).scalars()}
    if len(students) != len(ids) or any(row.cohort_id != offering.cohort_id for row in students.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scores can only include students from the offering cohort")
    existing = {row.student_profile_id: row for row in db.execute(select(CollegeAssessmentScore).where(
        CollegeAssessmentScore.organization_id == user.organization_id,
        CollegeAssessmentScore.assessment_id == assessment.id,
    )).scalars()}
    for item in body.scores:
        if item.marks_awarded is not None and item.marks_awarded > assessment.max_marks:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Awarded marks cannot exceed maximum marks")
        row = existing.get(item.student_profile_id)
        values = item.model_dump()
        if row:
            for key, value in values.items():
                setattr(row, key, value)
            row.graded_by_user_id = user.id
        else:
            db.add(CollegeAssessmentScore(
                organization_id=user.organization_id, assessment_id=assessment.id,
                graded_by_user_id=user.id, **values,
            ))
    if body.publish:
        assessment.status = "published"
        assessment.published_at = datetime.now(timezone.utc)
    return _commit(db, assessment, user, "college.assessment.score", "college.assessments.manage", {"score_count": len(body.scores), "published": body.publish})


@router.get("/assessments/{assessment_id}/register")
def assessment_register(
    assessment_id: str,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_permissions("college.assessments.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    assessment = tenant_row(db, CollegeAssessment, assessment_id, user, "Assessment")
    offering = tenant_row(db, CollegeCourseOffering, assessment.offering_id, user, "Course offering")
    access = resolve_college_access(db, user)
    validate_college_filters(access, cohort_id=offering.cohort_id)
    filters = {"assessment_id": assessment_id, "q": q}
    values = decode_cursor(cursor, scope="college.assessment-register", organization_id=user.organization_id, filters=filters)
    statement = select(CollegeStudentProfile, Client, CollegeAssessmentScore).join(
        Client, Client.id == CollegeStudentProfile.client_id,
    ).outerjoin(CollegeAssessmentScore, and_(
        CollegeAssessmentScore.assessment_id == assessment.id,
        CollegeAssessmentScore.student_profile_id == CollegeStudentProfile.id,
    )).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.cohort_id == offering.cohort_id,
        CollegeStudentProfile.status == "active",
    )
    if not access.unrestricted:
        statement = statement.where(CollegeStudentProfile.id.in_(access.student_ids))
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(func.lower(func.concat_ws(
            " ", Client.first_name, Client.last_name,
            CollegeStudentProfile.admission_number, CollegeStudentProfile.roll_number,
        )).like(term))
    if values:
        first = str(values.get("first") or "")
        last = str(values.get("last") or "")
        row_id = str(values.get("id") or "")
        statement = statement.where(or_(
            func.lower(Client.first_name) > first,
            and_(func.lower(Client.first_name) == first, func.lower(Client.last_name) > last),
            and_(func.lower(Client.first_name) == first, func.lower(Client.last_name) == last, CollegeStudentProfile.id > row_id),
        ))
    size = page_size(limit, default=50)
    rows = db.execute(statement.order_by(
        func.lower(Client.first_name), func.lower(Client.last_name), CollegeStudentProfile.id,
    ).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    total = db.scalar(select(func.count(CollegeStudentProfile.id)).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.cohort_id == offering.cohort_id,
        CollegeStudentProfile.status == "active",
        CollegeStudentProfile.id.in_(access.student_ids) if not access.unrestricted else CollegeStudentProfile.id.is_not(None),
    )) or 0
    scored = db.scalar(select(func.count(CollegeAssessmentScore.id)).where(
        CollegeAssessmentScore.organization_id == user.organization_id,
        CollegeAssessmentScore.assessment_id == assessment.id,
    )) or 0
    items = [{
        "student_profile_id": profile.id,
        "client_id": client.id,
        "student_name": f"{client.first_name} {client.last_name}".strip(),
        "admission_number": profile.admission_number,
        "roll_number": profile.roll_number,
        "score_id": score.id if score else None,
        "marks_awarded": float(score.marks_awarded) if score and score.marks_awarded is not None else None,
        "grade": score.grade if score else None,
        "feedback": score.feedback if score else None,
    } for profile, client, score in rows]
    next_cursor = encode_cursor(
        scope="college.assessment-register", organization_id=user.organization_id, filters=filters,
        values={"first": rows[-1][1].first_name.casefold(), "last": rows[-1][1].last_name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return {
        **page_response(items, next_cursor),
        "assessment": serialize(assessment),
        "summary": {"total": int(total), "scored": int(scored), "unscored": max(0, int(total) - int(scored))},
    }


@router.get("/internship-clearance/page")
def internship_clearance_page(
    q: str | None = None,
    clearance: Literal["all", "cleared", "pending", "needs_review"] = "all",
    cohort_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.fees.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user)
    validate_college_filters(access, cohort_id=cohort_id)
    filters = {"q": q, "clearance": clearance, "cohort_id": cohort_id}
    values = decode_cursor(cursor, scope="college.internship-clearance", organization_id=user.organization_id, filters=filters)
    valid_invoice = or_(SaleInvoice.id.is_(None), SaleInvoice.status.notin_(["void", "refunded"]))
    outstanding = case(
        (CollegeStudentFee.status == "waived", 0),
        (SaleInvoice.id.is_not(None), func.greatest(SaleInvoice.total_paise - SaleInvoice.paid_paise, 0)),
        else_=func.greatest(CollegeStudentFee.amount_paise - CollegeStudentFee.concession_paise, 0),
    )
    fee_summary = select(
        CollegeStudentFee.student_profile_id,
        func.count(case((valid_invoice, 1))).label("assigned_count"),
        func.coalesce(func.sum(case((valid_invoice, outstanding), else_=0)), 0).label("outstanding_paise"),
        func.max(CollegeStudentFee.updated_at).label("source_updated_at"),
    ).outerjoin(SaleInvoice, SaleInvoice.id == CollegeStudentFee.invoice_id).where(
        CollegeStudentFee.organization_id == user.organization_id,
    ).group_by(CollegeStudentFee.student_profile_id).subquery()
    status_expression = case(
        (func.coalesce(fee_summary.c.assigned_count, 0) == 0, "needs_review"),
        (func.coalesce(fee_summary.c.outstanding_paise, 0) > 0, "pending"),
        else_="cleared",
    )
    statement = select(
        CollegeStudentProfile, Client, CollegeProgram, CollegeCohort,
        status_expression.label("clearance_status"), fee_summary.c.source_updated_at,
    ).join(Client, Client.id == CollegeStudentProfile.client_id).join(
        CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id,
    ).join(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id).outerjoin(
        fee_summary, fee_summary.c.student_profile_id == CollegeStudentProfile.id,
    ).where(CollegeStudentProfile.organization_id == user.organization_id)
    if not access.unrestricted:
        statement = statement.where(CollegeStudentProfile.id.in_(access.student_ids))
    if cohort_id:
        statement = statement.where(CollegeStudentProfile.cohort_id == cohort_id)
    if clearance != "all":
        statement = statement.where(status_expression == clearance)
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(func.lower(func.concat_ws(
            " ", Client.first_name, Client.last_name,
            CollegeStudentProfile.admission_number, CollegeStudentProfile.roll_number,
        )).like(term))
    if values:
        first = str(values.get("first") or "")
        last = str(values.get("last") or "")
        row_id = str(values.get("id") or "")
        statement = statement.where(or_(
            func.lower(Client.first_name) > first,
            and_(func.lower(Client.first_name) == first, func.lower(Client.last_name) > last),
            and_(func.lower(Client.first_name) == first, func.lower(Client.last_name) == last, CollegeStudentProfile.id > row_id),
        ))
    size = page_size(limit)
    rows = db.execute(statement.order_by(
        func.lower(Client.first_name), func.lower(Client.last_name), CollegeStudentProfile.id,
    ).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        "student_profile_id": row[0].id,
        "client_id": row[1].id,
        "student_name": f"{row[1].first_name} {row[1].last_name}".strip(),
        "admission_number": row[0].admission_number,
        "roll_number": row[0].roll_number,
        "program_name": row[2].name,
        "cohort_name": row[3].name,
        "clearance_status": row.clearance_status,
        "source_updated_at": row.source_updated_at,
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.internship-clearance", organization_id=user.organization_id, filters=filters,
        values={"first": rows[-1][1].first_name.casefold(), "last": rows[-1][1].last_name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.post("/fee-plans", status_code=201)
def create_fee_plan(body: FeePlanBody, user: User = Depends(require_permissions("college.fees.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    program = tenant_row(db, CollegeProgram, body.program_id, user, "Program") if body.program_id else None
    cohort = tenant_row(db, CollegeCohort, body.cohort_id, user, "Cohort") if body.cohort_id else None
    if program and cohort and cohort.program_id != program.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cohort does not belong to the selected program")
    if body.term_id:
        tenant_row(db, CollegeTerm, body.term_id, user, "Term")
    row = CollegeFeePlan(
        organization_id=user.organization_id,
        **body.model_dump(mode="json"),
    )
    db.add(row)
    return _commit(db, row, user, "college.fee_plan.create", "college.fees.manage")


@router.post("/student-fees", status_code=201)
def assign_student_fee(body: StudentFeeBody, user: User = Depends(require_permissions("college.fees.manage")), db: Session = Depends(get_db)):
    organization = require_college(db, user)
    student = tenant_row(db, CollegeStudentProfile, body.student_profile_id, user, "Student")
    plan = tenant_row(db, CollegeFeePlan, body.fee_plan_id, user, "Fee plan")
    if plan.program_id and plan.program_id != student.program_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fee plan does not apply to the student's program")
    if plan.cohort_id and plan.cohort_id != student.cohort_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fee plan does not apply to the student's cohort")
    if body.concession_paise > plan.amount_paise:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Concession cannot exceed the fee amount")
    existing_invoice = db.execute(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.idempotency_key == body.idempotency_key,
    )).scalar_one_or_none()
    if existing_invoice:
        existing_fee = db.execute(select(CollegeStudentFee).where(CollegeStudentFee.invoice_id == existing_invoice.id)).scalar_one_or_none()
        return {**serialize(existing_fee), "invoice": serialize(existing_invoice)} if existing_fee else {"invoice": serialize(existing_invoice)}
    client = tenant_row(db, Client, student.client_id, user, "Student")
    location_id = client.home_location_id
    if not location_id:
        location_id = db.scalar(select(Location.id).where(
            Location.organization_id == user.organization_id,
            Location.is_primary.is_(True),
        ))
    if not location_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add an active primary location before assigning fees")
    ensure_location(db, user, location_id)
    location = db.execute(select(Location).where(
        Location.id == location_id,
        Location.organization_id == user.organization_id,
    ).with_for_update()).scalar_one()
    location.invoice_sequence += 1
    net = int(plan.amount_paise) - body.concession_paise
    local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(organization.timezone))
    invoice = SaleInvoice(
        organization_id=user.organization_id, location_id=location.id, client_id=client.id,
        invoice_number=f"{organization.invoice_prefix}-{location.code}-{local_now.year}-{location.invoice_sequence:06d}",
        status="paid" if net == 0 else "issued", subtotal_paise=plan.amount_paise,
        discount_paise=body.concession_paise, total_paise=net,
        tax_snapshot={"source": "college_fee", "tax_exempt": True, "fee_plan_id": plan.id},
        notes=f"College fee: {plan.name}", idempotency_key=body.idempotency_key,
        issued_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.flush()
    source_lines = plan.line_items or [{"name": plan.name, "amount_paise": int(plan.amount_paise)}]
    remaining_concession = body.concession_paise
    for index, item in enumerate(source_lines):
        amount = int(item["amount_paise"])
        discount = min(amount, remaining_concession)
        remaining_concession -= discount
        db.add(SaleLine(
            organization_id=user.organization_id, invoice_id=invoice.id,
            display_order=index,
            item_name=str(item["name"]), sku=f"COLLEGE-FEE-{index + 1}",
            quantity_milli=1000, unit_price_paise=amount,
            discount_paise=discount, tax_rate_bps=0, tax_paise=0,
            total_paise=amount - discount,
        ))
    fee = CollegeStudentFee(
        organization_id=user.organization_id, student_profile_id=student.id,
        fee_plan_id=plan.id, invoice_id=invoice.id, amount_paise=plan.amount_paise,
        concession_paise=body.concession_paise, status="waived" if net == 0 else "assigned",
    )
    db.add(fee)
    try:
        db.flush()
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action="college.student_fee.assign", resource_type="college_student_fees",
            resource_id=fee.id, permission="college.fees.manage",
            changes={"student_profile_id": student.id, "invoice_id": invoice.id, "total_paise": net},
        )
        db.commit()
        return {**serialize(fee), "invoice": serialize(invoice)}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This fee plan is already assigned to the student") from exc
