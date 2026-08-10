"""Platform permissions, authenticator MFA, and recovery codes."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timezone
from urllib.parse import quote

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.deps import get_current_user
from app.models import (
    PlatformMFADevice, PlatformPermission, PlatformRecoveryCode, PlatformRolePermission,
    PlatformUserRole, User,
)


def platform_permissions(db: Session, user: User) -> set[str]:
    if not user.is_super_admin:
        return set()
    return set(db.execute(
        select(PlatformPermission.code)
        .join(PlatformRolePermission, PlatformRolePermission.permission_id == PlatformPermission.id)
        .join(PlatformUserRole, PlatformUserRole.role_id == PlatformRolePermission.role_id)
        .where(PlatformUserRole.user_id == user.id)
    ).scalars())


def require_platform_permission(*codes: str):
    def dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        granted = platform_permissions(db, user)
        if not user.is_super_admin or not set(codes).issubset(granted):
            raise HTTPException(403, "This platform action is not available for your role")
        return user
    return dependency


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode()).decode()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def provisioning_uri(email: str, secret: str) -> str:
    label = quote(f"Edvatiq:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer=Edvatiq&algorithm=SHA1&digits=6&period=30"


def _totp(secret: str, step: int) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def verify_totp(device: PlatformMFADevice, code: str, *, consume: bool = True) -> bool:
    now_step = int(time.time() // 30)
    secret = decrypt_secret(device.secret_encrypted)
    for step in range(now_step - 1, now_step + 2):
        if hmac.compare_digest(_totp(secret, step), code.strip()):
            if consume and device.last_used_step is not None and step <= device.last_used_step:
                return False
            if consume:
                device.last_used_step = step
            return True
    return False


def create_recovery_codes(db: Session, user: User) -> list[str]:
    db.query(PlatformRecoveryCode).filter(PlatformRecoveryCode.user_id == user.id).delete()
    codes = [secrets.token_hex(4).upper() for _ in range(10)]
    for code in codes:
        db.add(PlatformRecoveryCode(user_id=user.id, code_hash=hashlib.sha256(code.encode()).hexdigest()))
    return codes


def verify_mfa_or_recovery(db: Session, user: User, code: str) -> bool:
    device = db.execute(select(PlatformMFADevice).where(PlatformMFADevice.user_id == user.id, PlatformMFADevice.verified.is_(True))).scalar_one_or_none()
    if device and code.isdigit() and verify_totp(device, code):
        return True
    digest = hashlib.sha256(code.strip().upper().encode()).hexdigest()
    recovery = db.execute(select(PlatformRecoveryCode).where(
        PlatformRecoveryCode.user_id == user.id, PlatformRecoveryCode.code_hash == digest,
        PlatformRecoveryCode.used_at.is_(None),
    )).scalar_one_or_none()
    if recovery:
        recovery.used_at = datetime.now(timezone.utc)
        return True
    return False
