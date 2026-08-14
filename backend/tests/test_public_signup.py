"""Public plan visibility and payment-first workspace creation."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.auth_security import token_hash
from app.models import Invoice, Organization, PlanDefinition, PlatformPayment, SignupCheckout, Subscription, User
from server import app


client = TestClient(app, raise_server_exceptions=True)


def registration_body(slug: str, **overrides) -> dict:
    body = {
        "organization_name": "Northstar Fitness",
        "organization_slug": slug,
        "industry": "gym",
        "admin_email": f"owner-{slug}@example.com",
        "admin_password": "StrongPass123",
        "admin_first_name": "Kavya",
        "admin_last_name": "Raman",
        "location_name": "Main Location",
        "city": "Chennai",
        "state": "Tamil Nadu",
    }
    body.update(overrides)
    return body


def test_public_catalog_contains_only_available_published_plans():
    response = client.get("/api/billing/public/plans")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["currency"] == "INR"
    assert payload["trial_enabled"] == any(plan["id"] == "trial" for plan in payload["plans"])
    assert all(plan["monthly_quote"] is None or "total_paise" in plan["monthly_quote"] for plan in payload["plans"])
    assert all("version_id" in plan for plan in payload["plans"])


def test_disabled_trial_blocks_free_account_creation():
    slug = f"paid-only-{uuid4().hex[:10]}"
    with SessionLocal() as db:
        trial = db.execute(select(PlanDefinition).where(PlanDefinition.slug == "trial")).scalar_one()
        original = (trial.is_active, trial.is_public)
        trial.is_active = False
        db.commit()
    try:
        response = client.post("/api/auth/register", json=registration_body(slug))
        assert response.status_code == 409, response.text
        assert "paid plan" in response.json()["detail"].lower()
        with SessionLocal() as db:
            assert not db.execute(select(Organization.id).where(Organization.slug == slug)).first()
    finally:
        with SessionLocal() as db:
            trial = db.execute(select(PlanDefinition).where(PlanDefinition.slug == "trial")).scalar_one()
            trial.is_active, trial.is_public = original
            db.commit()


def test_mock_payment_creates_account_only_after_completion(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_MODE", "mock")
    slug = f"paid-signup-{uuid4().hex[:10]}"
    checkout_id = None
    organization_id = None
    try:
        response = client.post("/api/auth/registration/checkout", json={
            **registration_body(slug),
            "plan": "growth",
            "billing_interval": "monthly",
            "idempotency_key": str(uuid4()),
        })
        assert response.status_code == 201, response.text
        checkout = response.json()
        checkout_id = checkout["checkout_id"]
        assert checkout["status"] == "ready"
        assert checkout["mock_mode"] is True

        with SessionLocal() as db:
            assert not db.execute(select(Organization.id).where(Organization.slug == slug)).first()
            pending = db.get(SignupCheckout, checkout_id)
            assert pending.admin_password_hash and pending.organization_id is None

        completed = client.post(
            f"/api/auth/registration/checkouts/{checkout_id}/mock-pay",
            json={"checkout_token": checkout["checkout_token"]},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["requires_verification"] is True

        with SessionLocal() as db:
            organization = db.execute(select(Organization).where(Organization.slug == slug)).scalar_one()
            organization_id = organization.id
            owner = db.execute(select(User).where(User.organization_id == organization.id)).scalar_one()
            subscription = db.execute(select(Subscription).where(Subscription.organization_id == organization.id)).scalar_one()
            invoice = db.execute(select(Invoice).where(Invoice.organization_id == organization.id)).scalar_one()
            pending = db.get(SignupCheckout, checkout_id)
            assert owner.email_verified is False
            assert subscription.plan == "growth" and subscription.status == "active"
            assert invoice.status == "paid" and invoice.fulfillment_status == "fulfilled"
            assert pending.status == "completed" and pending.admin_password_hash is None

        repeated = client.post(
            f"/api/auth/registration/checkouts/{checkout_id}/mock-pay",
            json={"checkout_token": checkout["checkout_token"]},
        )
        assert repeated.status_code == 200, repeated.text
        with SessionLocal() as db:
            assert len(db.execute(select(Organization.id).where(Organization.slug == slug)).all()) == 1
            assert len(db.execute(select(Invoice).where(Invoice.organization_id == organization_id)).scalars().all()) == 1
    finally:
        with SessionLocal() as db:
            if checkout_id:
                row = db.get(SignupCheckout, checkout_id)
                if row:
                    db.delete(row)
                    db.flush()
            if organization_id:
                db.query(PlatformPayment).filter(PlatformPayment.organization_id == organization_id).delete()
                organization = db.get(Organization, organization_id)
                if organization:
                    db.delete(organization)
            db.commit()


def test_cancelled_checkout_clears_credentials_and_quarantines_a_late_payment(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    token = "signup-token-value-that-is-long-enough"
    slug = f"cancelled-signup-{uuid4().hex[:10]}"
    checkout_id = None
    with SessionLocal() as db:
        checkout = SignupCheckout(
            status="ready",
            idempotency_key=str(uuid4()),
            access_token_hash=token_hash(token),
            organization_name="Cancelled Workspace",
            organization_slug=slug,
            industry="gym",
            admin_email=f"owner-{slug}@example.com",
            admin_password_hash="retained-password-hash",
            admin_first_name="Kavya",
            admin_last_name="Raman",
            location_name="Main Location",
            city="Chennai",
            state="Tamil Nadu",
            plan_snapshot={"slug": "growth", "name": "Growth"},
            billing_interval="monthly",
            subtotal_paise=99900,
            tax_paise=17982,
            total_paise=117882,
            tax_enabled=True,
            gst_rate_bps=1800,
            currency="INR",
            provider="razorpay",
            provider_mode="mock",
            provider_order_id=f"mock-order-{uuid4().hex}",
            provider_session_id=f"mock-session-{uuid4().hex}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(checkout)
        db.commit()
        checkout_id = checkout.id

    try:
        cancelled = client.post(
            f"/api/auth/registration/checkouts/{checkout_id}/cancel",
            headers={"X-Signup-Token": token},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["next_action"] == "restart"
        assert cancelled.json()["payment_session_id"] is None

        with SessionLocal() as db:
            row = db.get(SignupCheckout, checkout_id)
            assert row.admin_password_hash is None
            assert row.last_error == "cancelled_by_user"

        late_payment = client.post(
            f"/api/auth/registration/checkouts/{checkout_id}/mock-pay",
            json={"checkout_token": token},
        )
        assert late_payment.status_code == 200, late_payment.text
        assert late_payment.json()["status"] == "manual_review"
        assert late_payment.json()["next_action"] == "support"

        with SessionLocal() as db:
            row = db.get(SignupCheckout, checkout_id)
            assert row.status == "manual_review"
            assert not db.execute(select(Organization.id).where(Organization.slug == slug)).first()
    finally:
        with SessionLocal() as db:
            row = db.get(SignupCheckout, checkout_id) if checkout_id else None
            if row:
                db.delete(row)
            db.commit()
