"""Preserve original location and storage allowances.

Revision ID: 20260730_0006
Revises: 20260730_0005
"""
from alembic import op

revision = "20260730_0006"
down_revision = "20260730_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE plan_entitlements pe
        SET value = '{"value": null}'::jsonb
        FROM feature_definitions fd, plan_versions pv
        WHERE pe.feature_id = fd.id
          AND pe.plan_version_id = pv.id
          AND pv.version = 1
          AND fd.code IN ('limits.locations', 'limits.storage_mb')
    """)


def downgrade():
    # These limits did not exist before the control-plane migration.
    pass
