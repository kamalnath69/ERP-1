"""Add an authoritative graduation year to College cohorts.

Revision ID: 20260813_0033
Revises: 20260812_0032
"""
from alembic import op
import sqlalchemy as sa


revision = "20260813_0033"
down_revision = "20260812_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("college_cohorts", sa.Column("graduation_year", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE college_cohorts AS cohort
        SET graduation_year = cohort.admission_year + ((program.duration_semesters + 1) / 2)
        FROM college_programs AS program
        WHERE program.id = cohort.program_id
        """
    )
    op.execute(
        """
        UPDATE college_cohorts
        SET graduation_year = admission_year + 3
        WHERE graduation_year IS NULL
        """
    )
    op.alter_column("college_cohorts", "graduation_year", nullable=False)
    op.create_index(
        "ix_college_cohorts_graduation_year",
        "college_cohorts",
        ["graduation_year"],
    )
    op.create_index(
        "ix_college_cohorts_org_graduation_program_section_id",
        "college_cohorts",
        ["organization_id", "graduation_year", "program_id", "section", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_college_cohorts_org_graduation_program_section_id", table_name="college_cohorts")
    op.drop_index("ix_college_cohorts_graduation_year", table_name="college_cohorts")
    op.drop_column("college_cohorts", "graduation_year")
