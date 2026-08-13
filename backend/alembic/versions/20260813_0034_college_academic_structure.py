"""Add managed College academic structure lifecycle fields.

Revision ID: 20260813_0034
Revises: 20260813_0033
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260813_0034"
down_revision = "20260813_0033"
branch_labels = None
depends_on = None


MANAGED_TABLES = (
    "college_departments",
    "college_programs",
    "college_terms",
    "college_cohorts",
    "college_courses",
    "college_course_offerings",
)

PAGINATION_INDEXES = (
    ("ix_college_departments_org_active_name_id", "college_departments", ["organization_id", "is_active", "name", "id"]),
    ("ix_college_programs_org_department_active_name_id", "college_programs", ["organization_id", "department_id", "is_active", "name", "id"]),
    ("ix_college_terms_org_status_starts_id", "college_terms", ["organization_id", "status", "starts_on", "id"]),
    ("ix_college_cohorts_org_active_name_id", "college_cohorts", ["organization_id", "is_active", "name", "id"]),
    ("ix_college_courses_org_department_active_name_id", "college_courses", ["organization_id", "department_id", "is_active", "name", "id"]),
    ("ix_college_offerings_org_status_created_id", "college_course_offerings", ["organization_id", "status", "created_at", "id"]),
)

ACADEMIC_READ_ROLES = (
    "owner",
    "principal",
    "placement-head",
    "placement-coordinator",
    "hod",
    "academic-admin",
    "faculty",
    "admissions",
)

ACADEMIC_MANAGE_ROLES = ("owner", "academic-admin")


def upgrade() -> None:
    for table_name in MANAGED_TABLES:
        op.add_column(
            table_name,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )

    op.add_column("college_cohorts", sa.Column("bulk_operation_key", sa.String(length=120), nullable=True))
    op.add_column("college_cohorts", sa.Column("bulk_request_hash", sa.String(length=64), nullable=True))

    op.execute(
        """
        UPDATE college_cohorts
        SET section = COALESCE(NULLIF(UPPER(BTRIM(section)), ''), 'GENERAL')
        """
    )
    # Preserve every legacy row while making logical duplicates explicit before
    # the new uniqueness rule is installed.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY organization_id, program_id, graduation_year, section
                       ORDER BY created_at, id
                   ) AS duplicate_number
            FROM college_cohorts
        )
        UPDATE college_cohorts AS cohort
        SET section = LEFT(cohort.section, 11) || '-' || LEFT(REPLACE(cohort.id::text, '-', ''), 8)
        FROM ranked
        WHERE ranked.id = cohort.id AND ranked.duplicate_number > 1
        """
    )
    op.alter_column(
        "college_cohorts",
        "section",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="GENERAL",
    )
    op.create_unique_constraint(
        "uq_college_cohort_org_program_graduation_section",
        "college_cohorts",
        ["organization_id", "program_id", "graduation_year", "section"],
    )
    op.create_unique_constraint(
        "uq_college_cohort_org_bulk_section",
        "college_cohorts",
        ["organization_id", "bulk_operation_key", "section"],
    )
    op.create_index(
        "ix_college_cohorts_bulk_operation_key",
        "college_cohorts",
        ["bulk_operation_key"],
    )
    for name, table_name, columns in PAGINATION_INDEXES:
        op.create_index(name, table_name, columns)

    connection = op.get_bind()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {"code": "college.academics.view"},
    ).scalar_one_or_none()
    if permission_id is None:
        permission_id = str(uuid4())
        connection.execute(sa.text("""
            INSERT INTO permissions
                (id, code, label, module, description, organization_id, created_at, updated_at)
            VALUES
                (:id, :code, :label, :module, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {
            "id": permission_id,
            "code": "college.academics.view",
            "label": "View academic structure and course offerings",
            "module": "college",
        })

    role_ids = connection.execute(sa.text("""
        SELECT id FROM roles WHERE slug IN :slugs
    """).bindparams(sa.bindparam("slugs", expanding=True)), {
        "slugs": list(ACADEMIC_READ_ROLES),
    }).scalars().all()
    for role_id in role_ids:
        exists = connection.execute(sa.text("""
            SELECT 1 FROM role_permissions
            WHERE role_id = :role_id AND permission_id = :permission_id
        """), {"role_id": role_id, "permission_id": permission_id}).first()
        if not exists:
            connection.execute(sa.text("""
                INSERT INTO role_permissions (id, role_id, permission_id)
                VALUES (:id, :role_id, :permission_id)
            """), {
                "id": str(uuid4()),
                "role_id": role_id,
                "permission_id": permission_id,
            })

    manage_permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {"code": "college.academics.manage"},
    ).scalar_one_or_none()
    if manage_permission_id is None:
        manage_permission_id = str(uuid4())
        connection.execute(sa.text("""
            INSERT INTO permissions
                (id, code, label, module, description, organization_id, created_at, updated_at)
            VALUES
                (:id, :code, :label, :module, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {
            "id": manage_permission_id,
            "code": "college.academics.manage",
            "label": "Manage academic structure and course offerings",
            "module": "college",
        })

    manage_role_ids = connection.execute(sa.text("""
        SELECT id FROM roles WHERE slug IN :slugs
    """).bindparams(sa.bindparam("slugs", expanding=True)), {
        "slugs": list(ACADEMIC_MANAGE_ROLES),
    }).scalars().all()
    for role_id in manage_role_ids:
        exists = connection.execute(sa.text("""
            SELECT 1 FROM role_permissions
            WHERE role_id = :role_id AND permission_id = :permission_id
        """), {
            "role_id": role_id,
            "permission_id": manage_permission_id,
        }).first()
        if not exists:
            connection.execute(sa.text("""
                INSERT INTO role_permissions (id, role_id, permission_id)
                VALUES (:id, :role_id, :permission_id)
            """), {
                "id": str(uuid4()),
                "role_id": role_id,
                "permission_id": manage_permission_id,
            })


def downgrade() -> None:
    connection = op.get_bind()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {"code": "college.academics.view"},
    ).scalar_one_or_none()
    if permission_id is not None:
        connection.execute(sa.text(
            "DELETE FROM role_permissions WHERE permission_id = :permission_id"
        ), {"permission_id": permission_id})
        connection.execute(sa.text(
            "DELETE FROM user_permission_overrides WHERE permission_id = :permission_id"
        ), {"permission_id": permission_id})
        connection.execute(sa.text(
            "DELETE FROM permissions WHERE id = :permission_id"
        ), {"permission_id": permission_id})

    for name, table_name, _columns in reversed(PAGINATION_INDEXES):
        op.drop_index(name, table_name=table_name)
    op.drop_index("ix_college_cohorts_bulk_operation_key", table_name="college_cohorts")
    op.drop_constraint("uq_college_cohort_org_bulk_section", "college_cohorts", type_="unique")
    op.drop_constraint(
        "uq_college_cohort_org_program_graduation_section",
        "college_cohorts",
        type_="unique",
    )
    op.alter_column(
        "college_cohorts",
        "section",
        existing_type=sa.String(length=20),
        nullable=True,
        server_default=None,
    )
    op.drop_column("college_cohorts", "bulk_request_hash")
    op.drop_column("college_cohorts", "bulk_operation_key")
    for table_name in reversed(MANAGED_TABLES):
        op.drop_column(table_name, "version")
