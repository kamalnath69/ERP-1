"""JWT + password hashing helpers."""
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _encode(payload: dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
    import secrets
    now = datetime.now(timezone.utc)
    to_encode = payload.copy()
    to_encode.update({
        "exp": now + expires_delta,
        "iat": now,
        "type": token_type,
        "jti": secrets.token_urlsafe(16),
    })
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, tenant_id: str | None, extra: dict | None = None) -> str:
    payload = {"sub": subject, "tid": tenant_id, **(extra or {})}
    return _encode(payload, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")


def create_refresh_token(subject: str, tenant_id: str | None, extra: dict | None = None) -> str:
    return _encode({"sub": subject, "tid": tenant_id, **(extra or {})}, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
