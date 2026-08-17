"""College workspace, academic structure, attendance, assessment, and fee APIs."""
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import EmailStr, Field, model_validator
from sqlalchemy import and_, case, false, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.validation import RequestModel
from app.core.deps import require_any_permission, require_entitlements, require_permissions
from app.models import (
    Client, CollegeAssessment, CollegeAssessmentScore, CollegeAttendanceRecord,
    CollegeAttendanceSession, CollegeCareerProfile, CollegeCohort, CollegeCourse, CollegeCourseOffering,
    CollegeAttendanceSnapshot, CollegeClearanceSnapshot, CollegeDataConnector, CollegeDepartment,
    CollegeExamCycle, CollegeExternalRecord, CollegeFeePlan, CollegePlacementApplication, CollegeProgram,
    CollegeStudentFee, CollegeStudentProfile, CollegeTerm, CollegeTermResult,
    Employee, Location, SaleInvoice, SaleLine, User,
)
from app.services.audit import log_action
from app.services.access_policy import policy_v2_enabled, require_policy_domain, resolve_policy_context
from app.services.business_access import enforce_plan_limit, ensure_location, organization_for
from app.services.college import college_workspace, require_college, serialize, tenant_row
from app.services.college_access import CollegeAccess, resolve_college_access, validate_college_filters
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_response, page_size
from app.services.college_assessments import recalculate_assessment_score, validate_metric_values
from app.services.rbac import get_user_permissions


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
    graduation_year: int | None = Field(default=None, ge=2000, le=2200)
    current_semester: int = Field(default=1, ge=1, le=16)
    section: str | None = Field(default=None, max_length=20)
    advisor_employee_id: str | None = None

    @model_validator(mode="after")
    def valid_graduation_year(self):
        if self.graduation_year is not None and self.graduation_year < self.admission_year:
            raise ValueError("Graduation year cannot be before the admission year")
        return self


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


class DepartmentUpdateBody(RequestModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=180)
    code: str | None = Field(default=None, min_length=2, max_length=30)
    location_id: str | None = None
    hod_employee_id: str | None = None
    description: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)


class ProgramUpdateBody(RequestModel):
    version: int = Field(ge=1)
    department_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=200)
    code: str | None = Field(default=None, min_length=2, max_length=40)
    degree_type: Literal["undergraduate", "postgraduate", "diploma", "certificate"] | None = None
    duration_semesters: int | None = Field(default=None, ge=1, le=16)
    reason: str | None = Field(default=None, max_length=500)


class TermUpdateBody(RequestModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=80)
    academic_year: str | None = Field(default=None, min_length=4, max_length=20)
    term_number: int | None = Field(default=None, ge=1, le=16)
    starts_on: date | None = None
    ends_on: date | None = None
    status: Literal["planned", "active", "closed"] | None = None
    is_current: bool | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.starts_on and self.ends_on and self.ends_on <= self.starts_on:
            raise ValueError("Term end date must be after its start date")
        return self


class CohortUpdateBody(RequestModel):
    version: int = Field(ge=1)
    program_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    code: str | None = Field(default=None, min_length=2, max_length=50)
    admission_year: int | None = Field(default=None, ge=2000, le=2200)
    graduation_year: int | None = Field(default=None, ge=2000, le=2200)
    current_semester: int | None = Field(default=None, ge=1, le=16)
    section: str | None = Field(default=None, max_length=20)
    advisor_employee_id: str | None = None
    reason: str | None = Field(default=None, max_length=500)


class CourseUpdateBody(RequestModel):
    version: int = Field(ge=1)
    department_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=200)
    code: str | None = Field(default=None, min_length=2, max_length=40)
    credits: int | None = Field(default=None, ge=0, le=30)
    course_type: Literal["core", "elective", "lab", "project", "audit"] | None = None
    reason: str | None = Field(default=None, max_length=500)


class OfferingUpdateBody(RequestModel):
    version: int = Field(ge=1)
    term_id: str | None = None
    course_id: str | None = None
    cohort_id: str | None = None
    faculty_employee_id: str | None = None
    room: str | None = Field(default=None, max_length=60)
    weekly_schedule: list[ScheduleSlot] | None = Field(default=None, max_length=14)
    status: Literal["active", "inactive", "closed"] | None = None
    reason: str | None = Field(default=None, max_length=500)


class AcademicLifecycleBody(RequestModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class CohortBulkBody(RequestModel):
    program_id: str
    admission_year: int = Field(ge=2000, le=2200)
    graduation_year: int | None = Field(default=None, ge=2000, le=2200)
    current_semester: int = Field(default=1, ge=1, le=16)
    sections: list[str] = Field(min_length=1, max_length=26)
    advisor_employee_id: str | None = None
    code_prefix: str | None = Field(default=None, min_length=2, max_length=36)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @model_validator(mode="after")
    def valid_sections(self):
        normalized = [_normalized_section(value) for value in self.sections]
        if any(len(section) > 20 for section in normalized):
            raise ValueError("Section names must be 20 characters or fewer")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Each section can appear only once")
        self.sections = normalized
        if self.graduation_year is not None and self.graduation_year < self.admission_year:
            raise ValueError("Graduation year cannot be before the admission year")
        return self


StructureResource = Literal["departments", "programs", "terms", "cohorts", "courses"]


class StructureLinkBody(RequestModel):
    connector_id: str
    resource_type: StructureResource
    external_id: str = Field(min_length=1, max_length=180)
    local_resource_id: str
    manual_override_fields: list[str] = Field(default_factory=list, max_length=30)


class StructureLinkUpdateBody(RequestModel):
    manual_override_fields: list[str] = Field(default_factory=list, max_length=30)


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
    assessment_type: str = Field(default="assessment", min_length=2, max_length=50)
    max_marks: Decimal = Field(default=Decimal("100"), gt=0, max_digits=8, decimal_places=2)
    weightage_bps: int = Field(default=0, ge=0, le=10000)
    due_on: date | None = None
    status: Literal["draft", "published", "closed"] = "draft"


class ScoreBody(RequestModel):
    student_profile_id: str
    marks_awarded: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    grade: str | None = Field(default=None, max_length=12)
    feedback: str | None = Field(default=None, max_length=2000)
    metrics: dict = Field(default_factory=dict)
    version: int | None = Field(default=None, ge=1)


class ScoresBody(RequestModel):
    scores: list[ScoreBody] = Field(min_length=1)
    publish: bool = False
    correction_reason: str | None = Field(default=None, max_length=1000)


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


def _normalized_section(value: str | None) -> str:
    return " ".join(str(value or "").split()).upper() or "GENERAL"


def _cohort_graduation_year(body: CohortBody, program: CollegeProgram) -> int:
    return body.graduation_year or body.admission_year + ((program.duration_semesters + 1) // 2)


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


def _require_version(row, version: int) -> None:
    if row.version != version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This academic record changed. Refresh and try again",
        )


def _reject_null_patch_fields(body: RequestModel, *fields: str) -> None:
    invalid = [
        field for field in fields
        if field in body.model_fields_set and getattr(body, field) is None
    ]
    if invalid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"These fields cannot be null: {', '.join(invalid)}",
        )


def _offering_relations(
    db: Session,
    user: User,
    *,
    term_id: str,
    course_id: str,
    cohort_id: str,
) -> tuple[CollegeTerm, CollegeCourse, CollegeCohort]:
    term = tenant_row(db, CollegeTerm, term_id, user, "Term")
    course = tenant_row(db, CollegeCourse, course_id, user, "Course")
    cohort = tenant_row(db, CollegeCohort, cohort_id, user, "Cohort")
    program = tenant_row(db, CollegeProgram, cohort.program_id, user, "Program")
    if term.status == "archived":
        raise HTTPException(status.HTTP_409_CONFLICT, "Restore the term before using it")
    if not course.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Restore the course before using it")
    if not cohort.is_active or not program.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Restore the batch and program before using them")
    if course.department_id != program.department_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Course and cohort must belong to the same department",
        )
    return term, course, cohort


def _clear_current_term(db: Session, user: User, except_id: str | None = None) -> None:
    statement = select(CollegeTerm).where(
        CollegeTerm.organization_id == user.organization_id,
        CollegeTerm.is_current.is_(True),
    )
    if except_id:
        statement = statement.where(CollegeTerm.id != except_id)
    for term in db.execute(statement.with_for_update()).scalars():
        term.is_current = False
        if term.status == "active":
            term.status = "closed"
        term.version += 1


ACADEMIC_MODELS = {
    "departments": CollegeDepartment,
    "programs": CollegeProgram,
    "terms": CollegeTerm,
    "cohorts": CollegeCohort,
    "courses": CollegeCourse,
    "offerings": CollegeCourseOffering,
}


STRUCTURE_LINK_MODELS = {
    "departments": (CollegeDepartment, "college_department"),
    "programs": (CollegeProgram, "college_program"),
    "terms": (CollegeTerm, "college_term"),
    "cohorts": (CollegeCohort, "college_cohort"),
    "courses": (CollegeCourse, "college_course"),
}


def _dependency_count(db: Session, user: User, resource: str, row_id: str) -> int:
    organization_id = user.organization_id
    if resource == "departments":
        return int(db.scalar(select(func.count(CollegeProgram.id)).where(
            CollegeProgram.organization_id == organization_id,
            CollegeProgram.department_id == row_id,
            CollegeProgram.is_active.is_(True),
        )) or 0)
    if resource == "programs":
        return int(db.scalar(select(func.count(CollegeCohort.id)).where(
            CollegeCohort.organization_id == organization_id,
            CollegeCohort.program_id == row_id,
            CollegeCohort.is_active.is_(True),
        )) or 0)
    if resource == "cohorts":
        return int(db.scalar(select(func.count(CollegeStudentProfile.id)).where(
            CollegeStudentProfile.organization_id == organization_id,
            CollegeStudentProfile.cohort_id == row_id,
            CollegeStudentProfile.status == "active",
        )) or 0)
    if resource == "courses":
        return int(db.scalar(select(func.count(CollegeCourseOffering.id)).where(
            CollegeCourseOffering.organization_id == organization_id,
            CollegeCourseOffering.course_id == row_id,
            CollegeCourseOffering.status != "archived",
        )) or 0)
    if resource == "terms":
        return int(db.scalar(select(func.count(CollegeCourseOffering.id)).where(
            CollegeCourseOffering.organization_id == organization_id,
            CollegeCourseOffering.term_id == row_id,
            CollegeCourseOffering.status != "archived",
        )) or 0)
    return 0


@router.get("/workspace")
def workspace(
    location_id: str | None = None,
    range_days: int = Query(default=30, alias="range", ge=7, le=90),
    user: User = Depends(require_permissions("college.view")),
    db: Session = Depends(get_db),
):
    # This compatibility response predates scoped domain payloads. Restrict it
    # to whole-institution users; scoped users use the paged domain endpoints.
    academic_access = resolve_college_access(db, user, "academics")
    student_access = resolve_college_access(db, user, "students")
    if not academic_access.unrestricted or not student_access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Use the scoped College screens for your assigned access")
    return college_workspace(db, user, location_id, range_days)


def _academic_access(db: Session, user: User) -> CollegeAccess:
    return resolve_college_access(db, user, "academics")


def _require_whole_college(access: CollegeAccess, label: str) -> None:
    if not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Whole-institution access is required to manage {label}")


def _require_academic_row(access: CollegeAccess, resource: str, row) -> None:
    if access.unrestricted:
        return
    if resource == "departments":
        access.require_department(row.id)
    elif resource == "programs":
        access.require_program(row.id)
    elif resource == "cohorts":
        access.require_cohort(row.id)
    elif resource == "courses":
        access.require_department(row.department_id)
    elif resource == "offerings":
        access.require_course_offering(row.id)
    elif resource == "terms":
        _require_whole_college(access, "academic years and terms")


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
    access = resolve_college_access(db, user, "academics")
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


def _shared_student_ids(primary: CollegeAccess, secondary: CollegeAccess) -> set[str] | None:
    if primary.unrestricted and secondary.unrestricted:
        return None
    if primary.unrestricted:
        return set(secondary.student_ids)
    if secondary.unrestricted:
        return set(primary.student_ids)
    return set(primary.student_ids) & set(secondary.student_ids)


def _hierarchy_payload(
    db: Session,
    user: User,
    access: CollegeAccess,
    *,
    placement_access: CollegeAccess | None,
) -> dict:
    """Build one hierarchy while keeping optional placement aggregates independently scoped."""
    counts = (
        select(
            CollegeStudentProfile.cohort_id.label("cohort_id"),
            func.count(CollegeStudentProfile.id).label("student_count"),
        )
        .where(
            CollegeStudentProfile.organization_id == user.organization_id,
            CollegeStudentProfile.status == "active",
        )
    )
    if access.constrained_student_ids is not None:
        counts = counts.where(CollegeStudentProfile.id.in_(access.constrained_student_ids))
    counts = counts.group_by(CollegeStudentProfile.cohort_id).subquery()

    placed_applications = select(
        CollegePlacementApplication.student_profile_id.label("student_profile_id"),
    ).where(
        CollegePlacementApplication.organization_id == user.organization_id,
        CollegePlacementApplication.outcome.in_(("selected", "offered", "joined")),
    ).distinct().subquery()
    placement_counts = (
        select(
            CollegeStudentProfile.cohort_id.label("cohort_id"),
            func.count(CollegeStudentProfile.id).label("placement_scope_count"),
            func.sum(case(
                (or_(
                    CollegeCareerProfile.placement_status.in_(("placed", "joined")),
                    placed_applications.c.student_profile_id.is_not(None),
                ), 1),
                else_=0,
            )).label("placed_count"),
        )
        .outerjoin(
            CollegeCareerProfile,
            CollegeCareerProfile.student_profile_id == CollegeStudentProfile.id,
        )
        .outerjoin(
            placed_applications,
            placed_applications.c.student_profile_id == CollegeStudentProfile.id,
        )
        .where(
            CollegeStudentProfile.organization_id == user.organization_id,
            CollegeStudentProfile.status == "active",
        )
    )
    if placement_access is None:
        placement_counts = placement_counts.where(false())
    else:
        shared_ids = _shared_student_ids(access, placement_access)
        if shared_ids is not None:
            placement_counts = placement_counts.where(CollegeStudentProfile.id.in_(shared_ids))
    placement_counts = placement_counts.group_by(CollegeStudentProfile.cohort_id).subquery()

    statement = (
        select(
            CollegeCohort,
            CollegeProgram,
            CollegeDepartment,
            func.coalesce(counts.c.student_count, 0).label("student_count"),
            func.coalesce(placement_counts.c.placement_scope_count, 0).label("placement_scope_count"),
            func.coalesce(placement_counts.c.placed_count, 0).label("placed_count"),
        )
        .join(CollegeProgram, CollegeProgram.id == CollegeCohort.program_id)
        .join(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id)
        .outerjoin(counts, counts.c.cohort_id == CollegeCohort.id)
        .outerjoin(placement_counts, placement_counts.c.cohort_id == CollegeCohort.id)
        .where(
            CollegeCohort.organization_id == user.organization_id,
            CollegeCohort.is_active.is_(True),
            CollegeProgram.is_active.is_(True),
            CollegeDepartment.is_active.is_(True),
        )
    )
    if not access.unrestricted:
        statement = statement.where(CollegeCohort.id.in_(access.cohort_ids))
    rows = db.execute(statement.order_by(
        CollegeCohort.graduation_year,
        CollegeDepartment.name,
        CollegeProgram.name,
        CollegeCohort.section,
        CollegeCohort.name,
    )).all()

    batches: dict[int, dict] = {}
    department_ids: set[str] = set()
    section_count = 0
    total_students = 0
    total_placed = 0
    for cohort, program, department, student_count, placement_scope_count, placed_count in rows:
        year = int(cohort.graduation_year)
        students = int(student_count or 0)
        placement_students = int(placement_scope_count or 0)
        placed = int(placed_count or 0)
        batch = batches.setdefault(year, {
            "graduation_year": year,
            "label": f"Class of {year}",
            "student_count": 0,
            "placement_scope_count": 0,
            "placed_count": 0,
            "unplaced_count": 0,
            "_departments": {},
        })
        department_node = batch["_departments"].setdefault(department.id, {
            "id": department.id,
            "name": department.name,
            "code": department.code,
            "student_count": 0,
            "placement_scope_count": 0,
            "placed_count": 0,
            "unplaced_count": 0,
            "_programs": {},
        })
        program_node = department_node["_programs"].setdefault(program.id, {
            "id": program.id,
            "name": program.name,
            "code": program.code,
            "degree_type": program.degree_type,
            "student_count": 0,
            "placement_scope_count": 0,
            "placed_count": 0,
            "unplaced_count": 0,
            "sections": [],
        })
        section_name = (cohort.section or "").strip().upper() or "GENERAL"
        section_label = "General" if section_name == "GENERAL" else section_name
        section = {
            "id": cohort.id,
            "name": f"{department.code} {section_label}" if section_name != "GENERAL" else cohort.name,
            "section": section_name,
            "cohort_name": cohort.name,
            "code": cohort.code,
            "admission_year": cohort.admission_year,
            "graduation_year": year,
            "current_semester": cohort.current_semester,
            "student_count": students,
            "placement_scope_count": placement_students,
            "placed_count": placed if placement_access is not None else None,
            "unplaced_count": max(0, placement_students - placed) if placement_access is not None else None,
        }
        program_node["sections"].append(section)
        for node in (program_node, department_node, batch):
            node["student_count"] += students
            node["placement_scope_count"] += placement_students
            node["placed_count"] += placed
            node["unplaced_count"] += max(0, placement_students - placed)
        department_ids.add(department.id)
        section_count += 1
        total_students += students
        total_placed += placed

    items = []
    for year in sorted(batches):
        batch = batches[year]
        departments = []
        for department in sorted(batch.pop("_departments").values(), key=lambda row: row["name"].casefold()):
            programs = sorted(department.pop("_programs").values(), key=lambda row: row["name"].casefold())
            for program in programs:
                program["sections"].sort(key=lambda row: (row["section"].casefold(), row["cohort_name"].casefold()))
                program["section_count"] = len(program["sections"])
            department["programs"] = programs
            department["section_count"] = sum(row["section_count"] for row in programs)
            departments.append(department)
        batch["departments"] = departments
        batch["department_count"] = len(departments)
        batch["section_count"] = sum(row["section_count"] for row in departments)
        items.append(batch)

    if placement_access is None:
        for batch in items:
            batch["placement_scope_count"] = None
            batch["placed_count"] = None
            batch["unplaced_count"] = None
            for department in batch["departments"]:
                department["placement_scope_count"] = None
                department["placed_count"] = None
                department["unplaced_count"] = None
                for program in department["programs"]:
                    program["placement_scope_count"] = None
                    program["placed_count"] = None
                    program["unplaced_count"] = None

    academic_years = list(db.execute(
        select(CollegeTerm.academic_year)
        .where(CollegeTerm.organization_id == user.organization_id)
        .distinct()
        .order_by(CollegeTerm.academic_year.desc())
    ).scalars())
    return {
        "items": items,
        "academic_years": academic_years,
        "summary": {
            "batch_count": len(items),
            "department_count": len(department_ids),
            "section_count": section_count,
            "student_count": total_students,
            "placement_scope_count": sum(
                int(batch.get("placement_scope_count") or 0) for batch in items
            ) if placement_access is not None else None,
            "placed_count": total_placed if placement_access is not None else None,
            "unplaced_count": sum(
                int(batch.get("unplaced_count") or 0) for batch in items
            ) if placement_access is not None else None,
        },
        "capabilities": {"placement": placement_access is not None},
    }


def _optional_hierarchy_placement_access(db: Session, user: User) -> CollegeAccess | None:
    if "college.placements.view" not in get_user_permissions(db, user):
        return None
    try:
        return resolve_college_access(db, user, "placements")
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return None
        raise


@router.get("/academic-hierarchy")
def academic_hierarchy(
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    """Return the bounded academic hierarchy for structure and legacy consumers."""
    require_college(db, user)
    return _hierarchy_payload(
        db,
        user,
        resolve_college_access(db, user, "academics"),
        placement_access=_optional_hierarchy_placement_access(db, user),
    )


@router.get("/students/hierarchy")
def student_navigation_hierarchy(
    user: User = Depends(require_permissions("college.students.view")),
    db: Session = Depends(get_db),
):
    """Return only hierarchy branches reachable from the caller's student policy."""
    require_college(db, user)
    return _hierarchy_payload(
        db,
        user,
        resolve_college_access(db, user, "students"),
        placement_access=_optional_hierarchy_placement_access(db, user),
    )


@router.get("/departments/page")
def department_page(
    q: str | None = Query(default=None, max_length=120),
    active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "academics")
    filters = {"q": q, "active": active}
    values = decode_cursor(cursor, scope="college.departments", organization_id=user.organization_id, filters=filters)
    counts = select(
        CollegeProgram.department_id,
        func.count(CollegeProgram.id).label("program_count"),
        func.sum(case((CollegeProgram.is_active.is_(True), 1), else_=0)).label("active_program_count"),
    ).where(CollegeProgram.organization_id == user.organization_id).group_by(CollegeProgram.department_id).subquery()
    statement = select(
        CollegeDepartment,
        func.coalesce(counts.c.program_count, 0).label("program_count"),
        func.coalesce(counts.c.active_program_count, 0).label("active_program_count"),
    ).outerjoin(counts, counts.c.department_id == CollegeDepartment.id).where(
        CollegeDepartment.organization_id == user.organization_id,
    )
    if not access.unrestricted:
        statement = statement.where(CollegeDepartment.id.in_(access.department_ids))
    if active is not None:
        statement = statement.where(CollegeDepartment.is_active.is_(active))
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(or_(
            func.lower(CollegeDepartment.name).like(term),
            func.lower(CollegeDepartment.code).like(term),
        ))
    statement = _name_cursor(statement, CollegeDepartment, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(func.lower(CollegeDepartment.name), CollegeDepartment.id).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]),
        "program_count": int(row.program_count),
        "active_program_count": int(row.active_program_count),
        "dependency_count": int(row.active_program_count),
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.departments", organization_id=user.organization_id, filters=filters,
        values={"name": rows[-1][0].name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.get("/programs/page")
def program_page(
    q: str | None = Query(default=None, max_length=120),
    department_id: str | None = None,
    active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "academics")
    validate_college_filters(access, department_id=department_id)
    filters = {"q": q, "department_id": department_id, "active": active}
    values = decode_cursor(cursor, scope="college.programs", organization_id=user.organization_id, filters=filters)
    counts = select(
        CollegeCohort.program_id,
        func.count(CollegeCohort.id).label("cohort_count"),
        func.sum(case((CollegeCohort.is_active.is_(True), 1), else_=0)).label("active_cohort_count"),
    ).where(CollegeCohort.organization_id == user.organization_id).group_by(CollegeCohort.program_id).subquery()
    statement = select(
        CollegeProgram,
        CollegeDepartment.name.label("department_name"),
        CollegeDepartment.code.label("department_code"),
        func.coalesce(counts.c.cohort_count, 0).label("cohort_count"),
        func.coalesce(counts.c.active_cohort_count, 0).label("active_cohort_count"),
    ).join(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id).outerjoin(
        counts, counts.c.program_id == CollegeProgram.id,
    ).where(CollegeProgram.organization_id == user.organization_id)
    if not access.unrestricted:
        statement = statement.where(CollegeProgram.id.in_(access.program_ids))
    if department_id:
        statement = statement.where(CollegeProgram.department_id == department_id)
    if active is not None:
        statement = statement.where(CollegeProgram.is_active.is_(active))
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(or_(
            func.lower(CollegeProgram.name).like(term),
            func.lower(CollegeProgram.code).like(term),
            func.lower(CollegeDepartment.name).like(term),
            func.lower(CollegeDepartment.code).like(term),
        ))
    statement = _name_cursor(statement, CollegeProgram, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(func.lower(CollegeProgram.name), CollegeProgram.id).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]),
        "department_name": row.department_name,
        "department_code": row.department_code,
        "cohort_count": int(row.cohort_count),
        "active_cohort_count": int(row.active_cohort_count),
        "dependency_count": int(row.active_cohort_count),
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.programs", organization_id=user.organization_id, filters=filters,
        values={"name": rows[-1][0].name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.get("/terms/page")
def term_page(
    q: str | None = Query(default=None, max_length=120),
    term_status: Literal["planned", "active", "closed", "archived"] | None = Query(default=None, alias="status"),
    active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    resolve_college_access(db, user, "academics")
    filters = {"q": q, "status": term_status, "active": active}
    values = decode_cursor(cursor, scope="college.terms", organization_id=user.organization_id, filters=filters)
    counts = select(
        CollegeCourseOffering.term_id,
        func.count(CollegeCourseOffering.id).label("offering_count"),
        func.sum(case((CollegeCourseOffering.status != "archived", 1), else_=0)).label("active_offering_count"),
    ).where(CollegeCourseOffering.organization_id == user.organization_id).group_by(CollegeCourseOffering.term_id).subquery()
    statement = select(
        CollegeTerm,
        func.coalesce(counts.c.offering_count, 0).label("offering_count"),
        func.coalesce(counts.c.active_offering_count, 0).label("active_offering_count"),
    ).outerjoin(counts, counts.c.term_id == CollegeTerm.id).where(
        CollegeTerm.organization_id == user.organization_id,
    )
    if term_status:
        statement = statement.where(CollegeTerm.status == term_status)
    elif active is True:
        statement = statement.where(CollegeTerm.status != "archived")
    elif active is False:
        statement = statement.where(CollegeTerm.status == "archived")
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(or_(
            func.lower(CollegeTerm.name).like(term),
            func.lower(CollegeTerm.academic_year).like(term),
        ))
    statement = _dated_cursor(statement, CollegeTerm, values, "starts_on")
    size = page_size(limit)
    rows = db.execute(statement.order_by(CollegeTerm.starts_on.desc(), CollegeTerm.id.desc()).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]),
        "offering_count": int(row.offering_count),
        "active_offering_count": int(row.active_offering_count),
        "dependency_count": int(row.active_offering_count),
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.terms", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1][0].starts_on.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.get("/courses/page")
def course_page(
    q: str | None = Query(default=None, max_length=120),
    department_id: str | None = None,
    active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "academics")
    validate_college_filters(access, department_id=department_id)
    filters = {"q": q, "department_id": department_id, "active": active}
    values = decode_cursor(cursor, scope="college.courses", organization_id=user.organization_id, filters=filters)
    counts = select(
        CollegeCourseOffering.course_id,
        func.count(CollegeCourseOffering.id).label("offering_count"),
        func.sum(case((CollegeCourseOffering.status != "archived", 1), else_=0)).label("active_offering_count"),
    ).where(CollegeCourseOffering.organization_id == user.organization_id).group_by(CollegeCourseOffering.course_id).subquery()
    statement = select(
        CollegeCourse,
        CollegeDepartment.name.label("department_name"),
        CollegeDepartment.code.label("department_code"),
        func.coalesce(counts.c.offering_count, 0).label("offering_count"),
        func.coalesce(counts.c.active_offering_count, 0).label("active_offering_count"),
    ).join(CollegeDepartment, CollegeDepartment.id == CollegeCourse.department_id).outerjoin(
        counts, counts.c.course_id == CollegeCourse.id,
    ).where(CollegeCourse.organization_id == user.organization_id)
    if not access.unrestricted:
        statement = statement.where(CollegeCourse.department_id.in_(access.department_ids))
    if department_id:
        statement = statement.where(CollegeCourse.department_id == department_id)
    if active is not None:
        statement = statement.where(CollegeCourse.is_active.is_(active))
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(or_(
            func.lower(CollegeCourse.name).like(term),
            func.lower(CollegeCourse.code).like(term),
            func.lower(CollegeDepartment.name).like(term),
        ))
    statement = _name_cursor(statement, CollegeCourse, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(func.lower(CollegeCourse.name), CollegeCourse.id).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]),
        "department_name": row.department_name,
        "department_code": row.department_code,
        "offering_count": int(row.offering_count),
        "active_offering_count": int(row.active_offering_count),
        "dependency_count": int(row.active_offering_count),
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.courses", organization_id=user.organization_id, filters=filters,
        values={"name": rows[-1][0].name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.get("/offerings/page")
def offering_page(
    q: str | None = Query(default=None, max_length=120),
    term_id: str | None = None,
    cohort_id: str | None = None,
    offering_status: Literal["active", "inactive", "closed", "archived"] | None = Query(default=None, alias="status"),
    active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "academics")
    validate_college_filters(access, cohort_id=cohort_id)
    filters = {
        "q": q, "term_id": term_id, "cohort_id": cohort_id,
        "status": offering_status, "active": active,
    }
    values = decode_cursor(cursor, scope="college.offerings", organization_id=user.organization_id, filters=filters)
    statement = select(
        CollegeCourseOffering,
        CollegeCourse.name.label("course_name"),
        CollegeCourse.code.label("course_code"),
        CollegeTerm.name.label("term_name"),
        CollegeTerm.academic_year.label("academic_year"),
        CollegeCohort.name.label("cohort_name"),
        CollegeCohort.section.label("section"),
        CollegeCohort.graduation_year.label("graduation_year"),
        CollegeProgram.name.label("program_name"),
        CollegeDepartment.name.label("department_name"),
        CollegeDepartment.code.label("department_code"),
    ).join(CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id).join(
        CollegeTerm, CollegeTerm.id == CollegeCourseOffering.term_id,
    ).join(CollegeCohort, CollegeCohort.id == CollegeCourseOffering.cohort_id).join(
        CollegeProgram, CollegeProgram.id == CollegeCohort.program_id,
    ).join(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id).where(
        CollegeCourseOffering.organization_id == user.organization_id,
    )
    if not access.unrestricted:
        statement = statement.where(CollegeCourseOffering.cohort_id.in_(access.cohort_ids))
    if term_id:
        statement = statement.where(CollegeCourseOffering.term_id == term_id)
    if cohort_id:
        statement = statement.where(CollegeCourseOffering.cohort_id == cohort_id)
    if offering_status:
        statement = statement.where(CollegeCourseOffering.status == offering_status)
    elif active is True:
        statement = statement.where(CollegeCourseOffering.status != "archived")
    elif active is False:
        statement = statement.where(CollegeCourseOffering.status == "archived")
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(or_(
            func.lower(CollegeCourse.name).like(term),
            func.lower(CollegeCourse.code).like(term),
            func.lower(CollegeCohort.name).like(term),
            func.lower(CollegeTerm.name).like(term),
            func.lower(CollegeDepartment.name).like(term),
        ))
    statement = _dated_cursor(statement, CollegeCourseOffering, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(CollegeCourseOffering.created_at.desc(), CollegeCourseOffering.id.desc()).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]),
        "course_name": row.course_name,
        "course_code": row.course_code,
        "term_name": row.term_name,
        "academic_year": row.academic_year,
        "cohort_name": row.cohort_name,
        "section": row.section,
        "graduation_year": row.graduation_year,
        "program_name": row.program_name,
        "department_name": row.department_name,
        "department_code": row.department_code,
        "display_name": f"{row.course_code} / {row.cohort_name}",
        "display_meta": f"{row.term_name} / {row.academic_year}",
        "dependency_count": 0,
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.offerings", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1][0].created_at.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.get("/cohorts/page")
def cohort_page(
    q: str | None = Query(default=None, max_length=120),
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    graduation_year: int | None = Query(default=None, ge=2000, le=2200),
    section: str | None = Query(default=None, max_length=20),
    active: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "academics")
    validate_college_filters(
        access,
        department_id=department_id,
        program_id=program_id,
        cohort_id=cohort_id,
    )
    normalized_section = _normalized_section(section) if section else None
    filters = {
        "q": q,
        "department_id": department_id,
        "program_id": program_id,
        "cohort_id": cohort_id,
        "graduation_year": graduation_year,
        "section": normalized_section,
        "active": active,
    }
    values = decode_cursor(cursor, scope="college.cohorts", organization_id=user.organization_id, filters=filters)
    counts = select(
        CollegeStudentProfile.cohort_id,
        func.count(CollegeStudentProfile.id).label("student_count"),
        func.sum(case((CollegeStudentProfile.status == "active", 1), else_=0)).label("active_student_count"),
    ).where(CollegeStudentProfile.organization_id == user.organization_id).group_by(CollegeStudentProfile.cohort_id).subquery()
    statement = select(
        CollegeCohort,
        CollegeProgram.name.label("program_name"),
        CollegeProgram.code.label("program_code"),
        CollegeDepartment.id.label("department_id"),
        CollegeDepartment.name.label("department_name"),
        CollegeDepartment.code.label("department_code"),
        func.coalesce(counts.c.student_count, 0).label("student_count"),
        func.coalesce(counts.c.active_student_count, 0).label("active_student_count"),
    ).join(CollegeProgram, CollegeProgram.id == CollegeCohort.program_id).join(
        CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id,
    ).outerjoin(
        counts, counts.c.cohort_id == CollegeCohort.id,
    ).where(CollegeCohort.organization_id == user.organization_id)
    if not access.unrestricted:
        statement = statement.where(CollegeCohort.id.in_(access.cohort_ids))
    if program_id:
        statement = statement.where(CollegeCohort.program_id == program_id)
    if department_id:
        statement = statement.where(CollegeProgram.department_id == department_id)
    if cohort_id:
        statement = statement.where(CollegeCohort.id == cohort_id)
    if graduation_year is not None:
        statement = statement.where(CollegeCohort.graduation_year == graduation_year)
    if normalized_section:
        statement = statement.where(CollegeCohort.section == normalized_section)
    if active is not None:
        statement = statement.where(CollegeCohort.is_active.is_(active))
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(or_(
            func.lower(CollegeCohort.name).like(term),
            func.lower(CollegeCohort.code).like(term),
            func.lower(CollegeCohort.section).like(term),
            func.lower(CollegeProgram.name).like(term),
            func.lower(CollegeDepartment.name).like(term),
            func.lower(CollegeDepartment.code).like(term),
        ))
    statement = _name_cursor(statement, CollegeCohort, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(func.lower(CollegeCohort.name), CollegeCohort.id).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]),
        "program_name": row.program_name,
        "program_code": row.program_code,
        "department_id": row.department_id,
        "department_name": row.department_name,
        "department_code": row.department_code,
        "student_count": int(row.student_count),
        "active_student_count": int(row.active_student_count),
        "dependency_count": int(row.active_student_count),
    } for row in rows]
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
    access = resolve_college_access(db, user, "assessments" if kind == "term_results" else "attendance")
    if cohort_id and not access.unrestricted and cohort_id not in access.cohort_ids:
        offering_cohorts = set(db.execute(select(CollegeCourseOffering.cohort_id).where(
            CollegeCourseOffering.organization_id == user.organization_id,
            CollegeCourseOffering.id.in_(access.course_offering_ids),
        )).scalars()) if access.course_offering_ids else set()
        if cohort_id not in offering_cohorts:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cohort is outside your College access")
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
        if kind == "term_results":
            statement = statement.where(
                CollegeStudentProfile.id.in_(access.full_student_ids)
                if access.full_student_ids else false()
            )
        else:
            visibility = []
            if access.full_student_ids:
                visibility.append(CollegeStudentProfile.id.in_(access.full_student_ids))
            roster_student_ids = set(access.student_ids) - set(access.full_student_ids)
            if roster_student_ids and access.course_offering_ids:
                allowed_offerings = select(
                    CollegeCourseOffering.course_id,
                    CollegeCourseOffering.term_id,
                ).where(
                    CollegeCourseOffering.organization_id == user.organization_id,
                    CollegeCourseOffering.id.in_(access.course_offering_ids),
                )
                visibility.append(and_(
                    CollegeStudentProfile.id.in_(roster_student_ids),
                    tuple_(CollegeAttendanceSnapshot.course_id, CollegeAttendanceSnapshot.term_id).in_(allowed_offerings),
                ))
            statement = statement.where(or_(*visibility) if visibility else false())
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
    access = resolve_college_access(db, user, "attendance")
    if cohort_id and not access.unrestricted and cohort_id not in access.cohort_ids:
        offering_cohorts = set(db.execute(select(CollegeCourseOffering.cohort_id).where(
            CollegeCourseOffering.organization_id == user.organization_id,
            CollegeCourseOffering.id.in_(access.course_offering_ids),
        )).scalars()) if access.course_offering_ids else set()
        if cohort_id not in offering_cohorts:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cohort is outside your College access")
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
        statement = statement.where(
            CollegeAttendanceSession.offering_id.in_(access.course_offering_ids)
            if access.course_offering_ids else false()
        )
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
    access = resolve_college_access(db, user, "assessments")
    if cohort_id and not access.unrestricted and cohort_id not in access.cohort_ids:
        offering_cohorts = set(db.execute(select(CollegeCourseOffering.cohort_id).where(
            CollegeCourseOffering.organization_id == user.organization_id,
            CollegeCourseOffering.id.in_(access.course_offering_ids),
        )).scalars()) if access.course_offering_ids else set()
        if cohort_id not in offering_cohorts:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cohort is outside your College access")
    filters = {"cohort_id": cohort_id}
    values = decode_cursor(cursor, scope="college.assessments", organization_id=user.organization_id, filters=filters)
    score_counts = select(
        CollegeAssessmentScore.assessment_id,
        func.count(CollegeAssessmentScore.id).label("score_count"),
    ).where(CollegeAssessmentScore.organization_id == user.organization_id).group_by(CollegeAssessmentScore.assessment_id).subquery()
    statement = select(
        CollegeAssessment, CollegeCourse, CollegeCohort, CollegeExamCycle,
        func.coalesce(score_counts.c.score_count, 0).label("score_count"),
    ).outerjoin(CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id).outerjoin(
        CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id,
    ).outerjoin(CollegeCohort, CollegeCohort.id == func.coalesce(
        CollegeAssessment.cohort_id, CollegeCourseOffering.cohort_id,
    )).outerjoin(CollegeExamCycle, CollegeExamCycle.id == CollegeAssessment.exam_cycle_id).outerjoin(
        score_counts, score_counts.c.assessment_id == CollegeAssessment.id,
    ).where(CollegeAssessment.organization_id == user.organization_id)
    if not access.unrestricted:
        visibility = []
        if access.course_offering_ids:
            visibility.append(CollegeAssessment.offering_id.in_(access.course_offering_ids))
        if access.cohort_ids:
            visibility.append(and_(
                CollegeAssessment.offering_id.is_(None),
                CollegeAssessment.cohort_id.in_(access.cohort_ids),
            ))
        statement = statement.where(or_(*visibility) if visibility else false())
    if cohort_id:
        statement = statement.where(func.coalesce(
            CollegeAssessment.cohort_id, CollegeCourseOffering.cohort_id,
        ) == cohort_id)
    statement = _dated_cursor(statement, CollegeAssessment, values)
    size = page_size(limit)
    rows = db.execute(statement.order_by(CollegeAssessment.created_at.desc(), CollegeAssessment.id.desc()).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        **serialize(row[0]), "course_name": row[1].name if row[1] else None,
        "course_code": row[1].code if row[1] else None,
        "cohort_name": row[2].name if row[2] else None,
        "cohort_id": row[2].id if row[2] else row[0].cohort_id,
        "cycle_name": row[3].name if row[3] else None,
        "cycle_code": row[3].code if row[3] else None,
        "scheme_snapshot": row[3].scheme_snapshot if row[3] else None,
        "score_count": int(row.score_count),
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.assessments", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1][0].created_at.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.post("/departments", status_code=201)
def create_department(body: DepartmentBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    _require_whole_college(_academic_access(db, user), "departments")
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
    access = _academic_access(db, user)
    department = tenant_row(db, CollegeDepartment, body.department_id, user, "Department")
    access.require_department(department.id)
    if not department.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Restore the department before adding programs")
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
    _require_whole_college(_academic_access(db, user), "academic years and terms")
    if body.is_current:
        _clear_current_term(db, user)
    row = CollegeTerm(organization_id=user.organization_id, **body.model_dump())
    if row.is_current:
        row.status = "active"
    db.add(row)
    return _commit(db, row, user, "college.term.create", "college.academics.manage")


@router.post("/cohorts", status_code=201)
def create_cohort(body: CohortBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    access = _academic_access(db, user)
    program = tenant_row(db, CollegeProgram, body.program_id, user, "Program")
    access.require_program(program.id)
    if not program.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Restore the program before adding batches")
    if body.current_semester > program.duration_semesters:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Semester exceeds the program duration")
    _employee(db, user, body.advisor_employee_id)
    values = body.model_dump(exclude={"code", "graduation_year", "section"})
    row = CollegeCohort(
        organization_id=user.organization_id,
        **values,
        code=_normalized_code(body.code),
        graduation_year=_cohort_graduation_year(body, program),
        section=_normalized_section(body.section),
    )
    db.add(row)
    return _commit(db, row, user, "college.cohort.create", "college.academics.manage")


@router.post("/courses", status_code=201)
def create_course(body: CourseBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    access = _academic_access(db, user)
    department = tenant_row(db, CollegeDepartment, body.department_id, user, "Department")
    access.require_department(department.id)
    if not department.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Restore the department before adding courses")
    row = CollegeCourse(
        organization_id=user.organization_id, **body.model_dump(exclude={"code"}),
        code=_normalized_code(body.code),
    )
    db.add(row)
    return _commit(db, row, user, "college.course.create", "college.academics.manage")


@router.post("/offerings", status_code=201)
def create_offering(body: OfferingBody, user: User = Depends(require_permissions("college.academics.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    access = _academic_access(db, user)
    access.require_cohort(body.cohort_id)
    _offering_relations(
        db, user, term_id=body.term_id, course_id=body.course_id, cohort_id=body.cohort_id,
    )
    _employee(db, user, body.faculty_employee_id)
    values = body.model_dump(mode="json")
    row = CollegeCourseOffering(organization_id=user.organization_id, **values)
    db.add(row)
    return _commit(db, row, user, "college.offering.create", "college.academics.manage")


def _editable_academic_row(db: Session, user: User, model, row_id: str, label: str):
    row = tenant_row(db, model, row_id, user, label)
    archived = (
        (hasattr(row, "is_active") and not row.is_active)
        or (hasattr(row, "status") and row.status == "archived")
    )
    if archived:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Restore this {label.lower()} before editing it")
    return row


@router.patch("/departments/{department_id}")
def update_department(
    department_id: str,
    body: DepartmentUpdateBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    row = _editable_academic_row(db, user, CollegeDepartment, department_id, "Department")
    _require_academic_row(_academic_access(db, user), "departments", row)
    _require_version(row, body.version)
    _reject_null_patch_fields(body, "name", "code")
    fields = body.model_fields_set
    changes = {}
    if "location_id" in fields:
        if body.location_id:
            ensure_location(db, user, body.location_id)
        row.location_id = body.location_id
        changes["location_id"] = body.location_id
    if "hod_employee_id" in fields:
        _employee(db, user, body.hod_employee_id)
        row.hod_employee_id = body.hod_employee_id
        changes["hod_employee_id"] = body.hod_employee_id
    for field in ("name", "description"):
        if field in fields:
            value = getattr(body, field)
            if field == "name":
                value = value.strip()
            setattr(row, field, value)
            changes[field] = value
    if "code" in fields:
        row.code = _normalized_code(body.code)
        changes["code"] = row.code
    row.version += 1
    changes.update({"version": row.version, "reason": body.reason})
    return _commit(db, row, user, "college.department.update", "college.academics.manage", changes)


@router.patch("/programs/{program_id}")
def update_program(
    program_id: str,
    body: ProgramUpdateBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    row = _editable_academic_row(db, user, CollegeProgram, program_id, "Program")
    access = _academic_access(db, user)
    _require_academic_row(access, "programs", row)
    _require_version(row, body.version)
    _reject_null_patch_fields(
        body, "department_id", "name", "code", "degree_type", "duration_semesters",
    )
    fields = body.model_fields_set
    changes = {}
    if "department_id" in fields and body.department_id != row.department_id:
        access.require_department(body.department_id)
        if _dependency_count(db, user, "programs", row.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "A program with active batches cannot move to another department")
        department = tenant_row(db, CollegeDepartment, body.department_id, user, "Department")
        if not department.is_active:
            raise HTTPException(status.HTTP_409_CONFLICT, "The selected department is archived")
        row.department_id = department.id
        changes["department_id"] = department.id
    if "duration_semesters" in fields:
        highest_semester = db.scalar(select(func.max(CollegeCohort.current_semester)).where(
            CollegeCohort.organization_id == user.organization_id,
            CollegeCohort.program_id == row.id,
            CollegeCohort.is_active.is_(True),
        ))
        if highest_semester and body.duration_semesters < highest_semester:
            raise HTTPException(status.HTTP_409_CONFLICT, "Program duration is below an active batch semester")
        row.duration_semesters = body.duration_semesters
        changes["duration_semesters"] = body.duration_semesters
    for field in ("name", "degree_type"):
        if field in fields:
            value = getattr(body, field)
            row_value = value.strip() if field == "name" else value
            setattr(row, field, row_value)
            changes[field] = row_value
    if "code" in fields:
        row.code = _normalized_code(body.code)
        changes["code"] = row.code
    row.version += 1
    changes.update({"version": row.version, "reason": body.reason})
    return _commit(db, row, user, "college.program.update", "college.academics.manage", changes)


@router.patch("/terms/{term_id}")
def update_term(
    term_id: str,
    body: TermUpdateBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    row = _editable_academic_row(db, user, CollegeTerm, term_id, "Term")
    _require_academic_row(_academic_access(db, user), "terms", row)
    _require_version(row, body.version)
    _reject_null_patch_fields(
        body, "name", "academic_year", "term_number", "starts_on", "ends_on",
        "status", "is_current",
    )
    fields = body.model_fields_set
    starts_on = body.starts_on if "starts_on" in fields else row.starts_on
    ends_on = body.ends_on if "ends_on" in fields else row.ends_on
    if ends_on <= starts_on:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Term end date must be after its start date")
    changes = {}
    for field in ("name", "academic_year", "term_number", "starts_on", "ends_on", "status", "is_current"):
        if field not in fields:
            continue
        value = getattr(body, field)
        if field in {"name", "academic_year"}:
            value = value.strip()
        setattr(row, field, value)
        changes[field] = value.isoformat() if isinstance(value, date) else value
    if body.is_current is True:
        _clear_current_term(db, user, except_id=row.id)
        row.is_current = True
        row.status = "active"
        changes.update({"is_current": True, "status": "active"})
    elif body.status == "active" and "is_current" not in fields:
        row.is_current = False
    row.version += 1
    changes.update({"version": row.version, "reason": body.reason})
    return _commit(db, row, user, "college.term.update", "college.academics.manage", changes)


@router.patch("/cohorts/{cohort_id}")
def update_cohort(
    cohort_id: str,
    body: CohortUpdateBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    row = _editable_academic_row(db, user, CollegeCohort, cohort_id, "Batch")
    access = _academic_access(db, user)
    _require_academic_row(access, "cohorts", row)
    _require_version(row, body.version)
    _reject_null_patch_fields(
        body, "program_id", "name", "code", "admission_year", "graduation_year",
        "current_semester",
    )
    fields = body.model_fields_set
    active_students = _dependency_count(db, user, "cohorts", row.id)
    if "program_id" in fields and body.program_id != row.program_id and active_students:
        raise HTTPException(status.HTTP_409_CONFLICT, "A batch with active students cannot move to another program")
    program = tenant_row(db, CollegeProgram, body.program_id or row.program_id, user, "Program")
    access.require_program(program.id)
    if not program.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "The selected program is archived")
    admission_year = body.admission_year if "admission_year" in fields else row.admission_year
    graduation_year = body.graduation_year if "graduation_year" in fields else row.graduation_year
    current_semester = body.current_semester if "current_semester" in fields else row.current_semester
    if graduation_year < admission_year:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Graduation year cannot be before the admission year")
    if current_semester > program.duration_semesters:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Semester exceeds the program duration")
    changes = {}
    for field in ("program_id", "name", "admission_year", "graduation_year", "current_semester"):
        if field in fields:
            value = getattr(body, field)
            if field == "name":
                value = value.strip()
            setattr(row, field, value)
            changes[field] = value
    if "code" in fields:
        row.code = _normalized_code(body.code)
        changes["code"] = row.code
    if "section" in fields:
        row.section = _normalized_section(body.section)
        changes["section"] = row.section
    if "advisor_employee_id" in fields:
        _employee(db, user, body.advisor_employee_id)
        row.advisor_employee_id = body.advisor_employee_id
        changes["advisor_employee_id"] = body.advisor_employee_id
    row.version += 1
    changes.update({"version": row.version, "reason": body.reason})
    return _commit(db, row, user, "college.cohort.update", "college.academics.manage", changes)


@router.patch("/courses/{course_id}")
def update_course(
    course_id: str,
    body: CourseUpdateBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    row = _editable_academic_row(db, user, CollegeCourse, course_id, "Course")
    access = _academic_access(db, user)
    _require_academic_row(access, "courses", row)
    _require_version(row, body.version)
    _reject_null_patch_fields(
        body, "department_id", "name", "code", "credits", "course_type",
    )
    fields = body.model_fields_set
    if "department_id" in fields and body.department_id != row.department_id and _dependency_count(db, user, "courses", row.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A course with active offerings cannot move to another department")
    changes = {}
    if "department_id" in fields:
        access.require_department(body.department_id)
        department = tenant_row(db, CollegeDepartment, body.department_id, user, "Department")
        if not department.is_active:
            raise HTTPException(status.HTTP_409_CONFLICT, "The selected department is archived")
        row.department_id = department.id
        changes["department_id"] = department.id
    for field in ("name", "credits", "course_type"):
        if field in fields:
            value = getattr(body, field)
            if field == "name":
                value = value.strip()
            setattr(row, field, value)
            changes[field] = value
    if "code" in fields:
        row.code = _normalized_code(body.code)
        changes["code"] = row.code
    row.version += 1
    changes.update({"version": row.version, "reason": body.reason})
    return _commit(db, row, user, "college.course.update", "college.academics.manage", changes)


@router.patch("/offerings/{offering_id}")
def update_offering(
    offering_id: str,
    body: OfferingUpdateBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    row = _editable_academic_row(db, user, CollegeCourseOffering, offering_id, "Course offering")
    access = _academic_access(db, user)
    _require_academic_row(access, "offerings", row)
    _require_version(row, body.version)
    _reject_null_patch_fields(body, "term_id", "course_id", "cohort_id", "status")
    fields = body.model_fields_set
    term_id = body.term_id if "term_id" in fields else row.term_id
    course_id = body.course_id if "course_id" in fields else row.course_id
    cohort_id = body.cohort_id if "cohort_id" in fields else row.cohort_id
    access.require_cohort(cohort_id)
    _offering_relations(db, user, term_id=term_id, course_id=course_id, cohort_id=cohort_id)
    changes = {}
    for field in ("term_id", "course_id", "cohort_id", "room", "status"):
        if field in fields:
            value = getattr(body, field)
            setattr(row, field, value)
            changes[field] = value
    if "faculty_employee_id" in fields:
        _employee(db, user, body.faculty_employee_id)
        row.faculty_employee_id = body.faculty_employee_id
        changes["faculty_employee_id"] = body.faculty_employee_id
    if "weekly_schedule" in fields:
        row.weekly_schedule = [item.model_dump(mode="json") for item in (body.weekly_schedule or [])]
        changes["weekly_schedule"] = row.weekly_schedule
    row.version += 1
    changes.update({"version": row.version, "reason": body.reason})
    return _commit(db, row, user, "college.offering.update", "college.academics.manage", changes)


AcademicResource = Literal["departments", "programs", "terms", "cohorts", "courses", "offerings"]


def _lifecycle_change(
    db: Session,
    user: User,
    resource: AcademicResource,
    record_id: str,
    body: AcademicLifecycleBody,
    *,
    restore: bool,
):
    model = ACADEMIC_MODELS[resource]
    row = tenant_row(db, model, record_id, user, resource.rstrip("s").replace("_", " ").title())
    _require_academic_row(_academic_access(db, user), resource, row)
    _require_version(row, body.version)
    if not restore:
        dependency_count = _dependency_count(db, user, resource, row.id)
        if dependency_count:
            labels = {
                "departments": "active programs",
                "programs": "active batches",
                "terms": "active course offerings",
                "cohorts": "active students",
                "courses": "active course offerings",
            }
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Archive the {dependency_count} {labels.get(resource, 'dependent records')} first",
            )
        if hasattr(row, "is_active"):
            row.is_active = False
        else:
            row.status = "archived"
            if hasattr(row, "is_current"):
                row.is_current = False
    else:
        if resource == "programs":
            parent = tenant_row(db, CollegeDepartment, row.department_id, user, "Department")
            if not parent.is_active:
                raise HTTPException(status.HTTP_409_CONFLICT, "Restore the department first")
        elif resource == "cohorts":
            parent = tenant_row(db, CollegeProgram, row.program_id, user, "Program")
            if not parent.is_active:
                raise HTTPException(status.HTTP_409_CONFLICT, "Restore the program first")
        elif resource == "courses":
            parent = tenant_row(db, CollegeDepartment, row.department_id, user, "Department")
            if not parent.is_active:
                raise HTTPException(status.HTTP_409_CONFLICT, "Restore the department first")
        elif resource == "offerings":
            term, course, cohort = _offering_relations(
                db, user, term_id=row.term_id, course_id=row.course_id, cohort_id=row.cohort_id,
            )
            if term.status == "archived" or not course.is_active or not cohort.is_active:
                raise HTTPException(status.HTTP_409_CONFLICT, "Restore the term, course, and batch first")
        if hasattr(row, "is_active"):
            row.is_active = True
        else:
            row.status = "planned" if resource == "terms" else "active"
    row.version += 1
    action = "restore" if restore else "archive"
    return _commit(
        db, row, user, f"college.{resource.rstrip('s')}.{action}",
        "college.academics.manage",
        {"reason": body.reason, "version": row.version},
    )


@router.post("/{resource}/{record_id}/archive")
def archive_academic_record(
    resource: AcademicResource,
    record_id: str,
    body: AcademicLifecycleBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    return _lifecycle_change(db, user, resource, record_id, body, restore=False)


@router.post("/{resource}/{record_id}/restore")
def restore_academic_record(
    resource: AcademicResource,
    record_id: str,
    body: AcademicLifecycleBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    return _lifecycle_change(db, user, resource, record_id, body, restore=True)


@router.post("/cohorts/bulk", status_code=status.HTTP_201_CREATED)
def create_cohorts_bulk(
    body: CohortBulkBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    program = tenant_row(db, CollegeProgram, body.program_id, user, "Program")
    _academic_access(db, user).require_program(program.id)
    if not program.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Restore the program before adding batches")
    if body.current_semester > program.duration_semesters:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Semester exceeds the program duration")
    _employee(db, user, body.advisor_employee_id)
    graduation_year = body.graduation_year or body.admission_year + ((program.duration_semesters + 1) // 2)
    payload = {
        "program_id": body.program_id,
        "admission_year": body.admission_year,
        "graduation_year": graduation_year,
        "current_semester": body.current_semester,
        "sections": body.sections,
        "advisor_employee_id": body.advisor_employee_id,
        "code_prefix": _normalized_code(body.code_prefix or f"{program.code}-{graduation_year}"),
    }
    request_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    existing = list(db.execute(select(CollegeCohort).where(
        CollegeCohort.organization_id == user.organization_id,
        CollegeCohort.bulk_operation_key == body.idempotency_key,
    ).order_by(CollegeCohort.section)).scalars())
    if existing:
        if any(row.bulk_request_hash != request_hash for row in existing):
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key was already used with different batch details")
        return {"items": [serialize(row) for row in existing], "replayed": True}
    conflicting_sections = set(db.execute(select(CollegeCohort.section).where(
        CollegeCohort.organization_id == user.organization_id,
        CollegeCohort.program_id == program.id,
        CollegeCohort.graduation_year == graduation_year,
        CollegeCohort.section.in_(body.sections),
    )).scalars())
    if conflicting_sections:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"These sections already exist for the selected program and graduation batch: {', '.join(sorted(conflicting_sections))}",
        )
    code_prefix = payload["code_prefix"]
    generated_codes = [
        f"{code_prefix}{'' if section == 'GENERAL' else f'-{section}'}"
        for section in body.sections
    ]
    if any(len(code) > 50 for code in generated_codes):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Generated batch codes exceed 50 characters; use a shorter code prefix or section name",
        )
    rows = []
    for section, generated_code in zip(body.sections, generated_codes):
        display_section = "" if section == "GENERAL" else f" / {section}"
        generated_name = f"{program.name} {graduation_year}{display_section}"
        row = CollegeCohort(
            organization_id=user.organization_id,
            program_id=program.id,
            name=generated_name[:120].rstrip(),
            code=generated_code,
            admission_year=body.admission_year,
            graduation_year=graduation_year,
            current_semester=body.current_semester,
            section=section,
            advisor_employee_id=body.advisor_employee_id,
            bulk_operation_key=body.idempotency_key,
            bulk_request_hash=request_hash,
        )
        db.add(row)
        rows.append(row)
    try:
        db.flush()
        for row in rows:
            log_action(
                db, organization_id=user.organization_id, user_id=user.id,
                action="college.cohort.create", resource_type=row.__tablename__, resource_id=row.id,
                permission="college.academics.manage",
                changes={"bulk": True, "program_id": program.id, "section": row.section},
            )
        db.commit()
        return {"items": [serialize(row) for row in rows], "replayed": False}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "One or more generated batch names, codes, or sections already exist") from exc


STRUCTURE_OVERRIDE_FIELDS = {
    "departments": {"name", "code", "location_id", "hod_employee_id", "description"},
    "programs": {"name", "code", "department_id", "degree_type", "duration_semesters"},
    "terms": {"name", "academic_year", "term_number", "starts_on", "ends_on", "status", "is_current"},
    "cohorts": {"name", "code", "program_id", "admission_year", "graduation_year", "current_semester", "section", "advisor_employee_id"},
    "courses": {"name", "code", "department_id", "credits", "course_type"},
}


def _validated_override_fields(resource: StructureResource, values: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
    unsupported = set(normalized) - STRUCTURE_OVERRIDE_FIELDS[resource]
    if unsupported:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unsupported override fields: {', '.join(sorted(unsupported))}",
        )
    return normalized


@router.post("/integrations/structure-links", status_code=status.HTTP_201_CREATED)
def create_structure_link(
    body: StructureLinkBody,
    user: User = Depends(require_permissions("college.academics.manage", "college.integrations.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    connector = tenant_row(db, CollegeDataConnector, body.connector_id, user, "ERP connector")
    model, local_type = STRUCTURE_LINK_MODELS[body.resource_type]
    local = tenant_row(db, model, body.local_resource_id, user, body.resource_type.rstrip("s").title())
    _require_academic_row(_academic_access(db, user), body.resource_type, local)
    existing = db.execute(select(CollegeExternalRecord).where(
        CollegeExternalRecord.connector_id == connector.id,
        CollegeExternalRecord.resource_type == body.resource_type,
        CollegeExternalRecord.external_id == body.external_id.strip(),
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "This ERP record is already linked")
    row = CollegeExternalRecord(
        organization_id=user.organization_id,
        connector_id=connector.id,
        resource_type=body.resource_type,
        external_id=body.external_id.strip(),
        local_resource_type=local_type,
        local_resource_id=local.id,
        manual_override_fields=_validated_override_fields(body.resource_type, body.manual_override_fields),
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(row)
    return _commit(
        db, row, user, "college.integration.structure_link.create",
        "college.academics.manage",
        {"resource_type": body.resource_type, "local_resource_id": local.id},
    )


@router.patch("/integrations/structure-links/{link_id}")
def update_structure_link(
    link_id: str,
    body: StructureLinkUpdateBody,
    user: User = Depends(require_permissions("college.academics.manage", "college.integrations.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    row = tenant_row(db, CollegeExternalRecord, link_id, user, "ERP structure link")
    if row.resource_type not in STRUCTURE_LINK_MODELS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only academic structure links can be changed here")
    model, _ = STRUCTURE_LINK_MODELS[row.resource_type]
    local = tenant_row(db, model, row.local_resource_id, user, row.resource_type.rstrip("s").title())
    _require_academic_row(_academic_access(db, user), row.resource_type, local)
    row.manual_override_fields = _validated_override_fields(row.resource_type, body.manual_override_fields)
    return _commit(
        db, row, user, "college.integration.structure_link.update",
        "college.academics.manage",
        {"manual_override_fields": row.manual_override_fields},
    )


@router.post("/students", status_code=201)
def admit_student(body: StudentBody, user: User = Depends(require_permissions("college.students.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    access = resolve_college_access(db, user, "students")
    if policy_v2_enabled(db, user.organization_id):
        context = resolve_policy_context(db, user)
        if any((body.email, body.phone, body.address)) and not context.has_sensitive("college.students.contact.view"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Student contact access is required")
        if body.guardian and not context.has_sensitive("college.students.guardian.view"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Guardian access is required")
        if any((body.date_of_birth, body.gender, body.category)) and not context.has_sensitive("college.protected_fields.view"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Protected student field access is required")
    program = tenant_row(db, CollegeProgram, body.program_id, user, "Program")
    cohort = tenant_row(db, CollegeCohort, body.cohort_id, user, "Cohort")
    access.require_program(program.id)
    access.require_cohort(cohort.id)
    if not program.is_active or not cohort.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Complete or restore Academic structure before admitting students")
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
    access = resolve_college_access(db, user, "attendance")
    access.require_course_offering(offering.id)
    students = _validate_attendance_students(db, user, offering, body.records)
    for student_id in students:
        access.require_student(student_id)
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
    access = resolve_college_access(db, user, "attendance")
    access.require_course_offering(offering.id)
    students = _validate_attendance_students(db, user, offering, body.records)
    for student_id in students:
        access.require_student(student_id)
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
    session = tenant_row(db, CollegeAttendanceSession, session_id, user, "Attendance session")
    access = resolve_college_access(db, user, "attendance")
    access.require_course_offering(session.offering_id)
    rows = db.execute(select(CollegeAttendanceRecord, CollegeStudentProfile, Client).join(
        CollegeStudentProfile, CollegeStudentProfile.id == CollegeAttendanceRecord.student_profile_id,
    ).join(Client, Client.id == CollegeStudentProfile.client_id).where(
        CollegeAttendanceRecord.organization_id == user.organization_id,
        CollegeAttendanceRecord.session_id == session_id,
    ).order_by(Client.first_name, Client.last_name)).all()
    if not access.unrestricted:
        rows = [row for row in rows if row[1].id in access.student_ids]
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
    access = resolve_college_access(db, user, "attendance")
    access.require_course_offering(offering.id)
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
    offering = tenant_row(db, CollegeCourseOffering, body.offering_id, user, "Course offering")
    access = resolve_college_access(db, user, "assessments")
    access.require_course_offering(offering.id)
    row = CollegeAssessment(
        organization_id=user.organization_id, **body.model_dump(),
        published_at=datetime.now(timezone.utc) if body.status == "published" else None,
    )
    db.add(row)
    return _commit(db, row, user, "college.assessment.create", "college.assessments.manage")


@router.put("/assessments/{assessment_id}/scores")
def save_scores(assessment_id: str, body: ScoresBody, user: User = Depends(require_permissions("college.assessments.record")), db: Session = Depends(get_db)):
    require_college(db, user)
    assessment = tenant_row(db, CollegeAssessment, assessment_id, user, "Assessment")
    offering = tenant_row(db, CollegeCourseOffering, assessment.offering_id, user, "Course offering") if assessment.offering_id else None
    access = resolve_college_access(db, user, "assessments")
    if offering:
        access.require_course_offering(offering.id)
    cohort_id = assessment.cohort_id or (offering.cohort_id if offering else None)
    if not cohort_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This assessment has no student cohort")
    ids = {item.student_profile_id for item in body.scores}
    if len(ids) != len(body.scores):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A student can appear only once")
    students = {row.id: row for row in db.execute(select(CollegeStudentProfile).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.id.in_(ids),
    )).scalars()}
    if len(students) != len(ids) or any(row.cohort_id != cohort_id for row in students.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scores can only include students from the assessment cohort")
    for student_id in students:
        access.require_student(student_id)
    existing = {row.student_profile_id: row for row in db.execute(select(CollegeAssessmentScore).where(
        CollegeAssessmentScore.organization_id == user.organization_id,
        CollegeAssessmentScore.assessment_id == assessment.id,
    )).scalars()}
    configured = bool(assessment.metric_schema)
    cycle = db.get(CollegeExamCycle, assessment.exam_cycle_id) if assessment.exam_cycle_id else None
    published_correction = assessment.status == "published"
    if published_correction:
        permissions = get_user_permissions(db, user)
        if "college.assessments.correct" not in permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Published results require assessment correction access")
        if not body.correction_reason or len(body.correction_reason.strip()) < 3:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A correction reason is required for published results")
    audit_changes = []
    for item in body.scores:
        if item.marks_awarded is not None and item.marks_awarded > assessment.max_marks:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Awarded marks cannot exceed maximum marks")
        row = existing.get(item.student_profile_id)
        if row and item.version is not None and item.version != row.version:
            raise HTTPException(status.HTTP_409_CONFLICT, "A score changed after this register loaded. Refresh and try again")
        metrics = dict(item.metrics or {})
        if configured:
            if not metrics and item.marks_awarded is not None and len(assessment.metric_schema) == 1:
                metrics[str(assessment.metric_schema[0]["code"])] = float(item.marks_awarded)
            try:
                metrics = validate_metric_values(assessment.metric_schema, metrics, allow_partial=False)
            except ValueError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        calculated = None
        before = {
            "marks_awarded": float(row.marks_awarded) if row and row.marks_awarded is not None else None,
            "grade": row.grade if row else None,
            "feedback": row.feedback if row else None,
            "metrics": dict(row.metrics or {}) if row else {},
            "calculated_score": float(row.calculated_score) if row and row.calculated_score is not None else None,
        }
        values = {
            "student_profile_id": item.student_profile_id,
            "marks_awarded": item.marks_awarded,
            "grade": item.grade,
            "feedback": item.feedback,
            "metrics": metrics,
            "calculated_score": calculated,
        }
        if row:
            for key, value in values.items():
                if key == "student_profile_id":
                    continue
                setattr(row, key, value)
            row.graded_by_user_id = user.id
            row.version += 1
        else:
            row = CollegeAssessmentScore(
                organization_id=user.organization_id, assessment_id=assessment.id,
                graded_by_user_id=user.id, **values,
            )
            db.add(row)
        db.flush()
        if configured and cycle:
            calculated = recalculate_assessment_score(db, assessment, item.student_profile_id)
            row.calculated_score = calculated
        audit_changes.append({
            "student_profile_id": item.student_profile_id,
            "before": before,
            "after": {
                "marks_awarded": float(item.marks_awarded) if item.marks_awarded is not None else None,
                "grade": item.grade,
                "feedback": item.feedback,
                "metrics": metrics,
                "calculated_score": float(calculated) if calculated is not None else None,
            },
        })
    if body.publish:
        assessment.status = "published"
        assessment.published_at = datetime.now(timezone.utc)
    assessment.version += 1
    return _commit(db, assessment, user, "college.assessment.correct" if published_correction else "college.assessment.score", "college.assessments.correct" if published_correction else "college.assessments.record", {
        "score_count": len(body.scores), "published": body.publish,
        "correction_reason": body.correction_reason if published_correction else None,
        "scores": audit_changes,
    })


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
    offering = tenant_row(db, CollegeCourseOffering, assessment.offering_id, user, "Course offering") if assessment.offering_id else None
    cohort_id = assessment.cohort_id or (offering.cohort_id if offering else None)
    if not cohort_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This assessment has no student cohort")
    access = resolve_college_access(db, user, "assessments")
    if offering:
        access.require_course_offering(offering.id)
    else:
        access.require_cohort(cohort_id)
    filters = {"assessment_id": assessment_id, "q": q}
    values = decode_cursor(cursor, scope="college.assessment-register", organization_id=user.organization_id, filters=filters)
    statement = select(CollegeStudentProfile, Client, CollegeAssessmentScore).join(
        Client, Client.id == CollegeStudentProfile.client_id,
    ).outerjoin(CollegeAssessmentScore, and_(
        CollegeAssessmentScore.assessment_id == assessment.id,
        CollegeAssessmentScore.student_profile_id == CollegeStudentProfile.id,
    )).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.cohort_id == cohort_id,
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
        CollegeStudentProfile.cohort_id == cohort_id,
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
        "version": score.version if score else None,
        "marks_awarded": float(score.marks_awarded) if score and score.marks_awarded is not None else None,
        "grade": score.grade if score else None,
        "feedback": score.feedback if score else None,
        "metrics": score.metrics if score else {},
        "calculated_score": float(score.calculated_score) if score and score.calculated_score is not None else None,
    } for profile, client, score in rows]
    next_cursor = encode_cursor(
        scope="college.assessment-register", organization_id=user.organization_id, filters=filters,
        values={"first": rows[-1][1].first_name.casefold(), "last": rows[-1][1].last_name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return {
        **page_response(items, next_cursor),
        "assessment": {**serialize(assessment), "metric_schema": assessment.metric_schema or []},
        "summary": {"total": int(total), "scored": int(scored), "unscored": max(0, int(total) - int(scored))},
    }


@router.get("/internship-clearance/page")
def internship_clearance_page(
    q: str | None = None,
    clearance: Literal["all", "cleared", "pending", "needs_review"] = "all",
    cohort_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_any_permission("college.clearance.view", "college.placements.view", "college.fees.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "clearance")
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
    local_status = case(
        (func.coalesce(fee_summary.c.assigned_count, 0) == 0, "needs_review"),
        (func.coalesce(fee_summary.c.outstanding_paise, 0) > 0, "pending"),
        else_="cleared",
    )
    ranked_clearance = select(
        CollegeClearanceSnapshot.student_profile_id,
        CollegeClearanceSnapshot.status,
        CollegeClearanceSnapshot.source_type,
        CollegeClearanceSnapshot.source_updated_at,
        func.row_number().over(
            partition_by=CollegeClearanceSnapshot.student_profile_id,
            order_by=(
                CollegeClearanceSnapshot.source_updated_at.desc(),
                CollegeClearanceSnapshot.id.desc(),
            ),
        ).label("rank"),
    ).where(
        CollegeClearanceSnapshot.organization_id == user.organization_id,
    ).subquery()
    latest_clearance = select(
        ranked_clearance.c.student_profile_id,
        ranked_clearance.c.status,
        ranked_clearance.c.source_type,
        ranked_clearance.c.source_updated_at,
    ).where(ranked_clearance.c.rank == 1).subquery()
    stale_before = datetime.now(timezone.utc) - timedelta(days=7)
    imported_status = case(
        (latest_clearance.c.source_updated_at < stale_before, "needs_review"),
        else_=latest_clearance.c.status,
    )
    status_expression = case(
        (latest_clearance.c.student_profile_id.is_not(None), imported_status),
        else_=local_status,
    )
    source_updated_at = func.coalesce(
        latest_clearance.c.source_updated_at,
        fee_summary.c.source_updated_at,
    )
    source_type = case(
        (latest_clearance.c.student_profile_id.is_not(None), latest_clearance.c.source_type),
        (fee_summary.c.student_profile_id.is_not(None), "local_fees"),
        else_=None,
    )
    statement = select(
        CollegeStudentProfile, Client, CollegeProgram, CollegeCohort,
        status_expression.label("clearance_status"), source_updated_at.label("source_updated_at"),
        source_type.label("source_type"),
    ).join(Client, Client.id == CollegeStudentProfile.client_id).join(
        CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id,
    ).join(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id).outerjoin(
        fee_summary, fee_summary.c.student_profile_id == CollegeStudentProfile.id,
    ).outerjoin(
        latest_clearance, latest_clearance.c.student_profile_id == CollegeStudentProfile.id,
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
        "source_type": row.source_type,
        "is_stale": bool(row.source_type and row.source_updated_at and row.source_updated_at < stale_before),
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.internship-clearance", organization_id=user.organization_id, filters=filters,
        values={"first": rows[-1][1].first_name.casefold(), "last": rows[-1][1].last_name.casefold(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.post("/fee-plans", status_code=201)
def create_fee_plan(body: FeePlanBody, user: User = Depends(require_permissions("college.fees.manage")), db: Session = Depends(get_db)):
    require_college(db, user)
    if policy_v2_enabled(db, user.organization_id):
        context = require_policy_domain(db, user, "clearance", "manage")
        if not context.has_sensitive("college.fees.manage"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Finance management access is required")
    access = resolve_college_access(db, user, "clearance")
    program = tenant_row(db, CollegeProgram, body.program_id, user, "Program") if body.program_id else None
    cohort = tenant_row(db, CollegeCohort, body.cohort_id, user, "Cohort") if body.cohort_id else None
    if program:
        access.require_program(program.id)
    if cohort:
        access.require_cohort(cohort.id)
    if not program and not cohort:
        _require_whole_college(access, "institution-wide fee plans")
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
    if policy_v2_enabled(db, user.organization_id):
        context = require_policy_domain(db, user, "clearance", "work")
        if not context.has_sensitive("college.fees.manage"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Finance management access is required")
    access = resolve_college_access(db, user, "clearance")
    student = tenant_row(db, CollegeStudentProfile, body.student_profile_id, user, "Student")
    access.require_student(student.id)
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
