"""Deterministic billing, Razorpay integration, and exactly-once fulfillment."""
import logging
from calendar import monthrange
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AIWallet, BillingCheckoutAttempt, BillingProfile, Invoice, Organization,
    PlanDefinition, PlanVersion, PlatformPayment, PlatformSetting,
    ProviderPlanMapping, RechargePack, Subscription,
    SubscriptionSchedule,
)
from app.services.wallet import add_credits, apply_plan_credit_grant, ensure_wallet
from app.services.razorpay_provider import razorpay_provider

logger = logging.getLogger("edvatiq.billing")


def payment_config(require_webhook: bool = False) -> tuple[str, str, str, str]:
    mode = settings.RAZORPAY_MODE
    key_id, key_secret, webhook_secret = settings.razorpay_credentials()
    if mode == "mock":
        if settings.ENVIRONMENT == "production":
            raise HTTPException(503, "Online payments are not configured")
        return mode, "", "", ""
    expected_prefix = f"rzp_{mode}_"
    if not key_id or not key_secret:
        raise HTTPException(503, f"{mode.title()} payments are not configured")
    if not key_id.startswith(expected_prefix):
        raise HTTPException(503, f"The configured payment key does not match {mode} mode")
    if require_webhook and not webhook_secret:
        raise HTTPException(503, f"The {mode} payment webhook is not configured")
    return mode, key_id, key_secret, webhook_secret


def provider_error(exc: Exception, operation: str) -> tuple[str, str]:
    payload = getattr(exc, "error", None) or {}
    code = str(payload.get("code") or getattr(exc, "status_code", None) or type(exc).__name__)[:100]
    description = str(payload.get("description") or payload.get("reason") or str(exc) or "")
    missing_dependency = exc.name if isinstance(exc, ModuleNotFoundError) else None
    status_code = int(getattr(exc, "status_code", 0) or 0)
    request_id = str(getattr(exc, "request_id", "") or "none")[:100]
    safe_description = " ".join(description.split())[:240]
    logger.error(
        "razorpay_%s_failed code=%s status=%s request_id=%s error_type=%s missing_dependency=%s description=%s",
        operation, code, status_code or "none", request_id, type(exc).__name__, missing_dependency or "none", safe_description or "none",
    )
    if missing_dependency:
        return "provider_dependency_missing", "Online payments are temporarily unavailable"
    lowered = description.lower()
    if "subscription" in lowered and any(word in lowered for word in ("enable", "available", "access")):
        return "subscriptions_unavailable", "Automatic renewal is not available for this payment account yet"
    if status_code in {401, 403} or "unauthorized" in lowered or "authentication" in lowered or "credential" in lowered:
        return "provider_authentication", "Online payments are temporarily unavailable"
    if status_code == 429:
        return "provider_busy", "Razorpay is busy right now. Please wait a moment and retry"
    if status_code >= 500 or code.upper() in {"SERVER_ERROR", "GATEWAY_ERROR", "PROVIDER_CONNECTION_ERROR"}:
        return "provider_unavailable", "Razorpay is temporarily unavailable. Please retry in a moment"
    if "active" in lowered or "state" in lowered:
        return "invalid_subscription_state", "This subscription is still being updated. Please refresh shortly"
    return code, "The payment provider could not start this checkout. Please try again"


def _setting(db: Session, key: str, default: dict) -> dict:
    row = db.execute(select(PlatformSetting).where(PlatformSetting.key == key)).scalar_one_or_none()
    return row.value if row else default


def tax_quote(db: Session, organization: Organization, subtotal_paise: int, *, tax_enabled: bool, gst_rate_bps: int) -> dict:
    profile = db.execute(select(BillingProfile).where(BillingProfile.organization_id == organization.id)).scalar_one_or_none()
    exempt = bool(profile and profile.tax_exempt)
    effective = bool(tax_enabled and not exempt and gst_rate_bps > 0)
    tax = (subtotal_paise * gst_rate_bps + 5000) // 10000 if effective else 0
    identity = _setting(db, "billing_identity", {"registered_state": "Tamil Nadu"})
    seller_state = str(identity.get("registered_state") or "Tamil Nadu").strip().casefold()
    buyer_state = str(profile.state if profile and profile.state else "").strip().casefold()
    interstate = bool(buyer_state and seller_state and buyer_state != seller_state)
    return {
        "tax_enabled": effective,
        "configured_tax_enabled": bool(tax_enabled),
        "tax_exempt": exempt,
        "gst_rate_bps": gst_rate_bps if effective else 0,
        "tax_paise": tax,
        "cgst_paise": 0 if interstate else tax // 2,
        "sgst_paise": 0 if interstate else tax - tax // 2,
        "igst_paise": tax if interstate else 0,
        "total_paise": subtotal_paise + tax,
        "tax_reason": "organization_exempt" if exempt else "plan_disabled" if not tax_enabled else "applied",
        "billing_profile": {
            "legal_name": profile.legal_name if profile else organization.legal_name or organization.name,
            "gstin": profile.gstin if profile else organization.gstin,
            "state": profile.state if profile else None,
            "tax_exemption_meta": profile.tax_exemption_meta if exempt else {},
        },
    }


def plan_pair(db: Session, slug: str) -> tuple[PlanDefinition, PlanVersion]:
    row = db.execute(
        select(PlanDefinition, PlanVersion).join(PlanVersion, PlanVersion.plan_id == PlanDefinition.id)
        .where(PlanDefinition.slug == slug, PlanDefinition.is_active.is_(True), PlanVersion.status == "published")
        .order_by(PlanVersion.version.desc())
    ).first()
    if not row:
        raise HTTPException(404, "Plan not found")
    return row


def plan_price(version: PlanVersion, interval: str) -> int:
    value = version.monthly_price_paise if interval == "monthly" else version.annual_price_paise
    if value is None:
        raise HTTPException(400, "Contact sales for this plan")
    return int(value)


def create_invoice(
    db: Session, organization: Organization, *, purchase_type: str, subtotal_paise: int,
    description: str, tax_enabled: bool, gst_rate_bps: int, billing_interval: str | None,
    snapshot: dict,
) -> Invoice:
    quote = tax_quote(db, organization, subtotal_paise, tax_enabled=tax_enabled, gst_rate_bps=gst_rate_bps)
    mode = settings.RAZORPAY_MODE
    now = datetime.now(timezone.utc)
    invoice = Invoice(
        organization_id=organization.id,
        amount_paise=quote["total_paise"], subtotal_paise=subtotal_paise,
        tax_paise=quote["tax_paise"], cgst_paise=quote["cgst_paise"],
        sgst_paise=quote["sgst_paise"], igst_paise=quote["igst_paise"],
        tax_enabled=quote["tax_enabled"], gst_rate_bps=quote["gst_rate_bps"],
        purchase_type=purchase_type, billing_interval=billing_interval,
        fulfillment_status="pending", provider_mode=mode, currency="INR", status="created",
        description=description, billing_snapshot={**quote["billing_profile"], "tax_reason": quote["tax_reason"]},
        plan_snapshot={**snapshot, "tax_enabled": quote["tax_enabled"], "gst_rate_bps": quote["gst_rate_bps"]},
    )
    db.add(invoice)
    db.flush()
    invoice.invoice_number = f"EDV-{now:%Y%m}-{invoice.id[:8].upper()}"
    return invoice


def provider_order(db: Session, invoice: Invoice) -> tuple[str | None, str | None]:
    mode, key_id, key_secret, _ = payment_config()
    if mode == "mock":
        return None, None
    try:
        order = razorpay_provider(key_id, key_secret).create_order({
            "amount": int(invoice.amount_paise), "currency": invoice.currency,
            "receipt": invoice.id[:40],
            "notes": {"invoice_id": invoice.id, "organization_id": invoice.organization_id, "purchase_type": invoice.purchase_type, "mode": mode},
        })
        invoice.razorpay_order_id = order["id"]
        return order["id"], None
    except Exception as exc:
        code, message = provider_error(exc, "order")
        return None, f"{code}|{message}"


def ensure_provider_plan(db: Session, version: PlanVersion, definition: PlanDefinition, interval: str, amount_paise: int) -> ProviderPlanMapping:
    mode, key_id, key_secret, _ = payment_config()
    row = db.execute(select(ProviderPlanMapping).where(
        ProviderPlanMapping.plan_version_id == version.id,
        ProviderPlanMapping.billing_interval == interval,
        ProviderPlanMapping.provider_mode == mode,
        ProviderPlanMapping.amount_paise == amount_paise,
    ).with_for_update()).scalar_one_or_none()
    if row and row.status == "active" and row.provider_plan_id:
        return row
    if not row:
        row = ProviderPlanMapping(plan_version_id=version.id, billing_interval=interval, provider_mode=mode, amount_paise=amount_paise)
        db.add(row)
        db.flush()
    if mode == "mock":
        row.provider_plan_id = f"mock-plan-{row.id}"
        row.status = "active"
        return row
    try:
        result = razorpay_provider(key_id, key_secret).create_plan({
            "period": "monthly" if interval == "monthly" else "yearly",
            "interval": 1,
            "item": {"name": f"Edvatiq {definition.name}", "amount": amount_paise, "currency": "INR", "description": f"{definition.name} {interval} subscription"},
            "notes": {"plan_version_id": version.id, "mode": mode},
        })
        row.provider_plan_id = result["id"]
        row.status = "active"
        row.last_error_code = None
        return row
    except Exception as exc:
        code, message = provider_error(exc, "plan")
        row.status = "failed"
        row.last_error_code = code
        row.last_error_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(502, message) from exc


def provider_subscription(db: Session, mapping: ProviderPlanMapping, organization: Organization, version: PlanVersion, idempotency_key: str, start_at: datetime | None = None) -> str | None:
    mode, key_id, key_secret, _ = payment_config()
    if mode == "mock":
        return f"mock-sub-{idempotency_key[-20:]}"
    payload = {
        "plan_id": mapping.provider_plan_id,
        "total_count": 120 if mapping.billing_interval == "monthly" else 10,
        "client_notify": 1,
        "notes": {"organization_id": organization.id, "plan_version_id": version.id, "idempotency_key": idempotency_key, "mode": mode},
    }
    if start_at and start_at > datetime.now(timezone.utc):
        payload["start_at"] = int(start_at.timestamp())
    try:
        return razorpay_provider(key_id, key_secret).create_subscription(payload)["id"]
    except Exception as exc:
        _, message = provider_error(exc, "subscription")
        raise HTTPException(502, message) from exc


def update_provider_subscription(subscription: Subscription, mapping: ProviderPlanMapping, *, at_cycle_end: bool) -> None:
    mode, key_id, key_secret, _ = payment_config()
    if mode == "mock" or not subscription.razorpay_subscription_id:
        return
    try:
        razorpay_provider(key_id, key_secret).update_subscription(subscription.razorpay_subscription_id, {
            "plan_id": mapping.provider_plan_id,
            "schedule_change_at": "cycle_end" if at_cycle_end else "now",
            "client_notify": True,
        })
    except Exception as exc:
        _, message = provider_error(exc, "subscription_update")
        raise HTTPException(502, message) from exc


def cancel_provider_subscription(subscription: Subscription, *, at_cycle_end: bool = True) -> None:
    mode, key_id, key_secret, _ = payment_config()
    if mode == "mock" or not subscription.razorpay_subscription_id:
        return
    try:
        razorpay_provider(key_id, key_secret).cancel_subscription(
            subscription.razorpay_subscription_id, {"cancel_at_cycle_end": 1 if at_cycle_end else 0},
        )
    except Exception as exc:
        _, message = provider_error(exc, "subscription_cancel")
        raise HTTPException(502, message) from exc


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def fulfill_invoice(db: Session, invoice: Invoice, payment_id: str | None) -> dict:
    invoice = db.execute(select(Invoice).where(Invoice.id == invoice.id).with_for_update()).scalar_one()
    if invoice.fulfillment_status == "fulfilled":
        return {"status": "paid", "purchase_type": invoice.purchase_type, "already_fulfilled": True}
    organization = db.get(Organization, invoice.organization_id)
    if not organization:
        raise HTTPException(404, "Business not found")
    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    if payment_id:
        invoice.razorpay_payment_id = payment_id
    if invoice.purchase_type == "plan":
        version_id = (invoice.plan_snapshot or {}).get("plan_version_id")
        version = db.get(PlanVersion, version_id) if version_id else None
        definition = db.get(PlanDefinition, version.plan_id) if version else None
        if not version or not definition:
            raise HTTPException(409, "Invoice has no valid plan version")
        subscription = db.execute(select(Subscription).where(Subscription.organization_id == organization.id).with_for_update()).scalars().first()
        if not subscription:
            subscription = Subscription(organization_id=organization.id, plan=definition.slug)
            db.add(subscription)
            db.flush()
        now = datetime.now(timezone.utc)
        subscription.plan = definition.slug
        subscription.plan_version_id = version.id
        subscription.billing_interval = invoice.billing_interval or "monthly"
        subscription.provider_mode = invoice.provider_mode
        subscription.status = "active"
        subscription.current_period_start = now
        subscription.current_period_end = add_months(now, 12 if subscription.billing_interval == "annual" else 1)
        subscription.version += 1
        organization.plan = definition.slug
        apply_plan_credit_grant(db, organization, subscription, int(version.included_ai_credits))
    elif invoice.purchase_type == "wallet_pack":
        credits = int((invoice.plan_snapshot or {}).get("credits") or 0)
        if credits <= 0:
            raise HTTPException(409, "Invoice has no valid credit pack")
        wallet = ensure_wallet(db, organization)
        add_credits(
            db, organization, credits, f"wallet-pack:{invoice.id}", source_type="wallet_pack",
            source_id=(invoice.plan_snapshot or {}).get("pack_id"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            description=f"{credits:,} AI credit recharge",
        )
    else:
        raise HTTPException(409, "Unsupported invoice purchase type")
    invoice.fulfillment_status = "fulfilled"
    if payment_id and not db.execute(select(PlatformPayment).where(PlatformPayment.provider_payment_id == payment_id)).scalar_one_or_none():
        db.add(PlatformPayment(
            organization_id=organization.id, invoice_id=invoice.id, provider_payment_id=payment_id,
            provider_order_id=invoice.razorpay_order_id, mode=invoice.provider_mode,
            amount_paise=invoice.amount_paise, currency=invoice.currency, status="captured",
            captured_at=datetime.now(timezone.utc), meta={"purchase_type": invoice.purchase_type},
        ))
    return {"status": "paid", "purchase_type": invoice.purchase_type, "already_fulfilled": False}


def activate_subscription_schedule(
    db: Session, subscription: Subscription, *, period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> Subscription:
    schedule = db.execute(select(SubscriptionSchedule).where(
        SubscriptionSchedule.subscription_id == subscription.id,
        SubscriptionSchedule.status == "scheduled",
    ).order_by(SubscriptionSchedule.created_at.desc()).with_for_update()).scalars().first()
    if not schedule:
        return subscription
    now = datetime.now(timezone.utc)
    if schedule.action == "cancel":
        subscription.status = "cancelled"
        subscription.cancel_at_cycle_end = False
    elif schedule.target_plan_version_id:
        version = db.get(PlanVersion, schedule.target_plan_version_id)
        definition = db.get(PlanDefinition, version.plan_id) if version else None
        organization = db.get(Organization, subscription.organization_id)
        if not version or not definition or not organization:
            raise HTTPException(409, "Scheduled plan is no longer available")
        subscription.plan_version_id = version.id
        subscription.scheduled_plan_version_id = None
        subscription.plan = definition.slug
        subscription.billing_interval = schedule.billing_interval or subscription.billing_interval
        subscription.status = "active"
        subscription.current_period_start = period_start or now
        subscription.current_period_end = period_end or add_months(subscription.current_period_start, 12 if subscription.billing_interval == "annual" else 1)
        organization.plan = definition.slug
        apply_plan_credit_grant(db, organization, subscription, int(version.included_ai_credits))
    subscription.version += 1
    schedule.status = "completed"
    schedule.version += 1
    return subscription


def checkout_attempt(db: Session, organization_id: str, idempotency_key: str) -> BillingCheckoutAttempt | None:
    return db.execute(select(BillingCheckoutAttempt).where(
        BillingCheckoutAttempt.organization_id == organization_id,
        BillingCheckoutAttempt.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
