"""Subscription lifecycle rules shared by billing, entitlements, and wallets."""
from datetime import datetime, timedelta, timezone

from app.models import Subscription


TRIAL_DURATION = timedelta(days=30)


def start_trial(subscription: Subscription, *, started_at: datetime | None = None) -> Subscription:
    """Initialize one non-renewing 30-day trial period."""
    start = started_at or datetime.now(timezone.utc)
    end = start + TRIAL_DURATION
    subscription.plan = "trial"
    subscription.status = "trialing"
    subscription.billing_interval = "monthly"
    subscription.current_period_start = start
    subscription.current_period_end = end
    subscription.trial_end = end
    return subscription


def effective_subscription_status(
    subscription: Subscription | None, *, now: datetime | None = None,
) -> str:
    if not subscription:
        return "expired"
    current = now or datetime.now(timezone.utc)
    if subscription.status == "trialing":
        if not subscription.trial_end or subscription.trial_end <= current:
            return "expired"
    return subscription.status


def plan_credits_can_refresh(
    subscription: Subscription | None, *, now: datetime | None = None,
) -> bool:
    return effective_subscription_status(subscription, now=now) in {
        "trialing", "active", "authenticated",
    }
