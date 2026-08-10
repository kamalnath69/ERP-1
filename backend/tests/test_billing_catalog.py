"""Billing catalog, GST isolation, fulfillment, and schedule safety."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import (
    AIWallet, BillingProfile, Invoice, Organization, PlanDefinition, PlanVersion,
    RechargePack, Subscription, User, WalletCreditGrant,
)
from app.services.billing import create_invoice, fulfill_invoice, tax_quote
from app.services.subscriptions import effective_subscription_status, start_trial
from app.services.wallet import ensure_wallet
from server import app

client = TestClient(app, raise_server_exceptions=True)


def tenant_headers():
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.organization_id.is_not(None), User.is_active.is_(True)).order_by(User.created_at)).scalars().first()
        return {"Authorization": f"Bearer {create_access_token(user.id, user.organization_id, {'sv': user.session_version})}"}


def test_version_two_plan_matrix_and_independent_gst():
    with SessionLocal() as db:
        rows = db.execute(select(PlanDefinition, PlanVersion).join(PlanVersion).where(PlanVersion.version == 2)).all()
        plans = {definition.slug: version for definition, version in rows}
        assert plans["trial"].tax_enabled is False
        assert plans["starter"].tax_enabled is True
        assert plans["growth"].monthly_price_paise == 249900
        assert plans["business"].included_ai_credits == 10000
        assert plans["enterprise"].monthly_price_paise is None


def test_tax_quote_honors_plan_switch_exemption_and_state():
    with SessionLocal() as db:
        organization = db.execute(select(Organization).order_by(Organization.created_at)).scalars().first()
        profile = db.execute(select(BillingProfile).where(BillingProfile.organization_id == organization.id)).scalar_one()
        original = (profile.tax_exempt, profile.state)
        profile.tax_exempt = False; profile.state = "Tamil Nadu"
        local = tax_quote(db, organization, 100000, tax_enabled=True, gst_rate_bps=1800)
        assert (local["cgst_paise"], local["sgst_paise"], local["igst_paise"]) == (9000, 9000, 0)
        profile.state = "Karnataka"
        interstate = tax_quote(db, organization, 100000, tax_enabled=True, gst_rate_bps=1800)
        assert (interstate["cgst_paise"], interstate["sgst_paise"], interstate["igst_paise"]) == (0, 0, 18000)
        disabled = tax_quote(db, organization, 100000, tax_enabled=False, gst_rate_bps=1800)
        assert disabled["tax_paise"] == 0
        profile.tax_exempt = True
        exempt = tax_quote(db, organization, 100000, tax_enabled=True, gst_rate_bps=1800)
        assert exempt["tax_paise"] == 0 and exempt["tax_reason"] == "organization_exempt"
        profile.tax_exempt, profile.state = original
        db.rollback()


def test_wallet_pack_invoice_fulfills_exactly_once(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_MODE", "mock")
    with SessionLocal() as db:
        organization = db.execute(select(Organization).order_by(Organization.created_at)).scalars().first()
        pack = db.execute(select(RechargePack).order_by(RechargePack.display_order)).scalars().first()
        wallet = db.execute(select(AIWallet).where(AIWallet.organization_id == organization.id).with_for_update()).scalar_one()
        before = wallet.balance_credits
        invoice = create_invoice(
            db, organization, purchase_type="wallet_pack", subtotal_paise=pack.price_paise,
            description=pack.name, tax_enabled=pack.tax_enabled, gst_rate_bps=pack.gst_rate_bps,
            billing_interval=None, snapshot={"pack_id": pack.id, "credits": pack.credits, "reference_id": str(uuid4())},
        )
        first = fulfill_invoice(db, invoice, f"mock-{uuid4()}")
        second = fulfill_invoice(db, invoice, invoice.razorpay_payment_id)
        db.flush()
        assert first["already_fulfilled"] is False and second["already_fulfilled"] is True
        assert wallet.balance_credits == before + pack.credits
        assert db.execute(select(WalletCreditGrant).where(WalletCreditGrant.idempotency_key == f"wallet-pack:{invoice.id}")).scalar_one().remaining_credits == pack.credits
        db.rollback()


def test_billing_overview_is_normalized():
    headers = tenant_headers()
    created_ids = []
    try:
        with SessionLocal() as db:
            user = db.execute(select(User).where(
                User.organization_id.is_not(None), User.is_active.is_(True),
            ).order_by(User.created_at)).scalars().first()
            marker = uuid4().hex[:10]
            for index in range(3):
                invoice = Invoice(
                    organization_id=user.organization_id,
                    amount_paise=10000 + index,
                    subtotal_paise=10000 + index,
                    purchase_type="cursor_test",
                    status="paid" if index % 2 == 0 else "created",
                    description=f"Cursor invoice {marker} {index}",
                    invoice_number=f"CURSOR-{marker}-{index}",
                    created_at=datetime.now(timezone.utc) + timedelta(minutes=index + 1),
                )
                db.add(invoice)
                db.flush()
                created_ids.append(invoice.id)
            db.commit()

        response = client.get("/api/billing/overview", headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert {"plans", "subscription", "payment", "wallet", "invoices", "invoice_summary"}.issubset(payload)
        assert len(payload["invoices"]) <= 5
        assert payload["invoice_summary"]["total"] >= 3
        growth = next(plan for plan in payload["plans"] if plan["id"] == "growth")
        assert growth["recommended"] is True
        assert growth["monthly_quote"]["total_paise"] >= growth["monthly_price_paise"]

        first_page_response = client.get("/api/billing/invoices/page", headers=headers, params={
            "purchase_type": "cursor_test",
            "limit": 2,
        })
        assert first_page_response.status_code == 200, first_page_response.text
        first_page = first_page_response.json()
        assert len(first_page["items"]) == 2
        assert first_page["has_more"] is True
        second_page_response = client.get("/api/billing/invoices/page", headers=headers, params={
            "purchase_type": "cursor_test",
            "limit": 2,
            "cursor": first_page["next_cursor"],
        })
        assert second_page_response.status_code == 200, second_page_response.text
        invoice_ids = [row["id"] for row in first_page["items"] + second_page_response.json()["items"]]
        assert len(invoice_ids) == len(set(invoice_ids)) == 3
        changed_filter = client.get("/api/billing/invoices/page", headers=headers, params={
            "purchase_type": "cursor_test",
            "status": "paid",
            "cursor": first_page["next_cursor"],
        })
        assert changed_filter.status_code == 422
    finally:
        if created_ids:
            with SessionLocal() as db:
                db.execute(delete(Invoice).where(Invoice.id.in_(created_ids)))
                db.commit()


def test_expired_trial_does_not_receive_another_credit_grant():
    with SessionLocal() as db:
        trial = db.execute(
            select(PlanVersion).join(PlanDefinition).where(
                PlanDefinition.slug == "trial", PlanVersion.status == "published",
            ).order_by(PlanVersion.version.desc())
        ).scalars().first()
        organization = Organization(
            name="Trial Expiry Test", slug=f"trial-expiry-{uuid4()}",
            industry="gym", enabled_modules=["ai"],
        )
        db.add(organization); db.flush()
        subscription = start_trial(Subscription(
            organization_id=organization.id, plan_version_id=trial.id,
        ))
        db.add(subscription); db.flush()
        wallet = ensure_wallet(db, organization)
        assert wallet.balance_credits == trial.included_ai_credits

        ended = datetime.now(timezone.utc) - timedelta(seconds=1)
        subscription.trial_end = ended
        subscription.current_period_end = ended
        wallet = ensure_wallet(db, organization)
        db.flush()

        assert effective_subscription_status(subscription) == "expired"
        assert wallet.balance_credits == 0
        assert wallet.cycle_grant_credits == 0
        assert not db.execute(select(WalletCreditGrant).where(
            WalletCreditGrant.wallet_id == wallet.id,
            WalletCreditGrant.source_type == "plan_cycle",
            WalletCreditGrant.remaining_credits > 0,
        )).first()
        db.rollback()


def test_expired_trial_is_billing_only_at_the_api_boundary():
    organization_id = None
    try:
        with SessionLocal() as db:
            trial = db.execute(
                select(PlanVersion).join(PlanDefinition).where(
                    PlanDefinition.slug == "trial", PlanVersion.status == "published",
                ).order_by(PlanVersion.version.desc())
            ).scalars().first()
            organization = Organization(
                name="Expired Access Test", slug=f"expired-access-{uuid4()}",
                industry="gym", enabled_modules=["ai"],
            )
            db.add(organization); db.flush()
            organization_id = organization.id
            user = User(
                organization_id=organization.id, email=f"expired-{uuid4()}@example.com",
                hashed_password="not-used", first_name="Expired", last_name="Owner",
                is_active=True, email_verified=True,
            )
            db.add(user); db.flush()
            ended = datetime.now(timezone.utc) - timedelta(days=1)
            subscription = Subscription(
                organization_id=organization.id, plan="trial", status="trialing",
                plan_version_id=trial.id, current_period_start=ended - timedelta(days=30),
                current_period_end=ended, trial_end=ended,
            )
            db.add(subscription); db.commit()
            token = create_access_token(user.id, organization.id, {"sv": user.session_version})

        headers = {"Authorization": f"Bearer {token}"}
        blocked = client.get("/api/dashboard", headers=headers)
        account = client.get("/api/auth/me", headers=headers)
        assert blocked.status_code == 402
        assert "trial has ended" in blocked.json()["detail"].lower()
        assert account.status_code == 200
    finally:
        if organization_id:
            with SessionLocal() as db:
                organization = db.get(Organization, organization_id)
                if organization:
                    db.delete(organization)
                    db.commit()
