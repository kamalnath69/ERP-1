"""Install the universal assistant and Owner authorization invariant.

Revision ID: 20260817_0040
Revises: 20260817_0039
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260817_0040"
down_revision = "20260817_0039"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)
JSONB = postgresql.JSONB(astext_type=sa.Text())


OWNER_LEVELS = """{
  "students":"manage","academics":"manage","attendance":"manage",
  "assessments":"manage","readiness":"manage","coding":"manage",
  "placements":"manage","data":"manage","reports":"manage",
  "clearance":"manage","documents":"manage"
}"""


def _owner_invariant() -> None:
    connection = op.get_bind()
    # Built-in roles receive a stable machine identity. If malformed legacy
    # data contains duplicates, only the oldest retains the canonical key.
    connection.execute(sa.text("""
        WITH ranked AS (
            SELECT id, slug,
                   row_number() OVER (PARTITION BY organization_id, slug ORDER BY created_at, id) AS position
            FROM roles
            WHERE is_system = TRUE
        )
        UPDATE roles
        SET system_key = CASE
            WHEN ranked.position = 1 THEN ranked.slug
            ELSE ranked.slug || '-legacy-' || roles.id::text
        END
        FROM ranked
        WHERE roles.id = ranked.id
    """))
    # Every organization must have one canonical, active Owner role.
    connection.execute(sa.text("""
        INSERT INTO roles
            (id, organization_id, name, slug, system_key, description,
             is_system, is_active, version, created_at, updated_at)
        SELECT gen_random_uuid(), organizations.id, 'Owner', 'owner', 'owner',
               'Immutable organization Owner', TRUE, TRUE, 1,
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM organizations
        WHERE NOT EXISTS (
            SELECT 1 FROM roles
            WHERE roles.organization_id = organizations.id
              AND roles.system_key = 'owner' AND roles.is_system = TRUE
        )
    """))
    connection.execute(sa.text("""
        UPDATE roles SET is_active = TRUE
        WHERE system_key = 'owner' AND is_system = TRUE
    """))
    # Repair an organization with no active Owner by assigning its earliest
    # active tenant user. The health check still reports organizations with no
    # active users so operators can resolve them explicitly.
    connection.execute(sa.text("""
        WITH candidates AS (
            SELECT users.id AS user_id, users.organization_id,
                   row_number() OVER (
                       PARTITION BY users.organization_id ORDER BY users.created_at, users.id
                   ) AS position
            FROM users
            WHERE users.organization_id IS NOT NULL AND users.is_active = TRUE
        )
        INSERT INTO user_roles (id, user_id, role_id)
        SELECT gen_random_uuid(), candidates.user_id, roles.id
        FROM candidates
        JOIN roles ON roles.organization_id = candidates.organization_id
                  AND roles.system_key = 'owner' AND roles.is_system = TRUE
        WHERE candidates.position = 1
          AND NOT EXISTS (
              SELECT 1
              FROM user_roles existing
              JOIN users owner_user ON owner_user.id = existing.user_id
              WHERE existing.role_id = roles.id AND owner_user.is_active = TRUE
          )
          AND NOT EXISTS (
              SELECT 1 FROM user_roles duplicate
              WHERE duplicate.user_id = candidates.user_id AND duplicate.role_id = roles.id
          )
    """))
    # Physical grants aid administration and exports; runtime permission
    # resolution remains authoritative for all future catalogue entries.
    connection.execute(sa.text("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), roles.id, permissions.id
        FROM roles
        JOIN permissions ON permissions.organization_id IS NULL
                         OR permissions.organization_id = roles.organization_id
        WHERE roles.system_key = 'owner' AND roles.is_system = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions existing
              WHERE existing.role_id = roles.id
                AND existing.permission_id = permissions.id
          )
    """))
    connection.execute(sa.text("""
        DELETE FROM user_permission_overrides overrides
        USING user_roles, roles
        WHERE overrides.user_id = user_roles.user_id
          AND user_roles.role_id = roles.id
          AND roles.system_key = 'owner' AND roles.is_system = TRUE
          AND overrides.granted = FALSE
    """))
    connection.execute(sa.text("""
        INSERT INTO access_policies
            (id, organization_id, user_id, status, version, domain_levels,
             expires_at, created_by_user_id, reviewed_by_user_id, reviewed_at,
             review_note, created_at, updated_at)
        SELECT gen_random_uuid(), users.organization_id, users.id, 'active', 1,
               CAST(:levels AS jsonb), NULL, users.id, users.id,
               CURRENT_TIMESTAMP, 'Owner invariant repair',
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM users
        JOIN user_roles ON user_roles.user_id = users.id
        JOIN roles ON roles.id = user_roles.role_id
        WHERE roles.system_key = 'owner' AND roles.is_system = TRUE
        ON CONFLICT (organization_id, user_id) DO UPDATE SET
            status = 'active', domain_levels = EXCLUDED.domain_levels,
            expires_at = NULL, reviewed_by_user_id = EXCLUDED.reviewed_by_user_id,
            reviewed_at = CURRENT_TIMESTAMP, review_note = 'Owner invariant repair',
            version = access_policies.version + 1, updated_at = CURRENT_TIMESTAMP
    """), {"levels": OWNER_LEVELS})
    connection.execute(sa.text("""
        INSERT INTO access_policy_scopes
            (id, organization_id, policy_id, domain_key, scope_type,
             scope_value, created_at, updated_at)
        SELECT gen_random_uuid(), policies.organization_id, policies.id,
               '*', 'organization', '*', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM access_policies policies
        JOIN users ON users.id = policies.user_id
        JOIN user_roles ON user_roles.user_id = users.id
        JOIN roles ON roles.id = user_roles.role_id
        WHERE roles.system_key = 'owner' AND roles.is_system = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM access_policy_scopes scopes
              WHERE scopes.policy_id = policies.id
                AND scopes.domain_key = '*'
                AND scopes.scope_type = 'organization'
                AND scopes.scope_value = '*'
          )
    """))


def _migrate_messages() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE chat_messages
        SET artifacts = COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'id', COALESCE(block->>'id', 'legacy-' || ordinality::text),
                'type', CASE block->>'type'
                    WHEN 'entity_cards' THEN 'records'
                    WHEN 'table' THEN 'records'
                    WHEN 'kpi_grid' THEN 'metric'
                    WHEN 'chart' THEN 'chart'
                    WHEN 'action' THEN 'action'
                    ELSE 'notice'
                END,
                'title', block->'title',
                'data', COALESCE(block->'data', '{}'::jsonb),
                'evidence_ids', '[]'::jsonb,
                'security', jsonb_build_object(
                    'permissions', jsonb_build_array('ai.use'),
                    'domains', '[]'::jsonb,
                    'scope', jsonb_build_object('historical', TRUE),
                    'entity_ids', '[]'::jsonb
                )
            ))
            FROM jsonb_array_elements(COALESCE(blocks, '[]'::jsonb))
                 WITH ORDINALITY AS entries(block, ordinality)
        ), '[]'::jsonb)
        || CASE WHEN jsonb_array_length(COALESCE(citations, '[]'::jsonb)) > 0
            THEN jsonb_build_array(jsonb_build_object(
                'id', 'legacy-sources-' || id::text,
                'type', 'sources', 'title', 'Historical sources',
                'data', jsonb_build_object('items', citations),
                'evidence_ids', '[]'::jsonb,
                'security', jsonb_build_object(
                    'permissions', jsonb_build_array('ai.use'),
                    'domains', '[]'::jsonb,
                    'scope', jsonb_build_object('historical', TRUE),
                    'entity_ids', '[]'::jsonb
                )
            )) ELSE '[]'::jsonb END,
            outcome = CASE WHEN role = 'assistant' THEN 'success' ELSE NULL END
    """))


def upgrade() -> None:
    op.add_column("roles", sa.Column("system_key", sa.String(100), nullable=True))
    _owner_invariant()
    op.create_unique_constraint("uq_role_org_system_key", "roles", ["organization_id", "system_key"])
    op.create_index("ix_roles_system_key", "roles", ["system_key"])

    op.create_table(
        "ai_semantic_policies",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("definitions", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_by_user_id", UUID),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", name="uq_ai_semantic_policy_org"),
    )
    op.create_index("ix_ai_semantic_policies_organization_id", "ai_semantic_policies", ["organization_id"])
    op.create_index("ix_ai_semantic_policies_updated_by_user_id", "ai_semantic_policies", ["updated_by_user_id"])

    op.add_column("chat_conversations", sa.Column("state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.execute("""
        UPDATE chat_conversations SET state = jsonb_build_object(
            'referents', '[]'::jsonb,
            'pending_clarification', NULL,
            'last_query', NULL,
            'policy_version', COALESCE((memory_state->>'policy_version')::integer, 0),
            'legacy_context', COALESCE(context_state, '{}'::jsonb),
            'legacy_memory', COALESCE(memory_state, '{}'::jsonb)
        )
    """)
    op.drop_column("chat_conversations", "memory_version")
    op.drop_column("chat_conversations", "memory_summary_through_message_id")
    op.drop_column("chat_conversations", "memory_summary")
    op.drop_column("chat_conversations", "memory_state")
    op.drop_column("chat_conversations", "context_state")

    op.add_column("chat_messages", sa.Column("outcome", sa.String(40), nullable=True))
    op.add_column("chat_messages", sa.Column("artifacts", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("chat_messages", sa.Column("suggestions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("chat_messages", sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("chat_messages", sa.Column("scope", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("chat_messages", sa.Column("semantic_query", JSONB, nullable=True))
    op.create_index("ix_chat_messages_outcome", "chat_messages", ["outcome"])
    _migrate_messages()
    op.drop_column("chat_messages", "citations")
    op.drop_column("chat_messages", "blocks")
    op.drop_column("chat_messages", "response_schema_version")
    op.drop_column("chat_messages", "tool_calls")

    op.add_column("ai_execution_traces", sa.Column("outcome", sa.String(40), nullable=False, server_default="success"))
    op.add_column("ai_execution_traces", sa.Column("semantic_query", JSONB, nullable=True))
    op.add_column("ai_execution_traces", sa.Column("scope", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_index("ix_ai_execution_traces_outcome", "ai_execution_traces", ["outcome"])
    op.execute("UPDATE ai_execution_traces SET outcome = CASE WHEN error_category IS NULL THEN 'success' ELSE 'unavailable' END")
    for column in (
        "fallback_used", "policy_version", "verification_outcome", "model_rounds",
        "cache_status", "planner_confidence", "planner_kind", "trace_version",
    ):
        op.drop_column("ai_execution_traces", column)

    op.drop_table("ai_intent_resolutions")
    op.alter_column("ai_result_sessions", "tool_name", new_column_name="entity")
    op.execute("UPDATE ai_result_sessions SET expires_at = CURRENT_TIMESTAMP")
    op.alter_column("ai_actions", "policy_version", new_column_name="access_version")
    op.execute("""
        UPDATE ai_actions
        SET access_version = users.access_version,
            status = CASE
                WHEN ai_actions.status = 'pending_confirmation' THEN 'expired'
                ELSE ai_actions.status
            END
        FROM users
        WHERE users.id = ai_actions.user_id
    """)
    op.execute("UPDATE ai_saved_views SET is_active = FALSE WHERE query_spec->>'goal' IS NULL")
    op.execute("""
        DELETE FROM feature_flags
        WHERE flag IN ('ai.local_intent_v2', 'ai.execution_v3', 'authorization.policy_v2')
    """)
    op.execute("DELETE FROM platform_settings WHERE key = 'ai_models'")


def downgrade() -> None:
    op.alter_column("ai_actions", "access_version", new_column_name="policy_version")
    op.alter_column("ai_result_sessions", "entity", new_column_name="tool_name")
    op.add_column("chat_messages", sa.Column("tool_calls", JSONB))
    op.add_column("chat_messages", sa.Column("response_schema_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("chat_messages", sa.Column("blocks", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("chat_messages", sa.Column("citations", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    for column in ("semantic_query", "scope", "evidence", "suggestions", "artifacts", "outcome"):
        op.drop_column("chat_messages", column)
    op.add_column("chat_conversations", sa.Column("context_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("chat_conversations", sa.Column("memory_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("chat_conversations", sa.Column("memory_summary", sa.Text()))
    op.add_column("chat_conversations", sa.Column("memory_summary_through_message_id", UUID))
    op.add_column("chat_conversations", sa.Column("memory_version", sa.Integer(), nullable=False, server_default="1"))
    op.drop_column("chat_conversations", "state")
    op.drop_table("ai_semantic_policies")
    op.drop_constraint("uq_role_org_system_key", "roles", type_="unique")
    op.drop_index("ix_roles_system_key", table_name="roles")
    op.drop_column("roles", "system_key")
