"""One-time-code hashing, signed CSRF tokens, and secure cookie helpers."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuthCode, User


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def identifier_hash(value: str) -> str:
    return hmac.new(settings.JWT_SECRET_KEY.encode(), value.strip().lower().encode(), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _code_hash(user_id: str, purpose: str, code: str) -> str:
    material = f"{user_id}:{purpose}:{code}".encode()
    return hmac.new(settings.JWT_SECRET_KEY.encode(), material, hashlib.sha256).hexdigest()


def create_auth_code(db: Session, user: User, purpose: str, request: Request) -> str:
    now = datetime.now(timezone.utc)
    recent = db.scalar(select(func.count(AuthCode.id)).where(
        AuthCode.user_id == user.id, AuthCode.purpose == purpose,
        AuthCode.created_at >= now - timedelta(minutes=15),
    )) or 0
    if recent >= 3:
        raise HTTPException(429, "Too many code requests. Please wait 15 minutes")
    for row in db.execute(select(AuthCode).where(
        AuthCode.user_id == user.id, AuthCode.purpose == purpose,
        AuthCode.consumed_at.is_(None),
    )).scalars():
        row.consumed_at = now
    code = f"{secrets.randbelow(1_000_000):06d}"
    ttl = settings.PASSWORD_RESET_TTL_MINUTES if purpose == "password_reset" else settings.AUTH_CODE_TTL_MINUTES
    db.add(AuthCode(
        organization_id=user.organization_id, user_id=user.id, purpose=purpose,
        code_hash=_code_hash(user.id, purpose, code), expires_at=now + timedelta(minutes=ttl),
        request_ip=client_ip(request),
    ))
    db.flush()
    return code


def consume_auth_code(db: Session, user: User, purpose: str, code: str) -> AuthCode:
    now = datetime.now(timezone.utc)
    row = db.execute(select(AuthCode).where(
        AuthCode.user_id == user.id, AuthCode.purpose == purpose, AuthCode.consumed_at.is_(None),
    ).order_by(AuthCode.created_at.desc()).with_for_update()).scalars().first()
    if not row or row.expires_at < now or row.attempts >= settings.AUTH_CODE_MAX_ATTEMPTS:
        raise HTTPException(400, "Code is invalid or expired")
    if not hmac.compare_digest(row.code_hash, _code_hash(user.id, purpose, code)):
        row.attempts += 1
        db.commit()
        raise HTTPException(400, "Code is invalid or expired")
    row.consumed_at = now
    return row


def new_csrf_token() -> str:
    nonce = secrets.token_urlsafe(32)
    signature = hmac.new(settings.JWT_SECRET_KEY.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{signature}"


def valid_csrf_token(value: str | None) -> bool:
    if not value or "." not in value:
        return False
    nonce, signature = value.rsplit(".", 1)
    expected = hmac.new(settings.JWT_SECRET_KEY.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def set_auth_cookies(response: Response, access: str, refresh: str, csrf: str) -> None:
    common = {"secure": settings.AUTH_COOKIE_SECURE, "samesite": settings.AUTH_COOKIE_SAMESITE, "domain": settings.AUTH_COOKIE_DOMAIN or None}
    response.set_cookie(settings.ACCESS_COOKIE_NAME, access, httponly=True, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/", **common)
    response.set_cookie(settings.REFRESH_COOKIE_NAME, refresh, httponly=True, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path="/api/auth", **common)
    response.set_cookie(settings.CSRF_COOKIE_NAME, csrf, httponly=False, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path="/", **common)


def clear_auth_cookies(response: Response) -> None:
    domain = settings.AUTH_COOKIE_DOMAIN or None
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, path="/", domain=domain)
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/auth", domain=domain)
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/", domain=domain)
