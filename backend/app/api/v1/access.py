"""Atomic RBAC and ABAC configuration with effective-access previews."""
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import and_, delete, false, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.business import serialize
from app.core.database import get_db
from app.schemas.validation import RequestModel
from app.core.deps import require_entitlements, require_permissions
from app.models import (
    AccessDelegation, AccessDelegationScope, AccessPolicy, AccessPolicyScope, AccessScope, AuditLog,
    Client, CollegeCohort, CollegeCourse, CollegeCourseOffering, CollegeDepartment, CollegeProgram,
    CollegeStudentProfile,
    Location, Organization, Permission, Role, RolePermission, User,
    UserPermissionOverride, UserRole,
)
from app.services.audit import log_action
from app.services.business_access import allowed_client_ids, allowed_location_ids, client_scope_mode, filter_clients
from app.services.entitlements import entitlement_value
from app.services.rbac import get_user_permissions, get_user_roles
from app.services.access_policy import (
    ACCESS_LEVELS, COLLEGE_DOMAIN_LEVELS, COLLEGE_DOMAIN_LABELS,
    COLLEGE_ROLE_LEVEL_SUGGESTIONS, MANAGED_PERMISSION_CODES,
    POLICY_MANAGED_PERMISSION_CODES,
    SCOPE_TYPES,
    SENSITIVE_CAPABILITIES, ScopeRoot,
    active_delegation, college_domain_catalog, delegation_roots, ensure_policy,
    domain_level_from_permissions, ensure_roots_within, expand_college_roots, get_policy, grantable_permission_codes,
    is_owner, permission_codes_for_levels, policy_roots, policy_summary,
    policy_v2_enabled, require_access_administrator, resolve_policy_context, utc_datetime, validate_scope_roots,
)
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size

router = APIRouter(prefix="/access", tags=["access-control"])


class LocationAccessBody(RequestModel):
    location_ids: list[str]


class PermissionOverrideBody(RequestModel):
    permission_id: str
    granted: bool


class UserAccessConfiguration(RequestModel):
    role_ids: list[str] = Field(default_factory=list)
    permission_overrides: list[PermissionOverrideBody] = Field(default_factory=list)
    location_mode: str = Field(pattern="^(full|restricted)$")
    location_ids: list[str] = Field(default_factory=list)
    client_mode: str = Field(pattern="^(all|assigned|selected)$")
    client_ids: list[str] = Field(default_factory=list)
    version: int | None = Field(default=None, ge=1)


class PolicyScopeBody(RequestModel):
    scope_type: Literal[
        "organization", "location", "department", "program", "cohort",
        "course_offering", "student",
    ]
    scope_value: str = Field(min_length=1, max_length=200)


class EnterprisePolicyBody(RequestModel):
    role_ids: list[str] = Field(default_factory=list, max_length=100)
    maximum_reach: list[PolicyScopeBody] = Field(min_length=1, max_length=500)
    domain_levels: dict[str, Literal["none", "view", "work", "manage"]] = Field(default_factory=dict)
    domain_scope_limits: dict[str, list[PolicyScopeBody]] = Field(default_factory=dict)
    sensitive_capabilities: list[str] = Field(default_factory=list, max_length=100)
    ai_enabled: bool = False
    expires_at: datetime | None = None
    review_note: str | None = Field(default=None, max_length=500)
    version: int | None = Field(default=None, ge=1)


class DelegationBody(RequestModel):
    active: bool = True
    maximum_reach: list[PolicyScopeBody] = Field(min_length=1, max_length=500)
    domain_levels: dict[str, Literal["none", "view", "work", "manage"]] = Field(default_factory=dict)
    sensitive_capabilities: list[str] = Field(default_factory=list, max_length=100)
    expires_at: datetime | None = None
    version: int | None = Field(default=None, ge=1)


class GuidedRoleTemplateBody(RequestModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    domain_levels: dict[str, Literal["none", "view", "work", "manage"]] = Field(default_factory=dict)
    ai_enabled: bool = False
    source_role_id: str | None = Field(default=None, max_length=100)


def target_user(db, actor, user_id):
    row = db.get(User, user_id)
    if not row or row.organization_id != actor.organization_id: raise HTTPException(404, "User not found")
    return row


def _college_access_admin(db: Session, actor: User):
    organization = db.get(Organization, actor.organization_id)
    if organization and organization.industry.value == "college":
        return require_access_administrator(db, actor)
    return None


def _require_legacy_access_mode(db: Session, actor: User) -> None:
    organization = db.get(Organization, actor.organization_id)
    if (
        organization
        and organization.industry.value == "college"
        and policy_v2_enabled(db, actor.organization_id)
    ):
        raise HTTPException(
            status_code=409,
            detail="Use the reviewed College access policy instead of legacy role and location configuration",
        )


def _roots(rows: list[PolicyScopeBody]) -> list[ScopeRoot]:
    return [ScopeRoot(row.scope_type, row.scope_value) for row in rows]


def _validate_locations(db: Session, organization_id: str, roots: list[ScopeRoot]) -> None:
    location_ids = {root.scope_value for root in roots if root.scope_type == "location"}
    if not location_ids:
        return
    valid = set(db.execute(select(Location.id).where(
        Location.organization_id == organization_id,
        Location.id.in_(location_ids),
        Location.is_active.is_(True),
    )).scalars())
    if valid != location_ids:
        raise HTTPException(422, "One or more campus scopes are invalid")


def _role_codes(db: Session, role_ids: list[str], organization_id: str) -> tuple[list[Role], set[str]]:
    roles = list(db.execute(select(Role).where(
        Role.organization_id == organization_id,
        Role.id.in_(role_ids),
        Role.is_active.is_(True),
    )).scalars()) if role_ids else []
    if {row.id for row in roles} != set(role_ids):
        raise HTTPException(422, "One or more roles are invalid or inactive")
    codes = set(db.execute(select(Permission.code).join(
        RolePermission, RolePermission.permission_id == Permission.id,
    ).where(RolePermission.role_id.in_(role_ids))).scalars()) if role_ids else set()
    return roles, codes


CAPABILITY_REQUIREMENTS = {
    "college.students.contact.view": ("students", "view"),
    "college.students.guardian.view": ("students", "view"),
    "college.protected_fields.view": ("students", "view"),
    "college.notes.private.view": ("readiness", "view"),
    "college.documents.sensitive.view": ("documents", "view"),
    "college.data.export": ("data", "view"),
    "college.assessments.correct": ("assessments", "work"),
    "college.readiness.policy.manage": ("readiness", "manage"),
    "college.eligibility.override": ("placements", "work"),
    "college.integrations.manage": ("data", "manage"),
    "college.clearance.manage": ("clearance", "work"),
    "college.fees.view": ("clearance", "view"),
    "college.fees.manage": ("clearance", "work"),
}


def _normalize_domain_levels(levels: dict[str, str]) -> dict[str, str]:
    return {domain: levels.get(domain, "none") for domain in COLLEGE_DOMAIN_LEVELS}


def _custom_role_slug(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return f"custom-{value or 'responsibility'}"


def _validate_capability_dependencies(levels: dict[str, str], capabilities: set[str]) -> None:
    for capability in capabilities:
        requirement = CAPABILITY_REQUIREMENTS.get(capability)
        if requirement and ACCESS_LEVELS.index(levels[requirement[0]]) < ACCESS_LEVELS.index(requirement[1]):
            raise HTTPException(
                422,
                f"{SENSITIVE_CAPABILITIES[capability]} requires {COLLEGE_DOMAIN_LABELS[requirement[0]]} {requirement[1]} access",
            )
    if "college.fees.manage" in capabilities and "college.fees.view" not in capabilities:
        raise HTTPException(422, "Managing fee records also requires permission to view fee amounts")
    if "notifications.send" in capabilities and not any(
        ACCESS_LEVELS.index(levels[domain]) >= ACCESS_LEVELS.index("work")
        for domain in ("students", "readiness", "placements")
    ):
        raise HTTPException(422, "Student communications require Work access to Students, Readiness, or Placements")


def _validate_policy_body(db: Session, actor: User, target: User, body: EnterprisePolicyBody) -> dict:
    delegation = _college_access_admin(db, actor)
    actor_owner = is_owner(db, actor)
    if target.id == actor.id:
        raise HTTPException(409, "Another owner must review changes to your own access")
    target_role_slugs = {role.slug for role in get_user_roles(db, target) if role.is_system}
    if not actor_owner and target_role_slugs.intersection({"owner", "access-admin"}):
        raise HTTPException(403, "Only an owner can change owners or Access Admins")

    unknown_domains = set(body.domain_levels) - set(COLLEGE_DOMAIN_LEVELS)
    unknown_limits = set(body.domain_scope_limits) - set(COLLEGE_DOMAIN_LEVELS)
    if unknown_domains or unknown_limits:
        raise HTTPException(422, "One or more College access domains are invalid")
    if set(body.sensitive_capabilities) - set(SENSITIVE_CAPABILITIES):
        raise HTTPException(422, "One or more sensitive capabilities are invalid")
    if len(body.sensitive_capabilities) != len(set(body.sensitive_capabilities)):
        raise HTTPException(422, "Each sensitive capability may only be selected once")
    if utc_datetime(body.expires_at) and utc_datetime(body.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(422, "Access expiry must be in the future")

    roles, role_codes = _role_codes(db, body.role_ids, actor.organization_id)
    next_role_slugs = {role.slug for role in roles if role.is_system}
    if not actor_owner and next_role_slugs.intersection({"owner", "access-admin"}):
        raise HTTPException(403, "Only an owner can assign Owner or Access Admin")

    normalized_levels = _normalize_domain_levels(body.domain_levels)
    has_college_domain = any(level != "none" for level in normalized_levels.values())
    if not has_college_domain and "access-admin" not in next_role_slugs:
        raise HTTPException(422, "Enable at least one College work area")
    if body.ai_enabled and not has_college_domain:
        raise HTTPException(422, "Edvatiq AI needs at least one College work area")

    _validate_capability_dependencies(normalized_levels, set(body.sensitive_capabilities))

    maximum_roots = validate_scope_roots(db, actor.organization_id, _roots(body.maximum_reach))
    _validate_locations(db, actor.organization_id, maximum_roots)
    if any(root.scope_type == "organization" for root in maximum_roots) and len(maximum_roots) != 1:
        raise HTTPException(422, "Whole-institution reach cannot be combined with narrower roots")

    domain_roots: dict[str, list[ScopeRoot]] = {}
    for domain, rows in body.domain_scope_limits.items():
        roots = validate_scope_roots(db, actor.organization_id, _roots(rows))
        _validate_locations(db, actor.organization_id, roots)
        ensure_roots_within(db, actor.organization_id, roots, maximum_roots, domain=domain)
        domain_roots[domain] = roots

    desired_managed = permission_codes_for_levels(normalized_levels)
    desired_managed.update(body.sensitive_capabilities)
    if has_college_domain:
        desired_managed.add("college.view")
    if normalized_levels["reports"] != "none":
        desired_managed.add("dashboard.view")
    if body.ai_enabled:
        desired_managed.add("ai.use")
    effective_codes = (role_codes - POLICY_MANAGED_PERMISSION_CODES) | desired_managed

    ceiling = grantable_permission_codes(db, actor)
    if ceiling is not None:
        delegated_levels = _normalize_domain_levels(dict(delegation.domain_levels or {}))
        if any(
            ACCESS_LEVELS.index(level) > ACCESS_LEVELS.index(delegated_levels[domain])
            for domain, level in normalized_levels.items()
        ):
            raise HTTPException(403, "This access exceeds your delegated work-area ceiling")
        excessive = desired_managed - ceiling
        role_excessive = (role_codes - POLICY_MANAGED_PERMISSION_CODES) - ceiling
        if excessive or role_excessive:
            raise HTTPException(403, "This access exceeds your delegated capability ceiling")
        delegation_ceiling = delegation_roots(db, delegation)
        ensure_roots_within(
            db, actor.organization_id, maximum_roots, delegation_ceiling,
            domain="students",
        )

    visibility = expand_college_roots(db, actor.organization_id, maximum_roots, domain="students")
    warnings = []
    if not body.role_ids:
        warnings.append("No responsibility template is selected.")
    if not has_college_domain:
        warnings.append("This policy grants access administration only and exposes no College student data.")
    if "college.fees.view" in desired_managed:
        warnings.append("This person can view financial amounts, not only internship clearance.")
    return {
        "roles": roles,
        "role_codes": role_codes,
        "effective_codes": effective_codes,
        "desired_managed": desired_managed,
        "maximum_roots": maximum_roots,
        "domain_roots": domain_roots,
        "visibility": visibility,
        "warnings": warnings,
    }


def _scope_payload(rows: list[ScopeRoot]) -> list[dict]:
    return [{"scope_type": row.scope_type, "scope_value": row.scope_value} for row in rows]


def _plain_access_summary(body: EnterprisePolicyBody, visibility, role_names: list[str]) -> str:
    enabled = [
        f"{COLLEGE_DOMAIN_LABELS[domain]}: {level}"
        for domain, level in body.domain_levels.items() if level != "none"
    ]
    reach = "the whole institution" if visibility.unrestricted else (
        f"{len(visibility.department_ids)} departments, {len(visibility.cohort_ids)} cohorts, "
        f"and {len(visibility.student_ids)} students"
    )
    responsibilities = ", ".join(role_names) if role_names else "Custom responsibilities"
    work = "; ".join(enabled) if enabled else "No College work areas"
    return f"{responsibilities}. Reach: {reach}. {work}."


def _policy_payload(db: Session, target: User) -> dict:
    policy = ensure_policy(db, target)
    context = resolve_policy_context(db, target)
    roles = get_user_roles(db, target)
    maximum = policy_roots(db, policy)
    domain_limits = {}
    for domain in COLLEGE_DOMAIN_LEVELS:
        explicit = list(db.execute(select(AccessPolicyScope).where(
            AccessPolicyScope.policy_id == policy.id,
            AccessPolicyScope.domain_key == domain,
        )).scalars())
        if explicit:
            domain_limits[domain] = _scope_payload([
                ScopeRoot(row.scope_type, row.scope_value) for row in explicit
            ])
    return {
        "user": {
            "id": target.id, "first_name": target.first_name, "last_name": target.last_name,
            "email": target.email, "is_active": target.is_active,
        },
        "version": policy.version,
        "access_version": target.access_version,
        "status": policy.status,
        "expires_at": policy.expires_at,
        "review_note": policy.review_note,
        "role_ids": [role.id for role in roles],
        "roles": [{"id": role.id, "name": role.name, "slug": role.slug} for role in roles],
        "maximum_reach": _scope_payload(maximum),
        "domain_levels": policy_summary(context)["domain_levels"],
        "domain_scope_limits": domain_limits,
        "sensitive_capabilities": policy_summary(context)["sensitive_capabilities"],
        "ai_enabled": "ai.use" in context.permissions,
    }


def _configuration_preview(db: Session, actor: User, target: User, body: UserAccessConfiguration) -> dict:
    valid_roles = db.execute(select(Role).where(
        Role.organization_id == actor.organization_id,
        Role.id.in_(body.role_ids),
        Role.is_active.is_(True),
    )).scalars().all() if body.role_ids else []
    if {row.id for row in valid_roles} != set(body.role_ids):
        raise HTTPException(422, "One or more roles are invalid or inactive")

    actor_permissions = get_user_permissions(db, actor)
    role_permission_rows = db.execute(
        select(Permission.id, Permission.code, Permission.label, Permission.module)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id.in_(body.role_ids))
    ).all() if body.role_ids else []
    role_codes = {row.code for row in role_permission_rows}
    if not role_codes.issubset(actor_permissions):
        raise HTTPException(403, "Cannot assign capabilities you do not have")

    valid_locations = set(db.execute(select(Location.id).where(
        Location.organization_id == actor.organization_id,
        Location.id.in_(body.location_ids),
        Location.is_active.is_(True),
    )).scalars()) if body.location_ids else set()
    if valid_locations != set(body.location_ids):
        raise HTTPException(422, "One or more locations are invalid")
    if body.location_mode == "restricted" and not valid_locations:
        raise HTTPException(422, "Choose at least one location for restricted access")
    actor_locations = allowed_location_ids(db, actor)
    if actor_locations is not None and (body.location_mode == "full" or not valid_locations.issubset(actor_locations)):
        raise HTTPException(403, "Cannot grant locations outside your own access")

    actor_client_mode = client_scope_mode(db, actor)
    actor_clients = allowed_client_ids(db, actor)
    if actor_client_mode != "all" and body.client_mode != "selected":
        raise HTTPException(403, "Scoped administrators can only grant a selected subset of their clients")
    client_stmt = filter_clients(
        select(Client.id).where(Client.organization_id == actor.organization_id, Client.id.in_(body.client_ids)),
        db,
        actor,
    )
    valid_clients = set(db.execute(client_stmt).scalars()) if body.client_ids else set()
    if body.client_mode == "selected" and valid_clients != set(body.client_ids):
        raise HTTPException(422, "One or more selected clients are outside your access")
    if body.client_mode == "selected" and not valid_clients:
        raise HTTPException(422, "Choose at least one client for selected access")
    if actor_clients is not None and body.client_mode == "selected" and not valid_clients.issubset(actor_clients):
        raise HTTPException(403, "Cannot grant clients outside your own access")

    override_ids = [item.permission_id for item in body.permission_overrides]
    if len(override_ids) != len(set(override_ids)):
        raise HTTPException(422, "Each permission may only have one personal adjustment")
    permission_rows = db.execute(select(Permission).where(
        Permission.id.in_(override_ids),
        or_(Permission.organization_id.is_(None), Permission.organization_id == actor.organization_id),
    )).scalars().all() if override_ids else []
    if {row.id for row in permission_rows} != set(override_ids):
        raise HTTPException(422, "One or more permission overrides are invalid")
    permission_by_id = {row.id: row for row in permission_rows}
    for item in body.permission_overrides:
        if item.granted and permission_by_id[item.permission_id].code not in actor_permissions:
            raise HTTPException(403, "Cannot grant a personal capability you do not have")

    effective_codes = set(role_codes)
    for item in body.permission_overrides:
        code = permission_by_id[item.permission_id].code
        if item.granted:
            effective_codes.add(code)
        else:
            effective_codes.discard(code)
    effective_rows = db.execute(select(Permission).where(Permission.code.in_(effective_codes)).order_by(Permission.module, Permission.label)).scalars().all() if effective_codes else []
    warnings = []
    if not body.role_ids:
        warnings.append("No role is selected, so only personal allowances will apply.")
    if "dashboard.view" not in effective_codes:
        warnings.append("This person will not be able to open the business workspace.")
    if "clients.view" not in effective_codes and any(code.startswith("clients.") or code.startswith("gym.") for code in effective_codes):
        warnings.append("Some selected work needs Client access, but Client viewing is blocked.")
    return {
        "roles": [
            {"id": row.id, "name": row.name, "slug": row.slug, "is_system": row.is_system}
            for row in valid_roles
        ],
        "effective_permissions": [{"id": row.id, "code": row.code, "label": row.label, "module": row.module} for row in effective_rows],
        "location_scope": {
            "mode": body.location_mode,
            "count": None if body.location_mode == "full" else len(valid_locations),
        },
        "client_scope": {
            "mode": body.client_mode,
            "count": len(valid_clients) if body.client_mode == "selected" else None,
        },
        "warnings": warnings,
    }


@router.get("/workspace")
def workspace(include_directories: bool = True, actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    _college_access_admin(db, actor)
    _require_legacy_access_mode(db, actor)
    actor_permission_codes = get_user_permissions(db, actor)
    permissions = db.execute(select(Permission).where(
        or_(Permission.organization_id.is_(None), Permission.organization_id == actor.organization_id),
        Permission.code.in_(actor_permission_codes),
    ).order_by(Permission.module, Permission.label)).scalars().all()
    roles = db.execute(select(Role).where(Role.organization_id == actor.organization_id).order_by(Role.is_system.desc(), Role.name)).scalars().all()
    role_permissions = db.execute(select(RolePermission.role_id, RolePermission.permission_id).where(
        RolePermission.role_id.in_([row.id for row in roles])
    )).all() if roles else []
    role_users = db.execute(select(UserRole.role_id, func.count(UserRole.user_id)).where(
        UserRole.role_id.in_([row.id for row in roles])
    ).group_by(UserRole.role_id)).all() if roles else []
    permission_ids: dict[str, list[str]] = {row.id: [] for row in roles}
    for role_id, permission_id in role_permissions:
        permission_ids.setdefault(role_id, []).append(permission_id)
    user_counts = dict(role_users)

    users = db.execute(select(User).where(User.organization_id == actor.organization_id).order_by(User.first_name, User.last_name)).scalars().all() if include_directories else []
    user_role_rows = db.execute(select(UserRole.user_id, Role.id, Role.name).join(Role, Role.id == UserRole.role_id).where(
        UserRole.user_id.in_([row.id for row in users])
    )).all() if users else []
    roles_by_user: dict[str, list[dict]] = {row.id: [] for row in users}
    for user_id, role_id, role_name in user_role_rows:
        roles_by_user.setdefault(user_id, []).append({"id": role_id, "name": role_name})

    locations = db.execute(select(Location).where(
        Location.organization_id == actor.organization_id, Location.is_active.is_(True),
    ).order_by(Location.name)).scalars().all()
    clients = db.execute(filter_clients(select(Client).where(
        Client.organization_id == actor.organization_id,
    ).order_by(Client.first_name, Client.last_name).limit(250), db, actor)).scalars().all() if include_directories else []
    return {
        "roles": [{
            **serialize(row),
            "permission_ids": permission_ids.get(row.id, []),
            "user_count": int(user_counts.get(row.id, 0)),
        } for row in roles],
        "permissions": [serialize(row) for row in permissions],
        "users": [{
            "id": row.id, "first_name": row.first_name, "last_name": row.last_name,
            "email": row.email, "is_active": row.is_active, "access_version": row.access_version,
            "roles": roles_by_user.get(row.id, []),
        } for row in users],
        "locations": [serialize(row) for row in locations],
        "clients": [{
            "id": row.id, "first_name": row.first_name, "last_name": row.last_name,
            "phone": row.phone, "client_number": row.client_number,
        } for row in clients],
        "capabilities": {
            "create_custom_roles": bool(entitlement_value(db, db.get(Organization, actor.organization_id), "access.custom_roles", False)),
            "edit_system_roles": False,
            "view_audit": "settings.audit.view" in actor_permission_codes,
        },
    }


@router.get("/people/page")
@router.get("/users/page")
def access_users_page(
    q: str | None = Query(default=None, max_length=100),
    account_status: str = Query(default="all", alias="status", pattern="^(all|active|inactive)$"),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    _college_access_admin(db, actor)
    normalized_query = " ".join((q or "").casefold().split())
    filters = {"q": normalized_query, "status": account_status}
    values = decode_cursor(cursor, scope="access.users", organization_id=actor.organization_id, filters=filters)
    statement = select(User).where(User.organization_id == actor.organization_id)
    if account_status != "all":
        statement = statement.where(User.is_active.is_(account_status == "active"))
    if normalized_query:
        term = f"%{normalized_query}%"
        role_match = select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(
            UserRole.user_id == User.id,
            func.lower(Role.name).like(term),
        ).exists()
        statement = statement.where(or_(
            func.lower(User.first_name).like(term),
            func.lower(User.last_name).like(term),
            func.lower(User.email).like(term),
            role_match,
        ))
    first_key = func.lower(User.first_name)
    last_key = func.lower(User.last_name)
    if values:
        first = str(values["first"])
        last = str(values["last"])
        identifier = str(values["id"])
        statement = statement.where(or_(
            first_key > first,
            and_(first_key == first, last_key > last),
            and_(first_key == first, last_key == last, User.id > identifier),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(first_key, last_key, User.id).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    role_rows = db.execute(select(UserRole.user_id, Role.id, Role.name, Role.slug).join(
        Role, Role.id == UserRole.role_id,
    ).where(UserRole.user_id.in_([row.id for row in rows]))).all() if rows else []
    roles_by_user: dict[str, list[dict]] = {row.id: [] for row in rows}
    for user_id, role_id, role_name, role_slug in role_rows:
        roles_by_user.setdefault(user_id, []).append({
            "id": role_id, "name": role_name, "slug": role_slug,
        })
    policies = {
        row.user_id: row for row in db.execute(select(AccessPolicy).where(
            AccessPolicy.organization_id == actor.organization_id,
            AccessPolicy.user_id.in_([row.id for row in rows]),
        )).scalars()
    } if rows else {}
    next_cursor = encode_cursor(
        scope="access.users",
        organization_id=actor.organization_id,
        filters=filters,
        values={"first": rows[-1].first_name.casefold(), "last": rows[-1].last_name.casefold(), "id": rows[-1].id},
    ) if has_more and rows else None
    summary = db.execute(select(
        func.count(User.id),
        func.count(User.id).filter(User.is_active.is_(True)),
    ).where(User.organization_id == actor.organization_id)).one()
    return {
        "items": [{
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "email": row.email,
            "is_active": row.is_active,
            "access_version": row.access_version,
            "roles": roles_by_user.get(row.id, []),
            "policy_status": (
                "expired"
                if row.id in policies and utc_datetime(policies[row.id].expires_at)
                and utc_datetime(policies[row.id].expires_at) <= datetime.now(timezone.utc)
                else policies[row.id].status if row.id in policies
                else "active" if any(role.get("slug") == "owner" for role in roles_by_user.get(row.id, []))
                else "pending_review"
            ),
            "policy_version": policies[row.id].version if row.id in policies else 0,
            "policy_expires_at": policies[row.id].expires_at if row.id in policies else None,
        } for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "summary": {"total": int(summary[0] or 0), "active": int(summary[1] or 0)},
    }


@router.get("/clients/page")
def access_clients_page(
    q: str | None = Query(default=None, max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    _college_access_admin(db, actor)
    _require_legacy_access_mode(db, actor)
    normalized_query = " ".join((q or "").casefold().split())
    filters = {"q": normalized_query}
    values = decode_cursor(cursor, scope="access.clients", organization_id=actor.organization_id, filters=filters)
    statement = filter_clients(select(Client).where(Client.organization_id == actor.organization_id), db, actor)
    if normalized_query:
        term = f"%{normalized_query}%"
        statement = statement.where(or_(
            func.lower(Client.first_name).like(term),
            func.lower(Client.last_name).like(term),
            func.lower(func.coalesce(Client.phone, "")).like(term),
            func.lower(Client.client_number).like(term),
        ))
    first_key = func.lower(Client.first_name)
    last_key = func.lower(Client.last_name)
    if values:
        first = str(values["first"])
        last = str(values["last"])
        identifier = str(values["id"])
        statement = statement.where(or_(
            first_key > first,
            and_(first_key == first, last_key > last),
            and_(first_key == first, last_key == last, Client.id > identifier),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(first_key, last_key, Client.id).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="access.clients",
        organization_id=actor.organization_id,
        filters=filters,
        values={"first": rows[-1].first_name.casefold(), "last": rows[-1].last_name.casefold(), "id": rows[-1].id},
    ) if has_more and rows else None
    return {
        "items": [{
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "phone": row.phone,
            "client_number": row.client_number,
        } for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/students/page")
def access_students_page(
    q: str | None = Query(default=None, max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    delegation = _college_access_admin(db, actor)
    normalized_query = " ".join((q or "").casefold().split())
    filters = {"q": normalized_query}
    values = decode_cursor(
        cursor, scope="access.students", organization_id=actor.organization_id, filters=filters,
    )
    statement = select(
        CollegeStudentProfile, Client, CollegeProgram, CollegeDepartment, CollegeCohort,
    ).join(
        Client, Client.id == CollegeStudentProfile.client_id,
    ).join(
        CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id,
    ).join(
        CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id,
    ).join(
        CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id,
    ).where(
        CollegeStudentProfile.organization_id == actor.organization_id,
        CollegeStudentProfile.status == "active",
    )
    if delegation:
        # Delegated access administration does not expose a student directory.
        # An owner must explicitly include student roots to permit person-level assignment.
        explicit_students = {
            root.scope_value for root in delegation_roots(db, delegation)
            if root.scope_type == "student"
        }
        statement = statement.where(
            CollegeStudentProfile.id.in_(explicit_students) if explicit_students else false(),
        )
    if normalized_query:
        term = f"%{normalized_query}%"
        statement = statement.where(or_(
            func.lower(Client.first_name).like(term),
            func.lower(Client.last_name).like(term),
            func.lower(CollegeStudentProfile.admission_number).like(term),
            func.lower(func.coalesce(CollegeStudentProfile.roll_number, "")).like(term),
        ))
    first_key = func.lower(Client.first_name)
    last_key = func.lower(Client.last_name)
    if values:
        first = str(values["first"])
        last = str(values["last"])
        identifier = str(values["id"])
        statement = statement.where(or_(
            first_key > first,
            and_(first_key == first, last_key > last),
            and_(first_key == first, last_key == last, CollegeStudentProfile.id > identifier),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(
        first_key, last_key, CollegeStudentProfile.id,
    ).limit(size + 1)).all())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="access.students",
        organization_id=actor.organization_id,
        filters=filters,
        values={
            "first": rows[-1][1].first_name.casefold(),
            "last": rows[-1][1].last_name.casefold(),
            "id": rows[-1][0].id,
        },
    ) if has_more and rows else None
    return {
        "items": [{
            "id": student.id,
            "client_id": client.id,
            "name": f"{client.first_name} {client.last_name}".strip(),
            "admission_number": student.admission_number,
            "roll_number": student.roll_number,
            "department": department.code,
            "program": program.code,
            "cohort": cohort.name,
            "section": cohort.section,
            "graduation_year": cohort.graduation_year,
        } for student, client, program, department, cohort in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/audit")
def access_audit(limit: int = 100, actor=Depends(require_permissions("settings.audit.view")), db: Session = Depends(get_db)):
    _college_access_admin(db, actor)
    rows = db.execute(select(AuditLog).where(
        AuditLog.organization_id == actor.organization_id,
        or_(AuditLog.action.like("access.%"), AuditLog.action.like("role.%")),
    ).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 200))).scalars().all()
    user_ids = {row.user_id for row in rows if row.user_id}
    users = {row.id: row for row in db.execute(select(User).where(User.id.in_(user_ids))).scalars()} if user_ids else {}
    return [{
        "id": row.id,
        "action": row.action,
        "actor": f"{users[row.user_id].first_name} {users[row.user_id].last_name}".strip() if row.user_id in users else "System",
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "summary": (row.meta or {}).get("summary"),
        "created_at": row.created_at,
    } for row in rows]


@router.get("/audit/page")
def access_audit_page(
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    actor=Depends(require_permissions("settings.audit.view")),
    db: Session = Depends(get_db),
):
    _college_access_admin(db, actor)
    values = decode_cursor(cursor, scope="access.audit", organization_id=actor.organization_id)
    statement = select(AuditLog).where(
        AuditLog.organization_id == actor.organization_id,
        or_(AuditLog.action.like("access.%"), AuditLog.action.like("role.%")),
    )
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            AuditLog.created_at < pivot_at,
            and_(AuditLog.created_at == pivot_at, AuditLog.id < str(values["id"])),
        ))
    size = page_size(limit, default=50)
    rows = list(db.execute(statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    user_ids = {row.user_id for row in rows if row.user_id}
    users = {row.id: row for row in db.execute(select(User).where(User.id.in_(user_ids))).scalars()} if user_ids else {}
    next_cursor = encode_cursor(
        scope="access.audit",
        organization_id=actor.organization_id,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    return {
        "items": [{
            "id": row.id,
            "action": row.action,
            "actor": f"{users[row.user_id].first_name} {users[row.user_id].last_name}".strip() if row.user_id in users else "System",
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "summary": (row.meta or {}).get("summary"),
            "created_at": row.created_at,
        } for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/catalog")
def catalog(actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    delegation = _college_access_admin(db, actor)
    actor_owner = is_owner(db, actor)
    organization = db.get(Organization, actor.organization_id)
    locations = list(db.execute(select(Location).where(
        Location.organization_id == actor.organization_id,
        Location.is_active.is_(True),
    ).order_by(Location.name)).scalars())
    departments = list(db.execute(select(CollegeDepartment).where(
        CollegeDepartment.organization_id == actor.organization_id,
        CollegeDepartment.is_active.is_(True),
    ).order_by(CollegeDepartment.name)).scalars())
    programs = list(db.execute(select(CollegeProgram).where(
        CollegeProgram.organization_id == actor.organization_id,
        CollegeProgram.is_active.is_(True),
    ).order_by(CollegeProgram.name)).scalars())
    cohorts = list(db.execute(select(CollegeCohort).where(
        CollegeCohort.organization_id == actor.organization_id,
        CollegeCohort.is_active.is_(True),
    ).order_by(CollegeCohort.graduation_year, CollegeCohort.name)).scalars())
    offerings = list(db.execute(select(CollegeCourseOffering).where(
        CollegeCourseOffering.organization_id == actor.organization_id,
        CollegeCourseOffering.status == "active",
    ).order_by(CollegeCourseOffering.created_at)).scalars())
    course_ids = {row.course_id for row in offerings}
    courses = {
        row.id: row for row in db.execute(select(CollegeCourse).where(
            CollegeCourse.organization_id == actor.organization_id,
            CollegeCourse.id.in_(course_ids),
        )).scalars()
    } if course_ids else {}
    template_slugs = {
        "owner", "access-admin", "principal", "college-admin", "academic-admin",
        "college-manager", "placement-head", "placement-coordinator", "hod",
        "class-advisor", "faculty", "admissions", "finance", "auditor",
    }
    roles = list(db.execute(select(Role).where(
        Role.organization_id == actor.organization_id,
        Role.is_active.is_(True),
        Role.slug != "manager",
    ).order_by(Role.name)).scalars())
    if not actor_owner:
        roles = [row for row in roles if row.slug not in {"owner", "access-admin"}]
    role_code_rows = db.execute(select(RolePermission.role_id, Permission.code).join(
        Permission, Permission.id == RolePermission.permission_id,
    ).where(RolePermission.role_id.in_([row.id for row in roles]))).all() if roles else []
    codes_by_role: dict[str, set[str]] = {row.id: set() for row in roles}
    for role_id, code in role_code_rows:
        codes_by_role.setdefault(role_id, set()).add(code)

    grantable_codes = grantable_permission_codes(db, actor)
    grantable_levels = _normalize_domain_levels(
        dict(delegation.domain_levels or {}) if delegation else {
            domain: "manage" for domain in COLLEGE_DOMAIN_LEVELS
        },
    )
    if grantable_codes is not None:
        roles = [
            row for row in roles
            if (codes_by_role.get(row.id, set()) - POLICY_MANAGED_PERMISSION_CODES).issubset(grantable_codes)
        ]

    if delegation:
        ceiling = expand_college_roots(
            db, actor.organization_id, delegation_roots(db, delegation), domain="academics",
        )
        if not ceiling.unrestricted:
            locations = [row for row in locations if row.id in ceiling.location_ids]
            departments = [row for row in departments if row.id in ceiling.department_ids]
            programs = [row for row in programs if row.id in ceiling.program_ids]
            cohorts = [row for row in cohorts if row.id in ceiling.cohort_ids]
            offerings = [row for row in offerings if row.id in ceiling.course_offering_ids]

    return {
        "policy_v2": True,
        "can_manage_delegations": actor_owner,
        "can_manage_role_templates": bool(
            organization and entitlement_value(db, organization, "access.custom_roles", False)
        ),
        "can_grant_ai": grantable_codes is None or "ai.use" in grantable_codes,
        "levels": list(ACCESS_LEVELS),
        "domains": [
            {**row, "maximum_level": grantable_levels[row["key"]]}
            for row in college_domain_catalog()
        ],
        "sensitive_capabilities": [
            {
                "code": code,
                "label": label,
                "grantable": grantable_codes is None or code in grantable_codes,
                "requires_domain": CAPABILITY_REQUIREMENTS.get(code, (None, None))[0],
                "requires_level": CAPABILITY_REQUIREMENTS.get(code, (None, None))[1],
                "requires_capabilities": ["college.fees.view"] if code == "college.fees.manage" else [],
                "requires_any_work_domains": (
                    ["students", "readiness", "placements"] if code == "notifications.send" else []
                ),
            }
            for code, label in SENSITIVE_CAPABILITIES.items()
        ],
        "scope_types": list(SCOPE_TYPES),
        "role_templates": [{
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "description": row.description,
            "is_system": row.is_system,
            "is_template": row.slug in template_slugs,
            "suggested_domain_levels": {
                domain: ACCESS_LEVELS[min(
                    ACCESS_LEVELS.index(COLLEGE_ROLE_LEVEL_SUGGESTIONS.get(row.slug, {}).get(
                        domain,
                        domain_level_from_permissions(codes_by_role.get(row.id, set()), domain),
                    )),
                    ACCESS_LEVELS.index(grantable_levels[domain]),
                )]
                for domain in COLLEGE_DOMAIN_LEVELS
            },
            "suggested_sensitive_capabilities": [
                code for code in SENSITIVE_CAPABILITIES if code in codes_by_role.get(row.id, set())
            ],
            "suggested_ai_enabled": (
                "ai.use" in codes_by_role.get(row.id, set())
                and (grantable_codes is None or "ai.use" in grantable_codes)
            ),
        } for row in roles],
        "hierarchy": {
            "locations": [{"id": row.id, "name": row.name, "code": row.code} for row in locations],
            "departments": [{
                "id": row.id, "name": row.name, "code": row.code, "location_id": row.location_id,
            } for row in departments],
            "programs": [{
                "id": row.id, "name": row.name, "code": row.code, "department_id": row.department_id,
            } for row in programs],
            "cohorts": [{
                "id": row.id, "name": row.name, "code": row.code, "program_id": row.program_id,
                "section": row.section, "graduation_year": row.graduation_year,
            } for row in cohorts],
            "course_offerings": [{
                "id": row.id, "cohort_id": row.cohort_id, "course_id": row.course_id,
                "name": f"{courses[row.course_id].code} - {courses[row.course_id].name}" if row.course_id in courses else "Course offering",
            } for row in offerings],
        },
    }


@router.post("/role-templates", status_code=201)
def create_guided_role_template(
    body: GuidedRoleTemplateBody,
    actor=Depends(require_permissions("roles.manage")),
    _plan=Depends(require_entitlements("access.custom_roles")),
    db: Session = Depends(get_db),
):
    """Create a College responsibility without exposing raw permission codes."""
    delegation = _college_access_admin(db, actor)
    unknown_domains = set(body.domain_levels) - set(COLLEGE_DOMAIN_LEVELS)
    if unknown_domains:
        raise HTTPException(422, "One or more College work areas are invalid")
    levels = _normalize_domain_levels(body.domain_levels)
    if not any(level != "none" for level in levels.values()):
        raise HTTPException(422, "Enable at least one work area for this responsibility")

    name = " ".join(body.name.split()).strip()
    if len(name) < 2:
        raise HTTPException(422, "Responsibility name must contain at least two characters")
    existing = db.execute(select(Role.id).where(
        Role.organization_id == actor.organization_id,
        func.lower(Role.name) == name.lower(),
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "A responsibility with this name already exists")

    source = None
    if body.source_role_id:
        source = db.get(Role, body.source_role_id)
        if not source or source.organization_id != actor.organization_id or not source.is_active:
            raise HTTPException(404, "Source responsibility not found")

    desired_codes = permission_codes_for_levels(levels)
    if body.ai_enabled:
        desired_codes.add("ai.use")
    if delegation:
        ceiling_levels = _normalize_domain_levels(dict(delegation.domain_levels or {}))
        if any(
            ACCESS_LEVELS.index(level) > ACCESS_LEVELS.index(ceiling_levels[domain])
            for domain, level in levels.items()
        ):
            raise HTTPException(403, "This responsibility exceeds your delegated work-area ceiling")
        ceiling_codes = grantable_permission_codes(db, actor) or set()
        if not desired_codes.issubset(ceiling_codes):
            raise HTTPException(403, "This responsibility exceeds your delegated capability ceiling")

    permissions = list(db.execute(select(Permission).where(
        Permission.code.in_(desired_codes),
        (Permission.organization_id.is_(None)) | (Permission.organization_id == actor.organization_id),
    )).scalars())
    if {permission.code for permission in permissions} != desired_codes:
        raise HTTPException(409, "The College permission catalogue is not ready for this responsibility")

    role = Role(
        organization_id=actor.organization_id,
        name=name,
        slug=_custom_role_slug(name),
        description=(body.description or "").strip() or (
            f"Customized from {source.name}" if source else "Institution-specific responsibility"
        ),
        is_system=False,
        is_active=True,
    )
    db.add(role)
    db.flush()
    for permission in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    log_action(
        db,
        organization_id=actor.organization_id,
        user_id=actor.id,
        action="access.role_template_created",
        resource_type="role",
        resource_id=role.id,
        permission="roles.manage",
        meta={
            "summary": f"Created responsibility {role.name}",
            "source_role_id": source.id if source else None,
            "enabled_domain_count": sum(level != "none" for level in levels.values()),
            "ai_enabled": body.ai_enabled,
        },
    )
    db.commit()
    return {
        "id": role.id,
        "name": role.name,
        "slug": role.slug,
        "description": role.description,
        "is_system": False,
        "is_template": False,
        "suggested_domain_levels": levels,
        "suggested_sensitive_capabilities": [],
        "suggested_ai_enabled": body.ai_enabled,
    }


@router.get("/users/{user_id}")
def get_access(user_id: str, actor=Depends(require_permissions("users.view")), db: Session = Depends(get_db)):
    _college_access_admin(db, actor)
    _require_legacy_access_mode(db, actor)
    target = target_user(db, actor, user_id); allowed = allowed_location_ids(db, target)
    locations = db.execute(select(Location).where(Location.organization_id == actor.organization_id, Location.is_active.is_(True))).scalars().all()
    return {
        "mode": "full" if allowed is None else "restricted", "location_ids": [x.id for x in locations] if allowed is None else sorted(allowed),
        "locations": [serialize(x) for x in locations if allowed is None or x.id in allowed],
        "roles": [{"id": x.id, "name": x.name, "slug": x.slug} for x in get_user_roles(db, target)],
        "permissions": sorted(get_user_permissions(db, target)),
    }


@router.put("/users/{user_id}")
def set_access(user_id: str, body: LocationAccessBody, actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    _college_access_admin(db, actor)
    _require_legacy_access_mode(db, actor)
    target = target_user(db, actor, user_id)
    if target.id == actor.id: raise HTTPException(409, "Another owner must change your own location boundary")
    valid = set(db.execute(select(Location.id).where(Location.organization_id == actor.organization_id, Location.id.in_(body.location_ids), Location.is_active.is_(True))).scalars())
    if valid != set(body.location_ids): raise HTTPException(422, "One or more locations are invalid")
    actor_allowed = allowed_location_ids(db, actor)
    if actor_allowed is not None and not valid.issubset(actor_allowed): raise HTTPException(403, "Cannot grant a location outside your own access")
    db.execute(delete(AccessScope).where(AccessScope.organization_id == actor.organization_id, AccessScope.user_id == target.id, AccessScope.scope_type == "location"))
    for location_id in valid:
        db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="location", scope_value=location_id, meta={}))
    target.access_version += 1
    log_action(db, organization_id=actor.organization_id, user_id=actor.id, action="access.location_scope_updated", resource_type="user", resource_id=target.id, permission="roles.manage", meta={"summary": f"Location access updated for {target.first_name} {target.last_name}".strip(), "location_count": len(valid)})
    db.commit(); return get_access(user_id, actor, db)


@router.get("/users/{user_id}/configuration")
def get_configuration(user_id: str, actor=Depends(require_permissions("users.view")), db: Session = Depends(get_db)):
    _college_access_admin(db, actor)
    _require_legacy_access_mode(db, actor)
    target = target_user(db, actor, user_id)
    roles = get_user_roles(db, target)
    overrides = db.execute(select(UserPermissionOverride).where(UserPermissionOverride.user_id == target.id)).scalars().all()
    location_ids = allowed_location_ids(db, target)
    client_ids = allowed_client_ids(db, target)
    mode = client_scope_mode(db, target)
    selected_client_ids = sorted(client_ids) if client_ids is not None and mode == "selected" else []
    selected_clients = db.execute(filter_clients(select(Client).where(
        Client.organization_id == actor.organization_id,
        Client.id.in_(selected_client_ids),
    ), db, actor)).scalars().all() if selected_client_ids else []
    return {
        "user": {"id": target.id, "first_name": target.first_name, "last_name": target.last_name, "email": target.email},
        "role_ids": [role.id for role in roles],
        "permission_overrides": [{"permission_id": row.permission_id, "granted": row.granted} for row in overrides],
        "location_mode": "full" if location_ids is None else "restricted",
        "location_ids": [] if location_ids is None else sorted(location_ids),
        "client_mode": mode,
        "client_ids": selected_client_ids,
        "selected_clients": [{
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "phone": row.phone,
            "client_number": row.client_number,
        } for row in selected_clients],
        "effective_permissions": sorted(get_user_permissions(db, target)),
        "version": target.access_version,
    }


@router.post("/users/{user_id}/preview")
def preview_configuration(user_id: str, body: UserAccessConfiguration, actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    _college_access_admin(db, actor)
    _require_legacy_access_mode(db, actor)
    target = target_user(db, actor, user_id)
    if target.id == actor.id:
        raise HTTPException(409, "Another owner must review changes to your own effective access")
    return _configuration_preview(db, actor, target, body)


@router.put("/users/{user_id}/configuration")
def save_configuration(user_id: str, body: UserAccessConfiguration, actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    _college_access_admin(db, actor)
    _require_legacy_access_mode(db, actor)
    target = target_user(db, actor, user_id)
    if target.id == actor.id:
        raise HTTPException(409, "Another owner must change your own effective access")
    if body.version is not None and body.version != target.access_version:
        raise HTTPException(409, "This person's access changed on another screen. Refresh before saving.")
    preview = _configuration_preview(db, actor, target, body)

    current_owner = is_owner(db, target)
    next_owner = any(role["is_system"] and role["slug"] == "owner" for role in preview["roles"])
    if current_owner and not next_owner:
        owner_role = db.execute(select(Role).where(
            Role.organization_id == actor.organization_id,
            Role.slug == "owner",
            Role.is_system.is_(True),
        )).scalar_one_or_none()
        owners = set(db.execute(select(UserRole.user_id).where(UserRole.role_id == owner_role.id)).scalars()) if owner_role else set()
        if len(owners) <= 1:
            raise HTTPException(409, "The final owner cannot be removed")

    db.query(UserRole).filter(UserRole.user_id == target.id).delete()
    for role_id in body.role_ids:
        db.add(UserRole(user_id=target.id, role_id=role_id))
    db.query(UserPermissionOverride).filter(UserPermissionOverride.user_id == target.id).delete()
    for item in body.permission_overrides:
        db.add(UserPermissionOverride(user_id=target.id, permission_id=item.permission_id, granted=item.granted))
    db.execute(delete(AccessScope).where(AccessScope.organization_id == actor.organization_id, AccessScope.user_id == target.id, AccessScope.scope_type.in_(["location", "location_mode", "client", "client_mode"])))
    db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="location_mode", scope_value=body.location_mode, meta={}))
    if body.location_mode == "restricted":
        for location_id in body.location_ids:
            db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="location", scope_value=location_id, meta={}))
    db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="client_mode", scope_value=body.client_mode, meta={}))
    if body.client_mode == "selected":
        for client_id in body.client_ids:
            db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="client", scope_value=client_id, meta={}))
    target.access_version += 1
    log_action(
        db,
        organization_id=actor.organization_id,
        user_id=actor.id,
        action="access.configuration_updated",
        resource_type="user",
        resource_id=target.id,
        permission="roles.manage",
        meta={
            "summary": f"Access updated for {target.first_name} {target.last_name}".strip(),
            "role_count": len(body.role_ids),
            "permission_count": len(preview["effective_permissions"]),
            "location_mode": body.location_mode,
            "client_mode": body.client_mode,
        },
    )
    db.commit()
    return get_configuration(user_id, actor, db)


@router.get("/users/{user_id}/policy")
def get_enterprise_policy(
    user_id: str,
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    _college_access_admin(db, actor)
    target = target_user(db, actor, user_id)
    return _policy_payload(db, target)


@router.get("/users/{user_id}/effective")
def get_effective_policy(
    user_id: str,
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    _college_access_admin(db, actor)
    target = target_user(db, actor, user_id)
    context = resolve_policy_context(db, target)
    payload = _policy_payload(db, target)
    maximum = context.maximum_scope
    payload.update({
        "effective": policy_summary(context),
        "visibility": {
            "whole_institution": maximum.unrestricted,
            "departments": None if maximum.unrestricted else len(maximum.department_ids),
            "programs": None if maximum.unrestricted else len(maximum.program_ids),
            "cohorts": None if maximum.unrestricted else len(maximum.cohort_ids),
            "students": None if maximum.unrestricted else len(maximum.student_ids),
        },
    })
    return payload


@router.post("/users/{user_id}/policy/preview")
def preview_enterprise_policy(
    user_id: str,
    body: EnterprisePolicyBody,
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    target = target_user(db, actor, user_id)
    preview = _validate_policy_body(db, actor, target, body)
    visibility = preview["visibility"]
    return {
        "valid": True,
        "roles": [
            {"id": role.id, "name": role.name, "slug": role.slug}
            for role in preview["roles"]
        ],
        "domain_levels": body.domain_levels,
        "sensitive_capabilities": body.sensitive_capabilities,
        "ai_enabled": body.ai_enabled,
        "visibility": {
            "whole_institution": visibility.unrestricted,
            "department_count": None if visibility.unrestricted else len(visibility.department_ids),
            "program_count": None if visibility.unrestricted else len(visibility.program_ids),
            "cohort_count": None if visibility.unrestricted else len(visibility.cohort_ids),
            "student_count": None if visibility.unrestricted else len(visibility.student_ids),
        },
        "summary": _plain_access_summary(
            body, visibility, [role.name for role in preview["roles"]],
        ),
        "warnings": preview["warnings"],
    }


@router.put("/users/{user_id}/policy")
def save_enterprise_policy(
    user_id: str,
    body: EnterprisePolicyBody,
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    target = target_user(db, actor, user_id)
    preview = _validate_policy_body(db, actor, target, body)
    policy = ensure_policy(db, target, creator_id=actor.id)
    if body.version is not None and body.version != policy.version:
        raise HTTPException(409, "This access policy changed elsewhere. Refresh before saving.")

    current_owner = is_owner(db, target)
    next_owner = any(role.is_system and role.slug == "owner" for role in preview["roles"])
    if current_owner and not next_owner:
        owner_role = db.execute(select(Role).where(
            Role.organization_id == actor.organization_id,
            Role.slug == "owner",
            Role.is_system.is_(True),
        )).scalar_one_or_none()
        owner_count = db.scalar(select(func.count(UserRole.user_id)).where(
            UserRole.role_id == owner_role.id,
        )) if owner_role else 0
        if int(owner_count or 0) <= 1:
            raise HTTPException(409, "The final owner cannot be removed")

    db.query(UserRole).filter(UserRole.user_id == target.id).delete()
    for role in preview["roles"]:
        db.add(UserRole(user_id=target.id, role_id=role.id))

    managed_permissions = list(db.execute(select(Permission).where(
        Permission.code.in_(POLICY_MANAGED_PERMISSION_CODES),
    )).scalars())
    managed_ids = {row.id for row in managed_permissions}
    if managed_ids:
        db.query(UserPermissionOverride).filter(
            UserPermissionOverride.user_id == target.id,
            UserPermissionOverride.permission_id.in_(managed_ids),
        ).delete(synchronize_session=False)
    role_codes = preview["role_codes"]
    desired = preview["desired_managed"]
    for permission in managed_permissions:
        inherited = permission.code in role_codes
        requested = permission.code in desired
        if inherited != requested:
            db.add(UserPermissionOverride(
                user_id=target.id,
                permission_id=permission.id,
                granted=requested,
            ))

    db.query(AccessPolicyScope).filter(AccessPolicyScope.policy_id == policy.id).delete()
    for root in preview["maximum_roots"]:
        db.add(AccessPolicyScope(
            organization_id=actor.organization_id, policy_id=policy.id, domain_key="*",
            scope_type=root.scope_type, scope_value=root.scope_value,
        ))
    for domain, roots in preview["domain_roots"].items():
        for root in roots:
            db.add(AccessPolicyScope(
                organization_id=actor.organization_id, policy_id=policy.id, domain_key=domain,
                scope_type=root.scope_type, scope_value=root.scope_value,
            ))

    # Compatibility projection for legacy modules while College moves to the
    # centralized evaluator.
    db.execute(delete(AccessScope).where(
        AccessScope.organization_id == actor.organization_id,
        AccessScope.user_id == target.id,
        AccessScope.scope_type.like("college.%"),
    ))
    for root in preview["maximum_roots"]:
        if root.scope_type != "organization":
            db.add(AccessScope(
                organization_id=actor.organization_id, user_id=target.id,
                scope_type=f"college.{root.scope_type}", scope_value=root.scope_value,
                meta={"source": "access_policy_v2"},
            ))

    now = datetime.now(timezone.utc)
    policy.status = "active"
    policy.domain_levels = {
        domain: body.domain_levels.get(domain, "none")
        for domain in COLLEGE_DOMAIN_LEVELS
    }
    policy.expires_at = body.expires_at
    policy.reviewed_by_user_id = actor.id
    policy.reviewed_at = now
    policy.review_note = body.review_note
    policy.version += 1
    target.access_version += 1
    db.flush()
    log_action(
        db,
        organization_id=actor.organization_id,
        user_id=actor.id,
        action="access.policy_activated",
        resource_type="user",
        resource_id=target.id,
        permission="roles.manage",
        meta={
            "summary": f"Access policy reviewed for {target.first_name} {target.last_name}".strip(),
            "policy_version": policy.version,
            "role_count": len(body.role_ids),
            "scope_root_count": len(body.maximum_reach),
            "expires": bool(body.expires_at),
        },
    )
    db.commit()
    return _policy_payload(db, target)


@router.get("/delegations/{user_id}")
def get_delegation(
    user_id: str,
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    if not is_owner(db, actor):
        raise HTTPException(403, "Only an owner can review Access Admin delegation")
    target = target_user(db, actor, user_id)
    row = db.execute(select(AccessDelegation).where(
        AccessDelegation.organization_id == actor.organization_id,
        AccessDelegation.user_id == target.id,
    )).scalar_one_or_none()
    if not row:
        return {"active": False, "version": 0, "maximum_reach": [], "domain_levels": {}, "sensitive_capabilities": []}
    return {
        "active": row.active,
        "version": row.version,
        "expires_at": row.expires_at,
        "domain_levels": row.domain_levels or {},
        "sensitive_capabilities": row.sensitive_capabilities or [],
        "maximum_reach": _scope_payload(delegation_roots(db, row)),
    }


@router.put("/delegations/{user_id}")
def save_delegation(
    user_id: str,
    body: DelegationBody,
    actor=Depends(require_permissions("access.delegations.manage")),
    db: Session = Depends(get_db),
):
    if not is_owner(db, actor):
        raise HTTPException(403, "Only an owner can delegate access administration")
    target = target_user(db, actor, user_id)
    if target.id == actor.id or is_owner(db, target):
        raise HTTPException(409, "Owner access cannot be delegated or edited here")
    target_roles = {role.slug for role in get_user_roles(db, target) if role.is_system}
    if body.active and "access-admin" not in target_roles:
        raise HTTPException(422, "Assign the Access Admin responsibility before activating a delegation ceiling")
    if set(body.domain_levels) - set(COLLEGE_DOMAIN_LEVELS):
        raise HTTPException(422, "One or more delegation domains are invalid")
    allowed_sensitive = set(SENSITIVE_CAPABILITIES) | {"ai.use"}
    if set(body.sensitive_capabilities) - allowed_sensitive:
        raise HTTPException(422, "One or more delegated capabilities are invalid")
    if len(body.sensitive_capabilities) != len(set(body.sensitive_capabilities)):
        raise HTTPException(422, "Each delegated capability may only be selected once")
    normalized_levels = _normalize_domain_levels(body.domain_levels)
    has_grantable_domain = any(level != "none" for level in normalized_levels.values())
    if body.active and not has_grantable_domain:
        raise HTTPException(422, "Enable at least one grantable College work area")
    if "ai.use" in body.sensitive_capabilities and not has_grantable_domain:
        raise HTTPException(422, "Edvatiq AI needs at least one grantable College work area")
    _validate_capability_dependencies(
        normalized_levels,
        set(body.sensitive_capabilities).intersection(SENSITIVE_CAPABILITIES),
    )
    if utc_datetime(body.expires_at) and utc_datetime(body.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(422, "Delegation expiry must be in the future")
    roots = validate_scope_roots(db, actor.organization_id, _roots(body.maximum_reach))
    _validate_locations(db, actor.organization_id, roots)
    if any(root.scope_type == "organization" for root in roots) and len(roots) != 1:
        raise HTTPException(422, "Whole-institution reach cannot be combined with narrower roots")

    row = db.execute(select(AccessDelegation).where(
        AccessDelegation.organization_id == actor.organization_id,
        AccessDelegation.user_id == target.id,
    )).scalar_one_or_none()
    if row and body.version is not None and body.version != row.version:
        raise HTTPException(409, "This delegation changed elsewhere. Refresh before saving.")
    if not row:
        row = AccessDelegation(
            organization_id=actor.organization_id, user_id=target.id,
            created_by_user_id=actor.id,
        )
        db.add(row); db.flush()
    row.active = body.active
    row.domain_levels = normalized_levels
    row.sensitive_capabilities = sorted(set(body.sensitive_capabilities))
    row.expires_at = body.expires_at
    row.version += 1
    db.query(AccessDelegationScope).filter(AccessDelegationScope.delegation_id == row.id).delete()
    for root in roots:
        db.add(AccessDelegationScope(
            organization_id=actor.organization_id, delegation_id=row.id,
            scope_type=root.scope_type, scope_value=root.scope_value,
        ))

    access_admin_role = db.execute(select(Role).where(
        Role.organization_id == actor.organization_id,
        Role.slug == "access-admin",
        Role.is_system.is_(True),
    )).scalar_one_or_none()
    if body.active and access_admin_role and not db.execute(select(UserRole.id).where(
        UserRole.user_id == target.id, UserRole.role_id == access_admin_role.id,
    )).first():
        db.add(UserRole(user_id=target.id, role_id=access_admin_role.id))
    if not body.active and access_admin_role:
        db.query(UserRole).filter(
            UserRole.user_id == target.id, UserRole.role_id == access_admin_role.id,
        ).delete()
    target.access_version += 1
    log_action(
        db,
        organization_id=actor.organization_id,
        user_id=actor.id,
        action="access.delegation_updated",
        resource_type="user",
        resource_id=target.id,
        permission="access.delegations.manage",
        meta={
            "summary": f"Access Admin delegation {'enabled' if body.active else 'disabled'} for {target.first_name} {target.last_name}".strip(),
            "scope_root_count": len(roots),
            "expires": bool(body.expires_at),
        },
    )
    db.commit()
    return get_delegation(user_id, actor, db)
