"""Pre-registration email challenges and one-time signup proofs."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Role, SignupCheckout, SignupEmailChallenge, User, UserRole
from app.schemas import SignupEmailVerificationProof
from app.services.auth_security import client_ip, identifier_hash, token_hash


def normalize_signup_email(value: str) -> str:
    return value.strip().lower()


OWNER_EMAIL_CONFLICT_DETAIL = (
    "This email already owns another business or has an active signup. "
    "Sign in with that Business ID, or use a different owner email."
)
ACTIVE_SIGNUP_STATUSES = {"creating", "ready", "paid"}


def lock_signup_owner_email(db: Session, email: str) -> None:
    """Serialize ownership reservations without exposing account membership."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"signup-owner:{normalize_signup_email(email)}"},
        )


def signup_owner_email_conflict(
    db: Session,
    email: str,
    *,
    exclude_checkout_id: str | None = None,
) -> bool:
    normalized = normalize_signup_email(email)
    existing_owner = db.execute(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            func.lower(User.email) == normalized,
            User.organization_id.is_not(None),
            Role.is_system.is_(True),
            Role.system_key == "owner",
        )
        .limit(1)
    ).first()
    if existing_owner:
        return True

    checkout = select(SignupCheckout.id).where(
        func.lower(SignupCheckout.admin_email) == normalized,
        SignupCheckout.status.in_(ACTIVE_SIGNUP_STATUSES),
        SignupCheckout.expires_at > datetime.now(timezone.utc),
    )
    if exclude_checkout_id:
        checkout = checkout.where(SignupCheckout.id != exclude_checkout_id)
    return db.execute(checkout.limit(1)).first() is not None


def ensure_signup_owner_email_available(db: Session, email: str) -> None:
    lock_signup_owner_email(db, email)
    if signup_owner_email_conflict(db, email):
        raise HTTPException(409, OWNER_EMAIL_CONFLICT_DETAIL)


def _code_hash(challenge_id: str, code: str) -> str:
    material = f"signup-email:{challenge_id}:{code}".encode()
    return hmac.new(settings.JWT_SECRET_KEY.encode(), material, hashlib.sha256).hexdigest()


def create_signup_email_challenge(
    db: Session,
    email: str,
    request: Request,
) -> tuple[SignupEmailChallenge, str, str]:
    now = datetime.now(timezone.utc)
    normalized = normalize_signup_email(email)
    email_hash = identifier_hash(normalized)
    ip_address = client_ip(request)
    recent_filter = SignupEmailChallenge.email_hash == email_hash
    if ip_address:
        recent_filter = or_(recent_filter, SignupEmailChallenge.request_ip == ip_address)

    # Resend cooldown belongs to the address being verified. The broader IP
    # filter is retained below for the rolling abuse limit.
    latest = db.execute(
        select(SignupEmailChallenge)
        .where(SignupEmailChallenge.email_hash == email_hash)
        .order_by(SignupEmailChallenge.created_at.desc())
    ).scalars().first()
    if latest and latest.resend_at > now:
        retry_after = max(1, int((latest.resend_at - now).total_seconds()))
        raise HTTPException(
            429,
            "Wait before requesting another verification code",
            headers={"Retry-After": str(retry_after)},
        )

    recent = db.scalar(
        select(func.count(SignupEmailChallenge.id)).where(
            recent_filter,
            SignupEmailChallenge.created_at >= now - timedelta(minutes=15),
            SignupEmailChallenge.status != "delivery_failed",
        )
    ) or 0
    if recent >= settings.SIGNUP_EMAIL_MAX_SENDS_15_MINUTES:
        raise HTTPException(429, "Too many verification codes. Please wait 15 minutes")
    if ip_address:
        failed_from_ip = db.scalar(select(func.count(SignupEmailChallenge.id)).where(
            SignupEmailChallenge.request_ip == ip_address,
            SignupEmailChallenge.created_at >= now - timedelta(minutes=15),
            SignupEmailChallenge.status == "delivery_failed",
        )) or 0
        if failed_from_ip >= max(5, settings.SIGNUP_EMAIL_MAX_SENDS_15_MINUTES * 3):
            raise HTTPException(429, "Too many delivery attempts. Please wait 15 minutes")

    challenge_id = str(uuid4())
    challenge_token = secrets.token_urlsafe(48)
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = SignupEmailChallenge(
        id=challenge_id,
        email=normalized,
        email_hash=email_hash,
        browser_token_hash=token_hash(challenge_token),
        code_hash=_code_hash(challenge_id, code),
        status="sending",
        attempts=0,
        request_ip=ip_address,
        resend_at=now + timedelta(seconds=settings.SIGNUP_EMAIL_RESEND_SECONDS),
        expires_at=now + timedelta(minutes=settings.AUTH_CODE_TTL_MINUTES),
    )
    db.add(challenge)
    db.flush()
    return challenge, challenge_token, code


def complete_signup_email_delivery(
    db: Session,
    challenge_id: str,
    *,
    usable: bool,
) -> SignupEmailChallenge:
    """Publish a new code only after delivery, preserving any older valid code on failure."""
    challenge = db.execute(
        select(SignupEmailChallenge)
        .where(SignupEmailChallenge.id == challenge_id)
        .with_for_update()
    ).scalar_one()
    now = datetime.now(timezone.utc)
    if usable:
        for row in db.execute(select(SignupEmailChallenge).where(
            SignupEmailChallenge.email_hash == challenge.email_hash,
            SignupEmailChallenge.status == "pending",
            SignupEmailChallenge.id != challenge.id,
        )).scalars():
            row.status = "superseded"
        challenge.status = "pending"
    else:
        challenge.status = "delivery_failed"
        challenge.resend_at = now
        challenge.expires_at = now
    return challenge


def verify_signup_email_challenge(
    db: Session,
    challenge_id: str,
    challenge_token: str,
    code: str,
) -> tuple[SignupEmailChallenge, str]:
    now = datetime.now(timezone.utc)
    try:
        challenge_id = str(UUID(challenge_id))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(400, "Code is invalid or expired") from None
    challenge = db.execute(
        select(SignupEmailChallenge)
        .where(SignupEmailChallenge.id == challenge_id)
        .with_for_update()
    ).scalar_one_or_none()
    invalid = (
        not challenge
        or challenge.status != "pending"
        or challenge.expires_at <= now
        or challenge.attempts >= settings.AUTH_CODE_MAX_ATTEMPTS
        or not hmac.compare_digest(challenge.browser_token_hash, token_hash(challenge_token))
    )
    if invalid:
        if challenge and challenge.status == "pending" and challenge.expires_at <= now:
            challenge.status = "expired"
            db.commit()
        raise HTTPException(400, "Code is invalid or expired")
    if not hmac.compare_digest(challenge.code_hash, _code_hash(challenge.id, code)):
        challenge.attempts += 1
        if challenge.attempts >= settings.AUTH_CODE_MAX_ATTEMPTS:
            challenge.status = "exhausted"
        db.commit()
        raise HTTPException(400, "Code is invalid or expired")

    proof = secrets.token_urlsafe(48)
    challenge.proof_hash = token_hash(proof)
    challenge.status = "verified"
    challenge.verified_at = now
    challenge.proof_expires_at = now + timedelta(minutes=settings.SIGNUP_EMAIL_PROOF_TTL_MINUTES)
    return challenge, proof


def require_signup_email_proof(
    db: Session,
    verification: SignupEmailVerificationProof,
    expected_email: str,
) -> SignupEmailChallenge:
    now = datetime.now(timezone.utc)
    challenge = db.execute(
        select(SignupEmailChallenge)
        .where(SignupEmailChallenge.id == verification.challenge_id)
        .with_for_update()
    ).scalar_one_or_none()
    valid = bool(
        challenge
        and challenge.status == "verified"
        and challenge.consumed_at is None
        and challenge.proof_hash
        and challenge.proof_expires_at
        and challenge.proof_expires_at > now
        and challenge.email == normalize_signup_email(expected_email)
        and hmac.compare_digest(challenge.proof_hash, token_hash(verification.proof))
    )
    if not valid:
        raise HTTPException(400, "Verify the owner email again before continuing")
    return challenge


def bind_signup_email_challenge(challenge: SignupEmailChallenge) -> None:
    challenge.status = "bound"


def consume_signup_email_challenge(challenge: SignupEmailChallenge) -> None:
    challenge.status = "consumed"
    challenge.consumed_at = datetime.now(timezone.utc)
    challenge.proof_hash = None
