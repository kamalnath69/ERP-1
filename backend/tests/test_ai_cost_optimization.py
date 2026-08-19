from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.ai.catalog import catalog_for
from app.ai.compiler import deterministic_compile
from app.ai.contracts import ConversationState, QueryGoal
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


def test_common_live_business_queries_compile_without_a_provider_request():
    catalog = catalog_for("gym")
    state = ConversationState()
    clients = deterministic_compile("Show active clients", catalog, context=None, state=state)
    sales = deterministic_compile("Show revenue", catalog, context=None, state=state)
    complex_question = deterministic_compile("Explain why revenue dropped", catalog, context=None, state=state)

    assert clients.entity == "client"
    assert clients.goal == QueryGoal.LIST
    assert sales.entity == "sale"
    assert complex_question is None


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
