"""Central plan and organization entitlement resolution."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FeatureDefinition, Organization, OrganizationEntitlementOverride, PlanDefinition,
    PlanEntitlement, PlanVersion, Subscription,
)
from app.services.subscriptions import effective_subscription_status


def _value(payload: dict | None):
    return (payload or {}).get("value")


def active_plan_version(db: Session, organization: Organization) -> tuple[Subscription | None, PlanVersion | None, PlanDefinition | None]:
    subscription = db.execute(
        select(Subscription).where(Subscription.organization_id == organization.id).order_by(Subscription.created_at.desc())
    ).scalars().first()
    version = db.get(PlanVersion, subscription.plan_version_id) if subscription and subscription.plan_version_id else None
    definition = db.get(PlanDefinition, version.plan_id) if version else None
    if not version:
        slug = subscription.plan if subscription else getattr(organization.plan, "value", organization.plan)
        pair = db.execute(
            select(PlanVersion, PlanDefinition).join(PlanDefinition, PlanDefinition.id == PlanVersion.plan_id)
            .where(PlanDefinition.slug == slug, PlanVersion.status == "published")
            .order_by(PlanVersion.version.desc())
        ).first()
        if pair:
            version, definition = pair
    return subscription, version, definition


def resolve_entitlements(db: Session, organization: Organization) -> dict:
    subscription, version, definition = active_plan_version(db, organization)
    plan_slug = definition.slug if definition else getattr(organization.plan, "value", organization.plan)
    values = {}

    if version:
        rows = db.execute(
            select(FeatureDefinition.code, PlanEntitlement.value)
            .join(PlanEntitlement, PlanEntitlement.feature_id == FeatureDefinition.id)
            .where(PlanEntitlement.plan_version_id == version.id, FeatureDefinition.is_active.is_(True))
        ).all()
        values.update({code: _value(value) for code, value in rows})
        values["ai.tier"] = version.ai_tier
        values["ai.included_credits"] = version.included_ai_credits

    now = datetime.now(timezone.utc)
    overrides = db.execute(
        select(FeatureDefinition.code, OrganizationEntitlementOverride.value)
        .join(FeatureDefinition, FeatureDefinition.id == OrganizationEntitlementOverride.feature_id)
        .where(
            OrganizationEntitlementOverride.organization_id == organization.id,
            OrganizationEntitlementOverride.is_active.is_(True),
            OrganizationEntitlementOverride.approved_by_user_id.is_not(None),
            OrganizationEntitlementOverride.starts_at <= now,
            OrganizationEntitlementOverride.ends_at > now,
        )
    ).all()
    values.update({code: _value(value) for code, value in overrides})
    return {
        "plan": {
            "slug": plan_slug,
            "name": definition.name if definition else str(plan_slug).title(),
            "version_id": version.id if version else None,
            "version": version.version if version else None,
            "status": version.status if version else "legacy",
            "billing_interval": subscription.billing_interval if subscription else "monthly",
            "subscription_status": effective_subscription_status(subscription),
            "trial_end": subscription.trial_end if subscription else None,
            "current_period_end": subscription.current_period_end if subscription else None,
        },
        "values": values,
    }


def entitlement_value(db: Session, organization: Organization, code: str, default=None):
    return resolve_entitlements(db, organization)["values"].get(code, default)


def module_enabled(db: Session, organization: Organization, module: str) -> bool:
    value = entitlement_value(db, organization, f"module.{module}")
    if value is None:
        return module in (organization.enabled_modules or [])
    return bool(value)
