"""Edvatiq platform control-plane APIs."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import EmailStr, Field, model_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.business import serialize
from app.core.config import settings
from app.core.database import get_db
from app.core.validation_errors import validation_problem
from app.schemas.validation import RequestModel
from app.core.security import hash_password
from app.models import (
    AIExecutionTrace, AIUsage, AIWallet, ApprovalRequest, AuditLog, BillingProfile, Client, Document,
    Employee, FeatureDefinition, Invoice, Job, Location, Organization,
    OrganizationDeletionRequest, OrganizationEntitlementOverride, OrganizationStatusEnum,
    OutboundMessage, PaymentEvent, PlanDefinition, PlanEntitlement, PlanVersion,
    PlatformMFADevice, PlatformPayment, PlatformPermission, PlatformRefund, PlatformRole,
    PlatformRolePermission, PlatformSetting, PlatformSettlement, PlatformUserRole,
    ProviderPlanMapping,
    RechargePack, RefreshToken, RetentionArchive, Role, Subscription, SupportSession, User,
    UserRole, WalletLedger,
)
from app.services.audit import log_action
from app.services.entitlements import resolve_entitlements
from app.services.platform_security import (
    create_recovery_codes, encrypt_secret, generate_totp_secret, platform_permissions,
    provisioning_uri, require_platform_permission, verify_mfa_or_recovery, verify_totp,
)
from app.services.wallet import add_credits, ensure_wallet, wallet_summary
from app.services.billing import paise_to_rupees, provider_error
from app.services.cashfree_provider import cashfree_provider, cashfree_refund_state
from app.services.payment_gateways import gateway_config, gateway_inventory

router = APIRouter(prefix="/super-admin", tags=["super-admin"])
now_utc = lambda: datetime.now(timezone.utc)


class OrganizationUpdate(RequestModel):
    status: Literal["active", "trial", "suspended", "cancelled"] | None = None
    version: int | None = Field(default=None, ge=1)


class PlanDraftBody(RequestModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    monthly_price_paise: int | None = Field(default=None, ge=0)
    annual_price_paise: int | None = Field(default=None, ge=0)
    annual_discount_bps: int = Field(default=0, ge=0, le=10000)
    tax_enabled: bool = True
    gst_rate_bps: int = Field(default=1800, ge=0, le=10000)
    included_ai_credits: int = Field(default=0, ge=0, le=10_000_000)
    support_level: Literal["self-service", "standard", "priority", "dedicated"] = "standard"
    ai_tier: Literal["basic", "advanced", "actions", "enterprise"] = "basic"
    entitlements: dict[str, object] = {}
    version_lock: int | None = Field(default=None, ge=1)


class PlanAvailabilityBody(RequestModel):
    is_active: bool | None = None
    is_public: bool | None = None

    @model_validator(mode="after")
    def has_change(self):
        if self.is_active is None and self.is_public is None:
            raise ValueError("Choose at least one availability setting")
        return self


class PublishPlanBody(RequestModel):
    version_lock: int = Field(ge=1)
    effective_from: datetime | None = None


class RechargePackBody(RequestModel):
    name: str = Field(min_length=2, max_length=100)
    credits: int = Field(gt=0, le=10_000_000)
    price_paise: int = Field(gt=0)
    tax_enabled: bool = True
    gst_rate_bps: int = Field(default=1800, ge=0, le=10000)
    is_active: bool = True
    display_order: int = Field(default=0, ge=0)


class PlanAssignment(RequestModel):
    plan_version_id: str = Field(min_length=1, max_length=100)
    billing_interval: str = Field(pattern="^(monthly|annual)$")
    change_timing: str = Field(default="immediate", pattern="^(immediate|cycle_end)$")
    reason: str = Field(min_length=5, max_length=500)
    version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=160)


class OverrideBody(RequestModel):
    feature_code: str = Field(min_length=1, max_length=160)
    value: object
    reason: str = Field(min_length=8, max_length=1000)
    starts_at: datetime
    ends_at: datetime
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def valid_window(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Override end must be after its start")
        return self


class WalletRechargeBody(RequestModel):
    credits: int = Field(gt=0, le=10_000_000)
    reason: str = Field(min_length=5, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=160)
    mfa_code: str = Field(min_length=6, max_length=64)


class RefundBody(RequestModel):
    amount_paise: int = Field(gt=0, le=100_000_000_000)
    reason: str = Field(min_length=8, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=160)
    mfa_code: str = Field(min_length=6, max_length=64)


class GatewaySelectionBody(RequestModel):
    provider: Literal["razorpay", "cashfree"]
    version: int = Field(ge=1)


class TeamMemberBody(RequestModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(default="", max_length=120)
    role_id: str = Field(min_length=1, max_length=100)


class TeamRoleBody(RequestModel):
    role_id: str = Field(min_length=1, max_length=100)
    version: int | None = Field(default=None, ge=1)


class SupportBody(RequestModel):
    organization_id: str = Field(min_length=1, max_length=100)
    target_user_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=8, max_length=1000)
    ticket_reference: str = Field(min_length=3, max_length=120)
    mode: Literal["read_only", "limited_write"] = "read_only"


class ApprovalDecision(RequestModel):
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=64)


class MFAConfirm(RequestModel):
    code: str = Field(pattern=r"^\d{6}$")


class SettingsBody(RequestModel):
    value: dict
    version: int = Field(ge=1)


class DeletionBody(RequestModel):
    reason: str = Field(min_length=12, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=160)
    mfa_code: str = Field(min_length=6, max_length=64)


class OwnerTransferBody(RequestModel):
    new_owner_user_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=8, max_length=1000)
    mfa_code: str = Field(min_length=6, max_length=64)


class ManualInvoiceBody(RequestModel):
    organization_id: str = Field(min_length=1, max_length=100)
    subtotal_paise: int = Field(gt=0, le=100_000_000_000)
    gst_rate_bps: int = Field(default=1800, ge=0, le=10000)
    description: str = Field(min_length=3, max_length=1000)
    due_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)


class OfflinePaymentBody(RequestModel):
    amount_paise: int = Field(gt=0, le=100_000_000_000)
    method: Literal["cash", "card", "bank", "upi"]
    reference: str = Field(min_length=3, max_length=120)
    mfa_code: str = Field(min_length=6, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=160)


class CaptureBody(RequestModel):
    amount_paise: int = Field(gt=0, le=100_000_000_000)
    mfa_code: str = Field(min_length=6, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=160)


class ReconcileBody(RequestModel):
    mfa_code: str = Field(min_length=6, max_length=64)


class SettlementBody(RequestModel):
    amount_paise: int = Field(gt=0, le=100_000_000_000)
    reason: str = Field(min_length=8, max_length=1000)
    mfa_code: str = Field(min_length=6, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=160)


def _audit(db, actor, action, resource_type=None, resource_id=None, organization_id=None, changes=None):
    log_action(db, organization_id=organization_id, user_id=actor.id, action=action, resource_type=resource_type, resource_id=resource_id, changes=changes, meta={"platform_action": True})


def _require_mfa(db: Session, actor: User, code: str) -> None:
    device = db.execute(select(PlatformMFADevice).where(PlatformMFADevice.user_id == actor.id, PlatformMFADevice.verified.is_(True))).scalar_one_or_none()
    if not device:
        raise HTTPException(428, "Set up your authenticator before performing financial actions")
    if not verify_mfa_or_recovery(db, actor, code):
        raise HTTPException(403, "Authentication code is invalid")


def _setting(db: Session, key: str, fallback: dict) -> dict:
    row = db.execute(select(PlatformSetting).where(PlatformSetting.key == key)).scalar_one_or_none()
    return row.value if row else fallback


def _organization_or_404(db: Session, org_id: str) -> Organization:
    row = db.get(Organization, org_id)
    if not row:
        raise HTTPException(404, "Organization not found")
    return row


@router.get("/me")
def platform_me(actor=Depends(require_platform_permission("overview.view")), db: Session = Depends(get_db)):
    device = db.execute(select(PlatformMFADevice).where(PlatformMFADevice.user_id == actor.id)).scalar_one_or_none()
    roles = db.execute(select(PlatformRole).join(PlatformUserRole, PlatformUserRole.role_id == PlatformRole.id).where(PlatformUserRole.user_id == actor.id)).scalars().all()
    return {"user": serialize(actor), "roles": [serialize(row) for row in roles], "permissions": sorted(platform_permissions(db, actor)), "mfa": {"enrolled": bool(device and device.verified), "enrollment_required": not bool(device and device.verified)}}


@router.get("/security/mfa/status")
def mfa_status(actor=Depends(require_platform_permission("overview.view")), db: Session = Depends(get_db)):
    device = db.execute(select(PlatformMFADevice).where(PlatformMFADevice.user_id == actor.id)).scalar_one_or_none()
    return {"enrolled": bool(device and device.verified), "enrollment_required": not bool(device and device.verified)}


@router.post("/security/mfa/enroll")
def mfa_enroll(actor=Depends(require_platform_permission("overview.view")), db: Session = Depends(get_db)):
    device = db.execute(select(PlatformMFADevice).where(PlatformMFADevice.user_id == actor.id)).scalar_one_or_none()
    if device and device.verified:
        raise HTTPException(409, "Authenticator is already set up")
    secret = generate_totp_secret()
    if device:
        device.secret_encrypted = encrypt_secret(secret)
    else:
        device = PlatformMFADevice(user_id=actor.id, secret_encrypted=encrypt_secret(secret), verified=False)
        db.add(device)
    db.commit()
    return {"secret": secret, "provisioning_uri": provisioning_uri(actor.email, secret)}


@router.post("/security/mfa/confirm")
def mfa_confirm(body: MFAConfirm, actor=Depends(require_platform_permission("overview.view")), db: Session = Depends(get_db)):
    device = db.execute(select(PlatformMFADevice).where(PlatformMFADevice.user_id == actor.id)).scalar_one_or_none()
    if not device or device.verified:
        raise HTTPException(409, "Start authenticator setup first")
    if not verify_totp(device, body.code):
        raise HTTPException(400, "Authentication code is invalid")
    device.verified = True; device.verified_at = now_utc()
    codes = create_recovery_codes(db, actor)
    _audit(db, actor, "platform.mfa_enrolled", "platform_user", actor.id)
    db.commit()
    return {"ok": True, "recovery_codes": codes}


@router.get("/overview")
def overview(actor=Depends(require_platform_permission("overview.view")), db: Session = Depends(get_db)):
    month = now_utc().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    active_prices = db.execute(select(PlanVersion.monthly_price_paise, PlanVersion.annual_price_paise, Subscription.billing_interval).join(Subscription, Subscription.plan_version_id == PlanVersion.id).where(Subscription.status.in_(["active", "trialing"]))).all()
    mrr = sum(((annual or 0) // 12 if interval == "annual" else (monthly or 0)) for monthly, annual, interval in active_prices)
    failed = db.scalar(select(func.count(Invoice.id)).where(Invoice.status.in_(["failed", "past_due"]))) or 0
    outstanding = db.scalar(select(func.coalesce(func.sum(Invoice.amount_paise), 0)).where(Invoice.status.in_(["created", "issued", "past_due"]))) or 0
    queued = db.scalar(select(func.count(Job.id)).where(Job.status == "queued")) or 0
    incidents = db.scalar(select(func.count(Job.id)).where(Job.status == "failed")) or 0
    ai_totals = db.execute(select(
        func.coalesce(func.sum(AIUsage.input_tokens), 0),
        func.coalesce(func.sum(AIUsage.output_tokens), 0),
        func.coalesce(func.sum(AIUsage.embedding_tokens), 0),
        func.coalesce(func.sum(AIUsage.provider_cost_paise), 0),
    ).where(AIUsage.created_at >= month)).one()
    ai_tokens = ai_totals[0] + ai_totals[1] + ai_totals[2]
    ai_cost_paise = ai_totals[3]
    wallet_consumed = -(db.execute(select(func.coalesce(func.sum(WalletLedger.credits_delta), 0)).where(WalletLedger.entry_type == "usage", WalletLedger.created_at >= month)).scalar() or 0)
    return {
        "metrics": {"mrr_paise": mrr, "arr_paise": mrr * 12, "failed_payments": failed, "outstanding_paise": outstanding, "ai_tokens": ai_tokens, "ai_cost_paise": ai_cost_paise, "ai_credits_used": wallet_consumed, "queued_jobs": queued, "incidents": incidents},
        "organizations": {"total": db.scalar(select(func.count(Organization.id))) or 0, "trials": db.scalar(select(func.count(Organization.id)).where(Organization.status == OrganizationStatusEnum.trial)) or 0, "new_this_month": db.scalar(select(func.count(Organization.id)).where(Organization.created_at >= month)) or 0, "suspended": db.scalar(select(func.count(Organization.id)).where(Organization.status == OrganizationStatusEnum.suspended)) or 0, "churned_this_month": db.scalar(select(func.count(Subscription.id)).where(Subscription.status == "cancelled", Subscription.updated_at >= month)) or 0},
        "approvals": db.scalar(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "pending")) or 0,
    }


@router.get("/ai/performance")
def ai_performance(
    days: int = Query(default=30, ge=1, le=90),
    actor=Depends(require_platform_permission("operations.view")),
    db: Session = Depends(get_db),
):
    since = now_utc() - timedelta(days=days)
    total = func.count(AIExecutionTrace.id)
    provider_turns = func.sum(case((AIExecutionTrace.provider_requests > 0, 1), else_=0))
    zero_credit_turns = func.sum(case((AIExecutionTrace.zero_credit.is_(True), 1), else_=0))
    cache_hits = func.sum(case((AIExecutionTrace.cache_status == "hit", 1), else_=0))
    verification_failures = func.sum(case((AIExecutionTrace.verification_outcome == "deterministic_fallback", 1), else_=0))
    fallbacks = func.sum(case((AIExecutionTrace.fallback_used.is_(True), 1), else_=0))
    aggregates = db.execute(select(
        total,
        func.coalesce(provider_turns, 0),
        func.coalesce(zero_credit_turns, 0),
        func.coalesce(cache_hits, 0),
        func.coalesce(verification_failures, 0),
        func.coalesce(fallbacks, 0),
        func.coalesce(func.sum(AIExecutionTrace.provider_requests), 0),
        func.coalesce(func.sum(AIExecutionTrace.input_tokens), 0),
        func.coalesce(func.sum(AIExecutionTrace.output_tokens), 0),
        func.coalesce(func.sum(AIExecutionTrace.embedding_tokens), 0),
        func.percentile_cont(0.5).within_group(AIExecutionTrace.total_latency_ms),
        func.percentile_cont(0.95).within_group(AIExecutionTrace.total_latency_ms),
        func.percentile_cont(0.95).within_group(AIExecutionTrace.first_event_latency_ms),
    ).where(AIExecutionTrace.created_at >= since)).one()
    count = int(aggregates[0] or 0)

    route_rows = db.execute(select(
        AIExecutionTrace.route,
        func.count(AIExecutionTrace.id),
        func.avg(AIExecutionTrace.total_latency_ms),
        func.percentile_cont(0.95).within_group(AIExecutionTrace.total_latency_ms),
        func.sum(AIExecutionTrace.provider_requests),
        func.sum(case((AIExecutionTrace.zero_credit.is_(True), 1), else_=0)),
        func.sum(case((AIExecutionTrace.verification_outcome == "deterministic_fallback", 1), else_=0)),
    ).where(
        AIExecutionTrace.created_at >= since,
    ).group_by(AIExecutionTrace.route).order_by(func.count(AIExecutionTrace.id).desc())).all()

    def ratio(value: int) -> float:
        return round((int(value or 0) / count), 4) if count else 0.0

    return {
        "period_days": days,
        "turns": count,
        "provider_call_ratio": ratio(aggregates[1]),
        "zero_credit_ratio": ratio(aggregates[2]),
        "cache_hit_ratio": ratio(aggregates[3]),
        "verification_failure_ratio": ratio(aggregates[4]),
        "fallback_ratio": ratio(aggregates[5]),
        "provider_requests": int(aggregates[6] or 0),
        "tokens": {
            "input": int(aggregates[7] or 0),
            "output": int(aggregates[8] or 0),
            "embedding": int(aggregates[9] or 0),
        },
        "latency_ms": {
            "p50": int(aggregates[10] or 0),
            "p95": int(aggregates[11] or 0),
            "first_event_p95": int(aggregates[12] or 0),
        },
        "routes": [
            {
                "route": route,
                "turns": int(turns or 0),
                "average_latency_ms": int(average_latency or 0),
                "p95_latency_ms": int(p95_latency or 0),
                "provider_requests": int(requests or 0),
                "zero_credit_turns": int(free_turns or 0),
                "verification_fallbacks": int(failed_verification or 0),
            }
            for route, turns, average_latency, p95_latency, requests, free_turns, failed_verification in route_rows
        ],
    }


@router.get("/organizations")
def organizations(q: str | None = None, status: str | None = None, industry: str | None = None, plan: str | None = None, risk: str | None = None, cursor: str | None = None, limit: int = Query(25, ge=1, le=100), actor=Depends(require_platform_permission("organizations.view")), db: Session = Depends(get_db)):
    stmt = select(Organization)
    if q: stmt = stmt.where(or_(Organization.name.ilike(f"%{q}%"), Organization.slug.ilike(f"%{q}%"), Organization.contact_email.ilike(f"%{q}%")))
    if status: stmt = stmt.where(Organization.status == status)
    if industry: stmt = stmt.where(Organization.industry == industry)
    if plan: stmt = stmt.where(Organization.plan == plan)
    if cursor:
        pivot = db.get(Organization, cursor)
        if pivot: stmt = stmt.where(Organization.created_at < pivot.created_at)
    rows = db.execute(stmt.order_by(Organization.created_at.desc()).limit(limit + 1)).scalars().all()
    items = []
    for org in rows[:limit]:
        subscription = db.execute(select(Subscription).where(Subscription.organization_id == org.id).order_by(Subscription.created_at.desc())).scalars().first()
        wallet = ensure_wallet(db, org)
        items.append({**serialize(org), "subscription": serialize(subscription) if subscription else None, "usage": {"users": db.scalar(select(func.count(User.id)).where(User.organization_id == org.id)) or 0, "locations": db.scalar(select(func.count(Location.id)).where(Location.organization_id == org.id)) or 0}, "wallet": wallet_summary(wallet), "risk": "payment_attention" if subscription and subscription.status == "past_due" else "normal"})
    db.commit()
    return {"items": items, "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


@router.get("/organizations/{org_id}")
def organization_workspace(org_id: str, actor=Depends(require_platform_permission("organizations.view")), db: Session = Depends(get_db)):
    org = _organization_or_404(db, org_id)
    subscription = db.execute(select(Subscription).where(Subscription.organization_id == org.id).order_by(Subscription.created_at.desc())).scalars().first()
    profile = db.execute(select(BillingProfile).where(BillingProfile.organization_id == org.id)).scalar_one_or_none()
    wallet = ensure_wallet(db, org)
    users = db.execute(select(User).where(User.organization_id == org.id).order_by(User.created_at)).scalars().all()
    locations = db.execute(select(Location).where(Location.organization_id == org.id).order_by(Location.name)).scalars().all()
    invoices = db.execute(select(Invoice).where(Invoice.organization_id == org.id).order_by(Invoice.created_at.desc()).limit(20)).scalars().all()
    overrides = db.execute(select(OrganizationEntitlementOverride).where(OrganizationEntitlementOverride.organization_id == org.id).order_by(OrganizationEntitlementOverride.created_at.desc())).scalars().all()
    audit = db.execute(select(AuditLog).where(AuditLog.organization_id == org.id).order_by(AuditLog.created_at.desc()).limit(30)).scalars().all()
    db.commit()
    return {"organization": serialize(org), "subscription": serialize(subscription) if subscription else None, "billing_profile": serialize(profile) if profile else None, "entitlements": resolve_entitlements(db, org), "wallet": wallet_summary(wallet), "usage": {"users": len(users), "employees": db.scalar(select(func.count(Employee.id)).where(Employee.organization_id == org.id)) or 0, "clients": db.scalar(select(func.count(Client.id)).where(Client.organization_id == org.id)) or 0, "locations": len(locations), "storage_bytes": db.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.organization_id == org.id)) or 0}, "users": [serialize(row) for row in users], "locations": [serialize(row) for row in locations], "invoices": [serialize(row) for row in invoices], "overrides": [serialize(row) for row in overrides], "audit": [serialize(row) for row in audit]}


@router.patch("/organizations/{org_id}")
def update_organization(org_id: str, body: OrganizationUpdate, actor=Depends(require_platform_permission("organizations.manage")), db: Session = Depends(get_db)):
    org = _organization_or_404(db, org_id)
    changes = body.model_dump(exclude_none=True); changes.pop("version", None)
    if "status" in changes:
        changes["status"] = OrganizationStatusEnum(changes["status"])
    for key, value in changes.items(): setattr(org, key, value)
    _audit(db, actor, "platform.organization_update", "organization", org.id, org.id, body.model_dump(exclude_none=True)); db.commit()
    return serialize(org)


@router.post("/organizations/{org_id}/suspend")
def suspend(org_id: str, actor=Depends(require_platform_permission("organizations.manage")), db: Session = Depends(get_db)):
    return _change_org_state(db, actor, org_id, OrganizationStatusEnum.suspended)


@router.post("/organizations/{org_id}/activate")
@router.post("/organizations/{org_id}/restore")
def activate(org_id: str, actor=Depends(require_platform_permission("organizations.manage")), db: Session = Depends(get_db)):
    return _change_org_state(db, actor, org_id, OrganizationStatusEnum.active)


def _change_org_state(db, actor, org_id, state):
    org = _organization_or_404(db, org_id); org.status = state
    if state == OrganizationStatusEnum.suspended:
        db.query(User).filter(User.organization_id == org.id).update({User.session_version: User.session_version + 1})
        user_ids = select(User.id).where(User.organization_id == org.id)
        db.query(RefreshToken).filter(RefreshToken.user_id.in_(user_ids), RefreshToken.revoked.is_(False)).update({RefreshToken.revoked: True}, synchronize_session=False)
    _audit(db, actor, f"platform.organization_{state.value}", "organization", org.id, org.id); db.commit(); return {"ok": True, "status": state.value}


@router.post("/organizations/{org_id}/users/{user_id}/suspend")
def suspend_tenant_user(org_id: str, user_id: str, actor=Depends(require_platform_permission("organizations.manage")), db: Session = Depends(get_db)):
    row = db.get(User, user_id)
    if not row or row.organization_id != org_id: raise HTTPException(404, "User not found")
    row.is_active = False; row.session_version += 1
    db.query(RefreshToken).filter(RefreshToken.user_id == row.id, RefreshToken.revoked.is_(False)).update({RefreshToken.revoked: True})
    _audit(db, actor, "platform.tenant_user_suspended", "user", row.id, org_id); db.commit(); return {"ok": True}


@router.post("/organizations/{org_id}/users/{user_id}/restore")
def restore_tenant_user(org_id: str, user_id: str, actor=Depends(require_platform_permission("organizations.manage")), db: Session = Depends(get_db)):
    row = db.get(User, user_id)
    if not row or row.organization_id != org_id: raise HTTPException(404, "User not found")
    row.is_active = True; _audit(db, actor, "platform.tenant_user_restored", "user", row.id, org_id); db.commit(); return {"ok": True}


@router.post("/organizations/{org_id}/users/{user_id}/revoke-sessions")
def revoke_tenant_sessions(org_id: str, user_id: str, actor=Depends(require_platform_permission("organizations.manage")), db: Session = Depends(get_db)):
    row = db.get(User, user_id)
    if not row or row.organization_id != org_id: raise HTTPException(404, "User not found")
    row.session_version += 1; db.query(RefreshToken).filter(RefreshToken.user_id == row.id, RefreshToken.revoked.is_(False)).update({RefreshToken.revoked: True})
    _audit(db, actor, "platform.tenant_sessions_revoked", "user", row.id, org_id); db.commit(); return {"ok": True}


@router.post("/organizations/{org_id}/users/{user_id}/resend-verification")
def resend_tenant_verification(org_id: str, user_id: str, request: Request, actor=Depends(require_platform_permission("organizations.manage")), db: Session = Depends(get_db)):
    row = db.get(User, user_id)
    if not row or row.organization_id != org_id: raise HTTPException(404, "User not found")
    if row.email_verified: raise HTTPException(409, "This email is already verified")
    from app.api.v1.auth import _deliver_code
    sent, _ = _deliver_code(db, row, "email_verification", request)
    _audit(db, actor, "platform.verification_resent", "user", row.id, org_id); db.commit(); return {"ok": True, "sent": sent}


@router.post("/organizations/{org_id}/transfer-owner")
def transfer_owner(org_id: str, body: OwnerTransferBody, actor=Depends(require_platform_permission("organizations.manage")), db: Session = Depends(get_db)):
    _require_mfa(db, actor, body.mfa_code); _organization_or_404(db, org_id)
    target = db.get(User, body.new_owner_user_id)
    if not target or target.organization_id != org_id or not target.is_active: raise HTTPException(400, "Choose an active user in this organization")
    owner_role = db.execute(select(Role).where(
        Role.organization_id == org_id,
        Role.slug == "owner",
        Role.is_system.is_(True),
    )).scalar_one_or_none()
    if not owner_role: raise HTTPException(409, "This organization has no owner role")
    existing = db.execute(select(UserRole).where(UserRole.role_id == owner_role.id)).scalars().all()
    if not db.execute(select(UserRole).where(UserRole.role_id == owner_role.id, UserRole.user_id == target.id)).scalar_one_or_none(): db.add(UserRole(role_id=owner_role.id, user_id=target.id))
    for assignment in existing:
        if assignment.user_id != target.id: db.delete(assignment)
    db.query(User).filter(User.organization_id == org_id).update({User.session_version: User.session_version + 1})
    _audit(db, actor, "platform.owner_transferred", "user", target.id, org_id, {"reason": body.reason}); db.commit(); return {"ok": True, "owner_user_id": target.id}


@router.get("/features")
def features(actor=Depends(require_platform_permission("plans.view")), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.execute(select(FeatureDefinition).order_by(FeatureDefinition.category, FeatureDefinition.name)).scalars()]


@router.get("/plans")
def plans(actor=Depends(require_platform_permission("plans.view")), db: Session = Depends(get_db)):
    definitions = db.execute(select(PlanDefinition).order_by(PlanDefinition.display_order)).scalars().all(); result = []
    for plan in definitions:
        versions = db.execute(select(PlanVersion).where(PlanVersion.plan_id == plan.id).order_by(PlanVersion.version.desc())).scalars().all()
        result.append({**serialize(plan), "versions": [{
            **serialize(version),
            "entitlements": {code: value.get("value") for code, value in db.execute(select(FeatureDefinition.code, PlanEntitlement.value).join(PlanEntitlement, PlanEntitlement.feature_id == FeatureDefinition.id).where(PlanEntitlement.plan_version_id == version.id)).all()},
            "provider_plans": [serialize(mapping) for mapping in db.execute(select(ProviderPlanMapping).where(ProviderPlanMapping.plan_version_id == version.id)).scalars()],
        } for version in versions]})
    return result


@router.patch("/plans/{plan_id}")
def update_plan_availability(
    plan_id: str,
    body: PlanAvailabilityBody,
    actor=Depends(require_platform_permission("plans.manage")),
    db: Session = Depends(get_db),
):
    if not body.model_fields_set:
        raise HTTPException(400, "Choose an availability setting to update")
    if any(value is None for value in body.model_dump(exclude_unset=True).values()):
        raise HTTPException(400, "Plan availability must be true or false")
    plan = db.get(PlanDefinition, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    before = {"is_active": plan.is_active, "is_public": plan.is_public}
    if "is_active" in body.model_fields_set:
        plan.is_active = bool(body.is_active)
    if "is_public" in body.model_fields_set:
        plan.is_public = bool(body.is_public)
    changes = {"before": before, "after": {"is_active": plan.is_active, "is_public": plan.is_public}}
    _audit(db, actor, "platform.plan_availability_updated", "plan", plan.id, changes=changes)
    db.commit()
    return serialize(plan)


@router.post("/plans/{plan_id}/versions")
def create_plan_version(plan_id: str, body: PlanDraftBody, actor=Depends(require_platform_permission("plans.manage")), db: Session = Depends(get_db)):
    plan = db.get(PlanDefinition, plan_id)
    if not plan: raise HTTPException(404, "Plan not found")
    latest = db.execute(select(PlanVersion).where(PlanVersion.plan_id == plan.id).order_by(PlanVersion.version.desc())).scalars().first()
    row = PlanVersion(plan_id=plan.id, version=(latest.version + 1 if latest else 1), status="draft", monthly_price_paise=body.monthly_price_paise, annual_price_paise=body.annual_price_paise, annual_discount_bps=body.annual_discount_bps, tax_enabled=body.tax_enabled, gst_rate_bps=body.gst_rate_bps, included_ai_credits=body.included_ai_credits, support_level=body.support_level, ai_tier=body.ai_tier)
    db.add(row); db.flush(); _replace_entitlements(db, row.id, body.entitlements)
    _audit(db, actor, "platform.plan_version_created", "plan_version", row.id, changes=body.model_dump()); db.commit(); return serialize(row)


@router.patch("/plans/versions/{version_id}")
def update_plan_version(version_id: str, body: PlanDraftBody, actor=Depends(require_platform_permission("plans.manage")), db: Session = Depends(get_db)):
    row = db.get(PlanVersion, version_id)
    if not row: raise HTTPException(404, "Plan version not found")
    if row.status != "draft": raise HTTPException(409, "Published plan versions cannot be edited")
    if body.version_lock is not None and body.version_lock != row.version_lock: raise HTTPException(409, "This plan draft changed. Refresh and try again")
    for key in ("monthly_price_paise", "annual_price_paise", "annual_discount_bps", "tax_enabled", "gst_rate_bps", "included_ai_credits", "support_level", "ai_tier"):
        if key in body.model_fields_set: setattr(row, key, getattr(body, key))
    row.version_lock += 1; _replace_entitlements(db, row.id, body.entitlements)
    _audit(db, actor, "platform.plan_version_updated", "plan_version", row.id, changes=body.model_dump()); db.commit(); return serialize(row)


def _replace_entitlements(db, version_id, values):
    if not values: return
    features = {row.code: row for row in db.execute(select(FeatureDefinition).where(FeatureDefinition.code.in_(values))).scalars()}
    unknown = set(values) - set(features)
    if unknown: raise HTTPException(400, f"Unknown features: {', '.join(sorted(unknown))}")
    db.query(PlanEntitlement).filter(PlanEntitlement.plan_version_id == version_id).delete()
    for code, value in values.items(): db.add(PlanEntitlement(plan_version_id=version_id, feature_id=features[code].id, value={"value": value}))


@router.post("/plans/versions/{version_id}/publish")
def publish_plan(version_id: str, body: PublishPlanBody, actor=Depends(require_platform_permission("plans.publish")), db: Session = Depends(get_db)):
    row = db.get(PlanVersion, version_id)
    if not row: raise HTTPException(404, "Plan version not found")
    if row.status == "published": return serialize(row)
    if row.status != "draft": raise HTTPException(409, "Only a draft can be published")
    if body.version_lock != row.version_lock: raise HTTPException(409, "This plan draft changed. Refresh and try again")
    row.status = "published"; row.published_at = now_utc(); row.effective_from = body.effective_from or now_utc(); row.published_by_user_id = actor.id
    _audit(db, actor, "platform.plan_version_published", "plan_version", row.id); db.commit(); return serialize(row)


@router.post("/organizations/{org_id}/plan")
def assign_plan(org_id: str, body: PlanAssignment, actor=Depends(require_platform_permission("plans.manage")), db: Session = Depends(get_db)):
    org = _organization_or_404(db, org_id); version = db.get(PlanVersion, body.plan_version_id)
    if not version or version.status != "published": raise HTTPException(400, "Choose a published plan version")
    subscription = db.execute(select(Subscription).where(Subscription.organization_id == org.id).order_by(Subscription.created_at.desc())).scalars().first()
    if not subscription:
        from app.services.subscriptions import start_trial
        subscription = start_trial(Subscription(organization_id=org.id, plan="trial"))
        db.add(subscription); db.flush()
    if subscription.version != body.version: raise HTTPException(409, "Subscription changed. Refresh and try again")
    definition = db.get(PlanDefinition, version.plan_id)
    if body.change_timing == "cycle_end": subscription.scheduled_plan_version_id = version.id
    else:
        subscription.plan_version_id = version.id; subscription.plan = definition.slug; org.plan = definition.slug
        subscription.status = "trialing" if definition.slug == "trial" else "active"
    subscription.billing_interval = body.billing_interval; subscription.version += 1
    _audit(db, actor, "platform.plan_assigned", "subscription", subscription.id, org.id, body.model_dump()); db.commit(); return serialize(subscription)


@router.post("/organizations/{org_id}/overrides")
def grant_override(org_id: str, body: OverrideBody, actor=Depends(require_platform_permission("plans.manage")), db: Session = Depends(get_db)):
    _organization_or_404(db, org_id); feature = db.execute(select(FeatureDefinition).where(FeatureDefinition.code == body.feature_code)).scalar_one_or_none()
    if not feature: raise HTTPException(404, "Feature not found")
    if body.ends_at <= body.starts_at or body.ends_at <= now_utc(): raise HTTPException(400, "Choose a valid override period")
    row = OrganizationEntitlementOverride(organization_id=org_id, feature_id=feature.id, value={"value": body.value}, reason=body.reason, starts_at=body.starts_at, ends_at=body.ends_at, created_by_user_id=actor.id, approved_by_user_id=actor.id)
    db.add(row); _audit(db, actor, "platform.entitlement_override_granted", "entitlement_override", row.id, org_id, body.model_dump()); db.commit(); return serialize(row)


@router.get("/billing")
def billing(actor=Depends(require_platform_permission("billing.view")), db: Session = Depends(get_db)):
    invoices = db.execute(select(Invoice).order_by(Invoice.created_at.desc()).limit(100)).scalars().all()
    payments = db.execute(select(PlatformPayment).order_by(PlatformPayment.created_at.desc()).limit(100)).scalars().all()
    refunds = db.execute(select(PlatformRefund).order_by(PlatformRefund.created_at.desc()).limit(100)).scalars().all()
    settlements = db.execute(select(PlatformSettlement).order_by(PlatformSettlement.created_at.desc()).limit(100)).scalars().all()
    setting = db.execute(select(PlatformSetting).where(PlatformSetting.key == "payment_gateway")).scalar_one_or_none()
    return {"summary": {"collected_paise": db.scalar(select(func.coalesce(func.sum(PlatformPayment.amount_paise), 0)).where(PlatformPayment.status == "captured")) or 0, "outstanding_paise": db.scalar(select(func.coalesce(func.sum(Invoice.amount_paise), 0)).where(Invoice.status.in_(["created", "issued", "past_due"]))) or 0, "failed": db.scalar(select(func.count(Invoice.id)).where(Invoice.status == "failed")) or 0}, "invoices": [serialize(row) for row in invoices], "payments": [serialize(row) for row in payments], "refunds": [serialize(row) for row in refunds], "settlements": [serialize(row) for row in settlements], "provider": {**gateway_inventory(db), "version": setting.version if setting else 1}}


@router.put("/billing/gateway")
def select_payment_gateway(
    body: GatewaySelectionBody,
    actor=Depends(require_platform_permission("billing.manage")),
    db: Session = Depends(get_db),
):
    gateway_config(body.provider, require_configured=True, require_webhook=True)
    row = db.execute(select(PlatformSetting).where(
        PlatformSetting.key == "payment_gateway",
    ).with_for_update()).scalar_one_or_none()
    current_version = row.version if row else 1
    if body.version != current_version:
        raise HTTPException(409, "Payment gateway settings changed. Refresh and try again")
    previous = str((row.value if row else {}).get("provider") or settings.PAYMENT_GATEWAY)
    if not row:
        row = PlatformSetting(key="payment_gateway", value={"provider": body.provider}, version=1)
        db.add(row); db.flush()
    elif previous != body.provider:
        row.value = {"provider": body.provider}
        row.version += 1
    _audit(
        db, actor, "platform.payment_gateway_changed", "platform_setting", row.id,
        changes={"before": previous, "after": body.provider},
    )
    db.commit(); db.refresh(row)
    return {**gateway_inventory(db), "version": row.version}


@router.post("/billing/payments/{payment_id}/refund")
def refund(payment_id: str, body: RefundBody, actor=Depends(require_platform_permission("billing.refund")), db: Session = Depends(get_db)):
    _require_mfa(db, actor, body.mfa_code)
    existing = db.execute(select(PlatformRefund).where(PlatformRefund.idempotency_key == body.idempotency_key)).scalar_one_or_none()
    if existing: return serialize(existing)
    payment = db.get(PlatformPayment, payment_id)
    if not payment or payment.status not in {"captured", "partially_refunded"}: raise HTTPException(409, "Payment cannot be refunded")
    already = db.scalar(select(func.coalesce(func.sum(PlatformRefund.amount_paise), 0)).where(PlatformRefund.payment_id == payment.id, PlatformRefund.status.in_(["requested", "approved", "processed"]))) or 0
    if body.amount_paise > payment.amount_paise - already:
        raise validation_problem("amount_paise", "Refund exceeds the remaining payment amount")
    row = PlatformRefund(organization_id=payment.organization_id, payment_id=payment.id, amount_paise=body.amount_paise, reason=body.reason, requested_by_user_id=actor.id, idempotency_key=body.idempotency_key)
    db.add(row); db.flush()
    threshold = int(_setting(db, "financial_approvals", {"refund_threshold_paise": 1000000}).get("refund_threshold_paise", 1000000))
    if body.amount_paise >= threshold:
        approval = ApprovalRequest(organization_id=payment.organization_id, action_type="refund", amount_paise=body.amount_paise, payload={"refund_id": row.id}, reason=body.reason, requested_by_user_id=actor.id, expires_at=now_utc() + timedelta(days=2))
        db.add(approval); row.status = "requested"
    else:
        _execute_refund(db, row, actor)
    _audit(db, actor, "platform.refund_requested", "refund", row.id, payment.organization_id, {"amount_paise": body.amount_paise, "reason": body.reason}); db.commit(); return serialize(row)


@router.post("/billing/invoices")
def create_manual_invoice(body: ManualInvoiceBody, actor=Depends(require_platform_permission("billing.manage")), db: Session = Depends(get_db)):
    org = _organization_or_404(db, body.organization_id)
    existing = db.execute(select(Invoice).where(Invoice.organization_id == org.id, Invoice.plan_snapshot["idempotency_key"].astext == body.idempotency_key)).scalar_one_or_none()
    if existing: return serialize(existing)
    tax = (body.subtotal_paise * body.gst_rate_bps + 9999) // 10000
    count = db.scalar(select(func.count(Invoice.id))) or 0
    row = Invoice(organization_id=org.id, invoice_number=f"PLT-{now_utc().year}-{count + 1:06d}", subtotal_paise=body.subtotal_paise, tax_paise=tax, cgst_paise=tax // 2, sgst_paise=tax - tax // 2, amount_paise=body.subtotal_paise + tax, gst_rate_bps=body.gst_rate_bps, status="issued", description=body.description, due_at=body.due_at, billing_snapshot={"organization_name": org.name, "legal_name": org.legal_name, "gstin": org.gstin}, plan_snapshot={"source": "manual", "idempotency_key": body.idempotency_key})
    db.add(row); db.flush(); _audit(db, actor, "platform.manual_invoice_created", "invoice", row.id, org.id, {"amount_paise": row.amount_paise}); db.commit(); return serialize(row)


@router.post("/billing/invoices/{invoice_id}/offline-payment")
def record_offline_payment(invoice_id: str, body: OfflinePaymentBody, actor=Depends(require_platform_permission("billing.manage")), db: Session = Depends(get_db)):
    _require_mfa(db, actor, body.mfa_code)
    prior = db.execute(select(PlatformPayment).where(PlatformPayment.provider_payment_id == f"offline:{body.idempotency_key}")).scalar_one_or_none()
    if prior: return serialize(prior)
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.status in {"void", "refunded"}: raise HTTPException(409, "Invoice cannot accept a payment")
    paid = db.scalar(select(func.coalesce(func.sum(PlatformPayment.amount_paise), 0)).where(PlatformPayment.invoice_id == invoice.id, PlatformPayment.status == "captured")) or 0
    if body.amount_paise > invoice.amount_paise - paid:
        raise validation_problem("amount_paise", "Payment exceeds the outstanding invoice amount")
    row = PlatformPayment(organization_id=invoice.organization_id, invoice_id=invoice.id, provider="offline", provider_payment_id=f"offline:{body.idempotency_key}", mode="manual", amount_paise=body.amount_paise, currency=invoice.currency, status="captured", method=body.method, captured_at=now_utc(), meta={"reference": body.reference})
    db.add(row); db.flush(); total = paid + body.amount_paise; invoice.status = "paid" if total >= invoice.amount_paise else "partially_paid"; invoice.paid_at = now_utc() if invoice.status == "paid" else None
    _audit(db, actor, "platform.offline_payment_recorded", "payment", row.id, invoice.organization_id, {"amount_paise": body.amount_paise, "method": body.method}); db.commit(); return serialize(row)


def _execute_refund(db, refund, actor):
    payment = db.get(PlatformPayment, refund.payment_id)
    if payment.provider == "offline":
        refund.provider_refund_id = f"offline-refund-{refund.id}"
        refund.status = "processed"
    elif payment.mode != "mock" and payment.provider_payment_id:
        try:
            config = gateway_config(payment.provider, payment.mode)
            if payment.provider == "razorpay":
                from app.services.razorpay_provider import razorpay_provider
                result = razorpay_provider(config.client_id, config.secret).refund_payment(payment.provider_payment_id, {"amount": refund.amount_paise, "notes": {"edvatiq_refund_id": refund.id}})
                refund.provider_refund_id = result.get("id")
                refund.status = result.get("status", "processed")
            elif payment.provider == "cashfree":
                if not payment.provider_order_id:
                    raise HTTPException(409, "This Cashfree payment has no order reference")
                result = cashfree_provider(
                    config.client_id, config.secret, config.mode, settings.CASHFREE_API_VERSION,
                ).refund_order(payment.provider_order_id, {
                    "refund_amount": paise_to_rupees(refund.amount_paise),
                    "refund_id": f"edv_{refund.id.replace('-', '')}"[:40],
                    "refund_note": refund.reason[:100],
                    "refund_speed": "STANDARD",
                }, idempotency_key=refund.idempotency_key)
                provider_refund_id = result.get("cf_refund_id") or result.get("refund_id")
                refund.provider_refund_id = str(provider_refund_id) if provider_refund_id else None
                refund.status = cashfree_refund_state(result.get("refund_status"))
            else:
                raise HTTPException(409, "This payment provider does not support online refunds")
        except HTTPException:
            raise
        except Exception as exc:
            provider_error(exc, "refund", payment.provider)
            raise HTTPException(502, "The payment provider could not process this refund") from exc
    else:
        refund.provider_refund_id = f"mock-refund-{refund.id}"; refund.status = "processed"
    refund.approved_by_user_id = actor.id
    total = db.scalar(select(func.coalesce(func.sum(PlatformRefund.amount_paise), 0)).where(PlatformRefund.payment_id == payment.id, PlatformRefund.status == "processed")) or 0
    payment.status = "refunded" if total >= payment.amount_paise else "partially_refunded"


@router.post("/billing/payments/{payment_id}/reconcile")
def reconcile_payment(payment_id: str, body: ReconcileBody, actor=Depends(require_platform_permission("billing.manage")), db: Session = Depends(get_db)):
    _require_mfa(db, actor, body.mfa_code); payment = db.get(PlatformPayment, payment_id)
    if not payment: raise HTTPException(404, "Payment not found")
    payment.reconciled_at = now_utc(); _audit(db, actor, "platform.payment_reconciled", "payment", payment.id, payment.organization_id); db.commit(); return serialize(payment)


@router.post("/billing/payments/{payment_id}/capture")
def capture_payment(payment_id: str, body: CaptureBody, actor=Depends(require_platform_permission("billing.manage")), db: Session = Depends(get_db)):
    _require_mfa(db, actor, body.mfa_code); payment = db.get(PlatformPayment, payment_id)
    if not payment: raise HTTPException(404, "Payment not found")
    if payment.status == "captured": return serialize(payment)
    if payment.status != "authorized": raise HTTPException(409, "Only an authorized payment can be captured")
    if body.amount_paise != payment.amount_paise:
        raise validation_problem("amount_paise", "Capture amount must match the authorized payment")
    if payment.provider != "razorpay":
        raise HTTPException(409, "Manual capture is not supported for this payment provider")
    if payment.mode != "mock":
        try:
            from app.services.razorpay_provider import razorpay_provider
            key, secret, _ = settings.razorpay_credentials(payment.mode)
            result = razorpay_provider(key, secret).capture_payment(payment.provider_payment_id, body.amount_paise, payment.currency)
            payment.status = result.get("status", "captured")
        except Exception as exc: raise HTTPException(502, "The payment provider could not capture this payment") from exc
    else: payment.status = "captured"
    payment.captured_at = now_utc(); _audit(db, actor, "platform.payment_captured", "payment", payment.id, payment.organization_id, {"amount_paise": body.amount_paise, "idempotency_key": body.idempotency_key}); db.commit(); return serialize(payment)


@router.post("/billing/settlements")
def request_instant_settlement(body: SettlementBody, actor=Depends(require_platform_permission("billing.settlement")), db: Session = Depends(get_db)):
    _require_mfa(db, actor, body.mfa_code)
    if settings.RAZORPAY_MODE != "mock": raise HTTPException(503, "Instant settlement is not available for the connected payment account")
    existing = db.execute(select(ApprovalRequest).where(ApprovalRequest.action_type == "instant_settlement", ApprovalRequest.payload["idempotency_key"].astext == body.idempotency_key)).scalar_one_or_none()
    if existing: return serialize(existing)
    row = ApprovalRequest(action_type="instant_settlement", amount_paise=body.amount_paise, payload={"amount_paise": body.amount_paise, "mode": settings.RAZORPAY_MODE, "idempotency_key": body.idempotency_key}, reason=body.reason, requested_by_user_id=actor.id, expires_at=now_utc() + timedelta(days=1))
    db.add(row); _audit(db, actor, "platform.instant_settlement_requested", "approval", row.id, changes={"amount_paise": body.amount_paise}); db.commit(); return serialize(row)


@router.get("/wallets")
def wallets(actor=Depends(require_platform_permission("wallet.view")), db: Session = Depends(get_db)):
    result = []
    organizations = db.execute(
        select(Organization).order_by(Organization.name).with_for_update(of=Organization)
    ).scalars().all()
    for org in organizations:
        wallet = ensure_wallet(db, org); result.append({"organization": {"id": org.id, "name": org.name, "slug": org.slug}, "wallet": {**serialize(wallet), **wallet_summary(wallet)}})
    db.commit(); return {"wallets": result, "packs": [serialize(row) for row in db.execute(select(RechargePack).where(RechargePack.is_active.is_(True)).order_by(RechargePack.display_order)).scalars()]}


@router.post("/wallets/packs")
def create_recharge_pack(body: RechargePackBody, actor=Depends(require_platform_permission("wallet.manage")), db: Session = Depends(get_db)):
    row = RechargePack(**body.model_dump())
    db.add(row); db.flush()
    _audit(db, actor, "platform.wallet_pack_created", "recharge_pack", row.id, changes=body.model_dump())
    db.commit(); return serialize(row)


@router.patch("/wallets/packs/{pack_id}")
def update_recharge_pack(pack_id: str, body: RechargePackBody, actor=Depends(require_platform_permission("wallet.manage")), db: Session = Depends(get_db)):
    row = db.get(RechargePack, pack_id)
    if not row: raise HTTPException(404, "Credit pack not found")
    for key, value in body.model_dump().items(): setattr(row, key, value)
    _audit(db, actor, "platform.wallet_pack_updated", "recharge_pack", row.id, changes=body.model_dump())
    db.commit(); return serialize(row)


@router.get("/wallets/{org_id}/ledger")
def wallet_ledger(org_id: str, actor=Depends(require_platform_permission("wallet.view")), db: Session = Depends(get_db)):
    _organization_or_404(db, org_id); return [serialize(row) for row in db.execute(select(WalletLedger).where(WalletLedger.organization_id == org_id).order_by(WalletLedger.created_at.desc()).limit(200)).scalars()]


@router.post("/wallets/{org_id}/recharge")
def recharge_wallet(org_id: str, body: WalletRechargeBody, actor=Depends(require_platform_permission("wallet.manage")), db: Session = Depends(get_db)):
    _require_mfa(db, actor, body.mfa_code); org = _organization_or_404(db, org_id)
    wallet = add_credits(db, org, body.credits, body.idempotency_key, user_id=actor.id, description=body.reason)
    _audit(db, actor, "platform.wallet_recharged", "ai_wallet", wallet.id, org.id, {"credits": body.credits, "reason": body.reason}); db.commit(); return wallet_summary(wallet)


@router.get("/platform-team")
def platform_team(actor=Depends(require_platform_permission("platform_team.view")), db: Session = Depends(get_db)):
    users = db.execute(select(User).where(User.organization_id.is_(None), User.is_super_admin.is_(True)).order_by(User.created_at)).scalars().all()
    roles = db.execute(select(PlatformRole).where(PlatformRole.is_active.is_(True)).order_by(PlatformRole.name)).scalars().all()
    return {"users": [{**serialize(row), "roles": [serialize(role) for role in db.execute(select(PlatformRole).join(PlatformUserRole, PlatformUserRole.role_id == PlatformRole.id).where(PlatformUserRole.user_id == row.id)).scalars()]} for row in users], "roles": [{**serialize(role), "permissions": list(db.execute(select(PlatformPermission.code).join(PlatformRolePermission, PlatformRolePermission.permission_id == PlatformPermission.id).where(PlatformRolePermission.role_id == role.id)).scalars())} for role in roles]}


@router.post("/platform-team")
def add_platform_member(body: TeamMemberBody, request: Request, actor=Depends(require_platform_permission("platform_team.manage")), db: Session = Depends(get_db)):
    if db.execute(select(User).where(User.organization_id.is_(None), User.email == body.email.lower())).scalar_one_or_none(): raise HTTPException(409, "A platform team member already uses this email")
    role = db.get(PlatformRole, body.role_id)
    if not role or role.slug == "platform-owner": raise HTTPException(403, "Platform Owner access must be assigned by an existing owner through role review")
    row = User(organization_id=None, email=body.email.lower(), hashed_password=hash_password(secrets.token_urlsafe(24)), first_name=body.first_name, last_name=body.last_name, is_active=True, is_super_admin=True, email_verified=False)
    db.add(row); db.flush(); db.add(PlatformUserRole(user_id=row.id, role_id=role.id)); _audit(db, actor, "platform.team_member_added", "platform_user", row.id); db.commit()
    from app.api.v1.auth import _deliver_code
    sent, _ = _deliver_code(db, row, "platform_invite", request)
    return {**serialize(row), "invite_sent": sent}


@router.put("/platform-team/{user_id}/role")
def assign_platform_role(user_id: str, body: TeamRoleBody, actor=Depends(require_platform_permission("platform_team.manage")), db: Session = Depends(get_db)):
    target = db.get(User, user_id); role = db.get(PlatformRole, body.role_id)
    if not target or target.organization_id is not None or not role: raise HTTPException(404, "Platform team member or role not found")
    current = db.execute(select(PlatformRole).join(PlatformUserRole, PlatformUserRole.role_id == PlatformRole.id).where(PlatformUserRole.user_id == target.id)).scalars().all()
    if target.id == actor.id and all(item.id != role.id for item in current): raise HTTPException(409, "You cannot change your own platform role")
    if any(item.slug == "platform-owner" for item in current) and role.slug != "platform-owner":
        owners = db.scalar(select(func.count(PlatformUserRole.id)).join(PlatformRole, PlatformRole.id == PlatformUserRole.role_id).where(PlatformRole.slug == "platform-owner")) or 0
        if owners <= 1: raise HTTPException(409, "The final Platform Owner cannot be removed")
    db.query(PlatformUserRole).filter(PlatformUserRole.user_id == target.id).delete(); db.add(PlatformUserRole(user_id=target.id, role_id=role.id)); target.session_version += 1
    _audit(db, actor, "platform.team_role_changed", "platform_user", target.id, changes={"role": role.slug}); db.commit(); return {"ok": True}


@router.get("/support-sessions")
def support_sessions(actor=Depends(require_platform_permission("support.start")), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.execute(select(SupportSession).order_by(SupportSession.created_at.desc()).limit(100)).scalars()]


@router.post("/support-sessions")
def create_support_session(body: SupportBody, actor=Depends(require_platform_permission("support.start")), db: Session = Depends(get_db)):
    org = _organization_or_404(db, body.organization_id); target = db.get(User, body.target_user_id)
    if not target or target.organization_id != org.id or not target.is_active: raise HTTPException(400, "Choose an active user in this organization")
    approval = None
    if body.mode == "limited_write":
        if "support.write" not in platform_permissions(db, actor): raise HTTPException(403, "Your role cannot request temporary changes")
        approval = ApprovalRequest(organization_id=org.id, action_type="support_write", payload=body.model_dump(), reason=body.reason, requested_by_user_id=actor.id, expires_at=now_utc() + timedelta(hours=2))
        db.add(approval); db.flush()
        _audit(db, actor, "platform.support_write_requested", "approval", approval.id, org.id); db.commit()
        return {"approval_required": True, "approval_id": approval.id}
    return _issue_support_session(db, actor, body, approval)


def _issue_support_session(db, actor, body, approval=None):
    token = secrets.token_urlsafe(36)
    row = SupportSession(organization_id=body.organization_id, target_user_id=body.target_user_id, platform_user_id=actor.id, approval_id=approval.id if approval else None, mode=body.mode, reason=body.reason, ticket_reference=body.ticket_reference, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=now_utc() + timedelta(minutes=30))
    db.add(row); db.flush(); _audit(db, actor, "platform.support_session_started", "support_session", row.id, body.organization_id, {"mode": body.mode, "ticket_reference": body.ticket_reference}); db.commit()
    return {"session": serialize(row), "session_token": token}


@router.post("/support-sessions/{session_id}/end")
def end_support_session(session_id: str, actor=Depends(require_platform_permission("support.start")), db: Session = Depends(get_db)):
    row = db.get(SupportSession, session_id)
    if not row: raise HTTPException(404, "Support session not found")
    if row.platform_user_id != actor.id and "operations.manage" not in platform_permissions(db, actor): raise HTTPException(403, "You cannot end this session")
    row.status = "ended"; row.ended_at = now_utc(); _audit(db, actor, "platform.support_session_ended", "support_session", row.id, row.organization_id); db.commit(); return {"ok": True}


@router.get("/support-sessions/requests/mine")
def my_support_requests(actor=Depends(require_platform_permission("support.start")), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.execute(select(ApprovalRequest).where(ApprovalRequest.requested_by_user_id == actor.id, ApprovalRequest.action_type == "support_write").order_by(ApprovalRequest.created_at.desc()).limit(50)).scalars()]


@router.post("/support-sessions/requests/{approval_id}/start")
def start_approved_support_session(approval_id: str, actor=Depends(require_platform_permission("support.start")), db: Session = Depends(get_db)):
    approval = db.get(ApprovalRequest, approval_id)
    if not approval or approval.action_type != "support_write" or approval.requested_by_user_id != actor.id: raise HTTPException(404, "Support request not found")
    if approval.status != "approved": raise HTTPException(409, "This support request has not been approved")
    if approval.expires_at and approval.expires_at <= now_utc(): raise HTTPException(410, "This support approval has expired")
    existing = db.execute(select(SupportSession).where(SupportSession.approval_id == approval.id, SupportSession.status == "active")).scalar_one_or_none()
    if existing: raise HTTPException(409, "The approved support session has already been started")
    return _issue_support_session(db, actor, SupportBody(**approval.payload), approval)


@router.get("/approvals")
def approvals(status: str | None = None, actor=Depends(require_platform_permission("approvals.decide")), db: Session = Depends(get_db)):
    stmt = select(ApprovalRequest)
    if status: stmt = stmt.where(ApprovalRequest.status == status)
    return [serialize(row) for row in db.execute(stmt.order_by(ApprovalRequest.created_at.desc()).limit(200)).scalars()]


@router.post("/approvals/{approval_id}/{decision}")
def decide_approval(approval_id: str, decision: str, body: ApprovalDecision, actor=Depends(require_platform_permission("approvals.decide")), db: Session = Depends(get_db)):
    if decision not in {"approve", "reject"}: raise HTTPException(400, "Unknown decision")
    row = db.get(ApprovalRequest, approval_id)
    if not row or row.status != "pending": raise HTTPException(409, "Approval is no longer pending")
    if row.requested_by_user_id == actor.id: raise HTTPException(409, "The requester cannot approve their own action")
    if row.version != body.version: raise HTTPException(409, "Approval changed. Refresh and try again")
    if row.amount_paise:
        _require_mfa(db, actor, body.mfa_code or "")
    row.status = "approved" if decision == "approve" else "rejected"; row.decided_by_user_id = actor.id; row.decided_at = now_utc(); row.version += 1
    if decision == "approve":
        if row.action_type == "refund": _execute_refund(db, db.get(PlatformRefund, row.payload["refund_id"]), actor)
        elif row.action_type == "support_write": pass
        elif row.action_type == "organization_delete": _approve_deletion(db, actor, db.get(OrganizationDeletionRequest, row.payload["deletion_id"]))
        elif row.action_type == "instant_settlement":
            settlement = PlatformSettlement(provider_settlement_id=f"mock-settlement-{row.id}", mode=row.payload.get("mode", "mock"), amount_paise=row.amount_paise, status="processed", settled_at=now_utc(), meta={"approval_id": row.id})
            db.add(settlement)
    _audit(db, actor, f"platform.approval_{decision}d", "approval", row.id, row.organization_id, {"note": body.note}); db.commit(); return serialize(row)


@router.get("/operations")
def operations(actor=Depends(require_platform_permission("operations.view")), db: Session = Depends(get_db)):
    jobs = db.execute(select(Job).order_by(Job.created_at.desc()).limit(100)).scalars().all(); messages = db.execute(select(OutboundMessage).order_by(OutboundMessage.created_at.desc()).limit(100)).scalars().all(); webhooks = db.execute(select(PaymentEvent).order_by(PaymentEvent.created_at.desc()).limit(100)).scalars().all(); documents = db.execute(select(Document).where(Document.status.in_(["pending", "failed"])).order_by(Document.created_at.desc()).limit(100)).scalars().all()
    payment_gateway = gateway_inventory(db)
    return {"health": {"database": "healthy", "payments": "configured" if payment_gateway["configured"] else "setup_needed", "ai": "configured" if settings.AI_API_KEY else "local_mode", "workers": "attention" if any(row.status == "failed" for row in jobs) else "healthy"}, "jobs": [_safe(row, {"payload", "last_error"}) for row in jobs], "messages": [_safe(row, {"recipient", "body", "last_error"}) for row in messages], "webhooks": [_safe(row, {"payload", "error"}) for row in webhooks], "documents": [_safe(row, {"object_key", "extracted_text", "error"}) for row in documents]}


def _safe(row, hidden):
    return {key: value for key, value in serialize(row).items() if key not in hidden}


@router.post("/operations/jobs/{job_id}/retry")
def retry_job(job_id: str, actor=Depends(require_platform_permission("operations.manage")), db: Session = Depends(get_db)):
    row = db.get(Job, job_id)
    if not row: raise HTTPException(404, "Job not found")
    if row.status not in {"failed", "cancelled"}: raise HTTPException(409, "Only failed work can be retried")
    row.status = "queued"; row.run_at = now_utc(); row.last_error = None; row.locked_at = None
    _audit(db, actor, "platform.job_retried", "job", row.id, row.organization_id); db.commit(); return serialize(row)


@router.post("/operations/webhooks/{event_id}/replay")
def replay_webhook(event_id: str, actor=Depends(require_platform_permission("operations.manage")), db: Session = Depends(get_db)):
    event = db.get(PaymentEvent, event_id)
    if not event: raise HTTPException(404, "Webhook event not found")
    key = f"webhook-replay-{event.id}-{event.updated_at.isoformat()}"
    existing = db.execute(select(Job).where(Job.organization_id == event.organization_id, Job.idempotency_key == key)).scalar_one_or_none() if event.organization_id else None
    if existing: return serialize(existing)
    if not event.organization_id: raise HTTPException(409, "This event is not connected to an organization")
    job = Job(organization_id=event.organization_id, kind="replay_payment_webhook", payload={"payment_event_id": event.id}, status="queued", run_at=now_utc(), idempotency_key=key)
    db.add(job); _audit(db, actor, "platform.webhook_replay_queued", "payment_event", event.id, event.organization_id); db.commit(); return serialize(job)


@router.get("/audit")
def audit(q: str | None = None, organization_id: str | None = None, actor=Depends(require_platform_permission("audit.view")), db: Session = Depends(get_db)):
    stmt = select(AuditLog)
    if organization_id: stmt = stmt.where(AuditLog.organization_id == organization_id)
    if q: stmt = stmt.where(or_(AuditLog.action.ilike(f"%{q}%"), AuditLog.resource_type.ilike(f"%{q}%")))
    return [serialize(row) for row in db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(250)).scalars()]


@router.get("/settings")
def platform_settings(actor=Depends(require_platform_permission("overview.view")), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.execute(select(PlatformSetting).order_by(PlatformSetting.key)).scalars()]


@router.put("/settings/{key}")
def update_setting(key: str, body: SettingsBody, actor=Depends(require_platform_permission("settings.manage")), db: Session = Depends(get_db)):
    if key == "payment_gateway":
        raise HTTPException(409, "Use the Billing gateway control to change the payment provider")
    row = db.execute(select(PlatformSetting).where(PlatformSetting.key == key)).scalar_one_or_none()
    if key == "ai_credit_policy":
        if not row:
            raise HTTPException(409, "AI credit policy has not been initialized")
        current = dict(row.value or {})
        submitted_limits = (body.value or {}).get("route_max_credits") or {}
        required = {"business", "analytics", "knowledge", "action"}
        if set(submitted_limits) != required or any(
            not isinstance(submitted_limits[name], int) or not 1 <= submitted_limits[name] <= 100
            for name in required
        ):
            raise HTTPException(422, "Each request maximum must be between 1 and 100 credits")
        body.value = {**current, "route_max_credits": submitted_limits}
    if key == "ai_models":
        required = {"planner", "synthesis", "repair"}
        if set(body.value or {}) != required or any(
            not isinstance((body.value or {}).get(stage), str)
            or not 1 <= len((body.value or {})[stage].strip()) <= 100
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", (body.value or {})[stage].strip())
            for stage in required
        ):
            raise HTTPException(422, "Planner, synthesis, and repair models must be valid model identifiers")
        body.value = {stage: body.value[stage].strip() for stage in required}
    if not row: row = PlatformSetting(key=key, value=body.value); db.add(row)
    elif row.version != body.version: raise HTTPException(409, "Settings changed. Refresh and try again")
    else: row.value = body.value; row.version += 1
    _audit(db, actor, "platform.settings_updated", "platform_setting", key, changes={"value": body.value}); db.commit(); return serialize(row)


@router.post("/organizations/{org_id}/deletion")
def request_deletion(org_id: str, body: DeletionBody, actor=Depends(require_platform_permission("organizations.delete")), db: Session = Depends(get_db)):
    _require_mfa(db, actor, body.mfa_code); org = _organization_or_404(db, org_id)
    existing = db.execute(select(OrganizationDeletionRequest).where(OrganizationDeletionRequest.organization_id == org.id, OrganizationDeletionRequest.status.in_(["pending_approval", "approved"]))).scalar_one_or_none()
    if existing: return serialize(existing)
    _change_org_state(db, actor, org.id, OrganizationStatusEnum.suspended)
    db.query(Job).filter(Job.organization_id == org.id, Job.status.in_(["queued", "running"])).update({Job.status: "cancelled"})
    row = OrganizationDeletionRequest(organization_id=org.id, organization_name=org.name, organization_slug=org.slug, reason=body.reason, requested_by_user_id=actor.id)
    db.add(row); db.flush(); approval = ApprovalRequest(organization_id=org.id, action_type="organization_delete", payload={"deletion_id": row.id, "idempotency_key": body.idempotency_key}, reason=body.reason, requested_by_user_id=actor.id, expires_at=now_utc() + timedelta(days=7)); db.add(approval)
    _audit(db, actor, "platform.organization_deletion_requested", "deletion_request", row.id, org.id, {"reason": body.reason}); db.commit(); return serialize(row)


def _approve_deletion(db, actor, deletion):
    if not deletion or deletion.status != "pending_approval": raise HTTPException(409, "Deletion request is no longer pending")
    policy = _setting(db, "retention", {"gst_months": 72, "ordinary_grace_days": 30})
    deletion.status = "approved"; deletion.approved_by_user_id = actor.id; deletion.purge_after = now_utc() + timedelta(days=int(policy.get("ordinary_grace_days", 30)))
    invoices = db.execute(select(Invoice).where(Invoice.organization_id == deletion.organization_id)).scalars().all()
    if invoices:
        payload = str([{"invoice_number": row.invoice_number, "amount_paise": row.amount_paise, "created_at": row.created_at.isoformat()} for row in invoices])
        db.add(RetentionArchive(organization_id=deletion.organization_id, organization_slug=deletion.organization_slug, record_type="gst_finance", encrypted_payload=encrypt_secret(payload), retention_reason="GST record retention", purge_at=now_utc() + timedelta(days=30 * int(policy.get("gst_months", 72)))))


@router.get("/health")
def health(actor=Depends(require_platform_permission("overview.view")), db: Session = Depends(get_db)):
    return {"organizations": db.scalar(select(func.count(Organization.id))) or 0, "users": db.scalar(select(func.count(User.id))) or 0, "status": "healthy"}
