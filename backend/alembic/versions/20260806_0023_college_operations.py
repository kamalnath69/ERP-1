"""Add the College industry and academic operations foundation.

Revision ID: 20260806_0023
Revises: 20260806_0022
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260806_0023"
down_revision = "20260806_0022"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _tenant():
    return sa.Column(
        "organization_id", UUID,
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )


def upgrade():
    # PostgreSQL enum values are intentionally retained on downgrade because removing
    # a value safely requires rebuilding the type and every dependent column.
    op.execute("ALTER TYPE industry ADD VALUE IF NOT EXISTS 'college'")

    op.create_table(
        "college_departments",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("location_id", UUID, sa.ForeignKey("locations.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("hod_employee_id", UUID, sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_college_department_org_code"),
    )
    op.create_table(
        "college_programs",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("department_id", UUID, sa.ForeignKey("college_departments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("degree_type", sa.String(50), nullable=False),
        sa.Column("duration_semesters", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_college_program_org_code"),
    )
    op.create_table(
        "college_terms",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("academic_year", sa.String(20), nullable=False),
        sa.Column("term_number", sa.Integer(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "academic_year", "term_number", name="uq_college_term_org_year_number"),
    )
    op.create_table(
        "college_cohorts",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("program_id", UUID, sa.ForeignKey("college_programs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("admission_year", sa.Integer(), nullable=False),
        sa.Column("current_semester", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(20)),
        sa.Column("advisor_employee_id", UUID, sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_college_cohort_org_code"),
    )
    op.create_table(
        "college_student_profiles",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admission_number", sa.String(60), nullable=False),
        sa.Column("roll_number", sa.String(60)),
        sa.Column("program_id", UUID, sa.ForeignKey("college_programs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cohort_id", UUID, sa.ForeignKey("college_cohorts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("current_semester", sa.Integer(), nullable=False),
        sa.Column("admitted_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("guardian", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("category", sa.String(40)),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", name="uq_college_student_client"),
        sa.UniqueConstraint("organization_id", "admission_number", name="uq_college_student_org_admission"),
        sa.UniqueConstraint("organization_id", "roll_number", name="uq_college_student_org_roll"),
    )
    op.create_table(
        "college_courses",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("department_id", UUID, sa.ForeignKey("college_departments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("course_type", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_college_course_org_code"),
    )
    op.create_table(
        "college_course_offerings",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("term_id", UUID, sa.ForeignKey("college_terms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("course_id", UUID, sa.ForeignKey("college_courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cohort_id", UUID, sa.ForeignKey("college_cohorts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("faculty_employee_id", UUID, sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("room", sa.String(60)),
        sa.Column("weekly_schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term_id", "course_id", "cohort_id", name="uq_college_offering_term_course_cohort"),
    )
    op.create_table(
        "college_attendance_sessions",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("offering_id", UUID, sa.ForeignKey("college_course_offerings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.Time()),
        sa.Column("ends_at", sa.Time()),
        sa.Column("topic", sa.String(300)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("recorded_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_attendance_records",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("session_id", UUID, sa.ForeignKey("college_attendance_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("note", sa.String(300)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "student_profile_id", name="uq_college_attendance_session_student"),
    )
    op.create_table(
        "college_assessments",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("offering_id", UUID, sa.ForeignKey("college_course_offerings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("assessment_type", sa.String(30), nullable=False),
        sa.Column("max_marks", sa.Numeric(8, 2), nullable=False),
        sa.Column("weightage_bps", sa.Integer(), nullable=False),
        sa.Column("due_on", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_assessment_scores",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("assessment_id", UUID, sa.ForeignKey("college_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("marks_awarded", sa.Numeric(8, 2)),
        sa.Column("grade", sa.String(12)),
        sa.Column("feedback", sa.Text()),
        sa.Column("graded_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "student_profile_id", name="uq_college_score_assessment_student"),
    )
    op.create_table(
        "college_fee_plans",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("program_id", UUID, sa.ForeignKey("college_programs.id", ondelete="SET NULL")),
        sa.Column("cohort_id", UUID, sa.ForeignKey("college_cohorts.id", ondelete="SET NULL")),
        sa.Column("term_id", UUID, sa.ForeignKey("college_terms.id", ondelete="SET NULL")),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("due_on", sa.Date()),
        sa.Column("line_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_student_fees",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fee_plan_id", UUID, sa.ForeignKey("college_fee_plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("sale_invoices.id", ondelete="SET NULL")),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("concession_paise", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_profile_id", "fee_plan_id", name="uq_college_student_fee_plan"),
    )

    indexes = {
        "college_departments": ["organization_id", "location_id", "hod_employee_id"],
        "college_programs": ["organization_id", "department_id"],
        "college_terms": ["organization_id", "academic_year", "status", "is_current"],
        "college_cohorts": ["organization_id", "program_id", "admission_year", "advisor_employee_id"],
        "college_student_profiles": ["organization_id", "client_id", "admission_number", "roll_number", "program_id", "cohort_id", "status"],
        "college_courses": ["organization_id", "department_id"],
        "college_course_offerings": ["organization_id", "term_id", "course_id", "cohort_id", "faculty_employee_id", "status"],
        "college_attendance_sessions": ["organization_id", "offering_id", "held_on", "status", "recorded_by_user_id"],
        "college_attendance_records": ["organization_id", "session_id", "student_profile_id", "status"],
        "college_assessments": ["organization_id", "offering_id", "due_on", "status"],
        "college_assessment_scores": ["organization_id", "assessment_id", "student_profile_id", "graded_by_user_id"],
        "college_fee_plans": ["organization_id", "program_id", "cohort_id", "term_id"],
        "college_student_fees": ["organization_id", "student_profile_id", "fee_plan_id", "invoice_id", "status"],
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in (
        "college_student_fees", "college_fee_plans", "college_assessment_scores",
        "college_assessments", "college_attendance_records", "college_attendance_sessions",
        "college_course_offerings", "college_courses", "college_student_profiles",
        "college_cohorts", "college_terms", "college_programs", "college_departments",
    ):
        op.drop_table(table)

