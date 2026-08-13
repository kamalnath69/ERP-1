"""Enterprise action, reach, and field-visibility policy evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    AccessDelegation, AccessDelegationScope, AccessPolicy, AccessPolicyScope,
    CollegeCohort, CollegeCourseOffering, CollegeDepartment, CollegeProgram,
    CollegeStudentProfile, FeatureFlag, Organization, User,
)
from app.services.rbac import get_user_permissions, get_user_roles


ACCESS_LEVELS = ("none", "view", "work", "manage")
SCOPE_TYPES = (
    "organization", "location", "department", "program", "cohort",
    "course_offering", "student",
)

# Levels are presentation bundles over the existing permission catalogue. The
# permission table remains the single source for what a user can do.
COLLEGE_DOMAIN_LEVELS: dict[str, dict[str, set[str]]] = {
    "students": {
        "view": {"college.students.view", "clients.view"},
        "work": {"college.students.view", "college.students.update", "clients.view", "clients.manage"},
        "manage": {
            "college.students.view", "college.students.update", "college.students.manage",
            "clients.view", "clients.manage",
        },
    },
    "academics": {
        "view": {"college.academics.view"},
        "work": {"college.academics.view"},
        "manage": {"college.academics.view", "college.academics.manage"},
    },
    "attendance": {
        "view": {"college.attendance.view"},
        "work": {"college.attendance.view", "college.attendance.mark"},
        "manage": {"college.attendance.view", "college.attendance.mark", "college.attendance.correct"},
    },
    "assessments": {
        "view": {"college.assessments.view"},
        "work": {"college.assessments.view", "college.assessments.record"},
        "manage": {"college.assessments.view", "college.assessments.record", "college.assessments.manage"},
    },
    "readiness": {
        "view": {"college.readiness.view"},
        "work": {"college.readiness.view", "college.readiness.intervene"},
        "manage": {"college.readiness.view", "college.readiness.intervene", "college.readiness.manage"},
    },
    "coding": {
        "view": {"college.coding.view"},
        "work": {"college.coding.view", "college.coding.manage"},
        "manage": {"college.coding.view", "college.coding.manage"},
    },
    "placements": {
        "view": {"college.placements.view"},
        "work": {"college.placements.view", "college.applications.manage"},
        "manage": {
            "college.placements.view", "college.applications.manage", "college.companies.manage",
            "college.opportunities.manage", "college.offers.manage",
        },
    },
    "data": {
        "view": {"college.data.view"},
        "work": {"college.data.view", "college.imports.manage"},
        "manage": {"college.data.view", "college.imports.manage"},
    },
    "reports": {
        "view": {"college.placement_reports.view", "reports.view"},
        "work": {"college.placement_reports.view", "reports.view"},
        "manage": {"college.placement_reports.view", "reports.view"},
    },
    "clearance": {
        "view": {"college.clearance.view"},
        # Corrections are a separately reviewed sensitive capability. Routine
        # clearance work never grants that high-risk permission implicitly.
        "work": {"college.clearance.view"},
        "manage": {"college.clearance.view"},
    },
    "documents": {
        "view": {"documents.view"},
        "work": {"documents.view", "documents.manage"},
        "manage": {"documents.view", "documents.manage"},
    },
}

COLLEGE_DOMAIN_LABELS = {
    "students": "Students",
    "academics": "Academic structure",
    "attendance": "Attendance",
    "assessments": "Results and assessments",
    "readiness": "Readiness and support",
    "coding": "Coding and skills",
    "placements": "Placements",
    "data": "Imports and data exchange",
    "reports": "Placement reports",
    "clearance": "Internship clearance",
    "documents": "Student documents",
}

# These are deliberately conservative starting points for the guided console.
# They never select reach or sensitive capabilities and therefore cannot grant
# data by themselves.
COLLEGE_ROLE_LEVEL_SUGGESTIONS: dict[str, dict[str, str]] = {
    "owner": {domain: "manage" for domain in COLLEGE_DOMAIN_LEVELS},
    "access-admin": {},
    "principal": {domain: "view" for domain in COLLEGE_DOMAIN_LEVELS},
    "college-admin": {
        "students": "manage", "academics": "manage", "attendance": "manage",
        "assessments": "manage", "readiness": "work", "coding": "work",
        "placements": "work", "data": "manage", "reports": "view",
        "clearance": "view", "documents": "manage",
    },
    "academic-admin": {
        "students": "manage", "academics": "manage", "attendance": "manage",
        "assessments": "manage", "readiness": "view", "coding": "view",
        "data": "manage", "reports": "view", "clearance": "view",
        "documents": "manage",
    },
    "college-manager": {
        "students": "work", "academics": "view", "attendance": "work",
        "assessments": "work", "readiness": "work", "coding": "view",
        "placements": "work", "data": "view", "reports": "view",
        "clearance": "view", "documents": "view",
    },
    "placement-head": {
        "students": "view", "academics": "view", "attendance": "view",
        "assessments": "view", "readiness": "manage", "coding": "work",
        "placements": "manage", "data": "work", "reports": "view",
        "clearance": "view", "documents": "work",
    },
    "placement-coordinator": {
        "students": "view", "academics": "view", "attendance": "view",
        "assessments": "view", "readiness": "work", "coding": "view",
        "placements": "work", "data": "view", "reports": "view",
        "clearance": "view", "documents": "view",
    },
    "hod": {
        "students": "work", "academics": "view", "attendance": "work",
        "assessments": "work", "readiness": "work", "coding": "view",
        "placements": "view", "data": "view", "reports": "view",
        "clearance": "view", "documents": "view",
    },
    "class-advisor": {
        "students": "work", "academics": "view", "attendance": "work",
        "assessments": "work", "readiness": "work", "placements": "view",
        "clearance": "view", "documents": "view",
    },
    "faculty": {
        "students": "view", "academics": "view", "attendance": "work",
        "assessments": "work", "documents": "view",
    },
    "admissions": {
        "students": "manage", "academics": "view", "clearance": "view",
        "documents": "work",
    },
    "finance": {"students": "view", "clearance": "manage"},
    "auditor": {domain: "view" for domain in COLLEGE_DOMAIN_LEVELS},
}

SENSITIVE_CAPABILITIES = {
    "college.students.contact.view": "Student contact details",
    "college.students.guardian.view": "Guardian details",
    "college.notes.private.view": "Private intervention notes",
    "college.documents.sensitive.view": "Sensitive resumes and documents",
    "college.protected_fields.view": "Protected administrative fields",
    "college.data.export": "Export College data",
    "college.assessments.correct": "Correct published results",
    "college.readiness.policy.manage": "Manage readiness policy",
    "college.eligibility.override": "Override placement eligibility",
    "college.integrations.manage": "Manage integration credentials",
    "college.clearance.manage": "Correct internship clearance",
    "college.fees.view": "View fee amounts",
    "college.fees.manage": "Manage fee records",
    "notifications.send": "Send student communications",
}

MANAGED_PERMISSION_CODES = (
    set().union(*(codes for levels in COLLEGE_DOMAIN_LEVELS.values() for codes in levels.values()))
    | set(SENSITIVE_CAPABILITIES)
    | {"ai.use"}
)

POLICY_STRUCTURAL_PERMISSIONS = {
    "dashboard.view", "college.view", "ai.actions",
}

# These navigation dependencies are derived from an explicit policy rather
# than inherited blindly from a responsibility template.
POLICY_ASSIGNED_STRUCTURAL_PERMISSIONS = {"dashboard.view", "college.view"}
POLICY_MANAGED_PERMISSION_CODES = (
    MANAGED_PERMISSION_CODES | POLICY_ASSIGNED_STRUCTURAL_PERMISSIONS
)

# Any route protected by one of these permissions also needs an active College
# policy. This closes legacy role-only paths while non-College workspaces keep
# using the compatibility RBAC evaluator.
COLLEGE_POLICY_RELEVANT_PERMISSIONS = (
    MANAGED_PERMISSION_CODES | POLICY_STRUCTURAL_PERMISSIONS
)


@dataclass(frozen=True)
class ScopeRoot:
    scope_type: str
    scope_value: str


@dataclass(frozen=True)
class ExpandedCollegeScope:
    unrestricted: bool = False
    location_ids: frozenset[str] = frozenset()
    department_ids: frozenset[str] = frozenset()
    program_ids: frozenset[str] = frozenset()
    cohort_ids: frozenset[str] = frozenset()
    course_offering_ids: frozenset[str] = frozenset()
    student_ids: frozenset[str] = frozenset()
    full_student_ids: frozenset[str] = frozenset()

    def contains(self, scope_type: str, scope_value: str) -> bool:
        if self.unrestricted:
            return True
        values = {
            "location": self.location_ids,
            "department": self.department_ids,
            "program": self.program_ids,
            "cohort": self.cohort_ids,
            "course_offering": self.course_offering_ids,
            "student": self.student_ids,
        }
        return scope_value in values.get(scope_type, frozenset())


@dataclass(frozen=True)
class PolicyContext:
    organization_id: str
    user_id: str
    policy_id: str | None
    policy_version: int
    access_version: int
    status: str
    permissions: frozenset[str]
    maximum_scope: ExpandedCollegeScope
    domain_levels: dict[str, str] = field(default_factory=dict)
    domain_scopes: dict[str, ExpandedCollegeScope] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.status == "active"

    def level(self, domain: str) -> str:
        explicit = self.domain_levels.get(domain)
        if explicit in ACCESS_LEVELS:
            return explicit
        permissions = set(self.permissions)
        levels = COLLEGE_DOMAIN_LEVELS.get(domain, {})
        for level in reversed(ACCESS_LEVELS[1:]):
            required = levels.get(level, set())
            if required and required.issubset(permissions):
                return level
        return "none"

    def scope(self, domain: str) -> ExpandedCollegeScope:
        return self.domain_scopes.get(domain, self.maximum_scope)

    def has_sensitive(self, code: str) -> bool:
        return code in self.permissions


def college_domain_catalog() -> list[dict]:
    return [
        {
            "key": key,
            "label": COLLEGE_DOMAIN_LABELS[key],
            "levels": list(ACCESS_LEVELS),
            "supports_scope_narrowing": True,
        }
        for key in COLLEGE_DOMAIN_LEVELS
    ]


def domain_level_from_permissions(permissions: set[str], domain: str) -> str:
    levels = COLLEGE_DOMAIN_LEVELS[domain]
    selected = "none"
    previous_bundle: set[str] = set()
    for level in ACCESS_LEVELS[1:]:
        bundle = levels[level]
        if bundle and bundle.issubset(permissions) and bundle != previous_bundle:
            selected = level
        previous_bundle = bundle
    return selected


def permission_codes_for_levels(levels: dict[str, str]) -> set[str]:
    codes: set[str] = set()
    for domain, level in levels.items():
        if domain not in COLLEGE_DOMAIN_LEVELS or level not in ACCESS_LEVELS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid College access level")
        if level != "none":
            codes.update(COLLEGE_DOMAIN_LEVELS[domain][level])
    return codes


def is_owner(db: Session, user: User) -> bool:
    return any(role.is_system and role.slug == "owner" for role in get_user_roles(db, user))


def policy_v2_enabled(db: Session, organization_id: str) -> bool:
    flag = db.execute(select(FeatureFlag.enabled).where(
        FeatureFlag.organization_id == organization_id,
        FeatureFlag.flag == "authorization.policy_v2",
    )).scalar_one_or_none()
    return bool(flag)


def get_policy(db: Session, user: User) -> AccessPolicy | None:
    if not user.organization_id:
        return None
    return db.execute(
        select(AccessPolicy).where(
            AccessPolicy.organization_id == user.organization_id,
            AccessPolicy.user_id == user.id,
        ).execution_options(populate_existing=True)
    ).scalar_one_or_none()


def utc_datetime(value: datetime | None) -> datetime | None:
    """Normalize database datetimes before comparing policy expiries."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def ensure_policy(db: Session, user: User, *, creator_id: str | None = None) -> AccessPolicy:
    policy = get_policy(db, user)
    if policy:
        return policy
    owner = is_owner(db, user)
    policy = AccessPolicy(
        organization_id=user.organization_id,
        user_id=user.id,
        status="active" if owner else "pending_review",
        domain_levels={domain: "manage" for domain in COLLEGE_DOMAIN_LEVELS} if owner else {},
        created_by_user_id=creator_id,
        reviewed_by_user_id=user.id if owner else None,
        reviewed_at=datetime.now(timezone.utc) if owner else None,
    )
    db.add(policy)
    db.flush()
    if owner:
        db.add(AccessPolicyScope(
            organization_id=user.organization_id,
            policy_id=policy.id,
            domain_key="*",
            scope_type="organization",
            scope_value="*",
        ))
        db.flush()
    return policy


def policy_roots(db: Session, policy: AccessPolicy, domain: str = "*") -> list[ScopeRoot]:
    rows = list(db.execute(select(AccessPolicyScope).where(
        AccessPolicyScope.organization_id == policy.organization_id,
        AccessPolicyScope.policy_id == policy.id,
        AccessPolicyScope.domain_key == domain,
    )).scalars())
    if domain != "*" and not rows:
        rows = list(db.execute(select(AccessPolicyScope).where(
            AccessPolicyScope.organization_id == policy.organization_id,
            AccessPolicyScope.policy_id == policy.id,
            AccessPolicyScope.domain_key == "*",
        )).scalars())
    return [ScopeRoot(row.scope_type, row.scope_value) for row in rows]


def _ids(db: Session, statement) -> set[str]:
    return set(db.execute(statement).scalars())


def expand_college_roots(
    db: Session,
    organization_id: str,
    roots: Iterable[ScopeRoot],
    *,
    domain: str = "students",
) -> ExpandedCollegeScope:
    roots = list(roots)
    if any(root.scope_type == "organization" and root.scope_value == "*" for root in roots):
        return ExpandedCollegeScope(unrestricted=True)

    location_ids = {root.scope_value for root in roots if root.scope_type == "location"}
    department_roots = {root.scope_value for root in roots if root.scope_type == "department"}
    program_roots = {root.scope_value for root in roots if root.scope_type == "program"}
    cohort_roots = {root.scope_value for root in roots if root.scope_type == "cohort"}
    offering_roots = {root.scope_value for root in roots if root.scope_type == "course_offering"}
    student_roots = {root.scope_value for root in roots if root.scope_type == "student"}

    department_ids = set(department_roots)
    if location_ids:
        department_ids.update(_ids(db, select(CollegeDepartment.id).where(
            CollegeDepartment.organization_id == organization_id,
            CollegeDepartment.location_id.in_(location_ids),
        )))

    program_ids = set(program_roots)
    if department_ids:
        program_ids.update(_ids(db, select(CollegeProgram.id).where(
            CollegeProgram.organization_id == organization_id,
            CollegeProgram.department_id.in_(department_ids),
        )))

    cohort_ids = set(cohort_roots)
    if program_ids:
        cohort_ids.update(_ids(db, select(CollegeCohort.id).where(
            CollegeCohort.organization_id == organization_id,
            CollegeCohort.program_id.in_(program_ids),
        )))

    offering_ids = set(offering_roots)
    if cohort_ids:
        offering_ids.update(_ids(db, select(CollegeCourseOffering.id).where(
            CollegeCourseOffering.organization_id == organization_id,
            CollegeCourseOffering.cohort_id.in_(cohort_ids),
        )))

    offering_cohorts: set[str] = set()
    if offering_roots:
        offering_cohorts = _ids(db, select(CollegeCourseOffering.cohort_id).where(
            CollegeCourseOffering.organization_id == organization_id,
            CollegeCourseOffering.id.in_(offering_roots),
        ))

    full_student_ids = set(student_roots)
    roster_domains = {"attendance", "assessments"}
    full_student_conditions = []
    if department_ids:
        full_student_conditions.append(CollegeProgram.department_id.in_(department_ids))
    if program_ids:
        full_student_conditions.append(CollegeStudentProfile.program_id.in_(program_ids))
    if cohort_ids:
        full_student_conditions.append(CollegeStudentProfile.cohort_id.in_(cohort_ids))
    if full_student_conditions:
        full_student_ids.update(_ids(db, select(CollegeStudentProfile.id).join(
            CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id,
        ).where(
            CollegeStudentProfile.organization_id == organization_id,
            or_(*full_student_conditions),
        )))
    student_ids = set(full_student_ids)
    if domain in roster_domains and offering_cohorts:
        student_ids.update(_ids(db, select(CollegeStudentProfile.id).where(
            CollegeStudentProfile.organization_id == organization_id,
            CollegeStudentProfile.cohort_id.in_(offering_cohorts),
        )))
    if department_ids:
        location_ids.update(
            value for value in db.execute(select(CollegeDepartment.location_id).where(
                CollegeDepartment.organization_id == organization_id,
                CollegeDepartment.id.in_(department_ids),
                CollegeDepartment.location_id.is_not(None),
            )).scalars() if value
        )

    return ExpandedCollegeScope(
        location_ids=frozenset(location_ids),
        department_ids=frozenset(department_ids),
        program_ids=frozenset(program_ids),
        cohort_ids=frozenset(cohort_ids),
        course_offering_ids=frozenset(offering_ids),
        student_ids=frozenset(student_ids),
        full_student_ids=frozenset(full_student_ids),
    )


def resolve_policy_context(db: Session, user: User) -> PolicyContext:
    permissions = frozenset(get_user_permissions(db, user))
    if not user.organization_id:
        return PolicyContext(
            organization_id="", user_id=user.id, policy_id=None, policy_version=0,
            access_version=user.access_version, status="revoked", permissions=permissions,
            maximum_scope=ExpandedCollegeScope(),
        )

    if is_owner(db, user):
        policy = get_policy(db, user)
        return PolicyContext(
            organization_id=user.organization_id, user_id=user.id,
            policy_id=policy.id if policy else None,
            policy_version=policy.version if policy else user.access_version,
            access_version=user.access_version, status="active",
            permissions=permissions, maximum_scope=ExpandedCollegeScope(unrestricted=True),
            domain_levels={domain: "manage" for domain in COLLEGE_DOMAIN_LEVELS},
        )

    policy = get_policy(db, user)
    now = datetime.now(timezone.utc)
    expires_at = utc_datetime(policy.expires_at) if policy else None
    if not policy or policy.status != "active" or (expires_at and expires_at <= now):
        return PolicyContext(
            organization_id=user.organization_id, user_id=user.id,
            policy_id=policy.id if policy else None, policy_version=policy.version if policy else 0,
            access_version=user.access_version, status="expired" if policy and policy.expires_at else "pending_review",
            permissions=permissions, maximum_scope=ExpandedCollegeScope(),
            domain_levels=dict(policy.domain_levels or {}) if policy else {},
        )

    maximum = expand_college_roots(db, user.organization_id, policy_roots(db, policy), domain="students")
    domain_scopes: dict[str, ExpandedCollegeScope] = {}
    for domain in COLLEGE_DOMAIN_LEVELS:
        roots = policy_roots(db, policy, domain)
        domain_scopes[domain] = expand_college_roots(db, user.organization_id, roots, domain=domain)
    return PolicyContext(
        organization_id=user.organization_id, user_id=user.id, policy_id=policy.id,
        policy_version=policy.version, access_version=user.access_version, status=policy.status,
        permissions=permissions, maximum_scope=maximum,
        domain_levels=dict(policy.domain_levels or {}), domain_scopes=domain_scopes,
    )


def require_policy_domain(db: Session, user: User, domain: str, minimum: str = "view") -> PolicyContext:
    context = resolve_policy_context(db, user)
    if not context.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your College data access is awaiting review")
    if ACCESS_LEVELS.index(context.level(domain)) < ACCESS_LEVELS.index(minimum):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{COLLEGE_DOMAIN_LABELS.get(domain, domain)} access is required")
    return context


def active_delegation(db: Session, user: User) -> AccessDelegation | None:
    if not user.organization_id:
        return None
    row = db.execute(select(AccessDelegation).where(
        AccessDelegation.organization_id == user.organization_id,
        AccessDelegation.user_id == user.id,
        AccessDelegation.active.is_(True),
    )).scalar_one_or_none()
    expires_at = utc_datetime(row.expires_at) if row else None
    if row and expires_at and expires_at <= datetime.now(timezone.utc):
        return None
    return row


def require_access_administrator(db: Session, actor: User) -> AccessDelegation | None:
    if is_owner(db, actor):
        return None
    permissions = get_user_permissions(db, actor)
    delegation = active_delegation(db, actor)
    if "roles.manage" not in permissions or not delegation:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner or delegated Access Admin required")
    return delegation


def grantable_permission_codes(db: Session, actor: User) -> set[str] | None:
    """Return an Access Admin ceiling; owners have no catalogue ceiling."""
    if is_owner(db, actor):
        return None
    delegation = require_access_administrator(db, actor)
    codes = permission_codes_for_levels(dict(delegation.domain_levels or {}))
    codes.update(str(code) for code in (delegation.sensitive_capabilities or []))
    # Structural dependencies do not expose data without an active scope.
    codes.update(POLICY_STRUCTURAL_PERMISSIONS)
    if "ai.use" in delegation.sensitive_capabilities:
        codes.add("ai.use")
    return codes


def delegation_roots(db: Session, delegation: AccessDelegation) -> list[ScopeRoot]:
    rows = db.execute(select(AccessDelegationScope).where(
        AccessDelegationScope.organization_id == delegation.organization_id,
        AccessDelegationScope.delegation_id == delegation.id,
    )).scalars()
    return [ScopeRoot(row.scope_type, row.scope_value) for row in rows]


def validate_scope_roots(db: Session, organization_id: str, roots: Iterable[ScopeRoot]) -> list[ScopeRoot]:
    roots = list(roots)
    if len(roots) > 500:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Too many access scope roots")
    if len({(root.scope_type, root.scope_value) for root in roots}) != len(roots):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Duplicate access scope root")
    for root in roots:
        if root.scope_type not in SCOPE_TYPES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported access scope type")
        if root.scope_type == "organization":
            if root.scope_value != "*":
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid organization scope")
            continue
        model = {
            "department": CollegeDepartment,
            "program": CollegeProgram,
            "cohort": CollegeCohort,
            "course_offering": CollegeCourseOffering,
            "student": CollegeStudentProfile,
        }.get(root.scope_type)
        if model is not None:
            exists = db.execute(select(model.id).where(
                model.organization_id == organization_id,
                model.id == root.scope_value,
            )).first()
            if not exists:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "An access scope record is invalid")
        # Locations are validated by the Access API to avoid importing the
        # generic business model into College hierarchy policy calculations.
    return roots


def ensure_roots_within(
    db: Session,
    organization_id: str,
    roots: Iterable[ScopeRoot],
    ceiling_roots: Iterable[ScopeRoot],
    *,
    domain: str,
) -> None:
    ceiling = expand_college_roots(db, organization_id, ceiling_roots, domain=domain)
    for root in roots:
        if root.scope_type == "organization":
            allowed = ceiling.unrestricted
        else:
            allowed = ceiling.contains(root.scope_type, root.scope_value)
        if not allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot grant data outside the approved reach")


def policy_summary(context: PolicyContext) -> dict:
    return {
        "status": context.status,
        "policy_version": context.policy_version,
        "access_version": context.access_version,
        "domain_levels": {
            domain: context.level(domain) for domain in COLLEGE_DOMAIN_LEVELS
        },
        "sensitive_capabilities": [
            code for code in SENSITIVE_CAPABILITIES if code in context.permissions
        ],
        "ai_enabled": "ai.use" in context.permissions,
    }
