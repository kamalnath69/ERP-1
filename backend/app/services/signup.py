"""Public plan catalog and payment-first organization provisioning."""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.seed import seed_organization_defaults
from app.models import (
    BillingProfile, FeatureDefinition, IndustryEnum, Invoice, Location, Organization,
    PlanDefinition, PlanEntitlement, PlanVersion, PlatformSetting, SignupCheckout,
    SignupEmailChallenge, User,
)
from app.services.audit import log_action
from app.services.auth_security import token_hash
from app.services.billing import fulfill_invoice
from app.services.public_site import attach_checkout_acceptance
from app.services.signup_email import (
    OWNER_EMAIL_CONFLICT_DETAIL, consume_signup_email_challenge,
    lock_signup_owner_email, signup_owner_email_conflict,
)


ACTIVE_CHECKOUT_STATUSES = {"creating", "ready", "paid"}
CHECKOUT_TTL = timedelta(hours=24)


def lock_organization_slug(db: Session, slug: str) -> None:
    """Serialize slug reservations on PostgreSQL without a permanent lock row."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:slug))"), {"slug": slug})


def organization_modules(industry: str) -> list[str]:
    return {
        "gym": ["clients", "employees", "catalog", "inventory", "sales", "appointments", "gym", "ai"],
        "salon": ["clients", "employees", "catalog", "inventory", "sales", "appointments", "salon", "ai"],
        "clinic": ["clients", "employees", "catalog", "inventory", "sales", "appointments", "clinic", "documents", "ai"],
        "college": ["clients", "employees", "college", "documents", "reports", "notifications", "ai"],
    }[industry]


def expire_stale_checkouts(db: Session) -> None:
    now = datetime.now(timezone.utc)
    rows = db.execute(select(SignupCheckout).where(
        SignupCheckout.status.in_(ACTIVE_CHECKOUT_STATUSES),
        SignupCheckout.expires_at <= now,
    )).scalars()
    for row in rows:
        row.status = "expired"
    retained = db.execute(select(SignupCheckout).where(
        SignupCheckout.status.in_({"expired", "failed"}),
        SignupCheckout.expires_at <= now - timedelta(days=7),
        SignupCheckout.admin_password_hash.is_not(None),
    )).scalars()
    for row in retained:
        row.admin_password_hash = None


def _eligible_plan_statement():
    now = datetime.now(timezone.utc)
    return (
        select(PlanDefinition, PlanVersion)
        .join(PlanVersion, PlanVersion.plan_id == PlanDefinition.id)
        .where(
            PlanDefinition.is_public.is_(True),
            PlanDefinition.is_active.is_(True),
            PlanVersion.status == "published",
            or_(PlanVersion.effective_from.is_(None), PlanVersion.effective_from <= now),
        )
    )


def public_plan_rows(db: Session) -> list[tuple[PlanDefinition, PlanVersion]]:
    rows = db.execute(
        _eligible_plan_statement().order_by(PlanDefinition.display_order, PlanVersion.version.desc())
    ).all()
    result: list[tuple[PlanDefinition, PlanVersion]] = []
    seen: set[str] = set()
    for definition, version in rows:
        if definition.id not in seen:
            result.append((definition, version))
            seen.add(definition.id)
    return result


def public_plan_pair(db: Session, slug: str) -> tuple[PlanDefinition, PlanVersion]:
    row = db.execute(
        _eligible_plan_statement()
        .where(PlanDefinition.slug == slug.strip().lower())
        .order_by(PlanVersion.version.desc())
    ).first()
    if not row:
        raise HTTPException(404, "This plan is not available for new accounts")
    return row


def trial_signup_available(db: Session) -> bool:
    return any(definition.slug == "trial" for definition, _version in public_plan_rows(db))


def public_tax_quote(subtotal_paise: int, *, tax_enabled: bool, gst_rate_bps: int) -> dict:
    effective = bool(tax_enabled and gst_rate_bps > 0)
    tax = (subtotal_paise * gst_rate_bps + 5000) // 10000 if effective else 0
    return {
        "subtotal_paise": subtotal_paise,
        "tax_enabled": effective,
        "gst_rate_bps": gst_rate_bps if effective else 0,
        "tax_paise": tax,
        "total_paise": subtotal_paise + tax,
        "currency": "INR",
    }


def _plan_features(db: Session, version_id: str) -> tuple[dict, list[dict]]:
    rows = db.execute(
        select(FeatureDefinition, PlanEntitlement.value)
        .join(PlanEntitlement, PlanEntitlement.feature_id == FeatureDefinition.id)
        .where(
            PlanEntitlement.plan_version_id == version_id,
            FeatureDefinition.is_active.is_(True),
        )
        .order_by(FeatureDefinition.category, FeatureDefinition.name)
    ).all()
    entitlements = {definition.code: value.get("value") for definition, value in rows}
    features = [
        {"code": definition.code, "name": definition.name, "category": definition.category}
        for definition, value in rows
        if definition.value_type == "boolean" and value.get("value")
    ]
    return entitlements, features


def public_plan_payload(db: Session, definition: PlanDefinition, version: PlanVersion) -> dict:
    entitlements, features = _plan_features(db, version.id)
    monthly = public_tax_quote(
        int(version.monthly_price_paise),
        tax_enabled=version.tax_enabled,
        gst_rate_bps=version.gst_rate_bps,
    ) if version.monthly_price_paise is not None else None
    annual = public_tax_quote(
        int(version.annual_price_paise),
        tax_enabled=version.tax_enabled,
        gst_rate_bps=version.gst_rate_bps,
    ) if version.annual_price_paise is not None else None
    annual_saving = 0
    if monthly and annual and monthly["subtotal_paise"]:
        annual_saving = max(0, round((1 - annual["subtotal_paise"] / (monthly["subtotal_paise"] * 12)) * 100))
    return {
        "id": definition.slug,
        "definition_id": definition.id,
        "version_id": version.id,
        "version": version.version,
        "name": definition.name,
        "description": definition.description,
        "recommended": definition.slug == "growth",
        "purchasable": definition.slug not in {"trial", "enterprise"} and monthly is not None,
        "signup_mode": "trial" if definition.slug == "trial" else "contact" if monthly is None else "paid",
        "trial_days": 30 if definition.slug == "trial" else None,
        "monthly_price_paise": version.monthly_price_paise,
        "annual_price_paise": version.annual_price_paise,
        "monthly_quote": monthly,
        "annual_quote": annual,
        "annual_saving_percent": annual_saving,
        "ai_credits": version.included_ai_credits,
        "support_level": version.support_level,
        "ai_tier": version.ai_tier,
        "employee_limit": entitlements.get("limits.employees"),
        "client_limit": entitlements.get("limits.clients"),
        "location_limit": entitlements.get("limits.locations"),
        "storage_limit_mb": entitlements.get("limits.storage_mb"),
        "features": features,
        "feature_names": [feature["name"] for feature in features],
    }


def valid_checkout_token(checkout: SignupCheckout, value: str) -> bool:
    return bool(value) and hmac.compare_digest(checkout.access_token_hash, token_hash(value))


def checkout_response(checkout: SignupCheckout, access_token: str | None = None, key_id: str | None = None) -> dict:
    owner_verified = bool(checkout.email_challenge_id)
    next_action = {
        "completed": "open_workspace" if owner_verified else "verify_email",
        "manual_review": "support",
        "cancelled": "restart",
        "expired": "restart",
        "failed": "restart",
        "creating": "wait",
        "paid": "wait",
    }.get(checkout.status, "pay")
    safe_failure_codes = {
        "provider_order_failed", "provider_order_inactive", "payment_failed",
        "cancelled_by_user", "late_payment_inactive_checkout",
    }
    response = {
        "checkout_id": checkout.id,
        "status": checkout.status,
        "next_action": next_action,
        "order_id": checkout.provider_order_id,
        "payment_session_id": checkout.provider_session_id if next_action == "pay" else None,
        "amount_paise": int(checkout.total_paise),
        "subtotal_paise": int(checkout.subtotal_paise),
        "tax_paise": int(checkout.tax_paise),
        "currency": checkout.currency,
        "key_id": key_id,
        "provider": checkout.provider,
        "mode": checkout.provider_mode,
        "checkout_mode": "sandbox" if checkout.provider == "cashfree" and checkout.provider_mode == "test" else "production" if checkout.provider == "cashfree" else checkout.provider_mode,
        "mock_mode": checkout.provider_mode == "mock",
        "expires_at": checkout.expires_at,
        "plan": checkout.plan_snapshot,
        "billing_interval": checkout.billing_interval,
        "billing_state": checkout.state,
        "organization_name": checkout.organization_name,
        "organization_slug": checkout.organization_slug,
        "email": checkout.admin_email if checkout.status == "completed" else None,
        "requires_verification": checkout.status == "completed" and not owner_verified,
        "failure_code": checkout.last_error if checkout.last_error in safe_failure_codes else None,
    }
    if access_token:
        response["checkout_token"] = access_token
    return response


def finalize_signup(
    db: Session,
    checkout: SignupCheckout,
    payment_id: str,
    *,
    ip_address: str | None = None,
) -> tuple[Organization, User, bool]:
    checkout = db.execute(
        select(SignupCheckout).where(SignupCheckout.id == checkout.id).with_for_update()
    ).scalar_one()
    if checkout.status == "completed" and checkout.organization_id:
        organization = db.get(Organization, checkout.organization_id)
        user = db.execute(select(User).where(
            User.organization_id == checkout.organization_id,
            User.email == checkout.admin_email,
        )).scalar_one()
        return organization, user, False
    if checkout.status not in {"ready", "paid"}:
        raise HTTPException(409, "This signup checkout cannot be completed")
    if not checkout.admin_password_hash:
        checkout.status = "manual_review"
        checkout.provider_payment_id = payment_id
        checkout.last_error = "Account credentials are no longer available after payment"
        db.commit()
        raise HTTPException(409, "Payment was received, but account creation needs support review")

    email_challenge = None
    if checkout.email_challenge_id:
        email_challenge = db.execute(
            select(SignupEmailChallenge)
            .where(SignupEmailChallenge.id == checkout.email_challenge_id)
            .with_for_update()
        ).scalar_one_or_none()
        if (
            not email_challenge
            or email_challenge.status != "bound"
            or email_challenge.consumed_at is not None
            or email_challenge.email != checkout.admin_email.strip().lower()
        ):
            checkout.status = "manual_review"
            checkout.provider_payment_id = payment_id
            checkout.last_error = "Verified owner email proof is unavailable"
            db.commit()
            raise HTTPException(409, "Payment was received, but owner verification needs support review")
    lock_organization_slug(db, checkout.organization_slug)
    if db.execute(select(Organization.id).where(Organization.slug == checkout.organization_slug)).first():
        checkout.status = "manual_review"
        checkout.provider_payment_id = payment_id
        checkout.last_error = "Organization ID became unavailable after payment"
        db.commit()
        raise HTTPException(409, "Payment was received, but this Business ID needs support review")
    lock_signup_owner_email(db, checkout.admin_email)
    if signup_owner_email_conflict(db, checkout.admin_email, exclude_checkout_id=checkout.id):
        checkout.status = "manual_review"
        checkout.provider_payment_id = payment_id
        checkout.last_error = "Owner email became unavailable after payment"
        db.commit()
        raise HTTPException(409, f"Payment was received, but account creation needs support review. {OWNER_EMAIL_CONFLICT_DETAIL}")

    try:
        industry = IndustryEnum(checkout.industry)
    except ValueError as exc:
        raise HTTPException(400, "Invalid industry") from exc
    version = db.get(PlanVersion, checkout.plan_version_id)
    definition = db.get(PlanDefinition, version.plan_id) if version else None
    if not version or not definition or definition.slug in {"trial", "enterprise"}:
        checkout.status = "manual_review"
        checkout.provider_payment_id = payment_id
        checkout.last_error = "Purchased plan version is unavailable after payment"
        db.commit()
        raise HTTPException(409, "Payment was received, but the purchased plan needs support review")

    organization = Organization(
        name=checkout.organization_name,
        slug=checkout.organization_slug,
        industry=industry,
        status="active",
        plan=definition.slug,
        enabled_modules=organization_modules(industry.value),
        contact_email=checkout.admin_email,
    )
    db.add(organization)
    db.flush()
    owner = User(
        organization_id=organization.id,
        email=checkout.admin_email,
        hashed_password=checkout.admin_password_hash,
        first_name=checkout.admin_first_name,
        last_name=checkout.admin_last_name,
        phone=checkout.admin_phone,
        is_active=True,
        email_verified=email_challenge is not None,
    )
    db.add(owner)
    db.flush()
    if email_challenge:
        consume_signup_email_challenge(email_challenge)
    attach_checkout_acceptance(db, checkout.id, organization.id, owner.id)
    location = Location(
        organization_id=organization.id,
        name=checkout.location_name,
        code="MAIN",
        city=checkout.city,
        state=checkout.state,
        is_primary=True,
    )
    db.add(location)
    db.flush()
    seed_organization_defaults(db, organization, owner, location, create_trial=False)
    db.add(BillingProfile(
        organization_id=organization.id,
        legal_name=organization.name,
        billing_email=owner.email,
        billing_phone=checkout.admin_phone,
        state=checkout.state,
    ))

    now = datetime.now(timezone.utc)
    identity = db.execute(select(PlatformSetting).where(
        PlatformSetting.key == "billing_identity",
    )).scalar_one_or_none()
    seller_state = str((identity.value if identity else {}).get("registered_state") or "Tamil Nadu").strip().casefold()
    buyer_state = str(checkout.state or "").strip().casefold()
    interstate = bool(buyer_state and seller_state and buyer_state != seller_state)
    invoice = Invoice(
        organization_id=organization.id,
        razorpay_order_id=checkout.provider_order_id if checkout.provider == "razorpay" else None,
        razorpay_payment_id=payment_id if checkout.provider == "razorpay" else None,
        provider=checkout.provider,
        provider_order_id=checkout.provider_order_id,
        provider_payment_id=payment_id,
        provider_session_id=checkout.provider_session_id,
        amount_paise=checkout.total_paise,
        subtotal_paise=checkout.subtotal_paise,
        tax_paise=checkout.tax_paise,
        cgst_paise=0 if interstate else checkout.tax_paise // 2,
        sgst_paise=0 if interstate else checkout.tax_paise - checkout.tax_paise // 2,
        igst_paise=checkout.tax_paise if interstate else 0,
        tax_enabled=checkout.tax_enabled,
        gst_rate_bps=checkout.gst_rate_bps,
        purchase_type="plan",
        billing_interval=checkout.billing_interval,
        fulfillment_status="pending",
        provider_mode=checkout.provider_mode,
        currency=checkout.currency,
        status="created",
        description=f"{definition.name} {checkout.billing_interval} plan",
        billing_snapshot={
            "source": "public_signup",
            "legal_name": organization.name,
            "billing_email": owner.email,
            "state": checkout.state,
            "tax_reason": "applied" if checkout.tax_enabled else "plan_disabled",
        },
        plan_snapshot={**checkout.plan_snapshot, "plan_version_id": version.id, "reference_id": checkout.id},
    )
    db.add(invoice)
    db.flush()
    invoice.invoice_number = f"EDV-{now:%Y%m}-{invoice.id[:8].upper()}"
    fulfill_invoice(db, invoice, payment_id)

    checkout.status = "completed"
    checkout.provider_payment_id = payment_id
    checkout.organization_id = organization.id
    checkout.completed_at = now
    checkout.admin_password_hash = None
    checkout.last_error = None
    log_action(
        db,
        organization_id=organization.id,
        user_id=owner.id,
        action="organization.paid_registration",
        resource_type="organization",
        resource_id=organization.id,
        ip_address=ip_address,
        meta={"plan": definition.slug, "billing_interval": checkout.billing_interval},
    )
    return organization, owner, True


def hash_signup_password(password: str) -> str:
    return hash_password(password)
