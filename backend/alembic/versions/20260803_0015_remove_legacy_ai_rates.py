"""Remove superseded fixed AI rate settings.

Revision ID: 20260803_0015
Revises: 20260803_0014
"""
from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "20260803_0015"
down_revision = "20260803_0014"
branch_labels = None
depends_on = None


LEGACY_RATES = {
    "tool_call": 1,
    "voice_minute": 2,
    "document_page": 1,
    "output_per_1000_tokens": 2,
    "prompt_per_1000_tokens": 1,
}


def upgrade():
    op.execute("DELETE FROM platform_settings WHERE key IN ('ai_rates', 'ai_provider_costs')")


def downgrade():
    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    connection.execute(sa.text("""
        INSERT INTO platform_settings (id, key, value, version, created_at, updated_at)
        VALUES (:id, 'ai_rates', CAST(:value AS jsonb), 1, :now, :now)
        ON CONFLICT (key) DO NOTHING
    """), {"id": str(uuid.uuid4()), "value": json.dumps(LEGACY_RATES), "now": now})
