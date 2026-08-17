"""Permission-derived tool capabilities exposed to the V3 planner."""
from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.actions import ACTION_REGISTRY
from app.ai.tools import TOOL_SCHEMAS
from app.ai.v3_cache import CAPABILITY_CACHE
from app.models import Organization, User
from app.services.access_policy import policy_v2_enabled, resolve_policy_context
from app.services.rbac import get_user_permissions


READ_TOOLS = {
    "business_summary", "business_records", "business_analytics", "search_knowledge",
    "client_workspace", "resolve_records", "entity_workspace", "college_academic_structure",
    "college_students", "college_student_intelligence", "college_placement_dashboard",
    "college_opportunity_candidates",
}

RECORD_SUBJECT_PERMISSIONS = {
    "clients": ("clients.view",),
    "students": ("college.students.view",),
    "employees": ("employees.view",),
    "appointments": ("appointments.view",),
    "sales": ("sales.view",),
    "purchases": ("sales.view",),
    "catalog": ("catalog.view",),
    "inventory": ("inventory.view",),
    "memberships": ("gym.memberships.view",),
    "checkins": ("gym.attendance.view",),
    "clinic_queue": ("appointments.view", "clinical.view"),
    "patients": ("clinical.view",),
}

ANALYTIC_METRIC_PERMISSIONS = {
    "revenue": ("sales.view",),
    "appointments": ("appointments.view",),
    "clients": ("clients.view",),
    "memberships": ("gym.memberships.view",),
    "checkins": ("gym.attendance.view",),
    "top_products": ("sales.view",),
    "sales_by_category": ("sales.view",),
}

SUBJECT_ENTITY_KINDS = {
    "clients": {"client"},
    "students": {"client"},
    "employees": {"employee"},
    "appointments": {"appointment", "client"},
    "sales": {"invoice", "payment", "client"},
    "purchases": {"invoice", "catalog", "client"},
    "catalog": {"catalog"},
    "inventory": {"catalog", "inventory"},
    "memberships": {"membership", "membership_plan", "client"},
    "checkins": {"checkin", "client"},
    "clinic_queue": {"appointment", "patient", "client"},
    "patients": {"patient", "encounter", "prescription", "lab_order", "client"},
}


class CapabilitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str
    user_id: str
    industry: str
    access_version: int
    policy_version: int = 0
    tool_names: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    sensitive_fields: list[str] = Field(default_factory=list)
    record_subjects: list[str] = Field(default_factory=list)
    record_entity_kinds: list[str] = Field(default_factory=list)
    analytic_metrics: list[str] = Field(default_factory=list)
    action_names: list[str] = Field(default_factory=list)


def _has_any(permissions: set[str], *values: str) -> bool:
    return any(value in permissions for value in values)


def capability_snapshot(db: Session, user: User) -> CapabilitySnapshot:
    organization = db.get(Organization, user.organization_id)
    industry = getattr(getattr(organization, "industry", None), "value", None) or "business"
    policy_version = 0
    sensitive_fields: list[str] = []
    if industry == "college" and policy_v2_enabled(db, user.organization_id):
        policy = resolve_policy_context(db, user)
        policy_version = policy.policy_version
        sensitive_fields = sorted(
            permission for permission in policy.permissions
            if permission.startswith("college.") and any(marker in permission for marker in (
                ".contact.", ".guardian.", ".private.", ".sensitive.", ".protected_", ".fees.",
            ))
        )
    key = (str(user.organization_id), str(user.id), int(user.access_version), policy_version, industry)
    cached = CAPABILITY_CACHE.get(key)
    if cached is not None:
        return cached

    permissions = set(get_user_permissions(db, user))
    tools: set[str] = set()
    domains: set[str] = set()
    record_subjects = {
        subject for subject, required in RECORD_SUBJECT_PERMISSIONS.items()
        if _has_any(permissions, *required)
    }
    analytic_metrics = {
        metric for metric, required in ANALYTIC_METRIC_PERMISSIONS.items()
        if _has_any(permissions, *required)
    } if _has_any(permissions, "reports.view") else set()
    action_names = {
        name for name, definition in ACTION_REGISTRY.items()
        if definition.permission in permissions
    } if "ai.actions" in permissions else set()
    record_entity_kinds = {
        kind
        for subject in record_subjects
        for kind in SUBJECT_ENTITY_KINDS.get(subject, set())
    }

    if record_subjects:
        tools.update({"resolve_records", "entity_workspace"})
    if _has_any(permissions, "dashboard.view"):
        tools.add("business_summary")
        domains.add("operations")
    if record_subjects:
        tools.add("business_records")
        domains.add("records")
    if analytic_metrics:
        tools.add("business_analytics")
        domains.add("analytics")
    if "documents.view" in permissions:
        tools.add("search_knowledge")
        domains.add("knowledge")
    if "clients.view" in permissions:
        tools.add("client_workspace")
    if action_names:
        tools.add("prepare_action")
        domains.add("actions")

    if industry == "college":
        if _has_any(permissions, "college.academics.view", "college.students.view"):
            tools.add("college_academic_structure")
            domains.add("academics")
        if "college.students.view" in permissions:
            tools.add("college_students")
            domains.add("students")
        if _has_any(
            permissions, "college.students.view", "college.readiness.view", "college.coding.view",
            "college.assessments.view", "college.attendance.view", "college.placements.view",
        ):
            tools.add("college_student_intelligence")
            domains.add("student_intelligence")
        if _has_any(permissions, "college.readiness.view", "college.placements.view", "college.placement_reports.view"):
            tools.add("college_placement_dashboard")
            domains.add("placements")
        if _has_any(permissions, "college.placements.view", "college.readiness.view"):
            tools.add("college_opportunity_candidates")

    available = {schema["name"] for schema in TOOL_SCHEMAS}
    snapshot = CapabilitySnapshot(
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        industry=industry,
        access_version=int(user.access_version),
        policy_version=policy_version,
        tool_names=sorted(tools & available),
        domains=sorted(domains),
        sensitive_fields=sensitive_fields,
        record_subjects=sorted(record_subjects),
        record_entity_kinds=sorted(record_entity_kinds),
        analytic_metrics=sorted(analytic_metrics),
        action_names=sorted(action_names),
    )
    return CAPABILITY_CACHE.set(key, snapshot)


def planner_tool_schemas(snapshot: CapabilitySnapshot) -> list[dict]:
    allowed = set(snapshot.tool_names)
    schemas = [deepcopy(schema) for schema in TOOL_SCHEMAS if schema.get("name") in allowed]
    for schema in schemas:
        properties = schema.get("parameters", {}).get("properties", {})
        if schema.get("name") == "business_records":
            properties.get("subject", {})["enum"] = snapshot.record_subjects
        elif schema.get("name") == "resolve_records":
            properties.get("kinds", {}).get("items", {})["enum"] = snapshot.record_entity_kinds
        elif schema.get("name") == "entity_workspace":
            properties.get("kind", {})["enum"] = snapshot.record_entity_kinds
        elif schema.get("name") == "business_analytics":
            properties.get("metric", {})["enum"] = snapshot.analytic_metrics
        elif schema.get("name") == "prepare_action":
            properties.get("action_type", {})["enum"] = snapshot.action_names
    return schemas


def is_read_only_tool(name: str) -> bool:
    return name in READ_TOOLS
