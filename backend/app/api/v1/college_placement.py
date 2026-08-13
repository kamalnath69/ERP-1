"""College placement intelligence, student evidence, pipeline, and import APIs."""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import Field, HttpUrl, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.validation import RequestModel
from app.core.deps import require_entitlements, require_permissions
from app.models import (
    Client, CollegeApplicationStageEvent, CollegeAttendanceSnapshot, CollegeCareerEvidence,
    CollegeCareerProfile, CollegeCodingAccount, CollegeCodingSnapshot, CollegeDataConnector,
    CollegeImportRun, CollegePipelineStage, CollegePlacementApplication,
    CollegePlacementAssessment, CollegePlacementCompany, CollegePlacementInterview,
    CollegePlacementOffer, CollegePlacementOpportunity, CollegePreparationActivity,
    CollegeReadinessPolicy, CollegeResumeDraft, CollegeStudentIntervention,
    CollegeStudentProfile, CollegeTermResult, Document, FeatureFlag, Job, User,
)
from app.services.audit import log_action
from app.ai.retrieval import ensure_college_document_entity_access
from app.services.college import require_college, serialize, tenant_row
from app.services.college_access import CollegeAccess, resolve_college_access, validate_college_filters
from app.services.college_imports import RESOURCE_FIELDS, commit_run, stage_rows
from app.services.college_placement import (
    DEFAULT_BANDS, DEFAULT_WEIGHTS, active_readiness_policy, eligibility_context,
    ensure_default_pipeline, evaluate_eligibility, fee_clearance_by_student, placement_dashboard,
    opportunity_eligibility_rules, placement_leaderboards, recompute_readiness,
    student_intelligence, student_roster,
)
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_response, page_size
from app.services.platform_security import encrypt_secret
from app.services.rbac import get_user_permissions
from app.services.upload_validation import safe_upload_name, validate_upload_signature


def require_placement_v1(
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.view")),
) -> User:
    flag = db.execute(select(FeatureFlag).where(
        FeatureFlag.organization_id == user.organization_id,
        FeatureFlag.flag == "college.placement_v1",
        FeatureFlag.enabled.is_(True),
    )).scalar_one_or_none()
    if not flag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "College placement intelligence is not enabled")
    return user


router = APIRouter(
    prefix="/college",
    tags=["college-placement"],
    dependencies=[Depends(require_entitlements("module.college")), Depends(require_placement_v1)],
)


ERP_PULL_RESOURCES = {
    "departments", "programs", "terms", "cohorts", "courses", "students",
    "term_results", "attendance", "skills", "assessments", "exam_cycles",
    "assessment_marks", "internship_clearance",
}
MAPPING_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_.$\[\]-]{1,240}$")


class ReadinessPolicyBody(RequestModel):
    name: str = Field(default="Placement readiness", min_length=2, max_length=120)
    weights: dict[str, float]
    bands: dict[str, float]
    minimum_coverage_percent: float = Field(default=60, ge=1, le=100)

    @model_validator(mode="after")
    def validate_policy(self):
        expected = set(DEFAULT_WEIGHTS)
        if set(self.weights) != expected:
            raise ValueError(f"Weights must contain exactly: {', '.join(sorted(expected))}")
        if any(value < 0 or value > 100 for value in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError("Weights must be between 0 and 100 and include a positive total")
        if set(self.bands) != {"ready", "developing"}:
            raise ValueError("Bands must contain ready and developing")
        if not 0 <= self.bands["developing"] < self.bands["ready"] <= 100:
            raise ValueError("Readiness bands must be ordered between 0 and 100")
        return self


class CareerBody(RequestModel):
    participation_status: Literal["participating", "not_participating", "on_hold"] = "participating"
    graduation_year: int | None = Field(default=None, ge=2000, le=2200)
    preferred_roles: list[str] = Field(default_factory=list, max_length=20)
    preferred_locations: list[str] = Field(default_factory=list, max_length=20)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    resume_status: Literal["missing", "draft", "pending_review", "reviewed", "approved"] = "missing"
    profile_summary: str | None = Field(default=None, max_length=3000)
    placement_status: Literal["seeking", "not_seeking", "placed", "joined"] = "seeking"


class EvidenceBody(RequestModel):
    evidence_type: Literal["skill", "project", "certification"]
    title: str = Field(min_length=1, max_length=220)
    issuer: str | None = Field(default=None, max_length=180)
    description: str | None = Field(default=None, max_length=3000)
    evidence_url: str | None = Field(default=None, max_length=500)
    document_id: str | None = None
    started_on: date | None = None
    completed_on: date | None = None
    proficiency: str | None = Field(default=None, max_length=30)
    is_verified: bool = False
    details: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.started_on and self.completed_on and self.completed_on < self.started_on:
            raise ValueError("Completion date cannot be before the start date")
        return self


class TermResultBody(RequestModel):
    semester: int = Field(ge=1, le=16)
    term_id: str | None = None
    sgpa: Decimal | None = Field(default=None, ge=0, le=10)
    cgpa: Decimal | None = Field(default=None, ge=0, le=10)
    credits_earned: int | None = Field(default=None, ge=0, le=500)
    total_backlogs: int | None = Field(default=None, ge=0, le=100)
    active_backlogs: int | None = Field(default=None, ge=0, le=100)
    published_on: date | None = None

    @model_validator(mode="after")
    def valid_backlogs(self):
        if self.active_backlogs is not None and self.total_backlogs is not None and self.active_backlogs > self.total_backlogs:
            raise ValueError("Active backlogs cannot exceed total backlogs")
        return self


class AttendanceSnapshotBody(RequestModel):
    term_id: str | None = None
    course_id: str | None = None
    scope: str = Field(default="overall", min_length=1, max_length=180)
    classes_held: int = Field(ge=0, le=10000)
    classes_attended: int = Field(ge=0, le=10000)
    attendance_percent: Decimal | None = Field(default=None, ge=0, le=100)
    as_of: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def valid_counts(self):
        if self.classes_attended > self.classes_held:
            raise ValueError("Classes attended cannot exceed classes held")
        return self


class PlacementAssessmentBody(RequestModel):
    assessment_type: Literal["aptitude", "technical", "communication", "coding", "psychometric", "other"]
    title: str = Field(min_length=2, max_length=180)
    score_percent: Decimal | None = Field(default=None, ge=0, le=100)
    assessed_on: date | None = None
    provider: str | None = Field(default=None, max_length=120)
    details: dict = Field(default_factory=dict)


class PreparationBody(RequestModel):
    activity_type: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=2, max_length=180)
    status: Literal["planned", "in_progress", "completed", "cancelled"] = "completed"
    occurred_on: date | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=100000)
    outcome_score: Decimal | None = Field(default=None, ge=0, le=100)
    details: dict = Field(default_factory=dict)


class InterventionBody(RequestModel):
    reason_code: str = Field(min_length=2, max_length=50)
    title: str = Field(min_length=2, max_length=220)
    note: str | None = Field(default=None, max_length=3000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    assigned_to_user_id: str | None = None
    due_on: date | None = None


class InterventionUpdateBody(RequestModel):
    status: Literal["open", "snoozed", "resolved"]
    resolution_note: str | None = Field(default=None, max_length=3000)


class CodingAccountBody(RequestModel):
    username: str = Field(min_length=2, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    consent_status: Literal["pending", "granted", "revoked"] = "pending"
    verification_status: Literal["unverified", "verified", "failed"] = "unverified"


class CodingSnapshotBody(RequestModel):
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    easy_solved: int | None = Field(default=None, ge=0)
    medium_solved: int | None = Field(default=None, ge=0)
    hard_solved: int | None = Field(default=None, ge=0)
    total_solved: int | None = Field(default=None, ge=0)
    contest_rating: Decimal | None = Field(default=None, ge=0)
    contest_rank: int | None = Field(default=None, ge=0)
    global_rank: int | None = Field(default=None, ge=0)
    languages: list[str] = Field(default_factory=list, max_length=30)


class CompanyBody(RequestModel):
    name: str = Field(min_length=2, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=160)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=5000)


class StageBody(RequestModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    stage_type: Literal["active", "placed", "rejected", "withdrawn"] = "active"
    is_terminal: bool = False
    is_enabled: bool = True


class StageListBody(RequestModel):
    stages: list[StageBody] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_slugs(self):
        if len({row.slug for row in self.stages}) != len(self.stages):
            raise ValueError("Pipeline stage slugs must be unique")
        return self


class OpportunityBody(RequestModel):
    company_id: str
    title: str = Field(min_length=2, max_length=220)
    opportunity_type: Literal["campus_drive", "internship", "off_campus", "apprenticeship"] = "campus_drive"
    status: Literal["draft", "published", "active", "closed", "cancelled"] = "draft"
    opens_at: datetime | None = None
    deadline_at: datetime | None = None
    drive_at: datetime | None = None
    work_location: str | None = Field(default=None, max_length=180)
    employment_type: str | None = Field(default=None, max_length=50)
    package_min_paise: int | None = Field(default=None, ge=0)
    package_max_paise: int | None = Field(default=None, ge=0)
    role_description: str | None = Field(default=None, max_length=10000)
    eligibility_rules: dict = Field(default_factory=dict)
    rounds: list[dict] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_package(self):
        if self.package_min_paise is not None and self.package_max_paise is not None and self.package_max_paise < self.package_min_paise:
            raise ValueError("Maximum package must be at least the minimum package")
        if self.opens_at and self.deadline_at and self.deadline_at < self.opens_at:
            raise ValueError("Opportunity deadline cannot be before its opening time")
        if self.deadline_at and self.drive_at and self.drive_at < self.deadline_at:
            raise ValueError("Drive time cannot be before the application deadline")
        protected = {
            "age", "caste", "category", "date_of_birth", "disability", "ethnicity",
            "gender", "guardian", "guardian_income", "marital_status", "nationality",
            "pregnancy", "race", "religion", "sex",
        }

        def keys(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
                    yield normalized
                    yield from keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from keys(nested)

        if protected & set(keys(self.eligibility_rules)):
            raise ValueError("Protected attributes cannot be used in eligibility")
        if self.opportunity_type == "internship":
            self.eligibility_rules = {
                **self.eligibility_rules,
                "require_fee_clearance": True,
            }
        return self


class ApplicationBody(RequestModel):
    opportunity_id: str
    student_profile_id: str
    notes: str | None = Field(default=None, max_length=5000)


class StageMoveBody(RequestModel):
    stage_id: str
    reason: str | None = Field(default=None, max_length=2000)
    version: int = Field(ge=1)


class EligibilityOverrideBody(RequestModel):
    status: Literal["eligible", "ineligible", "needs_review"]
    reason: str = Field(min_length=3, max_length=2000)
    version: int = Field(ge=1)


class InterviewBody(RequestModel):
    interview_type: str = Field(min_length=2, max_length=40)
    scheduled_at: datetime | None = None
    status: Literal["scheduled", "completed", "cancelled", "no_show"] = "scheduled"
    mode: str | None = Field(default=None, max_length=30)
    venue_or_link: str | None = Field(default=None, max_length=500)
    interviewer: str | None = Field(default=None, max_length=180)
    score_percent: Decimal | None = Field(default=None, ge=0, le=100)
    feedback: str | None = Field(default=None, max_length=5000)


class OfferBody(RequestModel):
    offered_role: str | None = Field(default=None, max_length=180)
    package_paise: int | None = Field(default=None, ge=0)
    offered_on: date | None = None
    joining_on: date | None = None
    status: Literal["offered", "accepted", "declined", "joined", "withdrawn"] = "offered"
    document_id: str | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.offered_on and self.joining_on and self.joining_on < self.offered_on:
            raise ValueError("Joining date cannot be before the offer date")
        return self


class ImportPreviewBody(RequestModel):
    resource_type: Literal[
        "departments", "programs", "terms", "cohorts", "courses", "students",
        "term_results", "attendance", "skills", "assessments", "internship_clearance",
        "exam_cycles", "assessment_marks",
    ]
    rows: list[dict] = Field(min_length=1, max_length=5000)
    mapping: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=180)


class ConnectorBody(RequestModel):
    name: str = Field(min_length=2, max_length=120)
    base_url: str = Field(min_length=8, max_length=2000)
    auth_mode: Literal["bearer", "header"] = "bearer"
    auth_header: str | None = Field(default=None, max_length=100)
    api_key: str | None = Field(default=None, max_length=2000)
    mapping: dict = Field(default_factory=dict)
    pagination: dict = Field(default_factory=dict)
    sync_interval_hours: int = Field(default=6, ge=1, le=168)

    @model_validator(mode="after")
    def validate_auth_header(self):
        if self.auth_mode == "header" and not self.auth_header:
            raise ValueError("A header name is required for header authentication")
        if self.auth_header and not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", self.auth_header):
            raise ValueError("Authentication header name is invalid")
        if len(json.dumps(self.mapping, default=str)) > 100_000:
            raise ValueError("ERP mapping is too large")
        resources = self.mapping.get("resources", self.mapping)
        if not isinstance(resources, dict):
            raise ValueError("ERP mapping resources must be an object")
        unknown_resources = set(resources) - ERP_PULL_RESOURCES
        if unknown_resources:
            raise ValueError(f"Unsupported ERP resources: {', '.join(sorted(unknown_resources))}")
        for resource, config in resources.items():
            if not isinstance(config, dict):
                raise ValueError(f"{resource} mapping must be an object")
            path = config.get("path")
            if path is not None and (not isinstance(path, str) or len(path) > 500 or "://" in path):
                raise ValueError(f"{resource} endpoint must be a relative path")
            root_path = config.get("root_path")
            if root_path is not None and (not isinstance(root_path, str) or not MAPPING_PATH_PATTERN.fullmatch(root_path)):
                raise ValueError(f"{resource} root path is invalid")
            for mapping_key in ("fields", "metrics"):
                mapping = config.get(mapping_key, {})
                if not isinstance(mapping, dict) or len(mapping) > 200:
                    raise ValueError(f"{resource} {mapping_key} mapping must be an object with at most 200 entries")
                for target, source in mapping.items():
                    if not MAPPING_PATH_PATTERN.fullmatch(str(target)) or not MAPPING_PATH_PATTERN.fullmatch(str(source)):
                        raise ValueError(f"{resource} {mapping_key} contains an invalid field path")
            resource_pagination = config.get("pagination")
            if resource_pagination is not None and not isinstance(resource_pagination, dict):
                raise ValueError(f"{resource} pagination must be an object")
        if len(json.dumps(self.pagination, default=str)) > 20_000:
            raise ValueError("ERP pagination mapping is too large")
        if not isinstance(self.pagination, dict):
            raise ValueError("ERP pagination must be an object")
        mode = self.pagination.get("mode")
        if mode not in {None, "cursor", "updated_since"}:
            raise ValueError("ERP pagination mode must be cursor or updated_since")
        for key in ("cursor_param", "updated_since_param", "next_url_path", "cursor_path"):
            value = self.pagination.get(key)
            if value is not None and (not isinstance(value, str) or not MAPPING_PATH_PATTERN.fullmatch(value)):
                raise ValueError(f"ERP pagination {key} is invalid")
        return self


class SyncBody(RequestModel):
    resource_types: list[Literal[
        "departments", "programs", "terms", "cohorts", "courses", "students",
        "term_results", "attendance", "skills", "assessments", "exam_cycles",
        "assessment_marks", "internship_clearance",
    ]] = Field(default_factory=list, max_length=20)
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=8, max_length=120)

    @model_validator(mode="after")
    def validate_resources(self):
        if len(self.resource_types) != len(set(self.resource_types)):
            raise ValueError("ERP sync resources cannot contain duplicates")
        return self


class ResumeExtractBody(RequestModel):
    document_id: str
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=8, max_length=120)


class ResumeReviewBody(RequestModel):
    decision: Literal["approve", "reject"]
    accepted: dict = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=3000)


def _run_payload(run: CollegeImportRun) -> dict:
    return {
        "id": run.id,
        "source_type": run.source_type,
        "resource_type": run.resource_type,
        "status": run.status,
        "row_count": run.row_count,
        "valid_count": run.valid_count,
        "committed_count": run.committed_count,
        "failed_count": run.failed_count,
        "validation_errors": run.validation_errors,
        "preview": run.staged_rows[:25],
        "created_at": run.created_at,
        "completed_at": run.completed_at,
    }


def _connector_payload(row: CollegeDataConnector) -> dict:
    mapping = row.mapping or {}
    resource_configs = mapping.get("resources", mapping)
    return {
        "id": row.id,
        "name": row.name,
        "connector_type": row.connector_type,
        "base_url": row.base_url,
        "auth_mode": row.auth_mode,
        "auth_header": row.auth_header,
        "api_key_configured": bool(row.encrypted_api_key),
        "mapping": row.mapping,
        "resource_types": sorted(resource_configs) if isinstance(resource_configs, dict) else [],
        "pagination": row.pagination,
        "sync_interval_hours": row.sync_interval_hours,
        "status": row.status,
        "last_sync_at": row.last_sync_at,
        "next_sync_at": row.next_sync_at,
        "last_error": row.last_error,
        "is_active": row.is_active,
    }


def _validate_connector_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ERP URL must be a credential-free HTTPS URL")
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Private network ERP URLs are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Private network ERP URLs are not allowed")
    return value.strip().rstrip("/")


def _queue_job(db: Session, organization_id: str, kind: str, payload: dict, idempotency_key: str) -> Job:
    existing = db.execute(select(Job).where(
        Job.organization_id == organization_id,
        Job.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
    if existing:
        return existing
    job = Job(
        organization_id=organization_id,
        kind=kind,
        payload=payload,
        status="queued",
        run_at=datetime.now(timezone.utc),
        max_attempts=5,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    db.flush()
    return job


def _require_student_scope(db: Session, user: User, student_id: str, domain: str = "students") -> None:
    resolve_college_access(db, user, domain).require_student(student_id)


def _require_sensitive_capability(db: Session, user: User, permission: str, message: str) -> None:
    if permission not in get_user_permissions(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, message)


def _student_document(db: Session, user: User, document_id: str, student_id: str, label: str = "Document") -> Document:
    _require_sensitive_capability(
        db, user, "college.documents.sensitive.view", "Sensitive student document access is required",
    )
    if "documents.view" not in get_user_permissions(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Document access is required")
    document = tenant_row(db, Document, document_id, user, label)
    ensure_college_document_entity_access(db, user, document.entity_type, document.entity_id)
    if document.entity_type in {"client", "patient", "student", "college_student"}:
        linked = db.execute(select(CollegeStudentProfile).where(
            CollegeStudentProfile.organization_id == user.organization_id,
            or_(CollegeStudentProfile.id == document.entity_id, CollegeStudentProfile.client_id == document.entity_id),
        )).scalar_one_or_none()
        if not linked or linked.id != student_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return document


def _intersect_access(*items: CollegeAccess, domain: str) -> CollegeAccess:
    constrained = [item for item in items if not item.unrestricted]
    if not constrained:
        return CollegeAccess(
            unrestricted=True,
            policy_version=max((item.policy_version for item in items), default=0),
            domain=domain,
        )
    return CollegeAccess(
        unrestricted=False,
        student_ids=frozenset.intersection(*(item.student_ids for item in constrained)),
        full_student_ids=frozenset.intersection(*(item.full_student_ids for item in constrained)),
        department_ids=frozenset.intersection(*(item.department_ids for item in constrained)),
        program_ids=frozenset.intersection(*(item.program_ids for item in constrained)),
        cohort_ids=frozenset.intersection(*(item.cohort_ids for item in constrained)),
        course_offering_ids=frozenset.intersection(*(item.course_offering_ids for item in constrained)),
        location_ids=frozenset.intersection(*(item.location_ids for item in constrained)),
        policy_version=max((item.policy_version for item in items), default=0),
        domain=domain,
    )


LEGACY_IMPORT_REQUIREMENTS = {
    "departments": ("academics", "college.academics.manage"),
    "programs": ("academics", "college.academics.manage"),
    "terms": ("academics", "college.academics.manage"),
    "cohorts": ("academics", "college.academics.manage"),
    "courses": ("academics", "college.academics.manage"),
    "students": ("students", "college.students.manage"),
    "term_results": ("assessments", "college.assessments.record"),
    "assessments": ("assessments", "college.assessments.record"),
    "exam_cycles": ("assessments", "college.assessments.manage"),
    "assessment_marks": ("assessments", "college.assessments.record"),
    "attendance": ("attendance", "college.attendance.mark"),
    "skills": ("coding", "college.coding.manage"),
    "internship_clearance": ("clearance", "college.clearance.manage"),
}


def _legacy_import_access(db: Session, user: User, resource_type: str) -> CollegeAccess:
    requirement = LEGACY_IMPORT_REQUIREMENTS.get(resource_type)
    if not requirement:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported College import resource")
    domain, permission = requirement
    if permission not in get_user_permissions(db, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This import requires the corresponding College work area and safeguard",
        )
    data_access = resolve_college_access(db, user, "data")
    domain_access = resolve_college_access(db, user, domain)
    access = _intersect_access(data_access, domain_access, domain=domain)
    if resource_type in {"departments", "terms"} and not access.unrestricted:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This institution-wide structure import requires whole-institution reach",
        )
    return access


def _optional_domain_access(
    db: Session,
    user: User,
    permissions: set[str],
    domain: str,
    permission: str,
) -> CollegeAccess | None:
    if permission not in permissions:
        return None
    try:
        return resolve_college_access(db, user, domain)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return None
        raise


def _sanitize_student_intelligence(db: Session, user: User, student_id: str, payload: dict) -> dict:
    permissions = get_user_permissions(db, user)
    domains = {
        "assessments": _optional_domain_access(db, user, permissions, "assessments", "college.assessments.view"),
        "attendance": _optional_domain_access(db, user, permissions, "attendance", "college.attendance.view"),
        "coding": _optional_domain_access(db, user, permissions, "coding", "college.coding.view"),
        "placements": _optional_domain_access(db, user, permissions, "placements", "college.placements.view"),
        "documents": _optional_domain_access(db, user, permissions, "documents", "documents.view"),
        "clearance": _optional_domain_access(db, user, permissions, "clearance", "college.clearance.view"),
    }

    def can(domain: str) -> bool:
        access = domains.get(domain)
        return bool(access and access.allows_student(student_id))

    student = payload.get("student") or {}
    if "college.students.contact.view" not in permissions:
        student.pop("email", None)
        student.pop("phone", None)
    if not can("assessments"):
        payload["academics"] = []
        payload["assessments"] = []
    if not can("attendance"):
        payload["attendance"] = []
    if not can("coding"):
        payload["coding"] = {"account": None, "snapshots": []}
        payload["evidence"] = {"skill": [], "project": [], "certification": []}
    if not can("placements"):
        payload["career"] = None
        payload["applications"] = []
    if not can("clearance"):
        payload["fee_clearance"] = None
    elif payload.get("fee_clearance"):
        # Placement and academic staff need the gate, not financial details or
        # invoice counts. Amounts remain in the finance-only endpoints.
        payload["fee_clearance"] = {"status": payload["fee_clearance"].get("status")}
    if "college.notes.private.view" not in permissions:
        payload["interventions"] = []

    allowed_activity_types = {"preparation"}
    if can("assessments"):
        allowed_activity_types.add("term_result")
    if can("coding"):
        allowed_activity_types.add("coding_snapshot")
    if can("placements"):
        allowed_activity_types.add("application_stage")
    if "college.notes.private.view" in permissions:
        allowed_activity_types.add("intervention")
    payload["activity"] = [
        row for row in payload.get("activity", []) if row.get("type") in allowed_activity_types
    ]

    readiness = payload.get("readiness") or {}
    source_records = dict(readiness.get("source_records") or {})
    if not can("assessments"):
        for key in ("academics", "assessment", "assessments", "term_results"):
            source_records.pop(key, None)
    if not can("attendance"):
        source_records.pop("attendance", None)
    if not can("coding"):
        source_records.pop("coding", None)
    if not can("placements"):
        for key in ("profile", "projects", "placement"):
            source_records.pop(key, None)
    if readiness:
        readiness["source_records"] = source_records
    return payload


def _sanitize_roster_items(db: Session, user: User, payload: dict) -> dict:
    permissions = get_user_permissions(db, user)
    domain_permissions = {
        "assessments": "college.assessments.view",
        "attendance": "college.attendance.view",
        "coding": "college.coding.view",
        "placements": "college.placements.view",
        "documents": "documents.view",
        "clearance": "college.clearance.view",
    }
    domains = {
        domain: _optional_domain_access(db, user, permissions, domain, permission)
        for domain, permission in domain_permissions.items()
    }
    for item in payload.get("items", []):
        student_id = item.get("id")

        def can(domain: str) -> bool:
            access = domains.get(domain)
            return bool(access and access.allows_student(student_id))

        if not can("assessments"):
            item["cgpa"] = None
            item["active_backlogs"] = None
        if not can("attendance"):
            item["attendance_percent"] = None
        if not can("coding"):
            item["coding_total"] = None
            item["coding_fresh_at"] = None
        if not can("documents"):
            item["resume_status"] = None
        if not can("placements"):
            item["placement_status"] = None
        if not can("clearance"):
            item["fee_clearance_status"] = None
    return payload


def _require_application_scope(db: Session, user: User, application: CollegePlacementApplication) -> None:
    _require_student_scope(db, user, application.student_profile_id, "placements")


def _require_opportunity_scope(access: CollegeAccess, opportunity: CollegePlacementOpportunity) -> None:
    if not access.allows_opportunity(opportunity.eligibility_rules):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opportunity not found")


def _validate_opportunity_scope(access: CollegeAccess, rules: dict) -> None:
    if access.unrestricted:
        return
    department_ids = set(rules.get("department_ids") or [])
    program_ids = set(rules.get("program_ids") or [])
    cohort_ids = set(rules.get("cohort_ids") or rules.get("batch_ids") or [])
    if not department_ids and not program_ids and not cohort_ids:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Scoped staff must limit an opportunity to an assigned department, program, or batch",
        )
    if (
        not department_ids.issubset(access.department_ids)
        or not program_ids.issubset(access.program_ids)
        or not cohort_ids.issubset(access.cohort_ids)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Opportunity eligibility exceeds your College access")


@router.get("/placement-dashboard")
def get_placement_dashboard(
    academic_year: str | None = None,
    graduation_year: int | None = Query(default=None, ge=2000, le=2200),
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    cohort_ids: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.view", "college.placement_reports.view")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "reports")
    selected_cohort_ids = list(dict.fromkeys(cohort_ids or []))
    if len(selected_cohort_ids) > 50:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Compare at most 50 cohorts")
    validate_college_filters(
        access,
        department_id=department_id,
        program_id=program_id,
        cohort_id=cohort_id,
        cohort_ids=selected_cohort_ids,
    )
    payload = placement_dashboard(
        db, user.organization_id,
        academic_year=academic_year,
        graduation_year=graduation_year,
        department_id=department_id,
        program_id=program_id,
        cohort_id=cohort_id,
        cohort_ids=selected_cohort_ids,
        allowed_student_ids=access.constrained_student_ids,
    )
    db.commit()
    return payload


@router.get("/leaderboards")
def get_leaderboards(
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    window_days: Literal[30, 90] = 30,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.readiness.view", "college.coding.view")),
):
    require_college(db, user)
    access = _intersect_access(
        resolve_college_access(db, user, "coding"),
        resolve_college_access(db, user, "readiness"),
        domain="leaderboards",
    )
    validate_college_filters(access, department_id=department_id, program_id=program_id, cohort_id=cohort_id)
    payload = placement_leaderboards(
        db, user.organization_id,
        department_id=department_id,
        program_id=program_id,
        cohort_id=cohort_id,
        window_days=window_days,
        limit=limit,
        allowed_student_ids=access.constrained_student_ids,
    )
    db.commit()
    return payload


@router.get("/students/{student_id}/intelligence")
def get_student_intelligence(
    student_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.students.view", "college.readiness.view")),
):
    require_college(db, user)
    resolve_college_access(db, user, "students").require_student(student_id)
    resolve_college_access(db, user, "readiness").require_student(student_id)
    payload = student_intelligence(db, user.organization_id, student_id)
    if not payload:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    payload = _sanitize_student_intelligence(db, user, student_id, payload)
    db.commit()
    return payload


@router.get("/student-intelligence")
def list_student_intelligence(
    q: str | None = Query(default=None, max_length=120),
    graduation_year: int | None = Query(default=None, ge=2000, le=2200),
    graduation_years: list[int] | None = Query(default=None),
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    cohort_ids: list[str] | None = Query(default=None),
    section: str | None = Query(default=None, max_length=20),
    readiness_band: Literal["ready", "developing", "needs_support", "insufficient_evidence"] | None = None,
    placement_status: Literal["all", "placed", "unplaced", "seeking", "not_participating"] | None = None,
    sort: Literal["name", "academics_desc"] = "name",
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = None,
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.students.view", "college.readiness.view")),
):
    require_college(db, user)
    access = _intersect_access(
        resolve_college_access(db, user, "students"),
        resolve_college_access(db, user, "readiness"),
        domain="student-intelligence",
    )
    selected_cohort_ids = list(dict.fromkeys(cohort_ids or []))
    if len(selected_cohort_ids) > 50:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Compare at most 50 cohorts")
    validate_college_filters(
        access,
        department_id=department_id,
        program_id=program_id,
        cohort_id=cohort_id,
        cohort_ids=selected_cohort_ids,
    )
    requested_years = [*(graduation_years or []), *([graduation_year] if graduation_year else [])]
    if any(year < 2000 or year > 2200 for year in requested_years):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Graduation year must be between 2000 and 2200")
    years = sorted({int(year) for year in requested_years})
    filters = {
        "q": q, "department_id": department_id, "program_id": program_id,
        "cohort_id": cohort_id, "cohort_ids": selected_cohort_ids,
        "graduation_years": years, "section": section,
        "readiness_band": readiness_band, "placement_status": placement_status, "sort": sort,
    }
    cursor_values = decode_cursor(
        cursor, scope="college.student-intelligence",
        organization_id=user.organization_id, filters=filters,
    )
    payload = student_roster(
        db, user.organization_id,
        q=q,
        department_id=department_id,
        program_id=program_id,
        cohort_id=cohort_id,
        cohort_ids=selected_cohort_ids,
        graduation_years=years,
        section=section,
        readiness_band=readiness_band,
        placement_status=placement_status,
        sort=sort,
        limit=limit,
        offset=offset,
        cursor_values=cursor_values,
        allowed_student_ids=access.constrained_student_ids,
    )
    payload = _sanitize_roster_items(db, user, payload)
    next_values = payload.pop("_next_values", None)
    payload["next_cursor"] = encode_cursor(
        scope="college.student-intelligence", organization_id=user.organization_id,
        filters=filters, values=next_values,
    ) if next_values else None
    payload["has_more"] = bool(payload["next_cursor"])
    return payload


@router.get("/readiness-policy")
def get_readiness_policy(
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.readiness.view")),
):
    require_college(db, user)
    resolve_college_access(db, user, "readiness")
    row = active_readiness_policy(db, user.organization_id, created_by_user_id=user.id)
    db.commit()
    return serialize(row)


@router.put("/readiness-policy")
def update_readiness_policy(
    body: ReadinessPolicyBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.readiness.policy.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "readiness")
    if not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Whole-institution access is required to manage readiness policy")
    current = active_readiness_policy(db, user.organization_id, created_by_user_id=user.id)
    current.is_active = False
    row = CollegeReadinessPolicy(
        organization_id=user.organization_id,
        name=body.name.strip(),
        version=current.version + 1,
        weights=body.weights,
        bands=body.bands,
        minimum_coverage_percent=body.minimum_coverage_percent,
        is_active=True,
        created_by_user_id=user.id,
    )
    db.add(row)
    db.flush()
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.readiness_policy.updated", resource_type="college_readiness_policy",
        resource_id=row.id, permission="college.readiness.policy.manage",
        meta={"version": row.version},
    )
    db.commit()
    return serialize(row)


@router.post("/readiness/recompute")
def recompute_college_readiness(
    student_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.readiness.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "readiness")
    student_ids = access.constrained_student_ids
    if student_id:
        access.require_student(student_id)
        tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
        student_ids = [student_id]
    rows = recompute_readiness(db, user.organization_id, student_ids, created_by_user_id=user.id)
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.readiness.recomputed", resource_type="college_readiness_snapshot",
        permission="college.readiness.manage", rows_affected=len(rows),
    )
    db.commit()
    return {"recomputed": len(rows), "calculated_at": rows[0].calculated_at if rows else None}


@router.put("/students/{student_id}/career")
def upsert_career_profile(
    student_id: str,
    body: CareerBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.students.update")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "students")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    row = db.execute(select(CollegeCareerProfile).where(
        CollegeCareerProfile.organization_id == user.organization_id,
        CollegeCareerProfile.student_profile_id == student_id,
    )).scalar_one_or_none()
    if not row:
        row = CollegeCareerProfile(organization_id=user.organization_id, student_profile_id=student_id)
        db.add(row)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    db.flush()
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.career_profile.updated", resource_type="college_career_profile",
        resource_id=row.id, permission="college.students.manage",
    )
    db.commit()
    return serialize(row)


@router.post("/students/{student_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_career_evidence(
    student_id: str,
    body: EvidenceBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.students.update")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "students")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    if body.document_id:
        _student_document(db, user, body.document_id, student_id)
    payload = body.model_dump()
    verified = payload.pop("is_verified")
    row = CollegeCareerEvidence(
        organization_id=user.organization_id,
        student_profile_id=student_id,
        **payload,
        is_verified=verified,
        verified_by_user_id=user.id if verified else None,
        verified_at=datetime.now(timezone.utc) if verified else None,
        source_type="manual",
    )
    db.add(row)
    db.flush()
    db.commit()
    return serialize(row)


@router.post("/students/{student_id}/term-results", status_code=status.HTTP_201_CREATED)
def add_term_result(
    student_id: str,
    body: TermResultBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.assessments.record")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "assessments")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    if body.term_id:
        from app.models import CollegeTerm
        tenant_row(db, CollegeTerm, body.term_id, user, "Term")
    row = db.execute(select(CollegeTermResult).where(
        CollegeTermResult.student_profile_id == student_id,
        CollegeTermResult.semester == body.semester,
        CollegeTermResult.source_key == "manual",
    )).scalar_one_or_none()
    if not row:
        row = CollegeTermResult(
            organization_id=user.organization_id,
            student_profile_id=student_id,
            semester=body.semester,
            source_type="manual",
            source_key="manual",
        )
        db.add(row)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    db.flush()
    db.commit()
    return serialize(row)


@router.post("/students/{student_id}/attendance-snapshots", status_code=status.HTTP_201_CREATED)
def add_attendance_snapshot(
    student_id: str,
    body: AttendanceSnapshotBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.attendance.mark")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "attendance")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    percentage = body.attendance_percent
    if percentage is None and body.classes_held:
        percentage = Decimal(body.classes_attended * 100) / Decimal(body.classes_held)
    row = CollegeAttendanceSnapshot(
        organization_id=user.organization_id,
        student_profile_id=student_id,
        term_id=body.term_id,
        course_id=body.course_id,
        scope_key=body.scope.strip(),
        classes_held=body.classes_held,
        classes_attended=body.classes_attended,
        attendance_percent=percentage,
        as_of=body.as_of,
        source_type="manual",
        source_key="manual",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An attendance snapshot already exists for this date and scope")
    db.refresh(row)
    return serialize(row)


@router.post("/students/{student_id}/placement-assessments", status_code=status.HTTP_201_CREATED)
def add_placement_assessment(
    student_id: str,
    body: PlacementAssessmentBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.assessments.record")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "assessments")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    row = CollegePlacementAssessment(
        organization_id=user.organization_id,
        student_profile_id=student_id,
        source_type="manual",
        **body.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.post("/students/{student_id}/preparation", status_code=status.HTTP_201_CREATED)
def add_preparation_activity(
    student_id: str,
    body: PreparationBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.readiness.intervene")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "readiness")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    row = CollegePreparationActivity(
        organization_id=user.organization_id,
        student_profile_id=student_id,
        **body.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.post("/students/{student_id}/interventions", status_code=status.HTTP_201_CREATED)
def add_intervention(
    student_id: str,
    body: InterventionBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.readiness.intervene")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "readiness")
    _require_sensitive_capability(db, user, "college.notes.private.view", "Private student note access is required")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    row = CollegeStudentIntervention(
        organization_id=user.organization_id,
        student_profile_id=student_id,
        status="open",
        **body.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.patch("/interventions/{intervention_id}")
def update_intervention(
    intervention_id: str,
    body: InterventionUpdateBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.readiness.intervene")),
):
    require_college(db, user)
    row = tenant_row(db, CollegeStudentIntervention, intervention_id, user, "Intervention")
    _require_student_scope(db, user, row.student_profile_id, "readiness")
    _require_sensitive_capability(db, user, "college.notes.private.view", "Private student note access is required")
    row.status = body.status
    row.resolution_note = body.resolution_note
    row.resolved_at = datetime.now(timezone.utc) if body.status == "resolved" else None
    db.commit()
    return serialize(row)


@router.put("/students/{student_id}/coding-account")
def upsert_coding_account(
    student_id: str,
    body: CodingAccountBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.coding.manage")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "coding")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    row = db.execute(select(CollegeCodingAccount).where(
        CollegeCodingAccount.organization_id == user.organization_id,
        CollegeCodingAccount.student_profile_id == student_id,
        CollegeCodingAccount.platform == "leetcode",
    )).scalar_one_or_none()
    if not row:
        row = CollegeCodingAccount(
            organization_id=user.organization_id,
            student_profile_id=student_id,
            platform="leetcode",
        )
        db.add(row)
    row.username = body.username.strip()
    row.consent_status = body.consent_status
    row.verification_status = body.verification_status
    row.sync_status = "pending"
    row.is_active = body.consent_status != "revoked"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This LeetCode username is already connected")
    db.refresh(row)
    return serialize(row)


@router.post("/students/{student_id}/coding-snapshots", status_code=status.HTTP_201_CREATED)
def add_coding_snapshot(
    student_id: str,
    body: CodingSnapshotBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.coding.manage")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "coding")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    account = db.execute(select(CollegeCodingAccount).where(
        CollegeCodingAccount.organization_id == user.organization_id,
        CollegeCodingAccount.student_profile_id == student_id,
        CollegeCodingAccount.platform == "leetcode",
    )).scalar_one_or_none()
    if not account:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a coding account before adding a snapshot")
    values = body.model_dump()
    if values["total_solved"] is None:
        values["total_solved"] = sum(values[key] or 0 for key in ("easy_solved", "medium_solved", "hard_solved"))
    row = CollegeCodingSnapshot(
        organization_id=user.organization_id,
        coding_account_id=account.id,
        student_profile_id=student_id,
        source_type="manual",
        raw_metrics={},
        **values,
    )
    db.add(row)
    account.sync_status = "current"
    account.last_synced_at = values["captured_at"]
    account.last_success_at = values["captured_at"]
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.post("/coding/accounts/{account_id}/sync")
def queue_coding_sync(
    account_id: str,
    body: SyncBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.coding.manage")),
):
    require_college(db, user)
    account = tenant_row(db, CollegeCodingAccount, account_id, user, "Coding account")
    _require_student_scope(db, user, account.student_profile_id, "coding")
    if account.consent_status != "granted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Student consent is required before synchronization")
    job = _queue_job(
        db, user.organization_id, "college_coding_sync",
        {"account_id": account.id, "requested_by_user_id": user.id},
        f"college-coding:{account.id}:{body.idempotency_key}"[:120],
    )
    account.sync_status = "queued"
    db.commit()
    return {"job_id": job.id, "status": job.status}


@router.get("/pipeline/stages")
def list_pipeline_stages(
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.placements.view")),
):
    require_college(db, user)
    resolve_college_access(db, user, "placements")
    rows = ensure_default_pipeline(db, user.organization_id)
    db.commit()
    return {"items": [serialize(row) for row in rows]}


@router.put("/pipeline/stages")
def replace_pipeline_stages(
    body: StageListBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.opportunities.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "placements")
    if not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Whole-institution access is required to configure the placement pipeline")
    existing = {row.id: row for row in ensure_default_pipeline(db, user.organization_id)}
    used_ids = set()
    for row in existing.values():
        row.display_order += 1000
    db.flush()
    output = []
    for order, item in enumerate(body.stages, start=1):
        row = existing.get(item.id) if item.id else None
        if item.id and not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline stage not found")
        if not row:
            row = CollegePipelineStage(organization_id=user.organization_id)
            db.add(row)
        else:
            used_ids.add(row.id)
        row.name = item.name.strip()
        row.slug = item.slug.strip()
        row.display_order = order
        row.stage_type = item.stage_type
        row.is_terminal = item.is_terminal or item.stage_type != "active"
        row.is_enabled = item.is_enabled
        output.append(row)
    for row_id, row in existing.items():
        if row_id not in used_ids:
            row.is_enabled = False
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Pipeline stage names or order conflict")
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.pipeline.updated", resource_type="college_pipeline_stage",
        permission="college.opportunities.manage", rows_affected=len(output),
    )
    db.commit()
    return {"items": [serialize(row) for row in output]}


@router.get("/companies")
def list_companies(
    q: str | None = Query(default=None, max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.placements.view")),
):
    require_college(db, user)
    resolve_college_access(db, user, "placements")
    filters = {"q": q}
    values = decode_cursor(cursor, scope="college.companies", organization_id=user.organization_id, filters=filters)
    query = select(CollegePlacementCompany).where(
        CollegePlacementCompany.organization_id == user.organization_id,
        CollegePlacementCompany.is_active.is_(True),
    )
    if q:
        query = query.where(CollegePlacementCompany.name.ilike(f"%{q.strip()}%"))
    if values:
        name = str(values.get("name") or "")
        row_id = str(values.get("id") or "")
        query = query.where(or_(
            func.lower(CollegePlacementCompany.name) > name,
            and_(func.lower(CollegePlacementCompany.name) == name, CollegePlacementCompany.id > row_id),
        ))
    size = page_size(limit)
    rows = list(db.execute(query.order_by(func.lower(CollegePlacementCompany.name), CollegePlacementCompany.id).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="college.companies", organization_id=user.organization_id, filters=filters,
        values={"name": rows[-1].name.casefold(), "id": rows[-1].id},
    ) if has_more and rows else None
    return page_response([serialize(row) for row in rows], next_cursor)


@router.post("/companies", status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.companies.manage")),
):
    require_college(db, user)
    resolve_college_access(db, user, "placements")
    row = CollegePlacementCompany(
        organization_id=user.organization_id,
        **{**body.model_dump(), "name": body.name.strip()},
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A company with this name already exists")
    db.refresh(row)
    return serialize(row)


@router.patch("/companies/{company_id}")
def update_company(
    company_id: str,
    body: CompanyBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.companies.manage")),
):
    require_college(db, user)
    resolve_college_access(db, user, "placements")
    row = tenant_row(db, CollegePlacementCompany, company_id, user, "Company")
    for key, value in body.model_dump().items():
        setattr(row, key, value.strip() if key == "name" else value)
    db.commit()
    return serialize(row)


@router.get("/opportunities")
def list_opportunities(
    q: str | None = Query(default=None, max_length=120),
    opportunity_status: str | None = Query(default=None, alias="status", max_length=30),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.placements.view")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "placements")
    filters = {"q": q, "status": opportunity_status}
    values = decode_cursor(cursor, scope="college.opportunities", organization_id=user.organization_id, filters=filters)
    query = (
        select(CollegePlacementOpportunity, CollegePlacementCompany)
        .join(CollegePlacementCompany, CollegePlacementCompany.id == CollegePlacementOpportunity.company_id)
        .where(CollegePlacementOpportunity.organization_id == user.organization_id)
    )
    if opportunity_status:
        query = query.where(CollegePlacementOpportunity.status == opportunity_status)
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        query = query.where(func.lower(func.concat_ws(" ", CollegePlacementOpportunity.title, CollegePlacementCompany.name)).like(term))
    if values:
        at = datetime.fromisoformat(str(values.get("at")))
        row_id = str(values.get("id") or "")
        query = query.where(or_(
            CollegePlacementOpportunity.created_at < at,
            and_(CollegePlacementOpportunity.created_at == at, CollegePlacementOpportunity.id < row_id),
        ))
    size = page_size(limit)
    rows = db.execute(query.order_by(CollegePlacementOpportunity.created_at.desc(), CollegePlacementOpportunity.id.desc()).limit(size + 1)).all()
    if not access.unrestricted:
        rows = [
            (opportunity, company)
            for opportunity, company in rows
            if access.allows_opportunity(opportunity.eligibility_rules)
        ]
    has_more = len(rows) > size
    rows = rows[:size]
    items = [
            {
                **serialize(opportunity),
                "eligibility_rules": opportunity_eligibility_rules(opportunity),
                "company": {"id": company.id, "name": company.name},
            }
            for opportunity, company in rows
        ]
    next_cursor = encode_cursor(
        scope="college.opportunities", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1][0].created_at.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.post("/opportunities", status_code=status.HTTP_201_CREATED)
def create_opportunity(
    body: OpportunityBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.opportunities.manage")),
):
    require_college(db, user)
    _validate_opportunity_scope(resolve_college_access(db, user, "placements"), body.eligibility_rules)
    tenant_row(db, CollegePlacementCompany, body.company_id, user, "Company")
    row = CollegePlacementOpportunity(
        organization_id=user.organization_id,
        owner_user_id=user.id,
        **body.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.patch("/opportunities/{opportunity_id}")
def update_opportunity(
    opportunity_id: str,
    body: OpportunityBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.opportunities.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "placements")
    row = tenant_row(db, CollegePlacementOpportunity, opportunity_id, user, "Opportunity")
    _require_opportunity_scope(access, row)
    _validate_opportunity_scope(access, body.eligibility_rules)
    tenant_row(db, CollegePlacementCompany, body.company_id, user, "Company")
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return serialize(row)


@router.post("/opportunities/{opportunity_id}/evaluate")
def evaluate_opportunity(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.applications.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "placements")
    opportunity = tenant_row(db, CollegePlacementOpportunity, opportunity_id, user, "Opportunity")
    _require_opportunity_scope(access, opportunity)
    students = list(db.execute(select(CollegeStudentProfile).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.status == "active",
    )).scalars())
    if not access.unrestricted:
        students = [student for student in students if student.id in access.student_ids]
    fee_clearance = fee_clearance_by_student(
        db,
        user.organization_id,
        [student.id for student in students],
    )
    statuses = {"eligible": 0, "ineligible": 0, "needs_review": 0}
    items = []
    for student in students:
        result = evaluate_eligibility(
            eligibility_context(
                db,
                user.organization_id,
                student.id,
                fee_clearance_evidence=fee_clearance[student.id],
            ),
            opportunity_eligibility_rules(opportunity),
        )
        statuses[result["status"]] += 1
        items.append({"student_id": student.id, **result})
    return {"opportunity_id": opportunity.id, "summary": statuses, "items": items}


@router.get("/applications")
def list_applications(
    opportunity_id: str | None = None,
    student_id: str | None = None,
    stage_id: str | None = None,
    q: str | None = Query(default=None, max_length=120),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.placements.view")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "placements")
    filters = {
        "q": q, "opportunity_id": opportunity_id,
        "student_id": student_id, "stage_id": stage_id,
    }
    values = decode_cursor(cursor, scope="college.applications", organization_id=user.organization_id, filters=filters)
    query = (
        select(
            CollegePlacementApplication,
            CollegeStudentProfile,
            Client,
            CollegePlacementOpportunity,
            CollegePlacementCompany,
            CollegePipelineStage,
        )
        .join(CollegeStudentProfile, CollegeStudentProfile.id == CollegePlacementApplication.student_profile_id)
        .join(Client, Client.id == CollegeStudentProfile.client_id)
        .join(CollegePlacementOpportunity, CollegePlacementOpportunity.id == CollegePlacementApplication.opportunity_id)
        .join(CollegePlacementCompany, CollegePlacementCompany.id == CollegePlacementOpportunity.company_id)
        .outerjoin(CollegePipelineStage, CollegePipelineStage.id == CollegePlacementApplication.current_stage_id)
        .where(CollegePlacementApplication.organization_id == user.organization_id)
    )
    if opportunity_id:
        query = query.where(CollegePlacementApplication.opportunity_id == opportunity_id)
    if student_id:
        query = query.where(CollegePlacementApplication.student_profile_id == student_id)
    if stage_id:
        query = query.where(CollegePlacementApplication.current_stage_id == stage_id)
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        query = query.where(func.lower(func.concat_ws(
            " ", Client.first_name, Client.last_name, CollegeStudentProfile.admission_number,
            CollegePlacementOpportunity.title, CollegePlacementCompany.name,
        )).like(term))
    if not access.unrestricted:
        query = query.where(CollegePlacementApplication.student_profile_id.in_(access.student_ids))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    if values:
        at = datetime.fromisoformat(str(values.get("at")))
        row_id = str(values.get("id") or "")
        query = query.where(or_(
            CollegePlacementApplication.updated_at < at,
            and_(CollegePlacementApplication.updated_at == at, CollegePlacementApplication.id < row_id),
        ))
    size = page_size(limit)
    rows = db.execute(query.order_by(
        CollegePlacementApplication.updated_at.desc(), CollegePlacementApplication.id.desc(),
    ).offset(offset if not cursor else 0).limit(size + 1)).all()
    has_more = len(rows) > size
    rows = rows[:size]
    items = [
            {
                **serialize(application),
                "student": {
                    "id": student.id,
                    "client_id": student.client_id,
                    "name": f"{student_client.first_name} {student_client.last_name}".strip(),
                    "admission_number": student.admission_number,
                    "roll_number": student.roll_number,
                },
                "opportunity": {"id": opportunity.id, "title": opportunity.title, "status": opportunity.status},
                "company": {"id": company.id, "name": company.name},
                "stage": {"id": stage.id, "name": stage.name, "slug": stage.slug} if stage else None,
            }
            for application, student, student_client, opportunity, company, stage in rows
        ]
    next_cursor = encode_cursor(
        scope="college.applications", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1][0].updated_at.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return {
        "items": items,
        "total": total,
        "limit": size,
        "offset": offset if not cursor else 0,
        "next_cursor": next_cursor,
        "has_more": bool(next_cursor),
    }


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(
    body: ApplicationBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.applications.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "placements")
    access.require_student(body.student_profile_id)
    opportunity = tenant_row(db, CollegePlacementOpportunity, body.opportunity_id, user, "Opportunity")
    _require_opportunity_scope(access, opportunity)
    tenant_row(db, CollegeStudentProfile, body.student_profile_id, user, "Student")
    stages = ensure_default_pipeline(db, user.organization_id)
    initial_stage = next((row for row in stages if row.slug == "eligible"), stages[0])
    eligibility = evaluate_eligibility(
        eligibility_context(db, user.organization_id, body.student_profile_id),
        opportunity_eligibility_rules(opportunity),
    )
    if opportunity.opportunity_type == "internship":
        fee_check = next(
            (item for item in eligibility["checks"] if item["rule"] == "fee_clearance"),
            None,
        )
        if not fee_check or fee_check["passes"] is not True:
            message = (
                "Complete the student's fee clearance before adding them to this internship"
                if fee_check and fee_check["passes"] is False
                else "Verify the student's fee clearance before adding them to this internship"
            )
            raise HTTPException(status.HTTP_409_CONFLICT, message)
    row = CollegePlacementApplication(
        organization_id=user.organization_id,
        opportunity_id=opportunity.id,
        student_profile_id=body.student_profile_id,
        current_stage_id=initial_stage.id,
        eligibility_status=eligibility["status"],
        eligibility_evidence=eligibility,
        eligibility_evaluated_at=datetime.now(timezone.utc),
        notes=body.notes,
        version=1,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This student already has an application for the opportunity")
    db.add(CollegeApplicationStageEvent(
        organization_id=user.organization_id,
        application_id=row.id,
        to_stage_id=initial_stage.id,
        changed_by_user_id=user.id,
        reason="Application created",
        occurred_at=datetime.now(timezone.utc),
    ))
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.patch("/applications/{application_id}/stage")
def move_application_stage(
    application_id: str,
    body: StageMoveBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.applications.manage")),
):
    require_college(db, user)
    application = tenant_row(db, CollegePlacementApplication, application_id, user, "Application")
    _require_application_scope(db, user, application)
    stage = tenant_row(db, CollegePipelineStage, body.stage_id, user, "Pipeline stage")
    if not stage.is_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "The selected pipeline stage is disabled")
    if application.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Application changed on another device; refresh and try again")
    previous = application.current_stage_id
    application.current_stage_id = stage.id
    application.version += 1
    if stage.slug == "applied" and not application.applied_at:
        application.applied_at = datetime.now(timezone.utc)
    if stage.stage_type != "active":
        application.outcome = stage.stage_type
    db.add(CollegeApplicationStageEvent(
        organization_id=user.organization_id,
        application_id=application.id,
        from_stage_id=previous,
        to_stage_id=stage.id,
        changed_by_user_id=user.id,
        reason=body.reason,
        occurred_at=datetime.now(timezone.utc),
    ))
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.application.stage_changed", resource_type="college_placement_application",
        resource_id=application.id, permission="college.applications.manage",
        meta={"from_stage_id": previous, "to_stage_id": stage.id},
    )
    db.commit()
    return serialize(application)


@router.patch("/applications/{application_id}/eligibility-override")
def override_application_eligibility(
    application_id: str,
    body: EligibilityOverrideBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.applications.manage", "college.eligibility.override")),
):
    require_college(db, user)
    application = tenant_row(db, CollegePlacementApplication, application_id, user, "Application")
    _require_application_scope(db, user, application)
    if application.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Application changed on another device; refresh and try again")
    application.eligibility_override_status = body.status
    application.eligibility_override_reason = body.reason.strip()
    application.eligibility_override_by_user_id = user.id
    application.eligibility_override_at = datetime.now(timezone.utc)
    application.version += 1
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.application.eligibility_overridden", resource_type="college_placement_application",
        resource_id=application.id, permission="college.applications.manage",
        meta={"status": body.status, "reason": body.reason.strip()},
    )
    db.commit()
    return serialize(application)


@router.post("/applications/{application_id}/interviews", status_code=status.HTTP_201_CREATED)
def create_interview(
    application_id: str,
    body: InterviewBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.offers.manage")),
):
    require_college(db, user)
    application = tenant_row(db, CollegePlacementApplication, application_id, user, "Application")
    _require_application_scope(db, user, application)
    row = CollegePlacementInterview(
        organization_id=user.organization_id,
        application_id=application_id,
        **body.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.post("/applications/{application_id}/offers", status_code=status.HTTP_201_CREATED)
def create_offer(
    application_id: str,
    body: OfferBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.offers.manage")),
):
    require_college(db, user)
    application = tenant_row(db, CollegePlacementApplication, application_id, user, "Application")
    _require_application_scope(db, user, application)
    if body.document_id:
        _student_document(db, user, body.document_id, application.student_profile_id, "Offer document")
    row = CollegePlacementOffer(
        organization_id=user.organization_id,
        application_id=application.id,
        **body.model_dump(),
    )
    db.add(row)
    application.outcome = "joined" if body.status == "joined" else "offered"
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.post("/imports/preview", status_code=status.HTTP_201_CREATED)
def preview_import(
    body: ImportPreviewBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.imports.manage")),
):
    require_college(db, user)
    access = _legacy_import_access(db, user, body.resource_type)
    run = stage_rows(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        source_type="manual",
        resource_type=body.resource_type,
        rows=body.rows,
        mapping=body.mapping,
        idempotency_key=body.idempotency_key,
        allowed_student_ids=access.constrained_student_ids,
        allowed_program_ids=None if access.unrestricted else set(access.program_ids),
        allowed_cohort_ids=None if access.unrestricted else set(access.cohort_ids),
    )
    db.commit()
    return _run_payload(run)


@router.post("/imports/csv/preview", status_code=status.HTTP_201_CREATED)
async def preview_csv_import(
    resource_type: Literal[
        "departments", "programs", "terms", "cohorts", "courses", "students",
        "term_results", "attendance", "skills", "assessments", "internship_clearance",
    ] = Form(...),
    mapping_json: str = Form("{}"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.imports.manage")),
):
    require_college(db, user)
    access = _legacy_import_access(db, user, resource_type)
    content_type = (file.content_type or "text/csv").lower()
    if content_type not in {"text/csv", "application/vnd.ms-excel", "application/csv"}:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a CSV file")
    safe_upload_name(
        file.filename,
        content_type,
        allowed_extensions={
            "text/csv": {".csv"},
            "application/vnd.ms-excel": {".csv"},
            "application/csv": {".csv"},
        },
        fallback="import.csv",
    )
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "CSV files are limited to 5 MB")
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The CSV file is empty")
    validate_upload_signature(raw, content_type)
    try:
        mapping = json.loads(mapping_json)
        text = raw.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid CSV or mapping: {exc}")
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The CSV file has no data rows")
    if len(rows) > 5000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "CSV imports are limited to 5,000 rows")
    run = stage_rows(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        source_type="csv",
        resource_type=resource_type,
        rows=rows,
        mapping=mapping,
        allowed_student_ids=access.constrained_student_ids,
        allowed_program_ids=None if access.unrestricted else set(access.program_ids),
        allowed_cohort_ids=None if access.unrestricted else set(access.cohort_ids),
    )
    db.commit()
    return _run_payload(run)


@router.post("/imports/{run_id}/commit")
def commit_import(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.imports.manage")),
):
    require_college(db, user)
    run = tenant_row(db, CollegeImportRun, run_id, user, "Import run")
    access = _legacy_import_access(db, user, run.resource_type)
    if not access.unrestricted and run.started_by_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import run not found")
    try:
        commit_run(
            db,
            run,
            allowed_student_ids=access.constrained_student_ids,
            allowed_program_ids=None if access.unrestricted else set(access.program_ids),
            allowed_cohort_ids=None if access.unrestricted else set(access.cohort_ids),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.import.committed", resource_type="college_import_run",
        resource_id=run.id, permission="college.imports.manage",
        rows_affected=run.committed_count,
        meta={"resource_type": run.resource_type, "failed_count": run.failed_count},
    )
    db.commit()
    return _run_payload(run)


@router.get("/imports")
def list_imports(
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.imports.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "data")
    query = select(CollegeImportRun).where(CollegeImportRun.organization_id == user.organization_id)
    if not access.unrestricted:
        query = query.where(CollegeImportRun.started_by_user_id == user.id)
    values = decode_cursor(cursor, scope="college.imports", organization_id=user.organization_id)
    if values:
        at = datetime.fromisoformat(str(values.get("at")))
        row_id = str(values.get("id") or "")
        query = query.where(or_(
            CollegeImportRun.created_at < at,
            and_(CollegeImportRun.created_at == at, CollegeImportRun.id < row_id),
        ))
    size = page_size(limit)
    rows = list(db.execute(query.order_by(CollegeImportRun.created_at.desc(), CollegeImportRun.id.desc()).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="college.imports", organization_id=user.organization_id,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    return page_response([_run_payload(row) for row in rows], next_cursor)


@router.get("/integrations")
def list_integrations(
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.integrations.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "data")
    if not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Whole-institution access is required to manage ERP credentials")
    rows = db.execute(
        select(CollegeDataConnector)
        .where(CollegeDataConnector.organization_id == user.organization_id)
        .order_by(CollegeDataConnector.name)
    ).scalars()
    return {"items": [_connector_payload(row) for row in rows]}


@router.post("/integrations", status_code=status.HTTP_201_CREATED)
def create_integration(
    body: ConnectorBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.integrations.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "data")
    if not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Whole-institution access is required to manage ERP credentials")
    row = CollegeDataConnector(
        organization_id=user.organization_id,
        name=body.name.strip(),
        connector_type="erp",
        base_url=_validate_connector_url(body.base_url),
        auth_mode=body.auth_mode,
        auth_header=body.auth_header.strip() if body.auth_header else None,
        encrypted_api_key=encrypt_secret(body.api_key) if body.api_key else None,
        mapping=body.mapping,
        pagination=body.pagination,
        sync_interval_hours=body.sync_interval_hours,
        status="ready" if body.api_key else "setup",
        is_active=True,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An integration with this name already exists")
    db.refresh(row)
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.integration.created", resource_type="college_data_connector",
        resource_id=row.id, permission="college.integrations.manage",
    )
    db.commit()
    return _connector_payload(row)


@router.patch("/integrations/{connector_id}")
def update_integration(
    connector_id: str,
    body: ConnectorBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.integrations.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "data")
    if not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Whole-institution access is required to manage ERP credentials")
    row = tenant_row(db, CollegeDataConnector, connector_id, user, "Integration")
    row.name = body.name.strip()
    row.base_url = _validate_connector_url(body.base_url)
    row.auth_mode = body.auth_mode
    row.auth_header = body.auth_header.strip() if body.auth_header else None
    if body.api_key:
        row.encrypted_api_key = encrypt_secret(body.api_key)
    row.mapping = body.mapping
    row.pagination = body.pagination
    row.sync_interval_hours = body.sync_interval_hours
    row.status = "ready" if row.encrypted_api_key else "setup"
    db.commit()
    return _connector_payload(row)


@router.post("/integrations/{connector_id}/sync")
def queue_integration_sync(
    connector_id: str,
    body: SyncBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.integrations.manage")),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "data")
    if not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Whole-institution access is required to synchronize ERP data")
    row = tenant_row(db, CollegeDataConnector, connector_id, user, "Integration")
    if not row.encrypted_api_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add an API key before synchronizing")
    mapping = row.mapping or {}
    configured = set((mapping.get("resources", mapping) or {}).keys())
    requested = body.resource_types or sorted(configured)
    if configured and not set(requested).issubset(configured):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This sync contains resources not configured for the connector")
    if not requested:
        raise HTTPException(status.HTTP_409_CONFLICT, "Configure at least one ERP resource before synchronizing")
    for resource_type in requested:
        _legacy_import_access(db, user, resource_type)
    job = _queue_job(
        db, user.organization_id, "college_erp_sync",
        {"connector_id": row.id, "resource_types": requested, "requested_by_user_id": user.id},
        f"college-erp:{row.id}:{body.idempotency_key}"[:120],
    )
    row.status = "queued"
    db.commit()
    return {"job_id": job.id, "status": job.status}


@router.post("/students/{student_id}/resume/extract")
def queue_resume_extraction(
    student_id: str,
    body: ResumeExtractBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.students.update", "documents.view", "college.documents.sensitive.view")),
):
    require_college(db, user)
    _require_student_scope(db, user, student_id, "documents")
    tenant_row(db, CollegeStudentProfile, student_id, user, "Student")
    document = _student_document(db, user, body.document_id, student_id, "Resume document")
    if document.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "The resume must finish processing before extraction")
    draft = CollegeResumeDraft(
        organization_id=user.organization_id,
        student_profile_id=student_id,
        document_id=document.id,
        status="extracting",
        extracted_data={},
    )
    db.add(draft)
    db.flush()
    job = _queue_job(
        db, user.organization_id, "college_resume_extract",
        {"draft_id": draft.id, "requested_by_user_id": user.id},
        f"college-resume:{draft.id}:{body.idempotency_key}"[:120],
    )
    db.commit()
    return {"draft_id": draft.id, "job_id": job.id, "status": draft.status}


@router.patch("/resume-drafts/{draft_id}")
def review_resume_draft(
    draft_id: str,
    body: ResumeReviewBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.students.update", "college.documents.sensitive.view")),
):
    require_college(db, user)
    draft = tenant_row(db, CollegeResumeDraft, draft_id, user, "Resume draft")
    _require_student_scope(db, user, draft.student_profile_id, "documents")
    if draft.status not in {"pending_review", "approved", "rejected"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Resume extraction is not ready for review")
    if body.decision == "approve":
        accepted = body.accepted or draft.extracted_data
        for evidence_type, values in (
            ("skill", accepted.get("skills", [])),
            ("project", accepted.get("projects", [])),
            ("certification", accepted.get("certifications", [])),
        ):
            for item in values[:100]:
                title = item if isinstance(item, str) else item.get("title") or item.get("name")
                if not title:
                    continue
                db.add(CollegeCareerEvidence(
                    organization_id=user.organization_id,
                    student_profile_id=draft.student_profile_id,
                    evidence_type=evidence_type,
                    title=str(title)[:220],
                    issuer=(item.get("issuer") if isinstance(item, dict) else None),
                    description=(item.get("description") if isinstance(item, dict) else None),
                    evidence_url=(item.get("url") if isinstance(item, dict) else None),
                    document_id=draft.document_id,
                    is_verified=False,
                    source_type="resume_extraction",
                    details=item if isinstance(item, dict) else {},
                ))
        profile = db.execute(select(CollegeCareerProfile).where(
            CollegeCareerProfile.organization_id == user.organization_id,
            CollegeCareerProfile.student_profile_id == draft.student_profile_id,
        )).scalar_one_or_none()
        if not profile:
            profile = CollegeCareerProfile(
                organization_id=user.organization_id,
                student_profile_id=draft.student_profile_id,
            )
            db.add(profile)
        profile.resume_document_id = draft.document_id
        profile.resume_status = "reviewed"
        draft.status = "approved"
    else:
        draft.status = "rejected"
    draft.reviewed_by_user_id = user.id
    draft.reviewed_at = datetime.now(timezone.utc)
    draft.review_note = body.note
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action=f"college.resume_draft.{draft.status}", resource_type="college_resume_draft",
        resource_id=draft.id, permission="college.students.manage",
    )
    db.commit()
    return serialize(draft)
