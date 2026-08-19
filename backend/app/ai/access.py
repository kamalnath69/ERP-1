"""Authorization envelope shared by compilation, execution, and serialization."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.catalog import FieldDefinition, MetricDefinition, SemanticCatalog
from app.ai.contracts import AssistantOutcome, ResolvedScope, SemanticQuery
from app.models import Organization, User
from app.services.access_policy import COLLEGE_DOMAIN_LEVELS, resolve_policy_context
from app.services.business_access import allowed_client_ids, allowed_location_ids
from app.services.entitlements import resolve_entitlements
from app.services.rbac import get_user_permissions, is_system_owner


class AccessViolation(PermissionError):
    def __init__(self, outcome: AssistantOutcome, message: str, *, missing: Iterable[str] = ()):
        super().__init__(message)
        self.outcome = outcome
        self.message = message
        self.missing = tuple(sorted(set(missing)))


@dataclass(frozen=True)
class AccessEnvelope:
    organization_id: str
    user_id: str
    industry: str
    enabled_modules: frozenset[str]
    permissions: frozenset[str]
    owner: bool
    modules_configured: bool = True
    policy_version: int = 0
    domain_levels: dict[str, str] = field(default_factory=dict)
    domain_scopes: dict[str, object] = field(default_factory=dict)
    location_ids: frozenset[str] | None = None
    client_ids: frozenset[str] | None = None

    def has_permissions(self, permissions: Iterable[str]) -> bool:
        return set(permissions).issubset(self.permissions)

    def module_enabled(self, module: str) -> bool:
        if not self.modules_configured:
            return module in {"ai", "clients", "appointments", "sales", self.industry}
        return module in self.enabled_modules

    def domain_available(self, domain: str) -> bool:
        return self.industry != "college" or self.domain_levels.get(domain, "none") != "none"

    def field_available(self, definition: FieldDefinition) -> bool:
        if not self.has_permissions(definition.permissions):
            return False
        if definition.sensitive_permission and definition.sensitive_permission not in self.permissions:
            return False
        return all(self.domain_available(domain) for domain in definition.domains)

    def metric_available(self, definition: MetricDefinition) -> bool:
        return self.has_permissions(definition.permissions) and all(
            self.domain_available(domain) for domain in definition.domains
        )

    def require_query(self, catalog: SemanticCatalog, query: SemanticQuery) -> None:
        entity = catalog.entity(query.entity)
        if not self.module_enabled(entity.module):
            raise AccessViolation(
                AssistantOutcome.ENTITLEMENT_REQUIRED,
                f"{entity.label} is not enabled for your organization.",
                missing=(entity.module,),
            )
        if entity.permission not in self.permissions:
            raise AccessViolation(
                AssistantOutcome.ACCESS_LIMITED,
                f"{entity.label} is not included in your current access.",
                missing=(entity.permission,),
            )
        if entity.domain and not self.domain_available(entity.domain):
            raise AccessViolation(
                AssistantOutcome.ACCESS_LIMITED,
                f"{entity.label} is not included in your current College work areas.",
                missing=(entity.domain,),
            )

        # Projection fields can be omitted later. Any unavailable input to an
        # analytical operation must reject that operation to avoid inference.
        analytical_fields = {
            item.field for item in query.filters
        } | {item.field for item in query.sort} | set(query.group_by)
        unavailable = [
            key for key in analytical_fields
            if not self.field_available(catalog.field(query.entity, key))
        ]
        unavailable_metrics = [
            key for key in query.metrics
            if not self.metric_available(catalog.metric(key))
        ]
        if unavailable or unavailable_metrics:
            raise AccessViolation(
                AssistantOutcome.ACCESS_LIMITED,
                "This analysis needs a work area or sensitive capability that is not in your access.",
                missing=(*unavailable, *unavailable_metrics),
            )

    def projectable_fields(self, catalog: SemanticCatalog, query: SemanticQuery) -> tuple[list[str], list[str]]:
        requested = query.fields or ["id", "name"]
        allowed, unavailable = [], []
        for key in requested:
            if self.field_available(catalog.field(query.entity, key)):
                allowed.append(key)
            else:
                unavailable.append(key)
        return allowed, unavailable

    def student_scope(self, domains: Iterable[str]) -> set[str] | None:
        """Intersect every participating College domain before querying."""
        if self.industry != "college" or self.owner:
            return None
        constrained: list[set[str]] = []
        for domain in dict.fromkeys(("students", *domains)):
            if not self.domain_available(domain):
                raise AccessViolation(
                    AssistantOutcome.ACCESS_LIMITED,
                    f"The {domain} work area is not included in your access.",
                    missing=(domain,),
                )
            scope = self.domain_scopes.get(domain)
            if scope is not None and not getattr(scope, "unrestricted", False):
                constrained.append(set(getattr(scope, "student_ids", frozenset())))
        if not constrained:
            return None
        result = constrained[0]
        for values in constrained[1:]:
            result &= values
        return result

    def allows_student(self, student_id: str, domains: Iterable[str]) -> bool:
        allowed = self.student_scope(domains)
        return allowed is None or student_id in allowed

    def scope_label(self, population_size: int | None = None) -> str:
        if self.owner:
            return "your organization"
        if population_size is not None:
            return f"your {population_size} authorized records"
        return "your authorized scope"

    def public_scope(self) -> ResolvedScope:
        labels = {
            "locations": "all" if self.location_ids is None else len(self.location_ids),
            "clients": "all" if self.client_ids is None else len(self.client_ids),
        }
        return ResolvedScope(
            organization_id=self.organization_id,
            user_id=self.user_id,
            industry=self.industry,
            owner=self.owner,
            policy_version=self.policy_version,
            permission_codes=sorted(self.permissions),
            domain_levels=dict(self.domain_levels),
            scope_labels=labels,
        )


def resolve_access_envelope(db: Session, user: User, *, fresh: bool = False) -> AccessEnvelope:
    cache = db.info.setdefault("edvatiq.access_envelopes", {})
    cache_key = (str(user.id), int(user.access_version or 0))
    if not fresh and cache_key in cache:
        return cache[cache_key]
    if not user.organization_id:
        raise AccessViolation(AssistantOutcome.ACCESS_LIMITED, "Organization access is required.")
    if fresh:
        organization = db.execute(select(Organization).where(
            Organization.id == user.organization_id,
        ).execution_options(populate_existing=True)).scalar_one_or_none()
    else:
        organization = db.get(Organization, user.organization_id)
    if not organization or getattr(organization.status, "value", organization.status) in {"suspended", "cancelled"}:
        raise AccessViolation(AssistantOutcome.ACCESS_LIMITED, "Your organization is not active.")

    industry = getattr(organization.industry, "value", organization.industry)
    owner = is_system_owner(db, user)
    permissions = frozenset(get_user_permissions(db, user))
    domain_levels: dict[str, str] = {}
    domain_scopes: dict[str, object] = {}
    policy_version = 0
    if industry == "college":
        context = resolve_policy_context(db, user)
        policy_version = context.policy_version
        domain_levels = {
            domain: context.level(domain) for domain in COLLEGE_DOMAIN_LEVELS
        }
        domain_scopes = {
            domain: context.scope(domain) for domain in COLLEGE_DOMAIN_LEVELS
        }

    locations = allowed_location_ids(db, user)
    clients = allowed_client_ids(db, user)
    provisioned_modules = {str(item) for item in (organization.enabled_modules or [])}
    entitlement_values = resolve_entitlements(db, organization)["values"]
    enabled_modules = {
        module for module in provisioned_modules
        if bool(entitlement_values.get(f"module.{module}", True))
    }
    envelope = AccessEnvelope(
        organization_id=user.organization_id,
        user_id=user.id,
        industry=industry,
        enabled_modules=frozenset(enabled_modules),
        permissions=permissions,
        owner=owner,
        modules_configured=bool(provisioned_modules),
        policy_version=policy_version,
        domain_levels=domain_levels,
        domain_scopes=domain_scopes,
        location_ids=None if locations is None else frozenset(locations),
        client_ids=None if clients is None else frozenset(clients),
    )
    cache[cache_key] = envelope
    return envelope
