"""College academic operations built on shared clients, employees, and invoices."""
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
    Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class CollegeDepartment(TimestampMixin, Base):
    __tablename__ = "college_departments"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_college_department_org_code"),
        Index("ix_college_departments_org_active_name_id", "organization_id", "is_active", "name", "id"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    hod_employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeProgram(TimestampMixin, Base):
    __tablename__ = "college_programs"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_college_program_org_code"),
        Index(
            "ix_college_programs_org_department_active_name_id",
            "organization_id", "department_id", "is_active", "name", "id",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    department_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_departments.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    degree_type: Mapped[str] = mapped_column(String(50), default="undergraduate", nullable=False)
    duration_semesters: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeTerm(TimestampMixin, Base):
    __tablename__ = "college_terms"
    __table_args__ = (
        UniqueConstraint("organization_id", "academic_year", "term_number", name="uq_college_term_org_year_number"),
        Index("ix_college_terms_org_status_starts_id", "organization_id", "status", "starts_on", "id"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    term_number: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeCohort(TimestampMixin, Base):
    __tablename__ = "college_cohorts"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_college_cohort_org_code"),
        UniqueConstraint(
            "organization_id", "program_id", "graduation_year", "section",
            name="uq_college_cohort_org_program_graduation_section",
        ),
        UniqueConstraint(
            "organization_id", "bulk_operation_key", "section",
            name="uq_college_cohort_org_bulk_section",
        ),
        Index(
            "ix_college_cohorts_org_graduation_program_section_id",
            "organization_id", "graduation_year", "program_id", "section", "id",
        ),
        Index("ix_college_cohorts_org_active_name_id", "organization_id", "is_active", "name", "id"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    program_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_programs.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    admission_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    graduation_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    current_semester: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    section: Mapped[str] = mapped_column(String(20), default="GENERAL", nullable=False)
    advisor_employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    bulk_operation_key: Mapped[str | None] = mapped_column(String(120), index=True)
    bulk_request_hash: Mapped[str | None] = mapped_column(String(64))


class CollegeStudentProfile(TimestampMixin, Base):
    __tablename__ = "college_student_profiles"
    __table_args__ = (
        UniqueConstraint("client_id", name="uq_college_student_client"),
        UniqueConstraint("organization_id", "admission_number", name="uq_college_student_org_admission"),
        UniqueConstraint("organization_id", "roll_number", name="uq_college_student_org_roll"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    admission_number: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    roll_number: Mapped[str | None] = mapped_column(String(60), index=True)
    program_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_programs.id", ondelete="RESTRICT"), index=True)
    cohort_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_cohorts.id", ondelete="RESTRICT"), index=True)
    current_semester: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    admitted_on: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    guardian: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    category: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeCourse(TimestampMixin, Base):
    __tablename__ = "college_courses"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_college_course_org_code"),
        Index(
            "ix_college_courses_org_department_active_name_id",
            "organization_id", "department_id", "is_active", "name", "id",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    department_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_departments.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    course_type: Mapped[str] = mapped_column(String(30), default="core", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeCourseOffering(TimestampMixin, Base):
    __tablename__ = "college_course_offerings"
    __table_args__ = (
        UniqueConstraint("term_id", "course_id", "cohort_id", name="uq_college_offering_term_course_cohort"),
        Index(
            "ix_college_offerings_org_status_created_id",
            "organization_id", "status", "created_at", "id",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    term_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_terms.id", ondelete="RESTRICT"), index=True)
    course_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_courses.id", ondelete="RESTRICT"), index=True)
    cohort_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_cohorts.id", ondelete="RESTRICT"), index=True)
    faculty_employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    room: Mapped[str | None] = mapped_column(String(60))
    weekly_schedule: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeAttendanceSession(TimestampMixin, Base):
    __tablename__ = "college_attendance_sessions"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    offering_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_course_offerings.id", ondelete="RESTRICT"), index=True)
    held_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    starts_at: Mapped[time | None] = mapped_column(Time)
    ends_at: Mapped[time | None] = mapped_column(Time)
    topic: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    recorded_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), index=True)


class CollegeAttendanceRecord(TimestampMixin, Base):
    __tablename__ = "college_attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_profile_id", name="uq_college_attendance_session_student"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    session_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_attendance_sessions.id", ondelete="CASCADE"), index=True)
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="present", nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(String(300))


class CollegeAssessmentScheme(TimestampMixin, Base):
    __tablename__ = "college_assessment_schemes"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "code", "version_number",
            name="uq_college_assessment_scheme_code_version",
        ),
        Index(
            "ix_college_assessment_schemes_org_domain_status_name",
            "organization_id", "domain", "status", "name", "id",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    domain: Mapped[str] = mapped_column(String(30), default="academic", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_scheme_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("college_assessment_schemes.id", ondelete="SET NULL"), index=True,
    )
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    final_score_max: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=100, nullable=False)
    calculation_method: Mapped[str] = mapped_column(String(30), default="weighted_sum", nullable=False)
    calculation_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeAssessmentComponent(TimestampMixin, Base):
    __tablename__ = "college_assessment_components"
    __table_args__ = (
        UniqueConstraint("scheme_id", "code", name="uq_college_assessment_component_scheme_code"),
        UniqueConstraint("scheme_id", "display_order", name="uq_college_assessment_component_order"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    scheme_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("college_assessment_schemes.id", ondelete="CASCADE"), index=True,
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    component_type: Mapped[str] = mapped_column(String(50), default="assessment", nullable=False)
    metric_type: Mapped[str] = mapped_column(String(24), default="number", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    max_marks: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    weightage_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_marks: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    aggregation_group: Mapped[str | None] = mapped_column(String(50))
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class CollegeAssessmentSchemeAssignment(TimestampMixin, Base):
    __tablename__ = "college_assessment_scheme_assignments"
    __table_args__ = (
        UniqueConstraint("organization_id", "scope_key", name="uq_college_assessment_assignment_scope"),
        Index(
            "ix_college_assessment_assignments_org_active_scope",
            "organization_id", "is_active", "scope_key", "id",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    scheme_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("college_assessment_schemes.id", ondelete="RESTRICT"), index=True,
    )
    program_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("college_programs.id", ondelete="CASCADE"), index=True,
    )
    cohort_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("college_cohorts.id", ondelete="CASCADE"), index=True,
    )
    term_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("college_terms.id", ondelete="CASCADE"), index=True,
    )
    scope_key: Mapped[str] = mapped_column(String(180), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeAssessmentReadinessMapping(TimestampMixin, Base):
    __tablename__ = "college_assessment_readiness_mappings"
    __table_args__ = (
        UniqueConstraint(
            "scheme_id", "metric_code",
            name="uq_college_assessment_readiness_scheme_metric",
        ),
        Index(
            "ix_college_assessment_readiness_org_active_factor",
            "organization_id", "is_active", "factor_key", "scheme_id",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    scheme_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("college_assessment_schemes.id", ondelete="CASCADE"), index=True,
    )
    metric_code: Mapped[str] = mapped_column(String(50), nullable=False)
    factor_key: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    mapped_by_user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeExamCycle(TimestampMixin, Base):
    __tablename__ = "college_exam_cycles"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_college_exam_cycle_org_code"),
        Index(
            "ix_college_exam_cycles_org_term_status_date",
            "organization_id", "term_id", "status", "held_on", "id",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    scheme_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("college_assessment_schemes.id", ondelete="RESTRICT"), index=True,
    )
    scheme_component_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("college_assessment_components.id", ondelete="RESTRICT"), index=True,
    )
    term_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("college_terms.id", ondelete="RESTRICT"), index=True,
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    domain: Mapped[str] = mapped_column(String(30), default="academic", nullable=False, index=True)
    held_on: Mapped[date | None] = mapped_column(Date, index=True)
    due_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    target_cohort_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    target_offering_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    scheme_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeAssessment(TimestampMixin, Base):
    __tablename__ = "college_assessments"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    offering_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_course_offerings.id", ondelete="RESTRICT"), index=True)
    cohort_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_cohorts.id", ondelete="RESTRICT"), index=True)
    exam_cycle_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_exam_cycles.id", ondelete="SET NULL"), index=True)
    scheme_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_assessment_schemes.id", ondelete="SET NULL"), index=True)
    scheme_component_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_assessment_components.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    assessment_type: Mapped[str] = mapped_column(String(30), default="internal", nullable=False)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=100, nullable=False)
    weightage_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metric_schema: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeAssessmentScore(TimestampMixin, Base):
    __tablename__ = "college_assessment_scores"
    __table_args__ = (UniqueConstraint("assessment_id", "student_profile_id", name="uq_college_score_assessment_student"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    assessment_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_assessments.id", ondelete="CASCADE"), index=True)
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    marks_awarded: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    grade: Mapped[str | None] = mapped_column(String(12))
    feedback: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    calculated_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    graded_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)


class CollegeFeePlan(TimestampMixin, Base):
    __tablename__ = "college_fee_plans"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    program_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_programs.id", ondelete="SET NULL"), index=True)
    cohort_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_cohorts.id", ondelete="SET NULL"), index=True)
    term_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_terms.id", ondelete="SET NULL"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date)
    line_items: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CollegeStudentFee(TimestampMixin, Base):
    __tablename__ = "college_student_fees"
    __table_args__ = (UniqueConstraint("student_profile_id", "fee_plan_id", name="uq_college_student_fee_plan"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    fee_plan_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_fee_plans.id", ondelete="RESTRICT"), index=True)
    invoice_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("sale_invoices.id", ondelete="SET NULL"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    concession_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="assigned", nullable=False, index=True)
