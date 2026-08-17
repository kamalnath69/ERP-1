"""Pre-registration email challenges and one-time signup proofs."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import SignupEmailChallenge
from app.schemas import SignupEmailVerificationProof
from app.services.auth_security import client_ip, identifier_hash, token_hash


def normalize_signup_email(value: str) -> str:
    return value.strip().lower()


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
    if latest and latest.created_at > now - timedelta(seconds=settings.SIGNUP_EMAIL_RESEND_SECONDS):
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
        )
    ) or 0
    if recent >= settings.SIGNUP_EMAIL_MAX_SENDS_15_MINUTES:
        raise HTTPException(429, "Too many verification codes. Please wait 15 minutes")

    for row in db.execute(select(SignupEmailChallenge).where(
        SignupEmailChallenge.email_hash == email_hash,
        SignupEmailChallenge.status == "pending",
    )).scalars():
        row.status = "superseded"

    challenge_id = str(uuid4())
    challenge_token = secrets.token_urlsafe(48)
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = SignupEmailChallenge(
        id=challenge_id,
        email=normalized,
        email_hash=email_hash,
        browser_token_hash=token_hash(challenge_token),
        code_hash=_code_hash(challenge_id, code),
        status="pending",
        attempts=0,
        request_ip=ip_address,
        resend_at=now + timedelta(seconds=settings.SIGNUP_EMAIL_RESEND_SECONDS),
        expires_at=now + timedelta(minutes=settings.AUTH_CODE_TTL_MINUTES),
    )
    db.add(challenge)
    db.flush()
    return challenge, challenge_token, code


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
