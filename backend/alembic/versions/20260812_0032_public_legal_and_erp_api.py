"""Add public legal records, demo leads, and College integration API data.

Revision ID: 20260812_0032
Revises: 20260812_0031
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260812_0032"
down_revision = "20260812_0031"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "legal_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("version_lock", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("published_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_type", "version", name="uq_legal_document_type_version"),
    )
    op.create_index("ix_legal_documents_document_type", "legal_documents", ["document_type"])
    op.create_index("ix_legal_documents_status", "legal_documents", ["status"])
    op.create_index("ix_legal_documents_published_by_user_id", "legal_documents", ["published_by_user_id"])
    op.create_index("ix_legal_document_type_status", "legal_documents", ["document_type", "status"])
    op.create_index(
        "uq_legal_document_current", "legal_documents", ["document_type"], unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )

    op.create_table(
        "legal_acceptances",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("signup_checkout_id", UUID, sa.ForeignKey("signup_checkouts.id", ondelete="SET NULL")),
        sa.Column("subject_email", sa.String(255), nullable=False),
        sa.Column("terms_document_id", UUID, sa.ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("privacy_document_id", UUID, sa.ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("refund_document_id", UUID, sa.ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(80)),
        sa.Column("user_agent", sa.String(300)),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("signup_checkout_id", name="uq_legal_acceptance_signup_checkout"),
    )
    for column in ("organization_id", "user_id", "signup_checkout_id", "subject_email", "accepted_at"):
        op.create_index(f"ix_legal_acceptances_{column}", "legal_acceptances", [column])
    op.create_index("ix_legal_acceptance_org_time", "legal_acceptances", ["organization_id", "accepted_at"])

    op.create_table(
        "demo_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("work_email", sa.String(255), nullable=False),
        sa.Column("organization_name", sa.String(200), nullable=False),
        sa.Column("industry", sa.String(40), nullable=False),
        sa.Column("role", sa.String(120)),
        sa.Column("phone", sa.String(40)),
        sa.Column("message", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False, server_default="new"),
        sa.Column("privacy_document_id", UUID, sa.ForeignKey("legal_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent", sa.String(300)),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_demo_requests_work_email", "demo_requests", ["work_email"])
    op.create_index("ix_demo_requests_status", "demo_requests", ["status"])
    op.create_index("ix_demo_requests_ip_hash", "demo_requests", ["ip_hash"])
    op.create_index("ix_demo_request_status_time", "demo_requests", ["status", "created_at"])
    op.create_index("ix_demo_request_ip_time", "demo_requests", ["ip_hash", "created_at"])

    op.create_table(
        "college_clearance_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False, server_default="erp"),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("external_id", sa.String(180)),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("student_profile_id", "as_of", "source_key", name="uq_college_clearance_student_date_source"),
    )
    for column in ("organization_id", "student_profile_id", "status", "as_of", "external_id", "source_updated_at"):
        op.create_index(f"ix_college_clearance_snapshots_{column}", "college_clearance_snapshots", [column])

    op.create_table(
        "college_integration_credentials",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", UUID, sa.ForeignKey("college_data_connectors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_prefix", sa.String(40), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("last_ip", sa.String(80)),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_college_integration_credential_name"),
        sa.UniqueConstraint("connector_id", name="uq_college_integration_credential_connector"),
        sa.UniqueConstraint("key_prefix", name="uq_college_integration_credential_prefix"),
    )
    for column in ("organization_id", "connector_id", "key_prefix", "expires_at", "revoked_at", "created_by_user_id"):
        op.create_index(f"ix_college_integration_credentials_{column}", "college_integration_credentials", [column])

    op.create_table(
        "college_integration_rate_buckets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("credential_id", UUID, sa.ForeignKey("college_integration_credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("credential_id", "window_start", name="uq_college_integration_rate_window"),
    )
    op.create_index("ix_college_integration_rate_buckets_credential_id", "college_integration_rate_buckets", ["credential_id"])
    op.create_index("ix_college_integration_rate_buckets_window_start", "college_integration_rate_buckets", ["window_start"])

    op.add_column("college_import_runs", sa.Column("credential_id", UUID, sa.ForeignKey("college_integration_credentials.id", ondelete="SET NULL")))
    op.add_column("college_import_runs", sa.Column("request_hash", sa.String(64)))
    op.create_index("ix_college_import_runs_credential_id", "college_import_runs", ["credential_id"])
    op.create_unique_constraint(
        "uq_college_import_credential_idempotency", "college_import_runs",
        ["credential_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_college_import_credential_idempotency", "college_import_runs", type_="unique")
    op.drop_index("ix_college_import_runs_credential_id", table_name="college_import_runs")
    op.drop_column("college_import_runs", "request_hash")
    op.drop_column("college_import_runs", "credential_id")
    op.drop_table("college_integration_rate_buckets")
    op.drop_table("college_integration_credentials")
    op.drop_table("college_clearance_snapshots")
    op.drop_table("demo_requests")
    op.drop_table("legal_acceptances")
    op.drop_index("uq_legal_document_current", table_name="legal_documents")
    op.drop_table("legal_documents")
