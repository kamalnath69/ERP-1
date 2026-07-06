"""Authentication endpoints: register organization, login, refresh, logout, me."""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models import Organization, OrganizationTypeEnum, RefreshToken, User
from app.schemas import LoginRequest, LoginResponse, RefreshRequest, RegisterOrgRequest, UserOut
from app.services.audit import log_action
from app.db.seed import seed_organization_defaults

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue_tokens(db: Session, user: User, request: Request) -> LoginResponse:
    access = create_access_token(user.id, user.organization_id, {"is_super": user.is_super_admin})
    refresh = create_refresh_token(user.id, user.organization_id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_token_hash(refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=(request.headers.get("user-agent") or "")[:300],
            ip_address=(request.client.host if request.client else None),
        )
    )
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return LoginResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user).model_dump(),
    )


@router.post("/register", response_model=LoginResponse)
def register_organization(body: RegisterOrgRequest, request: Request, db: Session = Depends(get_db)):
    slug = body.organization_slug.strip().lower()
    if db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Organization slug already exists")
    if db.execute(select(User).where(User.email == body.admin_email)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    try:
        org_type_enum = OrganizationTypeEnum(body.org_type)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid org_type")

    org = Organization(
        name=body.organization_name,
        slug=slug,
        org_type=org_type_enum,
        contact_email=body.admin_email,
    )
    db.add(org)
    db.flush()

    admin = User(
        organization_id=org.id,
        email=body.admin_email.lower(),
        hashed_password=hash_password(body.admin_password),
        first_name=body.admin_first_name,
        last_name=body.admin_last_name,
        is_active=True,
    )
    db.add(admin)
    db.flush()

    seed_organization_defaults(db, org, admin)

    log_action(
        db,
        organization_id=org.id,
        user_id=admin.id,
        action="organization.register",
        resource_type="organization",
        resource_id=org.id,
        ip_address=(request.client.host if request.client else None),
    )
    db.commit()
    db.refresh(admin)
    return _issue_tokens(db, admin, request)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    q = select(User).where(User.email == body.email.lower())
    user = db.execute(q).scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    if body.org_slug and user.organization_id:
        org = db.get(Organization, user.organization_id)
        if not org or org.slug != body.org_slug.lower():
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organization")

    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.login",
        ip_address=(request.client.host if request.client else None),
    )
    return _issue_tokens(db, user, request)


@router.post("/refresh", response_model=LoginResponse)
def refresh_token(body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    rt = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _token_hash(body.refresh_token))
    ).scalar_one_or_none()
    if not rt or rt.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token revoked")
    if rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")

    rt.revoked = True
    return _issue_tokens(db, user, request)


@router.post("/logout")
def logout(body: RefreshRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rt = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _token_hash(body.refresh_token))
    ).scalar_one_or_none()
    if rt:
        rt.revoked = True
        db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.rbac import get_user_permissions, get_user_roles

    perms = list(get_user_permissions(db, user))
    roles = [{"id": r.id, "name": r.name, "slug": r.slug} for r in get_user_roles(db, user)]
    org = db.get(Organization, user.organization_id) if user.organization_id else None
    return {
        "user": UserOut.model_validate(user).model_dump(),
        "permissions": perms,
        "roles": roles,
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "org_type": org.org_type.value,
            "plan": org.plan.value,
            "status": org.status.value,
            "ai_provider": org.ai_provider,
            "ai_model": org.ai_model,
        }
        if org
        else None,
    }
