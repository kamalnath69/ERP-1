"""Authenticator MFA and recovery codes for tenant users."""
import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, User, UserMFADevice, UserRecoveryCode, UserRole
from app.services.platform_security import (
    decrypt_secret,
    encrypt_secret,
    generate_totp_secret,
    provisioning_uri,
    verify_totp,
)


PRIVILEGED_ROLE_SLUGS = {"owner", "manager", "accountant"}


def mfa_device(db: Session, user: User, *, verified: bool | None = True) -> UserMFADevice | None:
    statement = select(UserMFADevice).where(UserMFADevice.user_id == user.id)
    if verified is not None:
        statement = statement.where(UserMFADevice.verified.is_(verified))
    return db.execute(statement).scalar_one_or_none()


def mfa_requirement(db: Session, user: User) -> dict:
    device = mfa_device(db, user, verified=True)
    if not user.organization_id:
        return {"enabled": bool(device), "required": False, "policy": "optional"}
    from app.models import Organization
    organization = db.get(Organization, user.organization_id)
    policy = (organization.security_settings or {}).get("mfa_policy", "optional") if organization else "optional"
    required = policy == "all"
    if policy == "privileged":
        role_slugs = set(db.execute(
            select(Role.slug).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
        ).scalars())
        required = bool(role_slugs.intersection(PRIVILEGED_ROLE_SLUGS))
    return {"enabled": bool(device), "required": required, "policy": policy}


def begin_mfa_enrollment(db: Session, user: User) -> dict:
    current = mfa_device(db, user, verified=True)
    if current:
        raise ValueError("Authenticator security is already enabled")
    db.query(UserMFADevice).filter(UserMFADevice.user_id == user.id).delete()
    secret = generate_totp_secret()
    device = UserMFADevice(
        organization_id=user.organization_id,
        user_id=user.id,
        secret_encrypted=encrypt_secret(secret),
        verified=False,
    )
    db.add(device)
    db.flush()
    return {"secret": secret, "provisioning_uri": provisioning_uri(user.email, secret)}


def complete_mfa_enrollment(db: Session, user: User, code: str) -> list[str]:
    device = mfa_device(db, user, verified=False)
    if not device or not verify_totp(device, code):
        raise ValueError("Authenticator code is invalid")
    device.verified = True
    codes = replace_recovery_codes(db, user)
    return codes


def _recovery_digest(code: str) -> str:
    normalized = code.strip().upper().replace("-", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def replace_recovery_codes(db: Session, user: User) -> list[str]:
    db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == user.id).delete()
    codes = []
    for _ in range(10):
        raw = secrets.token_hex(4).upper()
        display = f"{raw[:4]}-{raw[4:]}"
        codes.append(display)
        db.add(UserRecoveryCode(
            organization_id=user.organization_id,
            user_id=user.id,
            code_hash=_recovery_digest(display),
        ))
    return codes


def verify_user_mfa_or_recovery(db: Session, user: User, code: str) -> bool:
    device = mfa_device(db, user, verified=True)
    normalized = code.strip()
    if device and normalized.isdigit() and verify_totp(device, normalized):
        return True
    recovery = db.execute(select(UserRecoveryCode).where(
        UserRecoveryCode.user_id == user.id,
        UserRecoveryCode.code_hash == _recovery_digest(normalized),
        UserRecoveryCode.used_at.is_(None),
    ).with_for_update()).scalar_one_or_none()
    if not recovery:
        return False
    recovery.used_at = datetime.now(timezone.utc)
    return True


def recovery_codes_remaining(db: Session, user: User) -> int:
    return len(db.execute(select(UserRecoveryCode.id).where(
        UserRecoveryCode.user_id == user.id,
        UserRecoveryCode.used_at.is_(None),
    )).all())


def disable_user_mfa(db: Session, user: User) -> None:
    db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == user.id).delete()
    db.query(UserMFADevice).filter(UserMFADevice.user_id == user.id).delete()
