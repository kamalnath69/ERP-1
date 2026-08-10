"""Typed organization settings with capability-aware serialization."""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuditLog, IndustryMigrationRequest, Location, Organization, User
from app.services.audit import log_action
from app.services.business_access import allowed_location_ids, organization_for
from app.services.entitlements import resolve_entitlements
from app.services.rbac import get_user_permissions


OPERATING_DEFAULTS = {
    "gym": {
        "attendance_edit_window_minutes": 60,
        "allow_checkin_without_membership": False,
        "class_booking_window_days": 30,
        "default_freeze_limit_days": 30,
    },
    "salon": {
        "allow_walk_ins": True,
        "default_buffer_minutes": 10,
        "default_visit_interval_days": 45,
        "require_checkout_before_completion": True,
    },
    "clinic": {
        "queue_mode": "token",
        "require_encounter_signature": True,
        "allow_reception_vitals": False,
        "default_follow_up_days": 7,
    },
}


def _merged(defaults: dict, value: dict | None) -> dict:
    return {**defaults, **(value or {})}


def _organization_view(organization: Organization) -> dict:
    return {
        "id": organization.id,
        "name": organization.name,
        "legal_name": organization.legal_name,
        "slug": organization.slug,
        "industry": organization.industry.value,
        "timezone": organization.timezone,
        "currency": organization.currency,
        "gstin": organization.gstin,
        "invoice_prefix": organization.invoice_prefix,
        "contact_email": organization.contact_email,
        "contact_phone": organization.contact_phone,
        "description": organization.description,
        "settings_version": organization.settings_version,
    }


def settings_workspace(db: Session, user: User) -> dict:
    organization = organization_for(db, user)
    permissions = get_user_permissions(db, user)
    locations_statement = select(Location).where(
        Location.organization_id == organization.id,
        Location.is_active.is_(True),
    )
    allowed = allowed_location_ids(db, user)
    if allowed is not None:
        locations_statement = locations_statement.where(Location.id.in_(allowed))
    locations = db.execute(locations_statement.order_by(Location.is_primary.desc(), Location.name)).scalars().all()
    audit = []
    if "settings.audit.view" in permissions or "audit.view" in permissions:
        rows = db.execute(select(AuditLog, User).outerjoin(User, User.id == AuditLog.user_id).where(
            AuditLog.organization_id == organization.id,
            or_(
                AuditLog.action.like("settings.%"),
                AuditLog.action.in_(["organization.update", "location.create", "location.update"]),
            ),
        ).order_by(AuditLog.created_at.desc()).limit(100)).all()
        audit = [{
            "id": event.id,
            "action": event.action,
            "resource_type": event.resource_type,
            "created_at": event.created_at,
            "actor": f"{actor.first_name} {actor.last_name}".strip() if actor else "System",
        } for event, actor in rows]
    entitlements = resolve_entitlements(db, organization)
    return {
        "organization": _organization_view(organization),
        "locations": [{
            "id": location.id, "name": location.name, "code": location.code,
            "address": location.address, "city": location.city, "state": location.state,
            "postal_code": location.postal_code, "phone": location.phone,
            "gstin": location.gstin, "is_primary": location.is_primary,
            "version": location.version,
        } for location in locations],
        "tax": _merged({"prices_include_tax": False, "default_tax_rate_bps": 0}, organization.tax_settings),
        "operations": _merged(OPERATING_DEFAULTS.get(organization.industry.value, {}), organization.operating_settings),
        "communications": _merged({"appointment_reminders": True, "payment_reminders": True}, organization.communication_settings),
        "security": _merged({"mfa_policy": "optional"}, organization.security_settings),
        "privacy": _merged({"conversation_retention_days": 90}, organization.privacy_settings),
        "modules": sorted(code.removeprefix("module.") for code, enabled in entitlements["values"].items() if code.startswith("module.") and enabled),
        "integrations": {
            "security_email": {"ready": bool(settings.RESEND_API_KEY) if settings.EMAIL_PROVIDER == "resend" else True},
            "whatsapp": {"ready": bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID), "reminders_enabled": settings.WHATSAPP_REMINDERS_ENABLED},
            "payments": {"managed_by_platform": True},
            "storage": {"managed_by_platform": True},
            "ai": {"managed_by_platform": True},
        },
        "pending_industry_request": _pending_industry_request(db, organization.id),
        "audit": audit,
        "capabilities": {
            "identity_manage": bool(permissions.intersection({"settings.manage", "settings.identity.manage"})),
            "locations_manage": bool(permissions.intersection({"settings.manage", "settings.locations.manage"})),
            "tax_manage": bool(permissions.intersection({"settings.manage", "settings.tax.manage"})),
            "operations_manage": bool(permissions.intersection({"settings.manage", "settings.operations.manage"})),
            "communications_manage": bool(permissions.intersection({"settings.manage", "settings.communication.manage"})),
            "security_manage": bool(permissions.intersection({"settings.manage", "settings.security.manage"})),
            "privacy_manage": bool(permissions.intersection({"settings.manage", "settings.privacy.manage"})),
            "audit_view": bool(permissions.intersection({"settings.audit.view", "audit.view"})),
        },
        "source_timestamp": datetime.now(timezone.utc),
    }


def _pending_industry_request(db: Session, organization_id: str) -> dict | None:
    row = db.execute(select(IndustryMigrationRequest).where(
        IndustryMigrationRequest.organization_id == organization_id,
        IndustryMigrationRequest.status == "pending",
    ).order_by(IndustryMigrationRequest.created_at.desc())).scalars().first()
    if not row:
        return None
    return {
        "id": row.id, "requested_industry": row.requested_industry,
        "reason": row.reason, "status": row.status, "created_at": row.created_at,
    }


def update_section(db: Session, user: User, section: str, values: dict, expected_version: int) -> dict:
    organization = organization_for(db, user)
    if organization.settings_version != expected_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Business settings changed on another device")
    if section == "identity":
        for key in ("name", "legal_name", "gstin", "timezone", "contact_email", "contact_phone", "description", "invoice_prefix"):
            if key in values:
                setattr(organization, key, values[key])
    elif section == "tax":
        organization.tax_settings = values
    elif section == "operations":
        organization.operating_settings = values
    elif section == "communications":
        organization.communication_settings = values
    elif section == "security":
        organization.security_settings = values
    elif section == "privacy":
        organization.privacy_settings = values
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown settings area")
    organization.settings_version += 1
    log_action(
        db, organization_id=organization.id, user_id=user.id,
        action=f"settings.{section}.updated", resource_type="organization",
        resource_id=organization.id, changes={"fields": sorted(values)},
    )
    db.commit()
    return {"section": section, "value": values, "settings_version": organization.settings_version}


def request_industry_migration(db: Session, user: User, requested_industry: str, reason: str) -> dict:
    organization = organization_for(db, user)
    if requested_industry == organization.industry.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a different industry")
    if _pending_industry_request(db, organization.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "An industry review is already pending")
    row = IndustryMigrationRequest(
        organization_id=organization.id,
        requested_by_user_id=user.id,
        current_industry=organization.industry.value,
        requested_industry=requested_industry,
        reason=reason,
    )
    db.add(row)
    db.flush()
    log_action(db, organization_id=organization.id, user_id=user.id, action="settings.industry_migration_requested", resource_type="industry_migration_request", resource_id=row.id)
    db.commit()
    return {"id": row.id, "status": row.status, "requested_industry": row.requested_industry}
