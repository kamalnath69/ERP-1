"""Add composite indexes for tenant-bound cursor pagination.

Revision ID: 20260810_0026
Revises: 20260806_0025
"""
from alembic import op


revision = "20260810_0026"
down_revision = "20260806_0025"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_clients_org_created_id", "clients", ["organization_id", "created_at", "id"]),
    ("ix_employees_org_status_name_id", "employees", ["organization_id", "status", "first_name", "last_name", "id"]),
    ("ix_sales_org_created_id", "sale_invoices", ["organization_id", "created_at", "id"]),
    ("ix_college_students_org_status_cohort_admission_id", "college_student_profiles", ["organization_id", "status", "cohort_id", "admission_number", "id"]),
    ("ix_college_cohorts_org_program_name_id", "college_cohorts", ["organization_id", "program_id", "name", "id"]),
    ("ix_college_attendance_org_held_id", "college_attendance_sessions", ["organization_id", "held_on", "id"]),
    ("ix_college_assessments_org_due_created_id", "college_assessments", ["organization_id", "due_on", "created_at", "id"]),
    ("ix_college_companies_org_active_name_id", "college_placement_companies", ["organization_id", "is_active", "name", "id"]),
    ("ix_college_opportunities_org_status_deadline_id", "college_placement_opportunities", ["organization_id", "status", "deadline_at", "id"]),
    ("ix_college_applications_org_stage_updated_id", "college_placement_applications", ["organization_id", "current_stage_id", "updated_at", "id"]),
    ("ix_college_imports_org_created_id", "college_import_runs", ["organization_id", "created_at", "id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
