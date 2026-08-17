import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import LegalDocument, SignupEmailChallenge


def verified_signup_body(client, body: dict) -> tuple[dict, str]:
    """Attach the same legal acceptance and email proof required in production."""
    payload = dict(body)
    with SessionLocal() as db:
        legal = {
            row.document_type: row.id
            for row in db.execute(
                select(LegalDocument).where(LegalDocument.status == "published")
            ).scalars()
        }
    payload["legal_acceptance"] = {
        "accepted": True,
        "terms_document_id": legal["terms"],
        "privacy_document_id": legal["privacy"],
        "refund_document_id": legal["refund"],
    }
    requested = client.post(
        "/api/auth/registration/email/challenges",
        json={"email": payload["admin_email"]},
    )
    assert requested.status_code == 201, requested.text
    challenge = requested.json()
    verified = client.post(
        f"/api/auth/registration/email/challenges/{challenge['challenge_id']}/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": challenge["test_code"],
        },
    )
    assert verified.status_code == 200, verified.text
    proof = verified.json()
    payload["email_verification"] = {
        "challenge_id": proof["challenge_id"],
        "proof": proof["verification_proof"],
    }
    return payload, challenge["challenge_id"]


def delete_signup_challenge(challenge_id: str) -> None:
    with SessionLocal() as db:
        challenge = db.get(SignupEmailChallenge, challenge_id)
        if challenge:
            db.delete(challenge)
            db.commit()


@pytest.fixture(autouse=True)
def prevent_external_email(monkeypatch):
    """Tests must never consume configured email or AI provider quotas."""
    delivered = lambda *_args, **_kwargs: True
    monkeypatch.setattr(settings, "AUTH_EXPOSE_TEST_CODES", True)
    # Parallel TestClient instances all report the same synthetic source IP.
    monkeypatch.setattr(settings, "SIGNUP_EMAIL_MAX_SENDS_15_MINUTES", 1000)
    # Registration integration tests must not depend on a live Super Admin plan toggle.
    monkeypatch.setattr("app.api.v1.auth.trial_signup_available", lambda _db: True)
    monkeypatch.setattr("app.api.v1.auth.send_auth_code_email", delivered)
    monkeypatch.setattr("app.api.v1.users.send_auth_code_email", delivered)
    monkeypatch.setattr("app.ai.orchestrator.provider", lambda: None)
