"""Add cost-backed AI usage and founder-friendly credit packs.

Revision ID: 20260803_0014
Revises: 20260803_0013
"""
from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "20260803_0014"
down_revision = "20260803_0013"
branch_labels = None
depends_on = None


POLICY = {
    "version": "2026-08-cost-v1", "paise_per_credit": 25, "minimum_credits": 1,
    "route_max_credits": {"business": 8, "analytics": 20, "knowledge": 25, "action": 15},
    "models": {
        "gpt-5.4-mini": {"input": 255, "cached_input": 26, "output": 1530},
        "gpt-5.6-luna": {"input": 340, "cached_input": 34, "output": 2040},
        "gpt-5.6-terra": {"input": 850, "cached_input": 85, "output": 5100},
        "gpt-5.6-sol": {"input": 1700, "cached_input": 170, "output": 10200},
        "text-embedding-3-small": {"input": 7, "cached_input": 7, "output": 0},
    },
    "fallback": {"input": 1700, "cached_input": 170, "output": 10200},
}


def upgrade():
    for name in ["cached_input_tokens", "embedding_tokens", "provider_requests", "provider_cost_paise"]:
        op.add_column("ai_usage", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ai_usage", sa.Column("rate_version", sa.String(60), nullable=False, server_default="legacy"))

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    exists = connection.execute(sa.text("SELECT 1 FROM platform_settings WHERE key = 'ai_credit_policy'")).first()
    if not exists:
        connection.execute(sa.text("""
            INSERT INTO platform_settings (id, key, value, version, created_at, updated_at)
            VALUES (:id, 'ai_credit_policy', CAST(:value AS jsonb), 1, :now, :now)
        """), {"id": str(uuid.uuid4()), "value": json.dumps(POLICY), "now": now})

    connection.execute(sa.text("""
        UPDATE wallet_credit_grants
        SET expires_at = GREATEST(expires_at, created_at + INTERVAL '365 days')
        WHERE source_type = 'wallet_pack' AND remaining_credits > 0
    """))
    connection.execute(sa.text("UPDATE recharge_packs SET is_active = false"))
    for order, (name, credits, price) in enumerate((
        ("Starter top-up", 100, 9900), ("Value top-up", 500, 29900),
        ("Growth top-up", 2000, 129900), ("Business top-up", 10000, 499900),
    )):
        connection.execute(sa.text("""
            INSERT INTO recharge_packs
                (id, name, credits, price_paise, tax_enabled, gst_rate_bps, is_active, display_order, created_at, updated_at)
            VALUES (:id, :name, :credits, :price, true, 1800, true, :display_order, :now, :now)
        """), {"id": str(uuid.uuid4()), "name": name, "credits": credits, "price": price,
               "display_order": order, "now": now})


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("""
        DELETE FROM recharge_packs
        WHERE (name, credits, price_paise) IN (
            ('Starter top-up', 100, 9900),
            ('Value top-up', 500, 29900),
            ('Growth top-up', 2000, 129900),
            ('Business top-up', 10000, 499900)
        )
    """))
    connection.execute(sa.text("""
        UPDATE recharge_packs SET is_active = true
        WHERE (name, credits, price_paise) IN (
            ('Quick top-up', 500, 49900),
            ('Team pack', 2000, 149900),
            ('Business pack', 10000, 599900)
        )
    """))
    connection.execute(sa.text("DELETE FROM platform_settings WHERE key = 'ai_credit_policy'"))
    op.drop_column("ai_usage", "rate_version")
    for name in ["provider_cost_paise", "provider_requests", "embedding_tokens", "cached_input_tokens"]:
        op.drop_column("ai_usage", name)
