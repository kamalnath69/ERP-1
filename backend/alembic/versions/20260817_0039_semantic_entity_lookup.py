"""Add typo-tolerant person and College student lookup indexes.

Revision ID: 20260817_0039
Revises: 20260817_0038
"""
from alembic import op


revision = "20260817_0039"
down_revision = "20260817_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_clients_person_name_trgm
        ON clients USING gin
        ((lower(coalesce(trim(first_name || ' ' || last_name), ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_clients_first_name_trgm
        ON clients USING gin ((lower(coalesce(first_name, ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_clients_last_name_trgm
        ON clients USING gin ((lower(coalesce(last_name, ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_employees_person_name_trgm
        ON employees USING gin
        ((lower(coalesce(trim(first_name || ' ' || last_name), ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_employees_first_name_trgm
        ON employees USING gin ((lower(coalesce(first_name, ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_employees_last_name_trgm
        ON employees USING gin ((lower(coalesce(last_name, ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_college_students_admission_trgm
        ON college_student_profiles USING gin
        ((lower(coalesce(admission_number, ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_college_students_roll_trgm
        ON college_student_profiles USING gin
        ((lower(coalesce(roll_number, ''))) gin_trgm_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_college_students_roll_trgm")
    op.execute("DROP INDEX IF EXISTS ix_college_students_admission_trgm")
    op.execute("DROP INDEX IF EXISTS ix_clients_last_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_clients_first_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_clients_person_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_employees_last_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_employees_first_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_employees_person_name_trgm")
