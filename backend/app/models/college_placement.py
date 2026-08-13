"""College placement intelligence, evidence, pipeline, and ingestion models."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class CollegeTermResult(TimestampMixin, Base):
    __tablename__ = "college_term_results"
    __table_args__ = (
        UniqueConstraint(
            "student_profile_id", "semester", "source_key",
            name="uq_college_term_result_student_semester_source",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    term_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_terms.id", ondelete="SET NULL"), index=True)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    sgpa: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cgpa: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    credits_earned: Mapped[int | None] = mapped_column(Integer)
    total_backlogs: Mapped[int | None] = mapped_column(Integer)
    active_backlogs: Mapped[int | None] = mapped_column(Integer)
    result_status: Mapped[str] = mapped_column(String(24), default="published", nullable=False, index=True)
    published_on: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), default="manual", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(180), index=True)
    source_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeAttendanceSnapshot(TimestampMixin, Base):
    __tablename__ = "college_attendance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "student_profile_id", "as_of", "scope_key", "source_key",
            name="uq_college_attendance_snapshot_scope",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    term_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_terms.id", ondelete="SET NULL"), index=True)
    course_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_courses.id", ondelete="SET NULL"), index=True)
    scope_key: Mapped[str] = mapped_column(String(180), default="overall", nullable=False)
    classes_held: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classes_attended: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attendance_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    as_of: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), default="manual", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(180), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeCareerProfile(TimestampMixin, Base):
    __tablename__ = "college_career_profiles"
    __table_args__ = (UniqueConstraint("student_profile_id", name="uq_college_career_profile_student"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    participation_status: Mapped[str] = mapped_column(String(30), default="participating", nullable=False, index=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, index=True)
    preferred_roles: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    preferred_locations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    portfolio_url: Mapped[str | None] = mapped_column(String(500))
    resume_document_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    resume_status: Mapped[str] = mapped_column(String(24), default="missing", nullable=False, index=True)
    profile_summary: Mapped[str | None] = mapped_column(Text)
    placement_status: Mapped[str] = mapped_column(String(24), default="seeking", nullable=False, index=True)
    manual_overrides: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class CollegeCareerEvidence(TimestampMixin, Base):
    __tablename__ = "college_career_evidence"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    evidence_url: Mapped[str | None] = mapped_column(String(500))
    document_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    started_on: Mapped[date | None] = mapped_column(Date)
    completed_on: Mapped[date | None] = mapped_column(Date)
    proficiency: Mapped[str | None] = mapped_column(String(30))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verified_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_type: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(180), index=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegePlacementAssessment(TimestampMixin, Base):
    __tablename__ = "college_placement_assessments"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    assessment_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    score_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    assessed_on: Mapped[date | None] = mapped_column(Date, index=True)
    provider: Mapped[str | None] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(180), index=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class CollegePreparationActivity(TimestampMixin, Base):
    __tablename__ = "college_preparation_activities"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="completed", nullable=False, index=True)
    occurred_on: Mapped[date | None] = mapped_column(Date, index=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    outcome_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class CollegeStudentIntervention(TimestampMixin, Base):
    __tablename__ = "college_student_interventions"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False, index=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)


class CollegeCodingAccount(TimestampMixin, Base):
    __tablename__ = "college_coding_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "platform", "username", name="uq_college_coding_platform_username"),
        UniqueConstraint("student_profile_id", "platform", name="uq_college_coding_student_platform"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(30), default="leetcode", nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified", nullable=False, index=True)
    consent_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    sync_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CollegeCodingSnapshot(TimestampMixin, Base):
    __tablename__ = "college_coding_snapshots"
    __table_args__ = (
        UniqueConstraint("coding_account_id", "captured_at", name="uq_college_coding_snapshot_time"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    coding_account_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_coding_accounts.id", ondelete="CASCADE"), index=True)
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    easy_solved: Mapped[int | None] = mapped_column(Integer)
    medium_solved: Mapped[int | None] = mapped_column(Integer)
    hard_solved: Mapped[int | None] = mapped_column(Integer)
    total_solved: Mapped[int | None] = mapped_column(Integer)
    contest_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    contest_rank: Mapped[int | None] = mapped_column(Integer)
    global_rank: Mapped[int | None] = mapped_column(Integer)
    languages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), default="sync", nullable=False)
    raw_metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class CollegeReadinessPolicy(TimestampMixin, Base):
    __tablename__ = "college_readiness_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "version", name="uq_college_readiness_policy_version"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120), default="Placement readiness", nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    weights: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    bands: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    minimum_coverage_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=60, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)


class CollegeReadinessSnapshot(TimestampMixin, Base):
    __tablename__ = "college_readiness_snapshots"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    policy_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_readiness_policies.id", ondelete="RESTRICT"), index=True)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), index=True)
    coverage_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, index=True)
    band: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    factors: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    missing_evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    source_records: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class CollegePlacementCompany(TimestampMixin, Base):
    __tablename__ = "college_placement_companies"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_college_company_org_name"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    industry: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(500))
    contact_name: Mapped[str | None] = mapped_column(String(160))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class CollegePipelineStage(TimestampMixin, Base):
    __tablename__ = "college_pipeline_stages"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_college_pipeline_stage_slug"),
        UniqueConstraint("organization_id", "display_order", name="uq_college_pipeline_stage_order"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_type: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class CollegePlacementOpportunity(TimestampMixin, Base):
    __tablename__ = "college_placement_opportunities"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    company_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_placement_companies.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(30), default="campus_drive", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    drive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    work_location: Mapped[str | None] = mapped_column(String(180))
    employment_type: Mapped[str | None] = mapped_column(String(50))
    package_min_paise: Mapped[int | None] = mapped_column(Integer)
    package_max_paise: Mapped[int | None] = mapped_column(Integer)
    role_description: Mapped[str | None] = mapped_column(Text)
    eligibility_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    rounds: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)


class CollegePlacementApplication(TimestampMixin, Base):
    __tablename__ = "college_placement_applications"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "student_profile_id", name="uq_college_application_opportunity_student"),
        Index("ix_college_app_eligibility_override_user", "eligibility_override_by_user_id"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    opportunity_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_placement_opportunities.id", ondelete="CASCADE"), index=True)
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    current_stage_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_pipeline_stages.id", ondelete="SET NULL"), index=True)
    eligibility_status: Mapped[str] = mapped_column(String(24), default="needs_review", nullable=False, index=True)
    eligibility_evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    eligibility_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eligibility_override_status: Mapped[str | None] = mapped_column(String(24))
    eligibility_override_reason: Mapped[str | None] = mapped_column(Text)
    eligibility_override_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    eligibility_override_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    outcome: Mapped[str | None] = mapped_column(String(30), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeApplicationStageEvent(TimestampMixin, Base):
    __tablename__ = "college_application_stage_events"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    application_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_placement_applications.id", ondelete="CASCADE"), index=True)
    from_stage_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_pipeline_stages.id", ondelete="SET NULL"))
    to_stage_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_pipeline_stages.id", ondelete="RESTRICT"), index=True)
    changed_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class CollegePlacementInterview(TimestampMixin, Base):
    __tablename__ = "college_placement_interviews"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    application_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_placement_applications.id", ondelete="CASCADE"), index=True)
    interview_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="scheduled", nullable=False, index=True)
    mode: Mapped[str | None] = mapped_column(String(30))
    venue_or_link: Mapped[str | None] = mapped_column(String(500))
    interviewer: Mapped[str | None] = mapped_column(String(180))
    score_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    feedback: Mapped[str | None] = mapped_column(Text)


class CollegePlacementOffer(TimestampMixin, Base):
    __tablename__ = "college_placement_offers"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    application_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_placement_applications.id", ondelete="CASCADE"), index=True)
    offered_role: Mapped[str | None] = mapped_column(String(180))
    package_paise: Mapped[int | None] = mapped_column(Integer)
    offered_on: Mapped[date | None] = mapped_column(Date, index=True)
    joining_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="offered", nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)


class CollegeDataConnector(TimestampMixin, Base):
    __tablename__ = "college_data_connectors"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_college_connector_org_name"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(30), default="erp", nullable=False, index=True)
    base_url: Mapped[str | None] = mapped_column(String(500))
    auth_mode: Mapped[str] = mapped_column(String(30), default="bearer", nullable=False)
    auth_header: Mapped[str | None] = mapped_column(String(100))
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    mapping: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    pagination: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sync_interval_hours: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="setup", nullable=False, index=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cursor: Mapped[str | None] = mapped_column(String(500))
    last_error: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class CollegeImportRun(TimestampMixin, Base):
    __tablename__ = "college_import_runs"
    __table_args__ = (
        UniqueConstraint(
            "credential_id", "idempotency_key",
            name="uq_college_import_credential_idempotency",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    connector_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_data_connectors.id", ondelete="SET NULL"), index=True)
    credential_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("college_integration_credentials.id", ondelete="SET NULL"), index=True)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="staged", nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(180), index=True)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    mapping: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    staged_rows: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    committed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CollegeExternalRecord(TimestampMixin, Base):
    __tablename__ = "college_external_records"
    __table_args__ = (
        UniqueConstraint("connector_id", "resource_type", "external_id", name="uq_college_external_record"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    connector_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_data_connectors.id", ondelete="CASCADE"), index=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    local_resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    local_resource_id: Mapped[str] = mapped_column(UUID_STR, nullable=False, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_hash: Mapped[str | None] = mapped_column(String(128))
    manual_override_fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CollegeClearanceSnapshot(TimestampMixin, Base):
    __tablename__ = "college_clearance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "student_profile_id", "as_of", "source_key",
            name="uq_college_clearance_student_date_source",
        ),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(24), default="erp", nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(180), index=True)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class CollegeIntegrationCredential(TimestampMixin, Base):
    __tablename__ = "college_integration_credentials"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_college_integration_credential_name"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    connector_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("college_data_connectors.id", ondelete="CASCADE"), unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ip: Mapped[str | None] = mapped_column(String(80))
    created_by_user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CollegeIntegrationRateBucket(Base):
    __tablename__ = "college_integration_rate_buckets"
    __table_args__ = (
        UniqueConstraint("credential_id", "window_start", name="uq_college_integration_rate_window"),
    )

    id: Mapped[str] = uuid_pk()
    credential_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("college_integration_credentials.id", ondelete="CASCADE"), index=True
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CollegeResumeDraft(TimestampMixin, Base):
    __tablename__ = "college_resume_drafts"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_profile_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("college_student_profiles.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending_review", nullable=False, index=True)
    extracted_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
