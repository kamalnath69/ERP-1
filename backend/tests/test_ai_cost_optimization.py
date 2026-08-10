from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.ai.fast_queries import deterministic_query_plan
from app.core.database import SessionLocal
from app.models import AIWallet, Organization, WalletCreditGrant
from app.services import ai_metering
from app.services.ai_metering import DEFAULT_AI_CREDIT_POLICY, calculate_charge
from app.services.wallet import add_credits, reserve_credit_budget


def _policy(monkeypatch):
    monkeypatch.setattr(ai_metering, "credit_policy", lambda _db: DEFAULT_AI_CREDIT_POLICY)


def test_metering_uses_provider_tokens_not_internal_tool_calls(monkeypatch):
    _policy(monkeypatch)
    charge = calculate_charge(None, "gpt-5.4-mini", {
        "input_tokens": 5160,
        "output_tokens": 195,
        "tool_calls": 8,
        "provider_requests": 2,
    })
    no_provider = calculate_charge(None, "gpt-5.4-mini", {
        "input_tokens": 0, "output_tokens": 0, "tool_calls": 8, "provider_requests": 0,
    })

    assert charge.credits == 2
    assert no_provider.credits == 0


def test_cached_input_receives_lower_charge(monkeypatch):
    _policy(monkeypatch)
    uncached = calculate_charge(None, "gpt-5.4-mini", {
        "input_tokens": 100_000, "provider_requests": 1,
    })
    cached = calculate_charge(None, "gpt-5.4-mini", {
        "input_tokens": 100_000, "cached_input_tokens": 100_000, "provider_requests": 1,
    })

    assert cached.credits < uncached.credits


def test_common_live_business_queries_use_the_free_database_path():
    assert deterministic_query_plan("34 clients yaar yaaru")["arguments"]["subject"] == "clients"
    assert deterministic_query_plan("evlo customers irukaanga")["arguments"] == {
        "subject": "clients", "location_id": None, "status": "active",
    }
    assert deterministic_query_plan("Who bought what?")["arguments"]["subject"] == "purchases"
    resistance_band = deterministic_query_plan("Who bought the Resistance Band?")
    assert resistance_band["arguments"] == {
        "subject": "purchases", "query": "resistance band", "location_id": None, "days": 365,
    }
    assert deterministic_query_plan("Show today's business summary")["tool"] == "business_summary"
    assert deterministic_query_plan("Explain why revenue dropped") is None
    assert deterministic_query_plan("list clients and sales") is None
    follow_up = deterministic_query_plan("who are they", context_state={
        "last_read": {
            "tool": "business_records",
            "arguments": {"subject": "clients", "status": "active", "location_id": "loc-1"},
        },
    })
    assert follow_up["arguments"] == {
        "subject": "clients", "status": "active", "location_id": "loc-1",
    }


def test_low_balance_can_reserve_a_bounded_request():
    with SessionLocal() as db:
        organization = db.execute(select(Organization).order_by(Organization.created_at)).scalars().first()
        wallet = db.execute(select(AIWallet).where(
            AIWallet.organization_id == organization.id,
        ).with_for_update()).scalar_one()
        wallet.balance_credits = 2
        wallet.reserved_credits = 0

        reservation = reserve_credit_budget(db, organization, 8, f"low-balance:{uuid4()}")

        assert reservation.credits == 2
        db.rollback()


def test_recharge_credits_default_to_twelve_month_validity():
    with SessionLocal() as db:
        organization = db.execute(select(Organization).order_by(Organization.created_at)).scalars().first()
        key = f"pack-validity:{uuid4()}"
        add_credits(db, organization, 100, key, source_type="wallet_pack")
        db.flush()
        grant = db.execute(select(WalletCreditGrant).where(
            WalletCreditGrant.idempotency_key == key,
        )).scalar_one()

        remaining_days = (grant.expires_at - datetime.now(timezone.utc)).days
        assert remaining_days >= 364
        db.rollback()
