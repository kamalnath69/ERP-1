"""Add institution-configured assessments and shared data exchange storage.

Revision ID: 20260813_0035
Revises: 20260813_0034
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260813_0035"
down_revision = "20260813_0034"
branch_labels = None
depends_on = None


def _add_permission(code: str, label: str, role_slugs: tuple[str, ...]) -> None:
    connection = op.get_bind()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code},
    ).scalar_one_or_none()
    if permission_id is None:
        permission_id = str(uuid4())
        connection.execute(sa.text("""
            INSERT INTO permissions
                (id, code, label, module, description, organization_id, created_at, updated_at)
            VALUES
                (:id, :code, :label, 'college', NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {"id": permission_id, "code": code, "label": label})
    role_ids = connection.execute(sa.text("""
        SELECT id FROM roles WHERE slug IN :slugs
    """).bindparams(sa.bindparam("slugs", expanding=True)), {
        "slugs": list(role_slugs),
    }).scalars().all()
    for role_id in role_ids:
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


def upgrade() -> None:
    op.create_table(
        "college_assessment_schemes",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("domain", sa.String(length=30), nullable=False, server_default="academic"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_scheme_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("final_score_max", sa.Numeric(precision=8, scale=2), nullable=False, server_default="100"),
        sa.Column("calculation_method", sa.String(length=30), nullable=False, server_default="weighted_sum"),
        sa.Column("calculation_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_scheme_id"], ["college_assessment_schemes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", "version_number", name="uq_college_assessment_scheme_code_version"),
    )
    op.create_index("ix_college_assessment_schemes_organization_id", "college_assessment_schemes", ["organization_id"])
    op.create_index("ix_college_assessment_schemes_domain", "college_assessment_schemes", ["domain"])
    op.create_index("ix_college_assessment_schemes_status", "college_assessment_schemes", ["status"])
    op.create_index("ix_college_assessment_schemes_supersedes_scheme_id", "college_assessment_schemes", ["supersedes_scheme_id"])
    op.create_index("ix_college_assessment_schemes_frozen_at", "college_assessment_schemes", ["frozen_at"])
    op.create_index(
        "ix_college_assessment_schemes_org_domain_status_name",
        "college_assessment_schemes", ["organization_id", "domain", "status", "name", "id"],
    )

    op.create_table(
        "college_assessment_components",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("component_type", sa.String(length=50), nullable=False, server_default="assessment"),
        sa.Column("metric_type", sa.String(length=24), nullable=False, server_default="number"),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("max_marks", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("weightage_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pass_marks", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("aggregation_group", sa.String(length=50), nullable=True),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheme_id"], ["college_assessment_schemes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheme_id", "code", name="uq_college_assessment_component_scheme_code"),
        sa.UniqueConstraint("scheme_id", "display_order", name="uq_college_assessment_component_order"),
    )
    op.create_index("ix_college_assessment_components_organization_id", "college_assessment_components", ["organization_id"])
    op.create_index("ix_college_assessment_components_scheme_id", "college_assessment_components", ["scheme_id"])

    op.create_table(
        "college_assessment_readiness_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("metric_code", sa.String(length=50), nullable=False),
        sa.Column("factor_key", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mapped_by_user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheme_id"], ["college_assessment_schemes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mapped_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheme_id", "metric_code", name="uq_college_assessment_readiness_scheme_metric"),
    )
    for column in ("organization_id", "scheme_id", "factor_key", "is_active", "mapped_by_user_id"):
        op.create_index(
            f"ix_college_assessment_readiness_mappings_{column}",
            "college_assessment_readiness_mappings", [column],
        )
    op.create_index(
        "ix_college_assessment_readiness_org_active_factor",
        "college_assessment_readiness_mappings",
        ["organization_id", "is_active", "factor_key", "scheme_id"],
    )

    op.create_table(
        "college_assessment_scheme_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("term_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("scope_key", sa.String(length=180), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheme_id"], ["college_assessment_schemes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["program_id"], ["college_programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cohort_id"], ["college_cohorts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["term_id"], ["college_terms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "scope_key", name="uq_college_assessment_assignment_scope"),
    )
    for column in ("organization_id", "scheme_id", "program_id", "cohort_id", "term_id", "is_active"):
        op.create_index(f"ix_college_assessment_scheme_assignments_{column}", "college_assessment_scheme_assignments", [column])
    op.create_index(
        "ix_college_assessment_assignments_org_active_scope",
        "college_assessment_scheme_assignments", ["organization_id", "is_active", "scope_key", "id"],
    )

    op.create_table(
        "college_exam_cycles",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scheme_component_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("term_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("domain", sa.String(length=30), nullable=False, server_default="academic"),
        sa.Column("held_on", sa.Date(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("target_cohort_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("target_offering_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scheme_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheme_id"], ["college_assessment_schemes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scheme_component_id"], ["college_assessment_components.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["term_id"], ["college_terms.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_college_exam_cycle_org_code"),
    )
    for column in ("organization_id", "scheme_id", "scheme_component_id", "term_id", "domain", "held_on", "status"):
        op.create_index(f"ix_college_exam_cycles_{column}", "college_exam_cycles", [column])
    op.create_index(
        "ix_college_exam_cycles_org_term_status_date",
        "college_exam_cycles", ["organization_id", "term_id", "status", "held_on", "id"],
    )

    op.alter_column("college_assessments", "offering_id", existing_type=postgresql.UUID(as_uuid=False), nullable=True)
    op.add_column("college_assessments", sa.Column("cohort_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("college_assessments", sa.Column("exam_cycle_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("college_assessments", sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("college_assessments", sa.Column("scheme_component_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("college_assessments", sa.Column("metric_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("college_assessments", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_foreign_key("fk_college_assessments_cohort", "college_assessments", "college_cohorts", ["cohort_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_college_assessments_cycle", "college_assessments", "college_exam_cycles", ["exam_cycle_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_college_assessments_scheme", "college_assessments", "college_assessment_schemes", ["scheme_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_college_assessments_component", "college_assessments", "college_assessment_components", ["scheme_component_id"], ["id"], ondelete="SET NULL")
    for column in ("cohort_id", "exam_cycle_id", "scheme_id", "scheme_component_id"):
        op.create_index(f"ix_college_assessments_{column}", "college_assessments", [column])

    op.add_column("college_assessment_scores", sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("college_assessment_scores", sa.Column("calculated_score", sa.Numeric(precision=8, scale=2), nullable=True))
    op.add_column("college_assessment_scores", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    # Stable versions make reviewed update workbooks optimistic and prevent stale
    # academic evidence from overwriting newer manual or ERP corrections.
    for table_name in ("college_term_results", "college_attendance_snapshots", "college_career_evidence"):
        op.add_column(table_name, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "data_exchange_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("resource_key", sa.String(length=100), nullable=False),
        sa.Column("operation", sa.String(length=24), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="uploaded"),
        sa.Column("schema_version", sa.String(length=40), nullable=False, server_default="1"),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("legacy_import_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("create_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("update_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["legacy_import_run_id"], ["college_import_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_data_exchange_org_idempotency"),
    )
    for column in ("organization_id", "resource_key", "operation", "source_type", "status", "legacy_import_run_id", "initiated_by_user_id", "expires_at"):
        op.create_index(f"ix_data_exchange_runs_{column}", "data_exchange_runs", [column])
    op.create_index("ix_data_exchange_runs_org_created_id", "data_exchange_runs", ["organization_id", "created_at", "id"])

    op.create_table(
        "data_exchange_rows",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False, server_default="validate"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("natural_key", sa.String(length=300), nullable=True),
        sa.Column("record_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=True),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("current_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["data_exchange_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "row_number", name="uq_data_exchange_row_number"),
    )
    for column in ("organization_id", "run_id", "action", "status", "natural_key", "record_id"):
        op.create_index(f"ix_data_exchange_rows_{column}", "data_exchange_rows", [column])
    op.create_index("ix_data_exchange_rows_run_status_row", "data_exchange_rows", ["run_id", "status", "row_number", "id"])

    op.create_table(
        "data_exchange_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["data_exchange_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "kind", name="uq_data_exchange_artifact_kind"),
    )
    for column in ("organization_id", "run_id", "kind", "expires_at"):
        op.create_index(f"ix_data_exchange_artifacts_{column}", "data_exchange_artifacts", [column])

    _add_permission(
        "college.assessments.correct",
        "Correct published College assessment results",
        ("owner", "academic-admin"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'college.assessments.correct'")
    ).scalar_one_or_none()
    if permission_id:
        connection.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :id"), {"id": permission_id})
        connection.execute(sa.text("DELETE FROM user_permission_overrides WHERE permission_id = :id"), {"id": permission_id})
        connection.execute(sa.text("DELETE FROM permissions WHERE id = :id"), {"id": permission_id})

    op.drop_table("data_exchange_artifacts")
    op.drop_table("data_exchange_rows")
    op.drop_table("data_exchange_runs")

    for table_name in ("college_career_evidence", "college_attendance_snapshots", "college_term_results"):
        op.drop_column(table_name, "version")

    op.drop_column("college_assessment_scores", "version")
    op.drop_column("college_assessment_scores", "calculated_score")
    op.drop_column("college_assessment_scores", "metrics")
    for column in ("scheme_component_id", "scheme_id", "exam_cycle_id", "cohort_id"):
        op.drop_index(f"ix_college_assessments_{column}", table_name="college_assessments")
    op.drop_constraint("fk_college_assessments_component", "college_assessments", type_="foreignkey")
    op.drop_constraint("fk_college_assessments_scheme", "college_assessments", type_="foreignkey")
    op.drop_constraint("fk_college_assessments_cycle", "college_assessments", type_="foreignkey")
    op.drop_constraint("fk_college_assessments_cohort", "college_assessments", type_="foreignkey")
    op.drop_column("college_assessments", "version")
    op.drop_column("college_assessments", "metric_schema")
    op.drop_column("college_assessments", "scheme_component_id")
    op.drop_column("college_assessments", "scheme_id")
    op.drop_column("college_assessments", "exam_cycle_id")
    op.drop_column("college_assessments", "cohort_id")
    op.alter_column("college_assessments", "offering_id", existing_type=postgresql.UUID(as_uuid=False), nullable=False)

    op.drop_table("college_exam_cycles")
    op.drop_table("college_assessment_scheme_assignments")
    op.drop_table("college_assessment_readiness_mappings")
    op.drop_table("college_assessment_components")
    op.drop_table("college_assessment_schemes")
