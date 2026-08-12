"""Deterministic billing, gateway routing, and exactly-once fulfillment."""
import hashlib
import hmac
import logging
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

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
from app.services.cashfree_provider import cashfree_provider
from app.services.payment_gateways import GatewayConfig, active_gateway, gateway_config
from app.services.razorpay_provider import razorpay_provider

logger = logging.getLogger("edvatiq.billing")


def payment_config(
    require_webhook: bool = False,
    *,
    db: Session | None = None,
    provider: str | None = None,
    mode: str | None = None,
) -> tuple[str, str, str, str]:
    """Compatibility tuple for older callers; new code should use GatewayConfig."""
    config = (
        active_gateway(db, require_webhook=require_webhook)
        if db is not None and provider is None and mode is None
        else gateway_config(provider or "razorpay", mode, require_webhook=require_webhook)
    )
    return config.mode, config.client_id, config.secret, config.webhook_secret


def provider_error(exc: Exception, operation: str, provider: str = "payment_provider") -> tuple[str, str]:
    payload = getattr(exc, "error", None) or {}
    code = str(payload.get("code") or getattr(exc, "status_code", None) or type(exc).__name__)[:100]
    description = str(payload.get("description") or payload.get("reason") or str(exc) or "")
    missing_dependency = exc.name if isinstance(exc, ModuleNotFoundError) else None
    status_code = int(getattr(exc, "status_code", 0) or 0)
    request_id = str(getattr(exc, "request_id", "") or "none")[:100]
    safe_description = " ".join(description.split())[:240]
    logger.error(
        "%s_%s_failed code=%s status=%s request_id=%s error_type=%s missing_dependency=%s description=%s",
        provider, operation, code, status_code or "none", request_id, type(exc).__name__, missing_dependency or "none", safe_description or "none",
    )
    if missing_dependency:
        return "provider_dependency_missing", "Online payments are temporarily unavailable"
    lowered = description.lower()
    if "subscription" in lowered and any(word in lowered for word in ("enable", "available", "access")):
        return "subscriptions_unavailable", "Automatic renewal is not available for this payment account yet"
    if status_code in {401, 403} or "unauthorized" in lowered or "authentication" in lowered or "credential" in lowered:
        return "provider_authentication", "Online payments are temporarily unavailable"
    if status_code == 429:
        return "provider_busy", "The payment provider is busy right now. Please wait a moment and retry"
    if status_code >= 500 or code.upper() in {"SERVER_ERROR", "GATEWAY_ERROR", "PROVIDER_CONNECTION_ERROR"}:
        return "provider_unavailable", "The payment provider is temporarily unavailable. Please retry in a moment"
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
    snapshot: dict, gateway: GatewayConfig | None = None,
) -> Invoice:
    quote = tax_quote(db, organization, subtotal_paise, tax_enabled=tax_enabled, gst_rate_bps=gst_rate_bps)
    config = gateway or gateway_config("razorpay")
    now = datetime.now(timezone.utc)
    invoice = Invoice(
        organization_id=organization.id,
        amount_paise=quote["total_paise"], subtotal_paise=subtotal_paise,
        tax_paise=quote["tax_paise"], cgst_paise=quote["cgst_paise"],
        sgst_paise=quote["sgst_paise"], igst_paise=quote["igst_paise"],
        tax_enabled=quote["tax_enabled"], gst_rate_bps=quote["gst_rate_bps"],
        purchase_type=purchase_type, billing_interval=billing_interval,
        fulfillment_status="pending", provider=config.provider, provider_mode=config.mode,
        currency="INR", status="created",
        description=description, billing_snapshot={**quote["billing_profile"], "tax_reason": quote["tax_reason"]},
        plan_snapshot={**snapshot, "tax_enabled": quote["tax_enabled"], "gst_rate_bps": quote["gst_rate_bps"]},
    )
    db.add(invoice)
    db.flush()
    invoice.invoice_number = f"EDV-{now:%Y%m}-{invoice.id[:8].upper()}"
    return invoice


def paise_to_rupees(value: int) -> float:
    return float((Decimal(int(value)) / Decimal(100)).quantize(Decimal("0.01")))


def rupees_to_paise(value) -> int:
    try:
        return int((Decimal(str(value)) * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(409, "The payment provider returned an invalid amount") from exc


def create_provider_order(
    config: GatewayConfig,
    *,
    reference_id: str,
    amount_paise: int,
    currency: str,
    customer: dict,
    notes: dict,
    idempotency_key: str,
) -> dict:
    if config.mode == "mock":
        return {
            "order_id": f"mock-{config.provider}-{reference_id}",
            "session_id": None,
        }
    try:
        if config.provider == "razorpay":
            order = razorpay_provider(config.client_id, config.secret).create_order({
                "amount": int(amount_paise),
                "currency": currency,
                "receipt": reference_id[:40],
                "notes": notes,
            })
            return {"order_id": order["id"], "session_id": None}

        phone = str(customer.get("phone") or "").strip()
        if not phone:
            raise HTTPException(422, "A billing phone number is required for Cashfree checkout")
        cashfree_order_id = f"edv_{reference_id.replace('-', '')}"[:45]
        order = cashfree_provider(
            config.client_id,
            config.secret,
            config.mode,
            settings.CASHFREE_API_VERSION,
        ).create_order({
            "order_id": cashfree_order_id,
            "order_amount": paise_to_rupees(amount_paise),
            "order_currency": currency,
            "customer_details": {
                "customer_id": str(customer.get("id") or reference_id).replace("-", "")[:50],
                "customer_name": str(customer.get("name") or "Edvatiq customer")[:100],
                "customer_email": str(customer.get("email") or "")[:100],
                "customer_phone": phone[:20],
            },
            "order_note": str(notes.get("description") or "Edvatiq checkout")[:200],
            "order_tags": {key: str(value)[:100] for key, value in notes.items() if value is not None},
        }, idempotency_key=idempotency_key)
        payment_session_id = str(order.get("payment_session_id") or "").strip()
        if not payment_session_id:
            raise HTTPException(502, "Cashfree did not return a checkout session")
        return {
            "order_id": str(order.get("order_id") or cashfree_order_id),
            "session_id": payment_session_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        code, message = provider_error(exc, "order", config.provider)
        raise HTTPException(502, message, headers={"X-Edvatiq-Error-Code": code}) from exc


def provider_order(
    db: Session,
    invoice: Invoice,
    *,
    customer: dict | None = None,
    idempotency_key: str | None = None,
) -> tuple[str | None, str | None]:
    config = gateway_config(invoice.provider, invoice.provider_mode)
    try:
        order = create_provider_order(
            config,
            reference_id=invoice.id,
            amount_paise=int(invoice.amount_paise),
            currency=invoice.currency,
            customer=customer or {"id": invoice.organization_id},
            notes={
                "invoice_id": invoice.id,
                "organization_id": invoice.organization_id,
                "purchase_type": invoice.purchase_type,
                "mode": config.mode,
                "description": invoice.description,
            },
            idempotency_key=idempotency_key or invoice.id,
        )
        invoice.provider_order_id = order["order_id"]
        invoice.provider_session_id = order.get("session_id")
        if config.provider == "razorpay":
            invoice.razorpay_order_id = order["order_id"]
        return order["order_id"], None
    except HTTPException as exc:
        code = str((exc.headers or {}).get("X-Edvatiq-Error-Code") or "provider_order_failed")
        return None, f"{code}|{exc.detail}"


def ensure_provider_plan(
    db: Session,
    version: PlanVersion,
    definition: PlanDefinition,
    interval: str,
    amount_paise: int,
    *,
    gateway: GatewayConfig | None = None,
) -> ProviderPlanMapping:
    config = gateway or active_gateway(db)
    if not config.recurring_supported:
        raise HTTPException(409, "Automatic renewal is not available with the active payment gateway. Choose one-time payment")
    mode, key_id, key_secret = config.mode, config.client_id, config.secret
    row = db.execute(select(ProviderPlanMapping).where(
        ProviderPlanMapping.plan_version_id == version.id,
        ProviderPlanMapping.billing_interval == interval,
        ProviderPlanMapping.provider == config.provider,
        ProviderPlanMapping.provider_mode == mode,
        ProviderPlanMapping.amount_paise == amount_paise,
    ).with_for_update()).scalar_one_or_none()
    if row and row.status == "active" and row.provider_plan_id:
        return row
    if not row:
        row = ProviderPlanMapping(plan_version_id=version.id, billing_interval=interval, provider=config.provider, provider_mode=mode, amount_paise=amount_paise)
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
    config = gateway_config(mapping.provider, mapping.provider_mode)
    if not config.recurring_supported:
        raise HTTPException(409, "Automatic renewal is not supported by this payment gateway")
    mode, key_id, key_secret = config.mode, config.client_id, config.secret
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
    config = gateway_config(subscription.provider, subscription.provider_mode)
    if not config.recurring_supported:
        raise HTTPException(409, "This subscription cannot be changed through the selected payment gateway")
    mode, key_id, key_secret = config.mode, config.client_id, config.secret
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
    config = gateway_config(subscription.provider, subscription.provider_mode)
    if not config.recurring_supported:
        raise HTTPException(409, "This subscription cannot be cancelled through the selected payment gateway")
    mode, key_id, key_secret = config.mode, config.client_id, config.secret
    if mode == "mock" or not subscription.razorpay_subscription_id:
        return
    try:
        razorpay_provider(key_id, key_secret).cancel_subscription(
            subscription.razorpay_subscription_id, {"cancel_at_cycle_end": 1 if at_cycle_end else 0},
        )
    except Exception as exc:
        _, message = provider_error(exc, "subscription_cancel")
        raise HTTPException(502, message) from exc


def checkout_customer(db: Session, organization: Organization, user=None) -> dict:
    profile = db.execute(
        select(BillingProfile).where(BillingProfile.organization_id == organization.id)
    ).scalar_one_or_none()
    name = (
        (profile.legal_name if profile else None)
        or organization.legal_name
        or organization.name
    )
    return {
        "id": organization.id,
        "name": name,
        "email": (profile.billing_email if profile else None) or getattr(user, "email", None),
        "phone": (profile.billing_phone if profile else None) or getattr(user, "phone", None),
    }


def verify_provider_payment(
    *,
    provider: str,
    mode: str,
    order_id: str,
    amount_paise: int,
    currency: str,
    payment_id: str | None = None,
    signature: str | None = None,
) -> dict:
    config = gateway_config(provider, mode)
    if config.mode == "mock":
        raise HTTPException(404, "Not available")
    if config.provider == "razorpay":
        if not payment_id or not signature:
            raise HTTPException(422, "Payment confirmation details are required")
        expected = hmac.new(
            config.secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(400, "Payment verification failed")
        try:
            payment = razorpay_provider(config.client_id, config.secret).fetch_payment(payment_id)
        except Exception as exc:
            provider_error(exc, "payment_fetch", config.provider)
            raise HTTPException(502, "Payment is being confirmed. Please refresh shortly") from exc
        if (
            payment.get("order_id") != order_id
            or int(payment.get("amount", 0)) != int(amount_paise)
            or payment.get("currency") != currency
        ):
            raise HTTPException(409, "Payment details do not match this checkout")
        return {
            "status": "paid" if payment.get("status") == "captured" else str(payment.get("status") or "pending"),
            "payment_id": str(payment.get("id") or payment_id),
            "method": payment.get("method"),
        }

    provider_client = cashfree_provider(
        config.client_id,
        config.secret,
        config.mode,
        settings.CASHFREE_API_VERSION,
    )
    try:
        order = provider_client.fetch_order(order_id)
    except Exception as exc:
        provider_error(exc, "order_fetch", config.provider)
        raise HTTPException(502, "Payment is being confirmed. Please refresh shortly") from exc
    if (
        str(order.get("order_id") or "") != order_id
        or rupees_to_paise(order.get("order_amount")) != int(amount_paise)
        or str(order.get("order_currency") or "") != currency
    ):
        raise HTTPException(409, "Payment details do not match this checkout")
    if order.get("order_status") != "PAID":
        provider_status = str(order.get("order_status") or "ACTIVE").upper()
        status = "failed" if provider_status in {"EXPIRED", "TERMINATED", "TERMINATION_REQUESTED"} else "pending"
        return {"status": status, "payment_id": None, "method": None}
    try:
        payments = provider_client.fetch_payments(order_id)
    except Exception as exc:
        provider_error(exc, "payment_fetch", config.provider)
        raise HTTPException(502, "Payment is being confirmed. Please refresh shortly") from exc
    successful = next((item for item in payments if item.get("payment_status") == "SUCCESS"), None)
    if not successful:
        return {"status": "pending", "payment_id": None, "method": None}
    received = successful.get("payment_amount")
    if received is not None and rupees_to_paise(received) != int(amount_paise):
        raise HTTPException(409, "Payment details do not match this checkout")
    provider_payment_id = str(successful.get("cf_payment_id") or "")
    if not provider_payment_id:
        raise HTTPException(409, "Cashfree did not return a payment reference")
    return {
        "status": "paid",
        "payment_id": provider_payment_id,
        "method": successful.get("payment_group"),
    }


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
        invoice.provider_payment_id = payment_id
        if invoice.provider == "razorpay":
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
        subscription.provider = invoice.provider
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
            provider_order_id=invoice.provider_order_id or invoice.razorpay_order_id,
            provider=invoice.provider, mode=invoice.provider_mode,
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
