"""Add field-level profile permissions.

Revision ID: 20260801_0010
Revises: 20260801_0009
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260801_0010"
down_revision = "20260801_0009"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    permission_id = connection.execute(sa.text(
        "SELECT id FROM permissions WHERE code = :code"
    ), {"code": "employees.compensation.view"}).scalar_one_or_none()
    if permission_id is None:
        permission_id = str(uuid4())
        connection.execute(sa.text("""
            INSERT INTO permissions
                (id, code, label, module, description, organization_id, created_at, updated_at)
            VALUES
                (:id, :code, :label, :module, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {
            "id": permission_id,
            "code": "employees.compensation.view",
            "label": "View employee compensation",
            "module": "employees",
        })

    owner_ids = connection.execute(sa.text(
        "SELECT id FROM roles WHERE slug = 'owner'"
    )).scalars().all()
    for role_id in owner_ids:
        exists = connection.execute(sa.text("""
            SELECT 1 FROM role_permissions
            WHERE role_id = :role_id AND permission_id = :permission_id
        """), {"role_id": role_id, "permission_id": permission_id}).first()
        if not exists:
            connection.execute(sa.text("""
                INSERT INTO role_permissions (id, role_id, permission_id)
                VALUES (:id, :role_id, :permission_id)
            """), {"id": str(uuid4()), "role_id": role_id, "permission_id": permission_id})


def downgrade():
    connection = op.get_bind()
    permission_id = connection.execute(sa.text(
        "SELECT id FROM permissions WHERE code = :code"
    ), {"code": "employees.compensation.view"}).scalar_one_or_none()
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
