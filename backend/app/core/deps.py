"""FastAPI dependencies: DB session, auth, tenant, permissions."""
from typing import Annotated
import hashlib
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.security import decode_token
from app.models import Organization, Subscription, SupportSession, User


EXPIRED_TRIAL_ALLOWED_PATHS = (
    "/api/auth",
    "/api/billing",
    "/api/events",
    "/api/notifications",
    "/api/organization/context",
    "/api/users/me",
)

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    raw_token = creds.credentials if creds else request.cookies.get(settings.ACCESS_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing authentication session")
    try:
        payload = decode_token(raw_token)
    except ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    if payload.get("sv") != user.session_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
    if payload.get("av", user.access_version) != user.access_version:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "access_changed", "message": "Your access changed. Refreshing permissions."},
        )
    platform_actor = user
    support_token = request.headers.get("x-support-session")
    support_session_active = False
    if support_token:
        if not user.is_super_admin or user.organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Support sessions require a platform administrator")
        token_digest = hashlib.sha256(support_token.encode()).hexdigest()
        support = db.execute(select(SupportSession).where(SupportSession.token_hash == token_digest)).scalar_one_or_none()
        if not support or support.platform_user_id != user.id or support.status != "active" or support.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Support session is no longer active")
        unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        permanently_blocked = any(part in request.url.path.lower() for part in ("billing", "payment", "refund", "access", "role", "clinical/sign", "export", "delete", "message"))
        if unsafe and (support.mode != "limited_write" or permanently_blocked):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This support session cannot make that change")
        effective = db.get(User, support.target_user_id)
        if not effective or not effective.is_active or effective.organization_id != support.organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Support target is unavailable")
        user = effective
        request.state.platform_actor = platform_actor
        request.state.support_session = support
        from app.services.audit import platform_audit_context
        platform_audit_context.set({"platform_actor_user_id": platform_actor.id, "support_session_id": support.id, "effective_user_id": user.id})
        support_session_active = True
    if user.organization_id:
        org = db.get(Organization, user.organization_id)
        if not org or org.status.value in {"suspended", "cancelled"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Organization is not active")
        if not support_session_active:
            subscription = db.execute(
                select(Subscription).where(Subscription.organization_id == org.id)
                .order_by(Subscription.created_at.desc())
            ).scalars().first()
            from app.services.subscriptions import effective_subscription_status
            allowed = request.url.path.startswith(EXPIRED_TRIAL_ALLOWED_PATHS)
            if effective_subscription_status(subscription) == "expired" and not allowed:
                raise HTTPException(
                    status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Your 30-day free trial has ended. Choose a plan to continue.",
                )
        if not support_session_active:
            from app.services.user_security import mfa_requirement
            security = mfa_requirement(db, user)
            requires_verified_session = security["required"] or security["enabled"]
            mfa_allowed = request.url.path.startswith((
                "/api/auth/me", "/api/auth/logout", "/api/users/me/mfa", "/api/users/me/security",
                "/api/organization/context",
            ))
            if requires_verified_session and not payload.get("mfa_verified") and not mfa_allowed:
                raise HTTPException(
                    status.HTTP_428_PRECONDITION_REQUIRED,
                    detail="Finish authenticator security to continue",
                )
    request.state.user = user
    request.state.tenant_id = user.organization_id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_super_admin(user: CurrentUser) -> User:
    if not user.is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Super admin required")
    return user


def require_tenant(user: CurrentUser) -> User:
    if not user.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No organization context")
    return user


def require_permissions(*codes: str):
    """Dependency factory that ensures user has ALL required permission codes."""
    from app.services.rbac import user_has_permissions

    def _check(
        user: CurrentUser,
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        if user.is_super_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Start an audited support session before accessing a tenant workspace",
            )
        if not user_has_permissions(db, user, list(codes)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {', '.join(codes)}")
        organization = db.get(Organization, user.organization_id)
        if organization and getattr(organization.industry, "value", organization.industry) == "college":
            from app.services.access_policy import (
                COLLEGE_POLICY_RELEVANT_PERMISSIONS,
                policy_v2_enabled,
                resolve_policy_context,
            )
            if (
                set(codes).intersection(COLLEGE_POLICY_RELEVANT_PERMISSIONS)
                and policy_v2_enabled(db, organization.id)
                and not resolve_policy_context(db, user).active
            ):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail="Your College data access is awaiting review",
                )
        from app.services.entitlements import entitlement_value, module_enabled
        module_map = {
            "clients": "clients", "client_memory": "clients", "client_signals": "clients",
            "employees": "employees", "catalog": "catalog", "inventory": "inventory",
            "appointments": "appointments", "sales": "sales", "payments": "sales",
            "gym": "gym", "clinic": "clinic", "clinical": "clinic", "pharmacy": "clinic",
            "documents": "documents", "reports": "reports", "notifications": "notifications", "ai": "ai",
        }
        disabled = {module_map.get(code.split(".", 1)[0]) for code in codes}
        disabled.discard(None)
        for module in disabled:
            if not module_enabled(db, organization, module):
                raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail=f"{module.replace('_', ' ').title()} is not included in the current plan")
        capability_map = {
            "ai.actions": "ai.actions",
            "ai.views.share": "ai.views.share",
            "notifications.send": "communications.send",
        }
        missing_capability = next((capability_map[code] for code in codes if code in capability_map and not entitlement_value(db, organization, capability_map[code], False)), None)
        if missing_capability:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail="This capability is not included in the current plan")
        return user

    return _check


def require_any_permission(*codes: str):
    """Require at least one action while preserving normal entitlement checks."""
    from app.services.rbac import get_user_permissions

    def _check(
        user: CurrentUser,
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        if user.is_super_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Start an audited support session before accessing a tenant workspace",
            )
        granted = get_user_permissions(db, user)
        matched = granted.intersection(codes)
        if not matched:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This settings area is not available for your role")
        organization = db.get(Organization, user.organization_id)
        if organization and getattr(organization.industry, "value", organization.industry) == "college":
            from app.services.access_policy import (
                COLLEGE_POLICY_RELEVANT_PERMISSIONS,
                policy_v2_enabled,
                resolve_policy_context,
            )
            if (
                matched.intersection(COLLEGE_POLICY_RELEVANT_PERMISSIONS)
                and policy_v2_enabled(db, organization.id)
                and not resolve_policy_context(db, user).active
            ):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail="Your College data access is awaiting review",
                )
        return user

    return _check


def require_entitlements(*codes: str):
    """Require plan capabilities independently from user permissions."""
    from app.services.entitlements import entitlement_value

    def _check(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> User:
        if user.is_super_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Start an audited support session before accessing a tenant workspace",
            )
        organization = db.get(Organization, user.organization_id)
        if not organization:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Organization is unavailable")
        if any(not bool(entitlement_value(db, organization, code, False)) for code in codes):
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail="This capability is not included in the current plan")
        return user

    return _check
