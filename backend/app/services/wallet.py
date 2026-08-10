"""Atomic AI credit wallet operations."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    AIWallet, Notification, Organization, Subscription, User, WalletCreditGrant,
    WalletLedger, WalletReservation,
)
from app.services.entitlements import active_plan_version, resolve_entitlements
from app.services.subscriptions import effective_subscription_status, plan_credits_can_refresh


def _credit_cycle_end(subscription: Subscription | None, now: datetime) -> datetime:
    monthly_end = now + timedelta(days=30)
    if subscription and subscription.current_period_end and subscription.current_period_end > now:
        return min(subscription.current_period_end, monthly_end)
    return monthly_end


def ensure_wallet(db: Session, organization: Organization, *, grant: bool = True) -> AIWallet:
    wallet = db.execute(select(AIWallet).where(AIWallet.organization_id == organization.id).with_for_update()).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    subscription, version, _ = active_plan_version(db, organization)
    if wallet:
        _expire_wallet_items(db, wallet, now)
    if wallet and effective_subscription_status(subscription, now=now) == "expired":
        previous_grant = wallet.cycle_grant_credits
        previous_end = wallet.cycle_end
        _expire_plan_cycle_credits(db, wallet)
        wallet.cycle_grant_credits = 0
        if subscription and subscription.trial_end:
            wallet.cycle_end = subscription.trial_end
        if previous_grant != wallet.cycle_grant_credits or previous_end != wallet.cycle_end:
            wallet.version += 1
        return wallet
    if wallet and wallet.cycle_end and wallet.cycle_end <= now:
        old_cycle_end = wallet.cycle_end
        end = _credit_cycle_end(subscription, now)
        included = int(version.included_ai_credits if version and grant and plan_credits_can_refresh(subscription, now=now) else 0)
        wallet.cycle_grant_credits = included
        wallet.cycle_start = now; wallet.cycle_end = end; wallet.version += 1
        grant_key = f"cycle-grant:{organization.id}:{end.isoformat()}"
        existing_grant = db.execute(select(WalletCreditGrant).where(
            WalletCreditGrant.idempotency_key == grant_key,
        )).scalar_one_or_none()
        if included and not existing_grant:
            db.add(WalletCreditGrant(
                organization_id=organization.id, wallet_id=wallet.id, source_type="plan_cycle",
                source_id=end.isoformat(), granted_credits=included, remaining_credits=included,
                expires_at=end, idempotency_key=grant_key,
            ))
            wallet.balance_credits += included
            db.add(WalletLedger(
                organization_id=organization.id, wallet_id=wallet.id, entry_type="cycle_grant",
                credits_delta=included, balance_after=wallet.balance_credits, reference_type="billing_cycle",
                reference_id=end.isoformat(), idempotency_key=grant_key,
                description="AI credits included with the current plan",
            ))
        return wallet
    if wallet:
        return wallet
    end = _credit_cycle_end(subscription, now)
    included = int(resolve_entitlements(db, organization)["values"].get("ai.included_credits") or 0) if grant and plan_credits_can_refresh(subscription, now=now) else 0
    wallet_id = str(uuid.uuid4())
    created_id = db.execute(
        insert(AIWallet).values(
            id=wallet_id, organization_id=organization.id, balance_credits=included,
            reserved_credits=0, cycle_grant_credits=included, cycle_start=now,
            cycle_end=end, version=1, created_at=now, updated_at=now,
        ).on_conflict_do_nothing(index_elements=[AIWallet.organization_id]).returning(AIWallet.id)
    ).scalar_one_or_none()
    wallet = db.execute(select(AIWallet).where(AIWallet.organization_id == organization.id).with_for_update()).scalar_one()
    if created_id and included:
        db.add(WalletCreditGrant(
            organization_id=organization.id, wallet_id=wallet.id, source_type="plan_cycle",
            source_id=end.isoformat(), granted_credits=included, remaining_credits=included,
            expires_at=end, idempotency_key=f"cycle-grant:{organization.id}:{end.isoformat()}",
        ))
        db.add(WalletLedger(
            organization_id=organization.id, wallet_id=wallet.id, entry_type="cycle_grant",
            credits_delta=included, balance_after=included, reference_type="billing_cycle",
            reference_id=end.isoformat(), idempotency_key=f"cycle-grant:{organization.id}:{end.isoformat()}",
            description="AI credits included with the current plan",
        ))
        # Callers may immediately evaluate expiry in the same transaction.
        db.flush()
    return wallet


def _expire_wallet_items(db: Session, wallet: AIWallet, now: datetime) -> None:
    reservations = db.execute(select(WalletReservation).where(
        WalletReservation.wallet_id == wallet.id,
        WalletReservation.status == "reserved",
        WalletReservation.expires_at <= now,
    ).with_for_update()).scalars().all()
    for reservation in reservations:
        wallet.reserved_credits = max(wallet.reserved_credits - reservation.credits, 0)
        reservation.status = "expired"
        reservation.settled_credits = 0

    grants = db.execute(select(WalletCreditGrant).where(
        WalletCreditGrant.wallet_id == wallet.id,
        WalletCreditGrant.remaining_credits > 0,
        WalletCreditGrant.expires_at <= now,
    ).order_by(WalletCreditGrant.expires_at).with_for_update()).scalars().all()
    for item in grants:
        expired = item.remaining_credits
        item.remaining_credits = 0
        wallet.balance_credits = max(wallet.balance_credits - expired, 0)
        key = f"grant-expiry:{item.id}"
        exists = db.execute(select(WalletLedger.id).where(WalletLedger.idempotency_key == key)).first()
        if not exists:
            db.add(WalletLedger(
                organization_id=wallet.organization_id, wallet_id=wallet.id, entry_type="credit_expiry",
                credits_delta=-expired, balance_after=wallet.balance_credits, reference_type=item.source_type,
                reference_id=item.id, idempotency_key=key,
                description="Unused AI credits expired",
            ))
    if reservations or grants:
        wallet.version += 1


def _expire_plan_cycle_credits(db: Session, wallet: AIWallet) -> None:
    grants = db.execute(select(WalletCreditGrant).where(
        WalletCreditGrant.wallet_id == wallet.id,
        WalletCreditGrant.source_type == "plan_cycle",
        WalletCreditGrant.remaining_credits > 0,
    ).with_for_update()).scalars().all()
    expired = sum(item.remaining_credits for item in grants)
    if not expired:
        return
    for item in grants:
        item.remaining_credits = 0
    wallet.balance_credits = max(wallet.balance_credits - expired, 0)
    wallet.version += 1
    key = f"trial-expiry:{wallet.organization_id}"
    if not db.execute(select(WalletLedger.id).where(WalletLedger.idempotency_key == key)).first():
        db.add(WalletLedger(
            organization_id=wallet.organization_id, wallet_id=wallet.id,
            entry_type="credit_expiry", credits_delta=-expired,
            balance_after=wallet.balance_credits, reference_type="trial",
            reference_id=wallet.organization_id, idempotency_key=key,
            description="Unused free-trial AI credits expired",
        ))


def wallet_summary(wallet: AIWallet) -> dict:
    return {
        "balance_credits": wallet.balance_credits,
        "reserved_credits": wallet.reserved_credits,
        "available_credits": max(wallet.balance_credits - wallet.reserved_credits, 0),
        "cycle_grant_credits": wallet.cycle_grant_credits,
        "cycle_start": wallet.cycle_start,
        "cycle_end": wallet.cycle_end,
    }


def apply_plan_credit_grant(db: Session, organization: Organization, subscription: Subscription, credits: int) -> AIWallet:
    """Replace only the current plan allowance while preserving valid paid top-ups."""
    wallet = db.execute(select(AIWallet).where(AIWallet.organization_id == organization.id).with_for_update()).scalar_one_or_none()
    wallet = wallet or ensure_wallet(db, organization, grant=False)
    now = datetime.now(timezone.utc)
    plan_grants = db.execute(select(WalletCreditGrant).where(
        WalletCreditGrant.wallet_id == wallet.id,
        WalletCreditGrant.source_type == "plan_cycle",
        WalletCreditGrant.remaining_credits > 0,
    ).with_for_update()).scalars().all()
    removed = sum(item.remaining_credits for item in plan_grants)
    for item in plan_grants:
        item.remaining_credits = 0
    wallet.balance_credits = max(wallet.balance_credits - removed, 0)
    end = _credit_cycle_end(subscription, now)
    key = f"plan-activation:{subscription.id}:{subscription.version}:{end.isoformat()}"
    existing = db.execute(select(WalletCreditGrant).where(WalletCreditGrant.idempotency_key == key)).scalar_one_or_none()
    if not existing and credits:
        db.add(WalletCreditGrant(
            organization_id=organization.id, wallet_id=wallet.id, source_type="plan_cycle",
            source_id=subscription.id, granted_credits=credits, remaining_credits=credits,
            expires_at=end, idempotency_key=key,
        ))
        wallet.balance_credits += credits
        db.add(WalletLedger(
            organization_id=organization.id, wallet_id=wallet.id, entry_type="cycle_grant",
            credits_delta=credits, balance_after=wallet.balance_credits, reference_type="subscription",
            reference_id=subscription.id, idempotency_key=key,
            description="AI credits included with the activated plan",
        ))
    wallet.cycle_grant_credits = credits
    wallet.cycle_start = now
    wallet.cycle_end = end
    wallet.version += 1
    return wallet


def reserve_credits(db: Session, organization: Organization, credits: int, idempotency_key: str) -> WalletReservation:
    existing = db.execute(select(WalletReservation).where(
        WalletReservation.organization_id == organization.id,
        WalletReservation.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
    if existing and existing.status in {"reserved", "settled"}: return existing
    wallet = ensure_wallet(db, organization)
    if wallet.balance_credits - wallet.reserved_credits < credits:
        raise HTTPException(402, "AI credit balance is insufficient")
    wallet.reserved_credits += credits
    wallet.version += 1
    if existing:
        existing.status = "reserved"; existing.credits = credits; existing.settled_credits = None
        existing.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        return existing
    reservation = WalletReservation(
        organization_id=organization.id, wallet_id=wallet.id, credits=credits,
        idempotency_key=idempotency_key, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(reservation)
    db.flush()
    return reservation


def reserve_credit_budget(
    db: Session, organization: Organization, maximum_credits: int, idempotency_key: str,
    *, minimum_credits: int = 1,
) -> WalletReservation:
    """Reserve the available part of a bounded request instead of blocking small balances."""
    existing = db.execute(select(WalletReservation).where(
        WalletReservation.organization_id == organization.id,
        WalletReservation.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
    if existing and existing.status in {"reserved", "settled"}:
        return existing
    wallet = ensure_wallet(db, organization)
    available = max(wallet.balance_credits - wallet.reserved_credits, 0)
    amount = min(maximum_credits, available)
    if amount < minimum_credits:
        raise HTTPException(402, "AI credit balance is insufficient")
    return reserve_credits(db, organization, amount, idempotency_key)


def settle_reservation(db: Session, reservation: WalletReservation, actual_credits: int) -> AIWallet:
    if reservation.status == "settled":
        return db.get(AIWallet, reservation.wallet_id)
    wallet = db.execute(select(AIWallet).where(AIWallet.id == reservation.wallet_id).with_for_update()).scalar_one()
    actual = min(max(actual_credits, 0), reservation.credits)
    wallet.reserved_credits = max(wallet.reserved_credits - reservation.credits, 0)
    wallet.balance_credits = max(wallet.balance_credits - actual, 0)
    remaining = actual
    grants = db.execute(select(WalletCreditGrant).where(
        WalletCreditGrant.wallet_id == wallet.id,
        WalletCreditGrant.remaining_credits > 0,
        WalletCreditGrant.expires_at > datetime.now(timezone.utc),
    ).order_by(WalletCreditGrant.expires_at, WalletCreditGrant.created_at).with_for_update()).scalars().all()
    for grant in grants:
        used = min(grant.remaining_credits, remaining)
        grant.remaining_credits -= used
        remaining -= used
        if not remaining:
            break
    wallet.version += 1
    reservation.status = "settled"
    reservation.settled_credits = actual
    db.add(WalletLedger(
        organization_id=reservation.organization_id, wallet_id=wallet.id, entry_type="usage",
        credits_delta=-actual, balance_after=wallet.balance_credits, reference_type="ai_reservation",
        reference_id=reservation.id, idempotency_key=f"settle:{reservation.id}", description="AI usage",
    ))
    _notify_threshold(db, wallet)
    return wallet


def release_reservation(db: Session, reservation: WalletReservation) -> AIWallet:
    wallet = db.execute(select(AIWallet).where(AIWallet.id == reservation.wallet_id).with_for_update()).scalar_one()
    if reservation.status == "reserved":
        wallet.reserved_credits = max(wallet.reserved_credits - reservation.credits, 0)
        wallet.version += 1
        reservation.status = "released"
        reservation.settled_credits = 0
    return wallet


def add_credits(
    db: Session, organization: Organization, credits: int, idempotency_key: str, *,
    user_id: str | None = None, description: str = "AI credit recharge",
    source_type: str = "manual_recharge", source_id: str | None = None,
    expires_at: datetime | None = None,
) -> AIWallet:
    prior = db.execute(select(WalletLedger).where(WalletLedger.idempotency_key == idempotency_key)).scalar_one_or_none()
    if prior:
        return db.get(AIWallet, prior.wallet_id)
    wallet = db.execute(select(AIWallet).where(AIWallet.organization_id == organization.id).with_for_update()).scalar_one_or_none()
    wallet = wallet or ensure_wallet(db, organization, grant=False)
    expiry = expires_at or datetime.now(timezone.utc) + timedelta(days=365)
    wallet.balance_credits += credits
    wallet.version += 1
    db.add(WalletCreditGrant(
        organization_id=organization.id, wallet_id=wallet.id, source_type=source_type,
        source_id=source_id, granted_credits=credits, remaining_credits=credits,
        expires_at=expiry, idempotency_key=idempotency_key,
    ))
    db.add(WalletLedger(
        organization_id=organization.id, wallet_id=wallet.id, entry_type="recharge",
        credits_delta=credits, balance_after=wallet.balance_credits, reference_type=source_type,
        reference_id=source_id,
        idempotency_key=idempotency_key, description=description, created_by_user_id=user_id,
    ))
    return wallet


def _notify_threshold(db: Session, wallet: AIWallet) -> None:
    if not wallet.cycle_grant_credits:
        return
    plan_remaining = db.scalar(select(func.coalesce(func.sum(WalletCreditGrant.remaining_credits), 0)).where(
        WalletCreditGrant.wallet_id == wallet.id,
        WalletCreditGrant.source_type == "plan_cycle",
        WalletCreditGrant.expires_at > datetime.now(timezone.utc),
    )) or 0
    percent = int((1 - min(plan_remaining, wallet.cycle_grant_credits) / wallet.cycle_grant_credits) * 100)
    threshold = next((item for item in (100, 95, 80) if percent >= item), None)
    if not threshold:
        return
    marker = f"ai-wallet-{wallet.cycle_end}-{threshold}"
    owners = db.execute(select(User).where(User.organization_id == wallet.organization_id, User.is_active.is_(True))).scalars().all()
    for owner in owners[:3]:
        exists = db.execute(select(Notification.id).where(Notification.user_id == owner.id, Notification.link == marker)).first()
        if not exists:
            db.add(Notification(
                organization_id=wallet.organization_id, user_id=owner.id, title="AI credits running low",
                body=f"{threshold}% of this cycle's AI credits have been used.", kind="warning", link=marker,
            ))
