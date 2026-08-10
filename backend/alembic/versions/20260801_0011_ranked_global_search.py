"""Add typo-tolerant indexes for ranked global search.

Revision ID: 20260801_0011
Revises: 20260801_0010
"""
from alembic import op


revision = "20260801_0011"
down_revision = "20260801_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_customers_global_search_trgm
        ON customers USING gin
        ((lower(trim(coalesce(first_name, '') || ' ' || coalesce(last_name, '')) || ' ' ||
            coalesce(customer_number, '') || ' ' || coalesce(phone, '') || ' ' || coalesce(email, ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_employees_global_search_trgm
        ON employees USING gin
        ((lower(trim(coalesce(first_name, '') || ' ' || coalesce(last_name, '')) || ' ' ||
            coalesce(employee_number, '') || ' ' || coalesce(designation, '') || ' ' ||
            coalesce(phone, '') || ' ' || coalesce(email, ''))) gin_trgm_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_catalog_global_search_trgm
        ON catalog_items USING gin
        ((lower(name || ' ' || coalesce(sku, '') || ' ' || coalesce(description, '') || ' ' ||
            coalesce(hsn_sac, ''))) gin_trgm_ops)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_catalog_global_search_trgm")
    op.execute("DROP INDEX IF EXISTS ix_employees_global_search_trgm")
    op.execute("DROP INDEX IF EXISTS ix_customers_global_search_trgm")
