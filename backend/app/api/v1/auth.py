"""Secure cookie authentication, payment-first registration, recovery, and sessions."""
import secrets
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import EmailStr, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.db.seed import seed_organization_defaults
from app.models import AuthAttempt, IndustryEnum, Location, Organization, RefreshToken, SignupCheckout, User
from app.schemas import (
    CodeRequest, LoginRequest, LoginResponse, PaidSignupAccessRequest,
    PaidSignupCheckoutRequest, PaidSignupVerifyRequest, RegisterOrgRequest,
    ResetPasswordRequest, UserOut, VerifyEmailRequest, validate_strong_password,
)
from app.schemas.validation import RequestModel
from app.services.audit import log_action
from app.services.auth_security import (
    clear_auth_cookies, client_ip, consume_auth_code, create_auth_code, identifier_hash,
    new_csrf_token, set_auth_cookies, token_hash,
)
from app.services.email import send_auth_code_email
from app.services.billing import (
    create_provider_order, plan_price, terminate_provider_order, verify_provider_payment,
)
from app.services.payment_gateways import active_gateway, gateway_config
from app.services.public_site import create_legal_acceptance, validate_legal_acceptance
from app.services.signup import (
    ACTIVE_CHECKOUT_STATUSES, CHECKOUT_TTL, checkout_response, expire_stale_checkouts,
    finalize_signup, hash_signup_password, organization_modules, public_plan_pair,
    public_tax_quote, trial_signup_available, valid_checkout_token, lock_organization_slug,
)

router = APIRouter(prefix="/auth", tags=["auth"])
DUMMY_PASSWORD_HASH = hash_password("NotARealPassword123")
PUBLIC_MESSAGE = "If the account exists, a code has been sent"
INACTIVE_CHECKOUT_STATUSES = {"cancelled", "expired", "failed"}


class PlatformInviteAccept(RequestModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value):
        return validate_strong_password(value)


def _find_users(db: Session, email: str, org_slug: str | None = None) -> list[User]:
    users = db.execute(select(User).where(func.lower(User.email) == email.strip().lower())).scalars().all()
    if org_slug:
        slug = org_slug.strip().lower()
        users = [user for user in users if user.organization_id and (org := db.get(Organization, user.organization_id)) and org.slug == slug]
    return users


def _single_user(db: Session, email: str, org_slug: str | None = None) -> User | None:
    users = _find_users(db, email, org_slug)
    return users[0] if len(users) == 1 else None


def _deliver_code(db: Session, user: User, purpose: str, request: Request) -> tuple[bool, str | None]:
    code = create_auth_code(db, user, purpose, request)
    db.commit()
    try:
        sent = send_auth_code_email(user.email, code, purpose, user.first_name)
    except Exception:
        sent = False
    return sent, code if settings.AUTH_EXPOSE_TEST_CODES else None


def _session_response(
    db: Session,
    user: User,
    request: Request,
    response: Response,
    family_id: str | None = None,
    replaced: RefreshToken | None = None,
    *,
    mfa_verified: bool = False,
    mfa_pending: bool = False,
) -> LoginResponse:
    csrf = new_csrf_token()
    security_claims = {"mfa_verified": mfa_verified, "mfa_pending": mfa_pending}
    access = create_access_token(user.id, user.organization_id, {
        "is_super": user.is_super_admin, "sv": user.session_version,
        "av": user.access_version, **security_claims,
    })
    refresh = create_refresh_token(user.id, user.organization_id, {
        "family": family_id or secrets.token_hex(16), "sv": user.session_version,
        "av": user.access_version, **security_claims,
    })
    family = family_id or decode_token(refresh)["family"]
    row = RefreshToken(
        user_id=user.id, token_hash=token_hash(refresh), family_id=family,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=(request.headers.get("user-agent") or "")[:300], ip_address=client_ip(request),
    )
    db.add(row); db.flush()
    if replaced:
        replaced.revoked = True; replaced.last_used_at = datetime.now(timezone.utc); replaced.replaced_by_token_id = row.id
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    set_auth_cookies(response, access, refresh, csrf)
    user_data = UserOut.model_validate(user).model_dump()
    if user.organization_id:
        from app.services.user_security import mfa_requirement
        mfa_state = mfa_requirement(db, user)
        user_data.update({
            "mfa_enabled": mfa_state["enabled"],
            "mfa_required": mfa_state["required"],
            "mfa_enrollment_required": mfa_pending,
        })
    return LoginResponse(user=user_data, csrf_token=csrf)


def _record_attempt(db: Session, request: Request, email: str, org_slug: str | None, kind: str, success: bool, user: User | None = None) -> None:
    identity = identifier_hash(f"{email}:{org_slug or ''}")
    if success:
        db.query(AuthAttempt).filter(AuthAttempt.identifier_hash == identity, AuthAttempt.kind == kind, AuthAttempt.succeeded.is_(False)).delete()
    db.add(AuthAttempt(
        organization_id=user.organization_id if user else None, user_id=user.id if user else None,
        identifier_hash=identity, ip_address=client_ip(request),
        kind=kind, succeeded=success,
    ))
    db.commit()


def _ensure_login_not_throttled(db: Session, request: Request, email: str, org_slug: str | None) -> None:
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    identity = identifier_hash(f"{email}:{org_slug or ''}")
    ip = client_ip(request)
    failures = db.scalar(select(func.count(AuthAttempt.id)).where(
        AuthAttempt.kind == "login", AuthAttempt.succeeded.is_(False), AuthAttempt.created_at >= since,
        or_(AuthAttempt.identifier_hash == identity, AuthAttempt.ip_address == ip) if ip else AuthAttempt.identifier_hash == identity,
    )) or 0
    if failures >= 10:
        raise HTTPException(429, "Too many sign-in attempts. Please wait 15 minutes")


def _ensure_signup_not_throttled(db: Session, request: Request, email: str) -> None:
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    identity = identifier_hash(email)
    ip = client_ip(request)
    attempts = db.scalar(select(func.count(AuthAttempt.id)).where(
        AuthAttempt.kind == "signup_checkout",
        AuthAttempt.created_at >= since,
        or_(AuthAttempt.identifier_hash == identity, AuthAttempt.ip_address == ip) if ip else AuthAttempt.identifier_hash == identity,
    )) or 0
    if attempts >= 5:
        raise HTTPException(429, "Too many checkout attempts. Please wait 15 minutes")


@router.get("/organization-id/availability")
def organization_id_availability(value: str, db: Session = Depends(get_db)):
    business_id = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", business_id) or not 2 <= len(business_id) <= 80:
        return {"value": business_id, "available": False, "valid": False, "message": "Use lowercase letters, numbers, and single hyphens", "suggestions": []}
    expire_stale_checkouts(db)
    now = datetime.now(timezone.utc)
    exists = db.execute(select(Organization.id).where(Organization.slug == business_id)).first() is not None
    reserved = db.execute(select(SignupCheckout.id).where(
        SignupCheckout.organization_slug == business_id,
        SignupCheckout.status.in_(ACTIVE_CHECKOUT_STATUSES),
        SignupCheckout.expires_at > now,
    )).first() is not None
    unavailable = exists or reserved
    suggestions = []
    if unavailable:
        candidates = [f"{business_id}-hq", f"{business_id}-india", f"{business_id}-2"]
        used = set(db.execute(select(Organization.slug).where(Organization.slug.in_(candidates))).scalars())
        reserved_candidates = set(db.execute(select(SignupCheckout.organization_slug).where(
            SignupCheckout.organization_slug.in_(candidates),
            SignupCheckout.status.in_(ACTIVE_CHECKOUT_STATUSES),
            SignupCheckout.expires_at > now,
        )).scalars())
        suggestions = [candidate for candidate in candidates if candidate not in used | reserved_candidates]
    db.commit()
    return {"value": business_id, "available": not unavailable, "valid": True, "message": "Available" if not unavailable else "Already used or reserved by another business", "suggestions": suggestions}


@router.post("/register", status_code=201)
def register_organization(body: RegisterOrgRequest, request: Request, db: Session = Depends(get_db)):
    expire_stale_checkouts(db)
    legal_documents = validate_legal_acceptance(db, body.legal_acceptance)
    if not trial_signup_available(db):
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Free trial is unavailable. Choose a paid plan to create your workspace")
    slug = body.organization_slug.strip().lower()
    lock_organization_slug(db, slug)
    if db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Organization slug already exists")
    if db.execute(select(SignupCheckout.id).where(
        SignupCheckout.organization_slug == slug,
        SignupCheckout.status.in_(ACTIVE_CHECKOUT_STATUSES),
        SignupCheckout.expires_at > datetime.now(timezone.utc),
    )).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Organization slug is reserved by a pending checkout")
    try: industry = IndustryEnum(body.industry)
    except ValueError: raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid industry")
    org = Organization(name=body.organization_name, slug=slug, industry=industry, enabled_modules=organization_modules(industry.value), contact_email=body.admin_email.lower())
    db.add(org); db.flush()
    admin = User(
        organization_id=org.id, email=body.admin_email.lower(), hashed_password=hash_password(body.admin_password),
        first_name=body.admin_first_name, last_name=body.admin_last_name, phone=body.admin_phone,
        is_active=True, email_verified=False,
    )
    db.add(admin); db.flush()
    location = Location(organization_id=org.id, name=body.location_name, code="MAIN", city=body.city, state=body.state, is_primary=True)
    db.add(location); db.flush(); seed_organization_defaults(db, org, admin, location)
    create_legal_acceptance(
        db,
        documents=legal_documents,
        subject_email=admin.email,
        source="trial_registration",
        organization_id=org.id,
        user_id=admin.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    log_action(db, organization_id=org.id, user_id=admin.id, action="organization.register", resource_type="organization", resource_id=org.id, ip_address=client_ip(request))
    db.commit()
    sent, test_code = _deliver_code(db, admin, "email_verification", request)
    return {"requires_verification": True, "email": admin.email, "organization_slug": org.slug, "email_sent": sent, **({"test_code": test_code} if test_code else {})}


def _authorized_checkout(db: Session, checkout_id: str, checkout_token: str, *, lock: bool = False) -> SignupCheckout:
    statement = select(SignupCheckout).where(SignupCheckout.id == checkout_id)
    if lock:
        statement = statement.with_for_update()
    checkout = db.execute(statement).scalar_one_or_none()
    if not checkout or not valid_checkout_token(checkout, checkout_token):
        raise HTTPException(404, "Signup checkout not found")
    return checkout


def _send_signup_verification(
    db: Session,
    checkout: SignupCheckout,
    owner: User,
    request: Request,
) -> tuple[bool, str | None]:
    if checkout.verification_sent_at:
        return True, None
    sent, test_code = _deliver_code(db, owner, "email_verification", request)
    checkout = db.get(SignupCheckout, checkout.id)
    checkout.verification_sent_at = datetime.now(timezone.utc)
    db.commit()
    return sent, test_code


def _checkout_status_payload(checkout: SignupCheckout, access_token: str | None = None) -> dict:
    config = gateway_config(checkout.provider, checkout.provider_mode, require_configured=False)
    key_id = config.client_id if (
        checkout.provider == "razorpay" and checkout.status == "ready" and config.configured
    ) else None
    return checkout_response(checkout, access_token, key_id)


def _completed_signup_payload(
    checkout: SignupCheckout,
    organization: Organization,
    owner: User,
    *,
    email_sent: bool | None = None,
    test_code: str | None = None,
) -> dict:
    payload = {
        **_checkout_status_payload(checkout),
        "ok": True,
        "status": "completed",
        "next_action": "verify_email",
        "requires_verification": True,
        "email": owner.email,
        "organization_slug": organization.slug,
        **({"test_code": test_code} if test_code else {}),
    }
    if email_sent is not None:
        payload["email_sent"] = email_sent
    return payload


def _idempotent_checkout_payload(checkout: SignupCheckout, checkout_token: str | None) -> dict:
    if not checkout_token or not valid_checkout_token(checkout, checkout_token):
        raise HTTPException(409, "This checkout request cannot be reused. Start a new checkout")
    config = gateway_config(checkout.provider, checkout.provider_mode, require_configured=False)
    key_id = config.client_id if (
        config.provider == "razorpay" and checkout.status == "ready" and config.configured
    ) else None
    return checkout_response(checkout, checkout_token, key_id)


def _reconcile_signup_checkout(
    db: Session,
    checkout: SignupCheckout,
    request: Request,
    *,
    razorpay_order_id: str | None = None,
    razorpay_payment_id: str | None = None,
    razorpay_signature: str | None = None,
) -> dict:
    if checkout.status == "completed" and checkout.organization_id:
        organization = db.get(Organization, checkout.organization_id)
        owner = db.execute(select(User).where(
            User.organization_id == checkout.organization_id,
            User.email == checkout.admin_email,
        )).scalar_one_or_none()
        if organization and owner:
            return _completed_signup_payload(checkout, organization, owner)

    if checkout.provider == "razorpay" and not razorpay_payment_id:
        return _checkout_status_payload(checkout)
    if checkout.provider == "razorpay" and checkout.provider_order_id != razorpay_order_id:
        raise HTTPException(409, "Payment does not match this signup checkout")

    verification = verify_provider_payment(
        provider=checkout.provider,
        mode=checkout.provider_mode,
        order_id=checkout.provider_order_id,
        amount_paise=int(checkout.total_paise),
        currency=checkout.currency,
        payment_id=razorpay_payment_id,
        signature=razorpay_signature,
    )
    provider_session_id = verification.get("payment_session_id")
    if provider_session_id and provider_session_id != checkout.provider_session_id:
        checkout.provider_session_id = provider_session_id

    if verification["status"] != "paid":
        if verification["status"] == "failed" and checkout.status not in {"completed", "manual_review"}:
            checkout.status = "failed"
            checkout.last_error = "provider_order_inactive"
            checkout.admin_password_hash = None
        db.commit()
        return _checkout_status_payload(checkout)

    payment_id = verification["payment_id"]
    if checkout.status in INACTIVE_CHECKOUT_STATUSES or checkout.status == "manual_review":
        checkout.status = "manual_review"
        checkout.provider_payment_id = payment_id
        checkout.last_error = "late_payment_inactive_checkout"
        checkout.admin_password_hash = None
        db.commit()
        return _checkout_status_payload(checkout)

    if checkout.status != "completed":
        checkout.status = "paid"
    try:
        organization, owner, created = finalize_signup(
            db,
            checkout,
            payment_id,
            ip_address=client_ip(request),
        )
    except HTTPException:
        if checkout.status == "manual_review":
            return _checkout_status_payload(checkout)
        raise
    db.commit()
    sent, test_code = _send_signup_verification(db, checkout, owner, request) if created else (True, None)
    return _completed_signup_payload(
        checkout,
        organization,
        owner,
        email_sent=sent,
        test_code=test_code,
    )


@router.post("/registration/checkout", status_code=201)
def create_registration_checkout(
    body: PaidSignupCheckoutRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    expire_stale_checkouts(db)
    existing = db.execute(select(SignupCheckout).where(
        SignupCheckout.idempotency_key == body.idempotency_key,
    )).scalar_one_or_none()
    if existing:
        payload = _idempotent_checkout_payload(existing, body.checkout_token)
        db.commit()
        return payload

    legal_documents = validate_legal_acceptance(db, body.legal_acceptance)

    slug = body.organization_slug.strip().lower()
    lock_organization_slug(db, slug)
    now = datetime.now(timezone.utc)
    # A concurrent retry can miss the uncommitted row before waiting on the
    # organization advisory lock. Recheck after acquiring it.
    existing = db.execute(select(SignupCheckout).where(
        SignupCheckout.idempotency_key == body.idempotency_key,
    )).scalar_one_or_none()
    if existing:
        payload = _idempotent_checkout_payload(existing, body.checkout_token)
        db.commit()
        return payload
    if db.execute(select(Organization.id).where(Organization.slug == slug)).first():
        raise HTTPException(409, "Organization slug already exists")
    if db.execute(select(SignupCheckout.id).where(
        SignupCheckout.organization_slug == slug,
        SignupCheckout.status.in_(ACTIVE_CHECKOUT_STATUSES),
        SignupCheckout.expires_at > now,
    )).first():
        raise HTTPException(409, "Organization slug is reserved by a pending checkout")
    try:
        industry = IndustryEnum(body.industry)
        organization_modules(industry.value)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, "Invalid industry") from exc

    definition, version = public_plan_pair(db, body.plan)
    if definition.slug == "trial":
        raise HTTPException(400, "Use free registration for the Trial plan")
    subtotal = plan_price(version, body.billing_interval)
    quote = public_tax_quote(
        subtotal,
        tax_enabled=version.tax_enabled,
        gst_rate_bps=version.gst_rate_bps,
    )
    if quote["tax_enabled"] and not (body.state or "").strip():
        raise HTTPException(400, "State is required to create a GST invoice")
    _ensure_signup_not_throttled(db, request, str(body.admin_email))
    config = active_gateway(db)
    if config.provider == "cashfree" and not body.admin_phone:
        raise HTTPException(422, "A phone number is required for Cashfree checkout")
    # A caller-provided high-entropy token lets the same browser safely recover
    # an idempotent checkout when the create response is lost in transit.
    access_token = body.checkout_token or secrets.token_urlsafe(36)
    checkout = SignupCheckout(
        status="creating",
        idempotency_key=body.idempotency_key,
        access_token_hash=token_hash(access_token),
        organization_name=body.organization_name.strip(),
        organization_slug=slug,
        industry=industry.value,
        admin_email=str(body.admin_email).strip().lower(),
        admin_password_hash=hash_signup_password(body.admin_password),
        admin_first_name=body.admin_first_name.strip(),
        admin_last_name=body.admin_last_name.strip(),
        admin_phone=body.admin_phone,
        location_name=body.location_name.strip(),
        city=body.city.strip() if body.city else None,
        state=body.state.strip() if body.state else None,
        plan_version_id=version.id,
        plan_snapshot={
            "slug": definition.slug,
            "name": definition.name,
            "version": version.version,
            "plan_version_id": version.id,
            "ai_credits": version.included_ai_credits,
        },
        billing_interval=body.billing_interval,
        subtotal_paise=quote["subtotal_paise"],
        tax_paise=quote["tax_paise"],
        total_paise=quote["total_paise"],
        tax_enabled=quote["tax_enabled"],
        gst_rate_bps=quote["gst_rate_bps"],
        currency=quote["currency"],
        provider=config.provider,
        provider_mode=config.mode,
        expires_at=now + CHECKOUT_TTL,
    )
    db.add(checkout)
    db.add(AuthAttempt(
        identifier_hash=identifier_hash(str(body.admin_email)),
        ip_address=client_ip(request),
        kind="signup_checkout",
        succeeded=True,
    ))
    db.flush()
    create_legal_acceptance(
        db,
        documents=legal_documents,
        subject_email=checkout.admin_email,
        source="paid_registration_checkout",
        signup_checkout_id=checkout.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    try:
        order = create_provider_order(
            config,
            reference_id=checkout.id,
            amount_paise=int(checkout.total_paise),
            currency=checkout.currency,
            customer={
                "id": checkout.id,
                "name": f"{checkout.admin_first_name} {checkout.admin_last_name}".strip(),
                "email": checkout.admin_email,
                "phone": checkout.admin_phone,
            },
            notes={
                "signup_checkout_id": checkout.id,
                "plan": definition.slug,
                "billing_interval": checkout.billing_interval,
                "mode": config.mode,
                "description": f"Edvatiq {definition.name} signup",
            },
            idempotency_key=checkout.idempotency_key,
            expires_at=checkout.expires_at,
            return_url=f"{settings.APP_URL.rstrip('/')}/register/payment/{checkout.id}?returned=1",
        )
        checkout.provider_order_id = order["order_id"]
        checkout.provider_session_id = order.get("session_id")
    except HTTPException as exc:
        checkout.status = "failed"
        checkout.last_error = str((exc.headers or {}).get("X-Edvatiq-Error-Code") or "provider_order_failed")
        checkout.admin_password_hash = None
        db.commit()
        raise
    checkout.status = "ready"
    db.commit()
    db.refresh(checkout)
    key_id = config.client_id if config.provider == "razorpay" else None
    return checkout_response(checkout, access_token, key_id or None)


@router.get("/registration/checkouts/{checkout_id}")
def registration_checkout_status(
    checkout_id: str,
    response: Response,
    checkout_token: str = Header(alias="X-Signup-Token", min_length=20, max_length=200),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    checkout = _authorized_checkout(db, checkout_id, checkout_token, lock=True)
    if checkout.status in ACTIVE_CHECKOUT_STATUSES and checkout.expires_at <= datetime.now(timezone.utc):
        checkout.status = "expired"
        db.commit()
    return _checkout_status_payload(checkout)


@router.post("/registration/checkouts/{checkout_id}/reconcile")
def reconcile_registration_checkout(
    checkout_id: str,
    request: Request,
    checkout_token: str = Header(alias="X-Signup-Token", min_length=20, max_length=200),
    db: Session = Depends(get_db),
):
    checkout = _authorized_checkout(db, checkout_id, checkout_token, lock=True)
    return _reconcile_signup_checkout(db, checkout, request)


@router.post("/registration/checkouts/{checkout_id}/cancel")
def cancel_registration_checkout(
    checkout_id: str,
    checkout_token: str = Header(alias="X-Signup-Token", min_length=20, max_length=200),
    db: Session = Depends(get_db),
):
    checkout = _authorized_checkout(db, checkout_id, checkout_token, lock=True)
    if checkout.status in {"completed", "paid", "manual_review"}:
        raise HTTPException(409, "This checkout can no longer be cancelled")
    if checkout.status in INACTIVE_CHECKOUT_STATUSES:
        checkout.admin_password_hash = None
        db.commit()
        return _checkout_status_payload(checkout)

    cancellation = terminate_provider_order(
        provider=checkout.provider,
        mode=checkout.provider_mode,
        order_id=checkout.provider_order_id,
    )
    if cancellation["status"] == "paid":
        raise HTTPException(409, "Payment has already been received. Check payment status")
    if cancellation["status"] != "cancelled":
        raise HTTPException(409, "The payment provider is still processing this checkout. Try again shortly")
    checkout.status = "cancelled"
    checkout.last_error = "cancelled_by_user"
    checkout.admin_password_hash = None
    db.commit()
    return _checkout_status_payload(checkout)


@router.post("/registration/checkouts/{checkout_id}/mock-pay")
def mock_registration_payment(
    checkout_id: str,
    body: PaidSignupAccessRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    checkout = _authorized_checkout(db, checkout_id, body.checkout_token, lock=True)
    if checkout.provider_mode != "mock" or settings.ENVIRONMENT == "production":
        raise HTTPException(404, "Not available")
    if checkout.status != "completed" and checkout.expires_at <= datetime.now(timezone.utc):
        checkout.status = "expired"
        db.commit()
        raise HTTPException(409, "This signup checkout has expired")
    payment_id = f"mock-payment-{checkout.id}"
    if checkout.status in INACTIVE_CHECKOUT_STATUSES or checkout.status == "manual_review":
        checkout.status = "manual_review"
        checkout.provider_payment_id = payment_id
        checkout.last_error = "late_payment_inactive_checkout"
        checkout.admin_password_hash = None
        db.commit()
        return _checkout_status_payload(checkout)
    if checkout.status != "completed":
        checkout.status = "paid"
    organization, owner, created = finalize_signup(
        db,
        checkout,
        payment_id,
        ip_address=client_ip(request),
    )
    db.commit()
    sent, test_code = _send_signup_verification(db, checkout, owner, request) if created else (True, None)
    return _completed_signup_payload(
        checkout,
        organization,
        owner,
        email_sent=sent,
        test_code=test_code,
    )


@router.post("/registration/payment/verify")
def verify_registration_payment(
    body: PaidSignupVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    checkout = _authorized_checkout(db, body.checkout_id, body.checkout_token, lock=True)
    return _reconcile_signup_checkout(
        db,
        checkout,
        request,
        razorpay_order_id=body.razorpay_order_id,
        razorpay_payment_id=body.razorpay_payment_id,
        razorpay_signature=body.razorpay_signature,
    )


@router.post("/email/request-code")
def request_verification_code(body: CodeRequest, request: Request, db: Session = Depends(get_db)):
    user = _single_user(db, body.email, body.org_slug)
    test_code = None
    if user and user.is_active and not user.email_verified:
        try: _, test_code = _deliver_code(db, user, "email_verification", request)
        except HTTPException: pass
    return {"message": PUBLIC_MESSAGE, **({"test_code": test_code} if test_code else {})}


@router.post("/email/verify", response_model=LoginResponse)
def verify_email(body: VerifyEmailRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = _single_user(db, body.email, body.org_slug)
    if not user or not user.is_active: raise HTTPException(400, "Code is invalid or expired")
    if user.email_verified: raise HTTPException(409, "Email is already verified. Please sign in")
    consume_auth_code(db, user, "email_verification", body.code)
    user.email_verified = True
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="auth.email_verified", ip_address=client_ip(request))
    return _session_response(db, user, request, response)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _ensure_login_not_throttled(db, request, body.email, body.org_slug)
    users = _find_users(db, body.email, body.org_slug)
    if len(users) > 1 and not body.org_slug:
        raise HTTPException(400, "Workspace slug is required for this email")
    user = users[0] if len(users) == 1 else None
    password_ok = verify_password(body.password, user.hashed_password if user else DUMMY_PASSWORD_HASH)
    if not user or not password_ok:
        _record_attempt(db, request, body.email, body.org_slug, "login", False, user)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active: raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    if user.organization_id:
        org = db.get(Organization, user.organization_id)
        if not org or org.status.value in {"suspended", "cancelled"}: raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is not active")
    if not user.email_verified: raise HTTPException(status.HTTP_403_FORBIDDEN, "Email is not verified")
    mfa_verified = False
    mfa_pending = False
    if user.is_super_admin:
        from app.models import PlatformMFADevice
        from app.services.platform_security import verify_mfa_or_recovery
        device = db.execute(select(PlatformMFADevice).where(PlatformMFADevice.user_id == user.id, PlatformMFADevice.verified.is_(True))).scalar_one_or_none()
        if device and not body.mfa_code:
            raise HTTPException(428, "Enter the code from your authenticator app")
        if device and not verify_mfa_or_recovery(db, user, body.mfa_code or ""):
            _record_attempt(db, request, body.email, body.org_slug, "login", False, user)
            raise HTTPException(401, "Authentication code is invalid")
        mfa_verified = bool(device)
    elif user.organization_id:
        from app.services.user_security import mfa_requirement, verify_user_mfa_or_recovery
        mfa_state = mfa_requirement(db, user)
        if mfa_state["enabled"] and not body.mfa_code:
            raise HTTPException(428, "Enter the code from your authenticator app")
        if mfa_state["enabled"] and not verify_user_mfa_or_recovery(db, user, body.mfa_code or ""):
            _record_attempt(db, request, body.email, body.org_slug, "login", False, user)
            raise HTTPException(401, "Authentication code is invalid")
        mfa_verified = mfa_state["enabled"]
        mfa_pending = mfa_state["required"] and not mfa_state["enabled"]
    _record_attempt(db, request, body.email, body.org_slug, "login", True, user)
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="auth.login", ip_address=client_ip(request))
    return _session_response(db, user, request, response, mfa_verified=mfa_verified, mfa_pending=mfa_pending)


@router.post("/platform-invite/accept", response_model=LoginResponse)
def accept_platform_invite(body: PlatformInviteAccept, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(func.lower(User.email) == body.email.strip().lower(), User.organization_id.is_(None), User.is_super_admin.is_(True))).scalar_one_or_none()
    if not user or not user.is_active or user.email_verified: raise HTTPException(400, "Invitation is invalid or has expired")
    consume_auth_code(db, user, "platform_invite", body.code)
    user.hashed_password = hash_password(body.new_password); user.email_verified = True; user.session_version += 1
    log_action(db, organization_id=None, user_id=user.id, action="platform.invite_accepted", resource_type="platform_user", resource_id=user.id, ip_address=client_ip(request))
    return _session_response(db, user, request, response)


@router.post("/refresh", response_model=LoginResponse)
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw: clear_auth_cookies(response); raise HTTPException(401, "Missing refresh session")
    try: payload = decode_token(raw)
    except Exception: clear_auth_cookies(response); raise HTTPException(401, "Invalid refresh session")
    if payload.get("type") != "refresh": clear_auth_cookies(response); raise HTTPException(401, "Wrong token type")
    row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw)).with_for_update()).scalar_one_or_none()
    if not row or row.revoked:
        if row:
            db.query(RefreshToken).filter(RefreshToken.user_id == row.user_id, RefreshToken.family_id == row.family_id).update({RefreshToken.revoked: True})
            db.commit()
        clear_auth_cookies(response); raise HTTPException(401, "Session reuse detected. Please sign in again")
    if row.expires_at < datetime.now(timezone.utc):
        row.revoked = True; db.commit(); clear_auth_cookies(response); raise HTTPException(401, "Refresh session expired")
    user = db.get(User, row.user_id)
    if not user or not user.is_active: clear_auth_cookies(response); raise HTTPException(401, "User inactive")
    if payload.get("sv") != user.session_version: clear_auth_cookies(response); raise HTTPException(401, "Session has been revoked")
    if user.organization_id:
        from app.services.user_security import mfa_requirement
        mfa_state = mfa_requirement(db, user)
        if (mfa_state["enabled"] or mfa_state["required"]) and not payload.get("mfa_verified"):
            row.revoked = True
            db.commit()
            clear_auth_cookies(response)
            raise HTTPException(428, "Sign in again to finish authenticator security")
    return _session_response(
        db, user, request, response, family_id=row.family_id, replaced=row,
        mfa_verified=bool(payload.get("mfa_verified")), mfa_pending=bool(payload.get("mfa_pending")),
    )


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if raw:
        row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw))).scalar_one_or_none()
        if row: row.revoked = True; row.last_used_at = datetime.now(timezone.utc); db.commit()
    clear_auth_cookies(response)
    return {"ok": True}


@router.post("/password/forgot")
def forgot_password(body: CodeRequest, request: Request, db: Session = Depends(get_db)):
    user = _single_user(db, body.email, body.org_slug)
    test_code = None
    if user and user.is_active:
        try: _, test_code = _deliver_code(db, user, "password_reset", request)
        except HTTPException: pass
    return {"message": PUBLIC_MESSAGE, **({"test_code": test_code} if test_code else {})}


@router.post("/password/reset")
def reset_password(body: ResetPasswordRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = _single_user(db, body.email, body.org_slug)
    if not user or not user.is_active: raise HTTPException(400, "Code is invalid or expired")
    consume_auth_code(db, user, "password_reset", body.code)
    user.hashed_password = hash_password(body.new_password)
    user.session_version += 1
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False)).update({RefreshToken.revoked: True})
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="auth.password_reset", ip_address=client_ip(request))
    db.commit(); clear_auth_cookies(response)
    return {"ok": True, "message": "Password reset. Sign in with your new password"}


@router.get("/sessions")
def sessions(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    current_hash = token_hash(raw) if raw else None
    now = datetime.now(timezone.utc)
    rows = db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False), RefreshToken.expires_at > now).order_by(RefreshToken.created_at.desc())).scalars().all()
    return [{"id": row.id, "created_at": row.created_at, "last_used_at": row.last_used_at, "expires_at": row.expires_at, "user_agent": row.user_agent, "ip_address": row.ip_address, "is_current": row.token_hash == current_hash} for row in rows]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: str, request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(RefreshToken, session_id)
    if not row or row.user_id != user.id: raise HTTPException(404, "Session not found")
    current = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    is_current = bool(current and row.token_hash == token_hash(current))
    row.revoked = True; db.commit()
    if is_current: clear_auth_cookies(response)
    return {"ok": True, "signed_out": is_current}


@router.post("/sessions/revoke-all")
def revoke_all_sessions(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False)).update({RefreshToken.revoked: True})
    user.session_version += 1
    db.commit(); clear_auth_cookies(response); return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.rbac import get_user_permissions, get_user_roles
    from app.services.access_policy import (
        COLLEGE_POLICY_RELEVANT_PERMISSIONS,
        policy_summary,
        policy_v2_enabled,
        resolve_policy_context,
    )
    perms = set(get_user_permissions(db, user)); roles = [{"id": role.id, "name": role.name, "slug": role.slug} for role in get_user_roles(db, user)]
    org = db.get(Organization, user.organization_id) if user.organization_id else None
    access_context = resolve_policy_context(db, user) if user.organization_id else None
    if (
        org
        and getattr(org.industry, "value", org.industry) == "college"
        and policy_v2_enabled(db, org.id)
        and access_context
        and not access_context.active
    ):
        perms.difference_update(COLLEGE_POLICY_RELEVANT_PERMISSIONS)
    user_data = UserOut.model_validate(user).model_dump()
    if user.organization_id:
        from app.services.user_security import mfa_requirement
        state = mfa_requirement(db, user)
        user_data.update({"mfa_enabled": state["enabled"], "mfa_required": state["required"], "mfa_enrollment_required": state["required"] and not state["enabled"]})
    return {
        "user": user_data, "permissions": sorted(perms), "roles": roles,
        "access_context": policy_summary(access_context) if access_context else None,
        "organization": {"id": org.id, "name": org.name, "slug": org.slug, "industry": org.industry.value, "plan": org.plan.value, "status": org.status.value, "ai_provider": org.ai_provider, "enabled_modules": org.enabled_modules, "timezone": org.timezone, "onboarding_complete": org.onboarding_complete} if org else None,
    }
