"""Add College placement intelligence, evidence, pipeline, and ingestion.

Revision ID: 20260806_0024
Revises: 20260806_0023
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260806_0024"
down_revision = "20260806_0023"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)
JSON = postgresql.JSONB(astext_type=sa.Text())


def _tenant():
    return sa.Column(
        "organization_id", UUID,
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _indexes(table, columns):
    for column in columns:
        name = f"ix_{table}_{column}"
        if name == "ix_college_placement_applications_eligibility_override_by_user_id":
            name = "ix_college_app_eligibility_override_user"
        op.create_index(name, table, [column])


def upgrade():
    op.create_table(
        "college_term_results",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term_id", UUID, sa.ForeignKey("college_terms.id", ondelete="SET NULL")),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("sgpa", sa.Numeric(5, 2)),
        sa.Column("cgpa", sa.Numeric(5, 2)),
        sa.Column("credits_earned", sa.Integer()),
        sa.Column("total_backlogs", sa.Integer()),
        sa.Column("active_backlogs", sa.Integer()),
        sa.Column("result_status", sa.String(24), nullable=False),
        sa.Column("published_on", sa.Date()),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("external_id", sa.String(180)),
        sa.Column("source_payload", JSON, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_profile_id", "semester", "source_key", name="uq_college_term_result_student_semester_source"),
    )
    op.create_table(
        "college_attendance_snapshots",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term_id", UUID, sa.ForeignKey("college_terms.id", ondelete="SET NULL")),
        sa.Column("course_id", UUID, sa.ForeignKey("college_courses.id", ondelete="SET NULL")),
        sa.Column("scope_key", sa.String(180), nullable=False),
        sa.Column("classes_held", sa.Integer(), nullable=False),
        sa.Column("classes_attended", sa.Integer(), nullable=False),
        sa.Column("attendance_percent", sa.Numeric(5, 2)),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("external_id", sa.String(180)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_profile_id", "as_of", "scope_key", "source_key", name="uq_college_attendance_snapshot_scope"),
    )
    op.create_table(
        "college_career_profiles",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participation_status", sa.String(30), nullable=False),
        sa.Column("graduation_year", sa.Integer()),
        sa.Column("preferred_roles", JSON, nullable=False),
        sa.Column("preferred_locations", JSON, nullable=False),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("github_url", sa.String(500)),
        sa.Column("portfolio_url", sa.String(500)),
        sa.Column("resume_document_id", UUID, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("resume_status", sa.String(24), nullable=False),
        sa.Column("profile_summary", sa.Text()),
        sa.Column("placement_status", sa.String(24), nullable=False),
        sa.Column("manual_overrides", JSON, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_profile_id", name="uq_college_career_profile_student"),
    )
    op.create_table(
        "college_career_evidence",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("issuer", sa.String(180)),
        sa.Column("description", sa.Text()),
        sa.Column("evidence_url", sa.String(500)),
        sa.Column("document_id", UUID, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("started_on", sa.Date()),
        sa.Column("completed_on", sa.Date()),
        sa.Column("proficiency", sa.String(30)),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("verified_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("external_id", sa.String(180)),
        sa.Column("details", JSON, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_placement_assessments",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assessment_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("score_percent", sa.Numeric(5, 2)),
        sa.Column("assessed_on", sa.Date()),
        sa.Column("provider", sa.String(120)),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("external_id", sa.String(180)),
        sa.Column("details", JSON, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_preparation_activities",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("occurred_on", sa.Date()),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("outcome_score", sa.Numeric(5, 2)),
        sa.Column("details", JSON, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_student_interventions",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("assigned_to_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("due_on", sa.Date()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_note", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_coding_accounts",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("username", sa.String(120), nullable=False),
        sa.Column("verification_status", sa.String(24), nullable=False),
        sa.Column("consent_status", sa.String(24), nullable=False),
        sa.Column("sync_status", sa.String(24), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "platform", "username", name="uq_college_coding_platform_username"),
        sa.UniqueConstraint("student_profile_id", "platform", name="uq_college_coding_student_platform"),
    )
    op.create_table(
        "college_coding_snapshots",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("coding_account_id", UUID, sa.ForeignKey("college_coding_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("easy_solved", sa.Integer()),
        sa.Column("medium_solved", sa.Integer()),
        sa.Column("hard_solved", sa.Integer()),
        sa.Column("total_solved", sa.Integer()),
        sa.Column("contest_rating", sa.Numeric(8, 2)),
        sa.Column("contest_rank", sa.Integer()),
        sa.Column("global_rank", sa.Integer()),
        sa.Column("languages", JSON, nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("raw_metrics", JSON, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coding_account_id", "captured_at", name="uq_college_coding_snapshot_time"),
    )
    op.create_table(
        "college_readiness_policies",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("weights", JSON, nullable=False),
        sa.Column("bands", JSON, nullable=False),
        sa.Column("minimum_coverage_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "version", name="uq_college_readiness_policy_version"),
    )
    op.create_table(
        "college_readiness_snapshots",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("policy_id", UUID, sa.ForeignKey("college_readiness_policies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2)),
        sa.Column("coverage_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("band", sa.String(30), nullable=False),
        sa.Column("factors", JSON, nullable=False),
        sa.Column("missing_evidence", JSON, nullable=False),
        sa.Column("source_records", JSON, nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_placement_companies",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("industry", sa.String(100)),
        sa.Column("website", sa.String(500)),
        sa.Column("contact_name", sa.String(160)),
        sa.Column("contact_email", sa.String(255)),
        sa.Column("contact_phone", sa.String(40)),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_college_company_org_name"),
    )
    op.create_table(
        "college_pipeline_stages",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("stage_type", sa.String(30), nullable=False),
        sa.Column("is_terminal", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_college_pipeline_stage_slug"),
        sa.UniqueConstraint("organization_id", "display_order", name="uq_college_pipeline_stage_order"),
    )
    op.create_table(
        "college_placement_opportunities",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("company_id", UUID, sa.ForeignKey("college_placement_companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("opportunity_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("drive_at", sa.DateTime(timezone=True)),
        sa.Column("work_location", sa.String(180)),
        sa.Column("employment_type", sa.String(50)),
        sa.Column("package_min_paise", sa.Integer()),
        sa.Column("package_max_paise", sa.Integer()),
        sa.Column("role_description", sa.Text()),
        sa.Column("eligibility_rules", JSON, nullable=False),
        sa.Column("rounds", JSON, nullable=False),
        sa.Column("owner_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_placement_applications",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("opportunity_id", UUID, sa.ForeignKey("college_placement_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_stage_id", UUID, sa.ForeignKey("college_pipeline_stages.id", ondelete="SET NULL")),
        sa.Column("eligibility_status", sa.String(24), nullable=False),
        sa.Column("eligibility_evidence", JSON, nullable=False),
        sa.Column("eligibility_evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("eligibility_override_status", sa.String(24)),
        sa.Column("eligibility_override_reason", sa.Text()),
        sa.Column("eligibility_override_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("eligibility_override_at", sa.DateTime(timezone=True)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(30)),
        sa.Column("notes", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_id", "student_profile_id", name="uq_college_application_opportunity_student"),
    )
    op.create_table(
        "college_application_stage_events",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("application_id", UUID, sa.ForeignKey("college_placement_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_stage_id", UUID, sa.ForeignKey("college_pipeline_stages.id", ondelete="SET NULL")),
        sa.Column("to_stage_id", UUID, sa.ForeignKey("college_pipeline_stages.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("changed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reason", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_placement_interviews",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("application_id", UUID, sa.ForeignKey("college_placement_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interview_type", sa.String(40), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("mode", sa.String(30)),
        sa.Column("venue_or_link", sa.String(500)),
        sa.Column("interviewer", sa.String(180)),
        sa.Column("score_percent", sa.Numeric(5, 2)),
        sa.Column("feedback", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_placement_offers",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("application_id", UUID, sa.ForeignKey("college_placement_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offered_role", sa.String(180)),
        sa.Column("package_paise", sa.Integer()),
        sa.Column("offered_on", sa.Date()),
        sa.Column("joining_on", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("document_id", UUID, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_data_connectors",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("connector_type", sa.String(30), nullable=False),
        sa.Column("base_url", sa.String(500)),
        sa.Column("auth_mode", sa.String(30), nullable=False),
        sa.Column("auth_header", sa.String(100)),
        sa.Column("encrypted_api_key", sa.Text()),
        sa.Column("mapping", JSON, nullable=False),
        sa.Column("pagination", JSON, nullable=False),
        sa.Column("sync_interval_hours", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("next_sync_at", sa.DateTime(timezone=True)),
        sa.Column("cursor", sa.String(500)),
        sa.Column("last_error", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_college_connector_org_name"),
    )
    op.create_table(
        "college_import_runs",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("connector_id", UUID, sa.ForeignKey("college_data_connectors.id", ondelete="SET NULL")),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("idempotency_key", sa.String(180)),
        sa.Column("mapping", JSON, nullable=False),
        sa.Column("staged_rows", JSON, nullable=False),
        sa.Column("validation_errors", JSON, nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False),
        sa.Column("committed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("started_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "college_external_records",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("connector_id", UUID, sa.ForeignKey("college_data_connectors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(180), nullable=False),
        sa.Column("local_resource_type", sa.String(60), nullable=False),
        sa.Column("local_resource_id", UUID, nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("source_hash", sa.String(128)),
        sa.Column("manual_override_fields", JSON, nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "resource_type", "external_id", name="uq_college_external_record"),
    )
    op.create_table(
        "college_resume_drafts",
        sa.Column("id", UUID, nullable=False), _tenant(),
        sa.Column("student_profile_id", UUID, sa.ForeignKey("college_student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", UUID, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("extracted_data", JSON, nullable=False),
        sa.Column("reviewed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_note", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )

    index_map = {
        "college_term_results": ["organization_id", "student_profile_id", "term_id", "result_status", "external_id"],
        "college_attendance_snapshots": ["organization_id", "student_profile_id", "term_id", "course_id", "as_of", "external_id"],
        "college_career_profiles": ["organization_id", "student_profile_id", "participation_status", "graduation_year", "resume_document_id", "resume_status", "placement_status"],
        "college_career_evidence": ["organization_id", "student_profile_id", "evidence_type", "document_id", "is_verified", "verified_by_user_id", "external_id"],
        "college_placement_assessments": ["organization_id", "student_profile_id", "assessment_type", "assessed_on", "external_id"],
        "college_preparation_activities": ["organization_id", "student_profile_id", "activity_type", "status", "occurred_on"],
        "college_student_interventions": ["organization_id", "student_profile_id", "reason_code", "status", "priority", "assigned_to_user_id", "due_on"],
        "college_coding_accounts": ["organization_id", "student_profile_id", "platform", "username", "verification_status", "consent_status", "sync_status", "last_synced_at", "last_success_at"],
        "college_coding_snapshots": ["organization_id", "coding_account_id", "student_profile_id", "captured_at"],
        "college_readiness_policies": ["organization_id", "is_active", "created_by_user_id"],
        "college_readiness_snapshots": ["organization_id", "student_profile_id", "policy_id", "score", "coverage_percent", "band", "calculated_at"],
        "college_placement_companies": ["organization_id", "name", "is_active"],
        "college_pipeline_stages": ["organization_id", "stage_type", "is_enabled"],
        "college_placement_opportunities": ["organization_id", "company_id", "opportunity_type", "status", "deadline_at", "drive_at", "owner_user_id"],
        "college_placement_applications": ["organization_id", "opportunity_id", "student_profile_id", "current_stage_id", "eligibility_status", "eligibility_override_by_user_id", "applied_at", "outcome"],
        "college_application_stage_events": ["organization_id", "application_id", "to_stage_id", "changed_by_user_id", "occurred_at"],
        "college_placement_interviews": ["organization_id", "application_id", "interview_type", "scheduled_at", "status"],
        "college_placement_offers": ["organization_id", "application_id", "offered_on", "status", "document_id"],
        "college_data_connectors": ["organization_id", "connector_type", "status", "last_sync_at", "next_sync_at", "is_active"],
        "college_import_runs": ["organization_id", "connector_id", "source_type", "resource_type", "status", "idempotency_key", "started_by_user_id"],
        "college_external_records": ["organization_id", "connector_id", "resource_type", "external_id", "local_resource_id"],
        "college_resume_drafts": ["organization_id", "student_profile_id", "document_id", "status", "reviewed_by_user_id"],
    }
    for table, columns in index_map.items():
        _indexes(table, columns)


def downgrade():
    for table in (
        "college_resume_drafts", "college_external_records", "college_import_runs",
        "college_data_connectors", "college_placement_offers", "college_placement_interviews",
        "college_application_stage_events", "college_placement_applications",
        "college_placement_opportunities", "college_pipeline_stages",
        "college_placement_companies", "college_readiness_snapshots",
        "college_readiness_policies", "college_coding_snapshots", "college_coding_accounts",
        "college_student_interventions", "college_preparation_activities",
        "college_placement_assessments", "college_career_evidence",
        "college_career_profiles", "college_attendance_snapshots", "college_term_results",
    ):
        op.drop_table(table)
