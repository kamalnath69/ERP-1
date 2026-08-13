"""Add versioned enterprise access policies and College safeguards.

Revision ID: 20260813_0036
Revises: 20260813_0035
"""
import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260813_0036"
down_revision = "20260813_0035"
branch_labels = None
depends_on = None


PERMISSIONS = (
    ("college.students.update", "Update student records", "college"),
    ("college.attendance.correct", "Correct published attendance", "college"),
    ("college.assessments.record", "Record assessment results", "college"),
    ("college.readiness.intervene", "Record readiness interventions", "college placement"),
    ("college.readiness.policy.manage", "Manage readiness policy", "college placement"),
    ("college.eligibility.override", "Override placement eligibility", "college placement"),
    ("college.clearance.view", "View internship clearance", "college placement"),
    ("college.clearance.manage", "Correct internship clearance", "college placement"),
    ("college.data.view", "View data exchange history", "college"),
    ("college.data.export", "Export College data", "college"),
    ("college.students.contact.view", "View student contact details", "college sensitive"),
    ("college.students.guardian.view", "View guardian details", "college sensitive"),
    ("college.notes.private.view", "View private student notes", "college sensitive"),
    ("college.documents.sensitive.view", "View sensitive student documents", "college sensitive"),
    ("college.protected_fields.view", "View protected administrative fields", "college sensitive"),
    ("access.delegations.manage", "Manage delegated access administrators", "access"),
)


ROLE_GRANTS = {
    "owner": {code for code, _label, _module in PERMISSIONS},
    "principal": {"college.clearance.view", "college.data.view"},
    "placement-head": {
        "college.students.update", "college.assessments.record", "college.readiness.intervene",
        "college.readiness.policy.manage", "college.eligibility.override", "college.clearance.view",
        "college.data.view", "college.data.export",
    },
    "placement-coordinator": {
        "college.readiness.intervene", "college.clearance.view", "college.data.view",
    },
    "hod": {
        "college.assessments.record", "college.readiness.intervene", "college.clearance.view",
        "college.data.view",
    },
    "academic-admin": {
        "college.students.update", "college.attendance.correct", "college.assessments.record",
        "college.data.view", "college.data.export", "college.students.contact.view",
        "college.students.guardian.view", "college.documents.sensitive.view",
    },
    "faculty": {"college.assessments.record"},
    "admissions": {
        "college.students.update", "college.students.contact.view", "college.students.guardian.view",
    },
    "accountant": {"college.clearance.view", "college.clearance.manage"},
}


ROLE_TEMPLATES = {
    "access-admin": ("Access Admin", "Delegated access administration without automatic student-data access"),
    "college-admin": ("College Admin", "Institution-wide College operations without ownership or billing authority"),
    "college-manager": ("College Manager", "Scoped day-to-day College operations"),
    "class-advisor": ("Class Advisor", "Student and attendance support for assigned cohorts or sections"),
    "finance": ("Finance", "Internship clearance and authorized College financial records"),
    "auditor": ("Auditor", "Read-only scoped oversight and audit access"),
}

TEMPLATE_GRANTS = {
    "access-admin": {"users.view", "users.manage", "roles.manage", "access.delegations.manage", "settings.audit.view"},
    "college-admin": {
        "dashboard.view", "clients.view", "clients.manage", "college.view",
        "college.academics.view", "college.academics.manage", "college.students.view",
        "college.students.update", "college.students.manage", "college.attendance.view",
        "college.attendance.mark", "college.assessments.view", "college.assessments.record",
        "college.assessments.manage", "college.readiness.view", "college.coding.view",
        "college.placements.view", "college.data.view", "college.imports.manage",
        "documents.view", "documents.manage", "reports.view", "ai.use", "ai.actions",
    },
    "college-manager": {
        "dashboard.view", "clients.view", "college.view", "college.academics.view",
        "college.students.view", "college.students.update", "college.attendance.view",
        "college.attendance.mark", "college.assessments.view", "college.assessments.record",
        "college.readiness.view", "college.readiness.intervene", "college.coding.view",
        "college.placements.view", "college.applications.manage", "college.clearance.view",
        "college.data.view", "documents.view", "ai.use",
    },
    "class-advisor": {
        "dashboard.view", "clients.view", "college.view", "college.academics.view",
        "college.students.view", "college.students.update", "college.attendance.view",
        "college.attendance.mark", "college.assessments.view", "college.readiness.view",
        "college.readiness.intervene", "college.placements.view", "college.clearance.view",
        "documents.view", "ai.use",
    },
    "finance": {
        "dashboard.view", "college.view", "college.students.view", "college.clearance.view",
        "college.clearance.manage", "college.fees.view", "college.fees.manage", "reports.view",
    },
    "auditor": {
        "dashboard.view", "college.view", "college.academics.view", "college.students.view",
        "college.attendance.view", "college.assessments.view", "college.readiness.view",
        "college.coding.view", "college.placements.view", "college.placement_reports.view",
        "college.clearance.view", "college.data.view", "documents.view", "audit.view",
    },
}

UNSAFE_EXISTING_GRANTS = {
    "principal": {"employees.view"},
    "manager": {
        "roles.manage", "billing.manage", "college.fees.view", "college.fees.manage",
        "college.integrations.manage", "college.readiness.policy.manage",
        "college.assessments.correct", "college.eligibility.override", "college.data.export",
        "college.protected_fields.view", "college.notes.private.view",
    },
    "placement-head": {
        "employees.view",
        "college.students.manage", "college.assessments.manage", "college.integrations.manage",
        "reports.exports",
    },
    "placement-coordinator": {
        "clients.manage", "college.students.manage", "college.readiness.manage",
        "college.coding.manage", "college.companies.manage", "college.opportunities.manage",
        "college.offers.manage", "college.imports.manage", "documents.manage",
    },
    "hod": {"employees.view", "college.assessments.manage", "college.readiness.manage"},
    "academic-admin": {"employees.view"},
    "faculty": {"employees.view"},
    "college-admin": {"employees.view"},
    "admissions": {"college.fees.view"},
}


def _add_permissions_and_templates() -> None:
    connection = op.get_bind()
    permission_ids: dict[str, str] = {}
    for code, label, module in PERMISSIONS:
        permission_id = connection.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code},
        ).scalar_one_or_none()
        if permission_id is None:
            permission_id = str(uuid4())
            connection.execute(sa.text("""
                INSERT INTO permissions
                    (id, code, label, module, description, organization_id, created_at, updated_at)
                VALUES
                    (:id, :code, :label, :module, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """), {"id": permission_id, "code": code, "label": label, "module": module})
        permission_ids[code] = permission_id

    college_orgs = connection.execute(sa.text(
        "SELECT id FROM organizations WHERE industry = 'college'"
    )).scalars().all()
    for organization_id in college_orgs:
        for slug, (name, description) in ROLE_TEMPLATES.items():
            exists = connection.execute(sa.text("""
                SELECT id FROM roles
                WHERE organization_id = :organization_id AND slug = :slug AND is_system = TRUE
            """), {"organization_id": organization_id, "slug": slug}).scalar_one_or_none()
            if exists is None:
                connection.execute(sa.text("""
                    INSERT INTO roles
                        (id, organization_id, name, slug, description, is_system, is_active, version, created_at, updated_at)
                    VALUES
                        (:id, :organization_id, :name, :slug, :description, TRUE, TRUE, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """), {
                    "id": str(uuid4()), "organization_id": organization_id, "name": name,
                    "slug": slug, "description": description,
                })

        for slug, codes in TEMPLATE_GRANTS.items():
            role_id = connection.execute(sa.text("""
                SELECT id FROM roles
                WHERE organization_id = :organization_id AND slug = :slug AND is_system = TRUE
            """), {"organization_id": organization_id, "slug": slug}).scalar_one()
            for code in codes:
                permission_id = connection.execute(
                    sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code},
                ).scalar_one_or_none()
                if permission_id:
                    connection.execute(sa.text("""
                        INSERT INTO role_permissions (id, role_id, permission_id)
                        SELECT :id, :role_id, :permission_id
                        WHERE NOT EXISTS (
                            SELECT 1 FROM role_permissions
                            WHERE role_id = :role_id AND permission_id = :permission_id
                        )
                    """), {
                        "id": str(uuid4()), "role_id": role_id, "permission_id": permission_id,
                    })

        for slug, codes in UNSAFE_EXISTING_GRANTS.items():
            connection.execute(sa.text("""
                DELETE FROM role_permissions
                WHERE role_id IN (
                    SELECT id FROM roles
                    WHERE organization_id = :organization_id AND slug = :slug AND is_system = TRUE
                )
                AND permission_id IN (
                    SELECT id FROM permissions WHERE code IN :codes
                )
            """).bindparams(sa.bindparam("codes", expanding=True)), {
                "organization_id": organization_id, "slug": slug, "codes": list(codes),
            })

    for slug, codes in ROLE_GRANTS.items():
        role_ids = connection.execute(
            sa.text("SELECT id FROM roles WHERE slug = :slug AND is_system = TRUE"), {"slug": slug},
        ).scalars().all()
        for role_id in role_ids:
            for code in codes:
                connection.execute(sa.text("""
                    INSERT INTO role_permissions (id, role_id, permission_id)
                    SELECT :id, :role_id, :permission_id
                    WHERE NOT EXISTS (
                        SELECT 1 FROM role_permissions
                        WHERE role_id = :role_id AND permission_id = :permission_id
                    )
                """), {
                    "id": str(uuid4()), "role_id": role_id, "permission_id": permission_ids[code],
                })


def _namespace_custom_role_slugs() -> None:
    # Legacy custom roles used display-name slugs and could collide with
    # privileged built-in roles. System roles retain their stable slugs.
    op.get_bind().execute(sa.text("""
        UPDATE roles
        SET slug = 'custom-' || slug
        WHERE is_system = FALSE AND slug NOT LIKE 'custom-%'
    """))


def _seed_college_policies() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT users.id AS user_id,
               users.organization_id AS organization_id,
               EXISTS (
                   SELECT 1
                   FROM user_roles
                   JOIN roles ON roles.id = user_roles.role_id
                   WHERE user_roles.user_id = users.id
                     AND roles.slug = 'owner'
                     AND roles.is_system = TRUE
               ) AS is_owner
        FROM users
        JOIN organizations ON organizations.id = users.organization_id
        WHERE organizations.industry = 'college'
    """)).mappings().all()
    for row in rows:
        existing = connection.execute(sa.text("""
            SELECT id FROM access_policies
            WHERE organization_id = :organization_id AND user_id = :user_id
        """), row).scalar_one_or_none()
        if existing:
            continue
        policy_id = str(uuid4())
        status = "active" if row["is_owner"] else "pending_review"
        domain_levels = {
            domain: "manage"
            for domain in (
                "students", "academics", "attendance", "assessments", "readiness",
                "coding", "placements", "data", "reports", "clearance", "documents",
            )
        } if row["is_owner"] else {}
        connection.execute(sa.text("""
            INSERT INTO access_policies
                (id, organization_id, user_id, status, version, domain_levels, created_at, updated_at)
            VALUES
                (:id, :organization_id, :user_id, :status, 1, CAST(:domain_levels AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {
            **row,
            "id": policy_id,
            "status": status,
            "domain_levels": json.dumps(domain_levels),
        })
        if row["is_owner"]:
            connection.execute(sa.text("""
                INSERT INTO access_policy_scopes
                    (id, organization_id, policy_id, domain_key, scope_type, scope_value, created_at, updated_at)
                VALUES
                    (:id, :organization_id, :policy_id, '*', 'organization', '*', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """), {
                "id": str(uuid4()), "organization_id": row["organization_id"], "policy_id": policy_id,
            })

    for organization_id in connection.execute(sa.text(
        "SELECT id FROM organizations WHERE industry = 'college'"
    )).scalars().all():
        connection.execute(sa.text("""
            INSERT INTO feature_flags
                (id, organization_id, flag, enabled, meta, created_at, updated_at)
            SELECT :id, :organization_id, 'authorization.policy_v2', TRUE,
                   CAST(:meta AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM feature_flags
                WHERE organization_id = :organization_id AND flag = 'authorization.policy_v2'
            )
        """), {
            "id": str(uuid4()),
            "organization_id": organization_id,
            "meta": json.dumps({"mode": "enabled", "version": 2}),
        })


def upgrade() -> None:
    op.create_table(
        "access_policies",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending_review"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("domain_levels", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_access_policy_org_user"),
    )
    op.create_index("ix_access_policies_user_id", "access_policies", ["user_id"])
    op.create_index("ix_access_policies_status", "access_policies", ["status"])
    op.create_index("ix_access_policies_expires_at", "access_policies", ["expires_at"])
    op.create_index("ix_access_policies_org_status_user", "access_policies", ["organization_id", "status", "user_id"])

    op.create_table(
        "access_policy_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("domain_key", sa.String(length=50), nullable=False, server_default="*"),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_value", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["access_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "domain_key", "scope_type", "scope_value", name="uq_access_policy_scope_root"),
    )
    op.create_index("ix_access_policy_scopes_policy_id", "access_policy_scopes", ["policy_id"])
    op.create_index("ix_access_policy_scopes_org", "access_policy_scopes", ["organization_id"])
    op.create_index("ix_access_policy_scopes_policy_domain_type", "access_policy_scopes", ["policy_id", "domain_key", "scope_type"])

    op.create_table(
        "access_delegations",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("domain_levels", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sensitive_capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_access_delegation_org_user"),
    )
    for column in ("organization_id", "user_id", "active", "expires_at", "created_by_user_id"):
        op.create_index(f"ix_access_delegations_{column}", "access_delegations", [column])

    op.create_table(
        "access_delegation_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("delegation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_value", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delegation_id"], ["access_delegations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delegation_id", "scope_type", "scope_value", name="uq_access_delegation_scope_root"),
    )
    op.create_index("ix_access_delegation_scopes_org", "access_delegation_scopes", ["organization_id"])
    op.create_index("ix_access_delegation_scopes_delegation", "access_delegation_scopes", ["delegation_id"])

    _namespace_custom_role_slugs()
    _add_permissions_and_templates()
    _seed_college_policies()


def downgrade() -> None:
    connection = op.get_bind()
    for code, _label, _module in PERMISSIONS:
        permission_id = connection.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code},
        ).scalar_one_or_none()
        if permission_id:
            connection.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :id"), {"id": permission_id})
            connection.execute(sa.text("DELETE FROM user_permission_overrides WHERE permission_id = :id"), {"id": permission_id})
            connection.execute(sa.text("DELETE FROM permissions WHERE id = :id"), {"id": permission_id})
    op.drop_table("access_delegation_scopes")
    op.drop_table("access_delegations")
    op.drop_table("access_policy_scopes")
    op.drop_table("access_policies")
