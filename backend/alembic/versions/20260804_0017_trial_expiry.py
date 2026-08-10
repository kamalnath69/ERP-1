"""Enforce a single 30-day free trial.

Revision ID: 20260804_0017
Revises: 20260803_0016
"""
from alembic import op


revision = "20260804_0017"
down_revision = "20260803_0016"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve the date already shown to users when a wallet exists. Otherwise,
    # derive the trial period from subscription creation.
    op.execute("""
        UPDATE subscriptions AS subscription
        SET current_period_start = COALESCE(
                subscription.current_period_start,
                wallet.cycle_start,
                subscription.created_at
            ),
            trial_end = COALESCE(
                subscription.trial_end,
                wallet.cycle_end,
                subscription.created_at + INTERVAL '30 days'
            ),
            current_period_end = COALESCE(
                subscription.current_period_end,
                subscription.trial_end,
                wallet.cycle_end,
                subscription.created_at + INTERVAL '30 days'
            )
        FROM ai_wallets AS wallet
        WHERE wallet.organization_id = subscription.organization_id
          AND subscription.plan = 'trial'
          AND subscription.status = 'trialing'
    """)
    op.execute("""
        UPDATE subscriptions
        SET current_period_start = COALESCE(current_period_start, created_at),
            trial_end = COALESCE(trial_end, created_at + INTERVAL '30 days'),
            current_period_end = COALESCE(
                current_period_end,
                trial_end,
                created_at + INTERVAL '30 days'
            )
        WHERE plan = 'trial' AND status = 'trialing'
    """)


def downgrade():
    # Trial dates are valid historical billing data and are intentionally kept.
    pass
