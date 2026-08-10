"""Tenant billing, Razorpay checkout, plan scheduling, and AI recharges."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    AIWallet, BillingCheckoutAttempt, FeatureDefinition, Invoice, Job, Organization,
    PaymentEvent, PlanDefinition, PlanEntitlement, PlanVersion, PlatformPayment,
    ProviderPlanMapping, RechargePack, Subscription, SubscriptionSchedule,
    WalletCreditGrant,
)
from app.schemas import CreateOrderRequest, VerifyRazorpayPaymentRequest
from app.services.billing import (
    activate_subscription_schedule, cancel_provider_subscription, checkout_attempt,
    create_invoice, ensure_provider_plan, fulfill_invoice, payment_config, plan_pair,
    plan_price, provider_error, provider_order, provider_subscription, tax_quote,
    update_provider_subscription,
)
from app.services.wallet import ensure_wallet, wallet_summary
from app.services.subscriptions import effective_subscription_status, start_trial
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size

router = APIRouter(prefix="/billing", tags=["billing"])


class PlanSelection(BaseModel):
    plan: str
    billing_interval: str = Field(default="monthly", pattern="^(monthly|annual)$")


class CheckoutBody(PlanSelection):
    renewal_mode: str = Field(default="auto_renew", pattern="^(auto_renew|one_time)$")
    idempotency_key: str = Field(min_length=8, max_length=160)


class RecurringSubscriptionBody(PlanSelection):
    idempotency_key: str = Field(min_length=8, max_length=160)


class PackCheckoutBody(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class ScheduleBody(PlanSelection):
    timing: str = Field(default="cycle_end", pattern="^(immediate|cycle_end)$")
    replace_pending: bool = False
    reason: str = Field(default="Plan change requested", min_length=5, max_length=500)
    version: int = Field(ge=1)


class CancelBody(BaseModel):
    at_cycle_end: bool = True
    reason: str = Field(default="Cancellation requested", min_length=5, max_length=500)
    version: int = Field(ge=1)


# Compatibility for existing tests and imports.
def _payment_config(require_webhook: bool = False):
    return payment_config(require_webhook)


def _row(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _subscription_row(row: Subscription) -> dict:
    payload = _row(row)
    payload["status"] = effective_subscription_status(row)
    return payload


def _organization(db: Session, user) -> Organization:
    organization = db.get(Organization, user.organization_id)
    if not organization:
        raise HTTPException(404, "Business not found")
    return organization


def _current_subscription(db: Session, organization_id: str, lock: bool = False) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.organization_id == organization_id).order_by(Subscription.created_at.desc())
    if lock:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalars().first()


def _features(db: Session, version_id: str) -> tuple[dict, list[dict]]:
    rows = db.execute(
        select(FeatureDefinition, PlanEntitlement.value)
        .join(PlanEntitlement, PlanEntitlement.feature_id == FeatureDefinition.id)
        .where(PlanEntitlement.plan_version_id == version_id, FeatureDefinition.is_active.is_(True))
        .order_by(FeatureDefinition.category, FeatureDefinition.name)
    ).all()
    entitlements = {definition.code: value.get("value") for definition, value in rows}
    included = [{"code": definition.code, "name": definition.name, "category": definition.category, "description": definition.description} for definition, value in rows if definition.value_type == "boolean" and value.get("value")]
    return entitlements, included


def _plan_payload(db: Session, organization: Organization, definition: PlanDefinition, version: PlanVersion) -> dict:
    entitlements, included = _features(db, version.id)
    monthly = tax_quote(db, organization, int(version.monthly_price_paise or 0), tax_enabled=version.tax_enabled, gst_rate_bps=version.gst_rate_bps) if version.monthly_price_paise is not None else None
    annual = tax_quote(db, organization, int(version.annual_price_paise or 0), tax_enabled=version.tax_enabled, gst_rate_bps=version.gst_rate_bps) if version.annual_price_paise is not None else None
    return {
        "id": definition.slug, "definition_id": definition.id, "version_id": version.id,
        "version": version.version, "name": definition.name, "description": definition.description,
        "recommended": definition.slug == "growth", "purchasable": definition.slug != "trial" and version.monthly_price_paise is not None,
        "monthly_price_paise": version.monthly_price_paise, "annual_price_paise": version.annual_price_paise,
        "price_paise": version.monthly_price_paise, "tax_enabled": version.tax_enabled,
        "gst_rate_bps": version.gst_rate_bps, "monthly_quote": monthly, "annual_quote": annual,
        "ai_credits": version.included_ai_credits, "support_level": version.support_level,
        "ai_tier": version.ai_tier, "employee_limit": entitlements.get("limits.employees"),
        "client_limit": entitlements.get("limits.clients"), "location_limit": entitlements.get("limits.locations"),
        "storage_limit_mb": entitlements.get("limits.storage_mb"), "entitlements": entitlements,
        "features": included, "feature_names": [item["name"] for item in included],
    }


@router.get("/plans")
def plans(user=Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    organization = _organization(db, user)
    rows = db.execute(
        select(PlanDefinition, PlanVersion).join(PlanVersion, PlanVersion.plan_id == PlanDefinition.id)
        .where(PlanDefinition.is_public.is_(True), PlanDefinition.is_active.is_(True), PlanVersion.status == "published")
        .order_by(PlanDefinition.display_order, PlanVersion.version.desc())
    ).all()
    seen = set(); payload = []
    for definition, version in rows:
        if definition.id in seen:
            continue
        seen.add(definition.id)
        payload.append(_plan_payload(db, organization, definition, version))
    return {"plans": payload}


@router.get("/configuration")
def payment_configuration(user=Depends(require_permissions("billing.view"))):
    mode = settings.RAZORPAY_MODE
    key_id, key_secret, webhook_secret = settings.razorpay_credentials()
    configured = mode == "mock" or bool(key_id and key_secret and key_id.startswith(f"rzp_{mode}_"))
    return {"mode": mode, "configured": configured, "webhook_configured": mode == "mock" or bool(webhook_secret)}


@router.get("/subscription")
def subscription(user=Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    row = _current_subscription(db, user.organization_id)
    schedule = db.execute(select(SubscriptionSchedule).where(SubscriptionSchedule.organization_id == user.organization_id, SubscriptionSchedule.status == "scheduled").order_by(SubscriptionSchedule.created_at.desc())).scalars().first()
    return {"subscription": _subscription_row(row) if row else None, "scheduled_change": _row(schedule) if schedule else None}


@router.get("/invoices")
def invoices(user=Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(Invoice).where(Invoice.organization_id == user.organization_id).order_by(Invoice.created_at.desc()).limit(100)).scalars()
    return [_row(row) for row in rows]


def _invoice_summary(db: Session, organization_id: str) -> dict:
    row = db.execute(select(
        func.count(Invoice.id),
        func.coalesce(func.sum(case((Invoice.status == "paid", 1), else_=0)), 0),
        func.coalesce(func.sum(Invoice.amount_paise), 0),
    ).where(Invoice.organization_id == organization_id)).one()
    return {
        "total": int(row[0] or 0),
        "paid": int(row[1] or 0),
        "amount_paise": int(row[2] or 0),
    }


@router.get("/invoices/page")
def invoice_page(
    status_filter: str | None = Query(default=None, alias="status", max_length=30),
    purchase_type: str | None = Query(default=None, max_length=30),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    user=Depends(require_permissions("billing.view")),
    db: Session = Depends(get_db),
):
    filters = {"status": status_filter, "purchase_type": purchase_type}
    values = decode_cursor(
        cursor,
        scope="billing.invoices",
        organization_id=user.organization_id,
        filters=filters,
    )
    statement = select(Invoice).where(Invoice.organization_id == user.organization_id)
    if status_filter and status_filter != "all":
        statement = statement.where(Invoice.status == status_filter)
    if purchase_type and purchase_type != "all":
        statement = statement.where(Invoice.purchase_type == purchase_type)
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            Invoice.created_at < pivot_at,
            and_(Invoice.created_at == pivot_at, Invoice.id < str(values["id"])),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(Invoice.created_at.desc(), Invoice.id.desc()).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="billing.invoices",
        organization_id=user.organization_id,
        filters=filters,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    return {
        "items": [_row(row) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "summary": _invoice_summary(db, user.organization_id),
    }


@router.get("/wallet/packs")
def wallet_packs(user=Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    organization = _organization(db, user)
    wallet = ensure_wallet(db, organization)
    packs = []
    for pack in db.execute(select(RechargePack).where(RechargePack.is_active.is_(True)).order_by(RechargePack.display_order)).scalars():
        quote = tax_quote(db, organization, pack.price_paise, tax_enabled=pack.tax_enabled, gst_rate_bps=pack.gst_rate_bps)
        packs.append({
            **_row(pack), "quote": quote,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=365),
        })
    grants = db.execute(select(WalletCreditGrant).where(WalletCreditGrant.organization_id == organization.id, WalletCreditGrant.remaining_credits > 0).order_by(WalletCreditGrant.expires_at)).scalars().all()
    return {"wallet": wallet_summary(wallet), "packs": packs, "active_grants": [_row(item) for item in grants]}


@router.get("/overview")
def billing_overview(user=Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    recent_invoices = list(db.execute(select(Invoice).where(
        Invoice.organization_id == user.organization_id,
    ).order_by(Invoice.created_at.desc(), Invoice.id.desc()).limit(5)).scalars())
    return {
        **plans(user, db), **subscription(user, db),
        "payment": payment_configuration(user),
        "wallet": wallet_packs(user, db),
        "invoices": [_row(row) for row in recent_invoices],
        "invoice_summary": _invoice_summary(db, user.organization_id),
    }


@router.post("/checkout/preview")
def checkout_preview(body: PlanSelection, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    organization = _organization(db, user)
    definition, version = plan_pair(db, body.plan)
    if definition.slug == "trial":
        raise HTTPException(400, "Trial is not a purchasable plan")
    subtotal = plan_price(version, body.billing_interval)
    quote = tax_quote(db, organization, subtotal, tax_enabled=version.tax_enabled, gst_rate_bps=version.gst_rate_bps)
    return {"plan": _plan_payload(db, organization, definition, version), "billing_interval": body.billing_interval, **quote}


def _attempt_response(db: Session, attempt: BillingCheckoutAttempt) -> dict | None:
    if attempt.status != "ready":
        return None
    if attempt.invoice_id:
        invoice = db.get(Invoice, attempt.invoice_id)
        return _order_response(invoice) if invoice else None
    if attempt.subscription_id:
        subscription_row = db.get(Subscription, attempt.subscription_id)
        return _subscription_response(subscription_row) if subscription_row else None
    return None


def _order_response(invoice: Invoice) -> dict:
    return {
        "checkout_type": "order", "order_id": invoice.razorpay_order_id,
        "invoice_id": invoice.id, "amount_paise": int(invoice.amount_paise),
        "currency": invoice.currency, "key_id": payment_config()[1] or None,
        "mode": invoice.provider_mode, "mock_mode": invoice.provider_mode == "mock",
        "purchase_type": invoice.purchase_type,
    }


def _subscription_response(subscription_row: Subscription) -> dict:
    return {
        "checkout_type": "subscription", "subscription": _row(subscription_row),
        "checkout": {"subscription_id": subscription_row.razorpay_subscription_id, "key_id": payment_config()[1] or None, "mode": subscription_row.provider_mode},
    }


@router.post("/checkout")
def create_checkout(body: CheckoutBody, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    organization = _organization(db, user)
    existing = checkout_attempt(db, organization.id, body.idempotency_key)
    if existing:
        response = _attempt_response(db, existing)
        if response:
            return response
        if existing.status == "creating":
            raise HTTPException(409, "This checkout is already being prepared")
    definition, version = plan_pair(db, body.plan)
    if definition.slug == "trial":
        raise HTTPException(400, "Trial is not a purchasable plan")
    subtotal = plan_price(version, body.billing_interval)
    quote = tax_quote(db, organization, subtotal, tax_enabled=version.tax_enabled, gst_rate_bps=version.gst_rate_bps)
    mode = payment_config()[0]
    attempt = existing or BillingCheckoutAttempt(organization_id=organization.id, purchase_type="plan", idempotency_key=body.idempotency_key, provider_mode=mode)
    db.add(attempt); db.flush()
    if body.renewal_mode == "one_time":
        invoice = create_invoice(
            db, organization, purchase_type="plan", subtotal_paise=subtotal,
            description=f"{definition.name} {body.billing_interval} plan", tax_enabled=version.tax_enabled,
            gst_rate_bps=version.gst_rate_bps, billing_interval=body.billing_interval,
            snapshot={"slug": definition.slug, "name": definition.name, "plan_version_id": version.id, "version": version.version, "reference_id": body.idempotency_key},
        )
        attempt.invoice_id = invoice.id
        order_id, error = provider_order(db, invoice)
        if error:
            code, message = error.split("|", 1)
            attempt.status = "failed"; attempt.error_code = code; invoice.status = "failed"
            db.commit()
            raise HTTPException(502, message)
        attempt.provider_reference = order_id
        attempt.status = "ready"
        db.commit(); db.refresh(invoice)
        return _order_response(invoice)

    subscription_row = _current_subscription(db, organization.id, lock=True)
    if not subscription_row:
        subscription_row = Subscription(organization_id=organization.id, plan=getattr(organization.plan, "value", organization.plan), status="trialing", provider_mode=mode)
        if getattr(organization.plan, "value", organization.plan) == "trial":
            start_trial(subscription_row)
        db.add(subscription_row); db.flush()
    if subscription_row.razorpay_subscription_id and subscription_row.status in {"created", "authenticated", "active", "pending", "halted", "paused"}:
        attempt.status = "failed"; attempt.error_code = "existing_subscription"; db.commit()
        raise HTTPException(409, "An automatic renewal already exists. Schedule a plan change instead")
    mapping = ensure_provider_plan(db, version, definition, body.billing_interval, quote["total_paise"])
    start_at = subscription_row.trial_end if subscription_row.status == "trialing" and subscription_row.trial_end else None
    try:
        provider_id = provider_subscription(db, mapping, organization, version, body.idempotency_key, start_at)
    except HTTPException:
        attempt.status = "failed"; attempt.error_code = "subscription_creation_failed"
        db.commit()
        raise
    pending = db.execute(select(SubscriptionSchedule).where(SubscriptionSchedule.subscription_id == subscription_row.id, SubscriptionSchedule.status == "scheduled")).scalar_one_or_none()
    if pending:
        pending.status = "replaced"; pending.version += 1
    schedule = SubscriptionSchedule(
        organization_id=organization.id, subscription_id=subscription_row.id, target_plan_version_id=version.id,
        billing_interval=body.billing_interval, action="activate", effective_at=start_at or datetime.now(timezone.utc),
        provider_reference=mapping.provider_plan_id, reason="Automatic renewal authorized",
    )
    db.add(schedule)
    subscription_row.provider_mode = mode
    subscription_row.razorpay_plan_id = mapping.provider_plan_id
    subscription_row.razorpay_subscription_id = provider_id
    subscription_row.scheduled_plan_version_id = version.id
    subscription_row.status = "active" if mode == "mock" else "created"
    subscription_row.version += 1
    attempt.subscription_id = subscription_row.id; attempt.provider_reference = provider_id; attempt.status = "ready"
    if mode == "mock":
        activate_subscription_schedule(db, subscription_row)
    db.commit(); db.refresh(subscription_row)
    response = _subscription_response(subscription_row)
    response["amount_paise"] = quote["total_paise"]
    return response


@router.post("/wallet/packs/{pack_id}/checkout")
def create_pack_checkout(pack_id: str, body: PackCheckoutBody, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    organization = _organization(db, user)
    existing = checkout_attempt(db, organization.id, body.idempotency_key)
    if existing:
        response = _attempt_response(db, existing)
        if response:
            return response
        if existing.status == "creating":
            raise HTTPException(409, "This checkout is already being prepared")
    pack = db.get(RechargePack, pack_id)
    if not pack or not pack.is_active:
        raise HTTPException(404, "Credit pack not found")
    attempt = existing or BillingCheckoutAttempt(organization_id=organization.id, purchase_type="wallet_pack", idempotency_key=body.idempotency_key, provider_mode=payment_config()[0])
    db.add(attempt); db.flush()
    invoice = create_invoice(
        db, organization, purchase_type="wallet_pack", subtotal_paise=pack.price_paise,
        description=f"{pack.name} AI credits", tax_enabled=pack.tax_enabled,
        gst_rate_bps=pack.gst_rate_bps, billing_interval=None,
        snapshot={"pack_id": pack.id, "name": pack.name, "credits": pack.credits, "reference_id": body.idempotency_key},
    )
    attempt.invoice_id = invoice.id
    order_id, error = provider_order(db, invoice)
    if error:
        code, message = error.split("|", 1)
        attempt.status = "failed"; attempt.error_code = code; invoice.status = "failed"
        db.commit(); raise HTTPException(502, message)
    attempt.provider_reference = order_id; attempt.status = "ready"
    db.commit(); db.refresh(invoice)
    return _order_response(invoice)


@router.post("/subscription/schedule")
def schedule_plan_change(body: ScheduleBody, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    organization = _organization(db, user)
    subscription_row = _current_subscription(db, organization.id, lock=True)
    if not subscription_row or subscription_row.status not in {"active", "authenticated"}:
        raise HTTPException(409, "There is no active automatic renewal to update")
    if subscription_row.version != body.version:
        raise HTTPException(409, "Your subscription changed. Refresh and try again")
    definition, version = plan_pair(db, body.plan)
    subtotal = plan_price(version, body.billing_interval)
    quote = tax_quote(db, organization, subtotal, tax_enabled=version.tax_enabled, gst_rate_bps=version.gst_rate_bps)
    mapping = ensure_provider_plan(db, version, definition, body.billing_interval, quote["total_paise"])
    pending = db.execute(select(SubscriptionSchedule).where(SubscriptionSchedule.subscription_id == subscription_row.id, SubscriptionSchedule.status == "scheduled").with_for_update()).scalar_one_or_none()
    if pending and not body.replace_pending:
        raise HTTPException(409, "A plan change is already scheduled. Confirm replacement to continue")
    if pending:
        pending.status = "replaced"; pending.version += 1
    at_cycle_end = body.timing == "cycle_end"
    update_provider_subscription(subscription_row, mapping, at_cycle_end=at_cycle_end)
    effective_at = subscription_row.current_period_end if at_cycle_end and subscription_row.current_period_end else datetime.now(timezone.utc)
    schedule = SubscriptionSchedule(
        organization_id=organization.id, subscription_id=subscription_row.id,
        target_plan_version_id=version.id, billing_interval=body.billing_interval,
        action="change", effective_at=effective_at, provider_reference=mapping.provider_plan_id,
        reason=body.reason,
    )
    db.add(schedule)
    subscription_row.scheduled_plan_version_id = version.id; subscription_row.version += 1
    db.flush()
    db.add(Job(
        organization_id=organization.id, kind="subscription_transition",
        payload={"schedule_id": schedule.id}, run_at=effective_at,
        idempotency_key=f"subscription-transition:{schedule.id}",
    ))
    if payment_config()[0] == "mock" and not at_cycle_end:
        activate_subscription_schedule(db, subscription_row)
    db.commit()
    return {"subscription": _row(subscription_row), "scheduled_change": _row(schedule)}


@router.post("/subscription/cancel")
def cancel_subscription(body: CancelBody, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    organization = _organization(db, user)
    subscription_row = _current_subscription(db, organization.id, lock=True)
    if not subscription_row or subscription_row.status not in {"active", "authenticated", "paused", "past_due"}:
        raise HTTPException(409, "There is no active subscription to cancel")
    if subscription_row.version != body.version:
        raise HTTPException(409, "Your subscription changed. Refresh and try again")
    pending = db.execute(select(SubscriptionSchedule).where(SubscriptionSchedule.subscription_id == subscription_row.id, SubscriptionSchedule.status == "scheduled").with_for_update()).scalar_one_or_none()
    if pending:
        pending.status = "replaced"; pending.version += 1
    cancel_provider_subscription(subscription_row, at_cycle_end=body.at_cycle_end)
    effective_at = subscription_row.current_period_end if body.at_cycle_end and subscription_row.current_period_end else datetime.now(timezone.utc)
    schedule = SubscriptionSchedule(
        organization_id=organization.id, subscription_id=subscription_row.id,
        action="cancel", effective_at=effective_at, reason=body.reason,
    )
    db.add(schedule); subscription_row.cancel_at_cycle_end = body.at_cycle_end; subscription_row.version += 1
    db.flush(); db.add(Job(organization_id=organization.id, kind="subscription_transition", payload={"schedule_id": schedule.id}, run_at=effective_at, idempotency_key=f"subscription-transition:{schedule.id}"))
    if payment_config()[0] == "mock" and not body.at_cycle_end:
        activate_subscription_schedule(db, subscription_row)
    db.commit()
    return {"subscription": _row(subscription_row), "scheduled_change": _row(schedule)}


@router.delete("/subscription/scheduled-change")
def remove_scheduled_change(user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    subscription_row = _current_subscription(db, user.organization_id, lock=True)
    schedule = db.execute(select(SubscriptionSchedule).where(SubscriptionSchedule.organization_id == user.organization_id, SubscriptionSchedule.status == "scheduled").with_for_update()).scalar_one_or_none()
    if not schedule:
        raise HTTPException(404, "No plan change is scheduled")
    schedule.status = "cancelled"; schedule.version += 1
    if subscription_row:
        subscription_row.scheduled_plan_version_id = None; subscription_row.cancel_at_cycle_end = False; subscription_row.version += 1
    db.commit()
    return {"ok": True}


# One-release compatibility wrappers.
@router.post("/subscriptions")
def start_recurring_subscription(body: RecurringSubscriptionBody, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    return create_checkout(CheckoutBody(**body.model_dump(), renewal_mode="auto_renew"), user, db)


@router.post("/orders")
def create_order(body: CreateOrderRequest, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    return create_checkout(CheckoutBody(plan=body.plan, billing_interval=getattr(body, "billing_interval", "monthly"), renewal_mode="one_time", idempotency_key=str(uuid4())), user, db)


@router.post("/orders/{invoice_id}/mock-pay")
def mock_pay(invoice_id: str, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    if settings.RAZORPAY_MODE != "mock":
        raise HTTPException(404, "Not available")
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.organization_id != user.organization_id:
        raise HTTPException(404, "Invoice not found")
    result = fulfill_invoice(db, invoice, f"mock-{invoice.id}")
    db.commit()
    return {"ok": True, **result}


@router.post("/payments/verify")
def verify_payment(body: VerifyRazorpayPaymentRequest, user=Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    mode, _, key_secret, _ = payment_config()
    if mode == "mock":
        raise HTTPException(404, "Not available")
    invoice = db.get(Invoice, body.invoice_id)
    if not invoice or invoice.organization_id != user.organization_id:
        raise HTTPException(404, "Invoice not found")
    if invoice.provider_mode != mode or invoice.razorpay_order_id != body.razorpay_order_id:
        raise HTTPException(409, "Payment does not match this invoice")
    expected = hmac.new(key_secret.encode(), f"{invoice.razorpay_order_id}|{body.razorpay_payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(400, "Payment verification failed")
    try:
        from app.services.razorpay_provider import razorpay_provider
        payment = razorpay_provider(payment_config()[1], key_secret).fetch_payment(body.razorpay_payment_id)
    except Exception as exc:
        provider_error(exc, "payment_fetch")
        raise HTTPException(502, "Payment is being confirmed. Please refresh shortly") from exc
    if payment.get("order_id") != invoice.razorpay_order_id or int(payment.get("amount", 0)) != int(invoice.amount_paise) or payment.get("currency") != invoice.currency:
        raise HTTPException(409, "Payment details do not match this invoice")
    if payment.get("status") != "captured":
        invoice.status = payment.get("status", "pending"); db.commit()
        return {"ok": True, "status": invoice.status, "purchase_type": invoice.purchase_type}
    result = fulfill_invoice(db, invoice, body.razorpay_payment_id)
    db.commit()
    return {"ok": True, **result}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    mode, _, _, webhook_secret = payment_config(require_webhook=True)
    if mode == "mock":
        raise HTTPException(404, "Not available")
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "Invalid signature")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid webhook payload") from exc
    event_type = data.get("event", "unknown")
    provider_event_id = request.headers.get("X-Razorpay-Event-Id") or data.get("id")
    if provider_event_id and db.execute(select(PaymentEvent.id).where(PaymentEvent.provider_event_id == provider_event_id)).first():
        return {"ok": True, "duplicate": True}
    provider_subscription_data = data.get("payload", {}).get("subscription", {}).get("entity", {})
    payment = data.get("payload", {}).get("payment", {}).get("entity", {})
    order = data.get("payload", {}).get("order", {}).get("entity", {})
    linked_subscription = None
    if provider_subscription_data.get("id"):
        linked_subscription = db.execute(select(Subscription).where(Subscription.razorpay_subscription_id == provider_subscription_data["id"], Subscription.provider_mode == mode).with_for_update()).scalar_one_or_none()
        if linked_subscription:
            status_map = {"subscription.authenticated": "authenticated", "subscription.activated": "active", "subscription.paused": "paused", "subscription.resumed": "active", "subscription.cancelled": "cancelled", "subscription.completed": "completed", "subscription.pending": "pending", "subscription.halted": "halted"}
            linked_subscription.status = status_map.get(event_type, provider_subscription_data.get("status", linked_subscription.status))
            period_start = datetime.fromtimestamp(provider_subscription_data["current_start"], timezone.utc) if provider_subscription_data.get("current_start") else None
            period_end = datetime.fromtimestamp(provider_subscription_data["current_end"], timezone.utc) if provider_subscription_data.get("current_end") else None
            if period_start: linked_subscription.current_period_start = period_start
            if period_end: linked_subscription.current_period_end = period_end
            schedule = db.execute(select(SubscriptionSchedule).where(SubscriptionSchedule.subscription_id == linked_subscription.id, SubscriptionSchedule.status == "scheduled")).scalar_one_or_none()
            provider_matches = schedule and schedule.provider_reference and provider_subscription_data.get("plan_id") == schedule.provider_reference
            due = schedule and schedule.effective_at <= datetime.now(timezone.utc)
            if event_type == "subscription.activated" or (event_type == "subscription.updated" and provider_matches and due):
                activate_subscription_schedule(db, linked_subscription, period_start=period_start, period_end=period_end)
    order_id = payment.get("order_id") or order.get("id")
    invoice = db.execute(select(Invoice).where(Invoice.razorpay_order_id == order_id, Invoice.provider_mode == mode)).scalar_one_or_none() if order_id else None
    payment_id = payment.get("id")
    if invoice and event_type in {"payment.captured", "order.paid"}:
        received = int(payment.get("amount") or order.get("amount_paid") or 0)
        currency = payment.get("currency") or order.get("currency")
        if received == int(invoice.amount_paise) and currency == invoice.currency:
            fulfill_invoice(db, invoice, payment_id)
    elif invoice and event_type == "payment.failed" and invoice.status != "paid":
        invoice.status = "failed"
    elif payment_id and linked_subscription and event_type == "payment.captured" and not db.execute(select(PlatformPayment).where(PlatformPayment.provider_payment_id == payment_id)).scalar_one_or_none():
        db.add(PlatformPayment(organization_id=linked_subscription.organization_id, provider_payment_id=payment_id, provider_order_id=order_id, mode=mode, amount_paise=int(payment.get("amount") or 0), currency=payment.get("currency") or "INR", status="captured", captured_at=datetime.now(timezone.utc), meta={"subscription_id": linked_subscription.id}))
    db.add(PaymentEvent(
        organization_id=invoice.organization_id if invoice else (linked_subscription.organization_id if linked_subscription else None),
        event_type=event_type, provider_event_id=provider_event_id, provider_mode=mode,
        processed_at=datetime.now(timezone.utc), payload={**data, "edvatiq_payment_mode": mode},
    ))
    db.commit()
    return {"ok": True}
