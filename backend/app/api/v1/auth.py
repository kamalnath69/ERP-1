"""Secure cookie authentication, email verification, recovery, and sessions."""
import secrets
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.db.seed import seed_organization_defaults
from app.models import AuthAttempt, IndustryEnum, Location, Organization, RefreshToken, User
from app.schemas import CodeRequest, LoginRequest, LoginResponse, RegisterOrgRequest, ResetPasswordRequest, UserOut, VerifyEmailRequest, validate_strong_password
from app.services.audit import log_action
from app.services.auth_security import (
    clear_auth_cookies, client_ip, consume_auth_code, create_auth_code, identifier_hash,
    new_csrf_token, set_auth_cookies, token_hash,
)
from app.services.email import send_auth_code_email

router = APIRouter(prefix="/auth", tags=["auth"])
DUMMY_PASSWORD_HASH = hash_password("NotARealPassword123")
PUBLIC_MESSAGE = "If the account exists, a code has been sent"


class PlatformInviteAccept(BaseModel):
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
    access = create_access_token(user.id, user.organization_id, {"is_super": user.is_super_admin, "sv": user.session_version, **security_claims})
    refresh = create_refresh_token(user.id, user.organization_id, {"family": family_id or secrets.token_hex(16), "sv": user.session_version, **security_claims})
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


@router.get("/organization-id/availability")
def organization_id_availability(value: str, db: Session = Depends(get_db)):
    business_id = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", business_id) or not 2 <= len(business_id) <= 80:
        return {"value": business_id, "available": False, "valid": False, "message": "Use lowercase letters, numbers, and single hyphens", "suggestions": []}
    exists = db.execute(select(Organization.id).where(Organization.slug == business_id)).first() is not None
    suggestions = []
    if exists:
        candidates = [f"{business_id}-hq", f"{business_id}-india", f"{business_id}-2"]
        used = set(db.execute(select(Organization.slug).where(Organization.slug.in_(candidates))).scalars())
        suggestions = [candidate for candidate in candidates if candidate not in used]
    return {"value": business_id, "available": not exists, "valid": True, "message": "Available" if not exists else "Already used by another business", "suggestions": suggestions}


@router.post("/register", status_code=201)
def register_organization(body: RegisterOrgRequest, request: Request, db: Session = Depends(get_db)):
    slug = body.organization_slug.strip().lower()
    if db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Organization slug already exists")
    try: industry = IndustryEnum(body.industry)
    except ValueError: raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid industry")
    module_map = {
        "gym": ["clients", "employees", "catalog", "inventory", "sales", "appointments", "gym", "ai"],
        "salon": ["clients", "employees", "catalog", "inventory", "sales", "appointments", "salon", "ai"],
        "clinic": ["clients", "employees", "catalog", "inventory", "sales", "appointments", "clinic", "documents", "ai"],
        "college": ["clients", "employees", "sales", "college", "documents", "reports", "notifications", "ai"],
    }
    org = Organization(name=body.organization_name, slug=slug, industry=industry, enabled_modules=module_map[industry.value], contact_email=body.admin_email.lower())
    db.add(org); db.flush()
    admin = User(
        organization_id=org.id, email=body.admin_email.lower(), hashed_password=hash_password(body.admin_password),
        first_name=body.admin_first_name, last_name=body.admin_last_name, is_active=True, email_verified=False,
    )
    db.add(admin); db.flush()
    location = Location(organization_id=org.id, name=body.location_name, code="MAIN", city=body.city, is_primary=True)
    db.add(location); db.flush(); seed_organization_defaults(db, org, admin, location)
    log_action(db, organization_id=org.id, user_id=admin.id, action="organization.register", resource_type="organization", resource_id=org.id, ip_address=client_ip(request))
    db.commit()
    sent, test_code = _deliver_code(db, admin, "email_verification", request)
    return {"requires_verification": True, "email": admin.email, "organization_slug": org.slug, "email_sent": sent, **({"test_code": test_code} if test_code else {})}


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
    perms = list(get_user_permissions(db, user)); roles = [{"id": role.id, "name": role.name, "slug": role.slug} for role in get_user_roles(db, user)]
    org = db.get(Organization, user.organization_id) if user.organization_id else None
    user_data = UserOut.model_validate(user).model_dump()
    if user.organization_id:
        from app.services.user_security import mfa_requirement
        state = mfa_requirement(db, user)
        user_data.update({"mfa_enabled": state["enabled"], "mfa_required": state["required"], "mfa_enrollment_required": state["required"] and not state["enabled"]})
    return {
        "user": user_data, "permissions": perms, "roles": roles,
        "organization": {"id": org.id, "name": org.name, "slug": org.slug, "industry": org.industry.value, "plan": org.plan.value, "status": org.status.value, "ai_provider": org.ai_provider, "enabled_modules": org.enabled_modules, "timezone": org.timezone, "onboarding_complete": org.onboarding_complete} if org else None,
    }
