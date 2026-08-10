"""Cut over to Clients and add product-experience foundations.

Revision ID: 20260804_0018
Revises: 20260804_0017
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260804_0018"
down_revision = "20260804_0017"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=False)


CLIENT_ID_TABLES = (
    "appointments",
    "diet_plans",
    "fitness_measurements",
    "memberships",
    "outbound_messages",
    "patient_profiles",
    "sale_invoices",
    "tasks",
    "trainer_assignments",
    "workout_plans",
    "class_bookings",
    "gym_check_ins",
    "client_media",
    "client_memories",
    "client_commitments",
    "client_signals",
    "fitness_goals",
    "workout_sessions",
    "coaching_notes",
    "salon_client_profiles",
)


def _rename_schema_identifiers(source: str, target: str) -> None:
    # PostgreSQL does not rename indexes or constraints when their table/column is
    # renamed. Keep schema diagnostics and future autogeneration client-native.
    op.execute(sa.text(f"""
        DO $$
        DECLARE item record;
        BEGIN
            FOR item IN
                SELECT n.nspname AS schema_name, c.relname AS old_name
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                  AND c.relkind IN ('i', 'S')
                  AND c.relname LIKE '%{source}%'
            LOOP
                EXECUTE format(
                    'ALTER %s %I.%I RENAME TO %I',
                    CASE WHEN item.old_name LIKE '%_seq' THEN 'SEQUENCE' ELSE 'INDEX' END,
                    item.schema_name,
                    item.old_name,
                    replace(item.old_name, '{source}', '{target}')
                );
            END LOOP;

            FOR item IN
                SELECT con.conname AS old_name, rel.relname AS table_name
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = rel.relnamespace
                WHERE n.nspname = current_schema()
                  AND con.conname LIKE '%{source}%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I RENAME CONSTRAINT %I TO %I',
                    item.table_name,
                    item.old_name,
                    replace(item.old_name, '{source}', '{target}')
                );
            END LOOP;
        END $$;
    """))


def _replace_json_text(table: str, column: str, source: str, target: str) -> None:
    op.execute(sa.text(f"""
        UPDATE {table}
        SET {column} = replace({column}::text, :source, :target)::jsonb
        WHERE {column}::text LIKE :needle
    """).bindparams(source=source, target=target, needle=f"%{source}%"))


def _merge_client_permissions() -> None:
    # Some development databases already received client-native permissions from
    # newer seeds. Merge references before renaming the legacy catalogue rows.
    op.execute("""
        DELETE FROM role_permissions legacy_link
        USING permissions legacy_permission, permissions client_permission
        WHERE legacy_link.permission_id = legacy_permission.id
          AND legacy_permission.code LIKE '%customers%'
          AND client_permission.code = replace(legacy_permission.code, 'customers', 'clients')
          AND EXISTS (
              SELECT 1 FROM role_permissions current_link
              WHERE current_link.role_id = legacy_link.role_id
                AND current_link.permission_id = client_permission.id
          )
    """)
    op.execute("""
        UPDATE role_permissions legacy_link
        SET permission_id = client_permission.id
        FROM permissions legacy_permission, permissions client_permission
        WHERE legacy_link.permission_id = legacy_permission.id
          AND legacy_permission.code LIKE '%customers%'
          AND client_permission.code = replace(legacy_permission.code, 'customers', 'clients')
    """)
    op.execute("""
        UPDATE user_permission_overrides current_override
        SET granted = legacy_override.granted,
            updated_at = GREATEST(current_override.updated_at, legacy_override.updated_at)
        FROM user_permission_overrides legacy_override,
             permissions legacy_permission,
             permissions client_permission
        WHERE legacy_override.permission_id = legacy_permission.id
          AND current_override.permission_id = client_permission.id
          AND current_override.user_id = legacy_override.user_id
          AND legacy_permission.code LIKE '%customers%'
          AND client_permission.code = replace(legacy_permission.code, 'customers', 'clients')
    """)
    op.execute("""
        DELETE FROM user_permission_overrides legacy_override
        USING permissions legacy_permission, permissions client_permission
        WHERE legacy_override.permission_id = legacy_permission.id
          AND legacy_permission.code LIKE '%customers%'
          AND client_permission.code = replace(legacy_permission.code, 'customers', 'clients')
          AND EXISTS (
              SELECT 1 FROM user_permission_overrides current_override
              WHERE current_override.user_id = legacy_override.user_id
                AND current_override.permission_id = client_permission.id
          )
    """)
    op.execute("""
        UPDATE user_permission_overrides legacy_override
        SET permission_id = client_permission.id
        FROM permissions legacy_permission, permissions client_permission
        WHERE legacy_override.permission_id = legacy_permission.id
          AND legacy_permission.code LIKE '%customers%'
          AND client_permission.code = replace(legacy_permission.code, 'customers', 'clients')
    """)
    op.execute("""
        DELETE FROM permissions legacy_permission
        USING permissions client_permission
        WHERE legacy_permission.code LIKE '%customers%'
          AND client_permission.code = replace(legacy_permission.code, 'customers', 'clients')
    """)


def _merge_client_features() -> None:
    op.execute("""
        DELETE FROM plan_entitlements legacy_entitlement
        USING feature_definitions legacy_feature, feature_definitions client_feature
        WHERE legacy_entitlement.feature_id = legacy_feature.id
          AND legacy_feature.code LIKE '%customers%'
          AND client_feature.code = replace(legacy_feature.code, 'customers', 'clients')
          AND EXISTS (
              SELECT 1 FROM plan_entitlements current_entitlement
              WHERE current_entitlement.plan_version_id = legacy_entitlement.plan_version_id
                AND current_entitlement.feature_id = client_feature.id
          )
    """)
    op.execute("""
        UPDATE plan_entitlements legacy_entitlement
        SET feature_id = client_feature.id
        FROM feature_definitions legacy_feature, feature_definitions client_feature
        WHERE legacy_entitlement.feature_id = legacy_feature.id
          AND legacy_feature.code LIKE '%customers%'
          AND client_feature.code = replace(legacy_feature.code, 'customers', 'clients')
    """)
    op.execute("""
        UPDATE organization_entitlement_overrides legacy_override
        SET feature_id = client_feature.id
        FROM feature_definitions legacy_feature, feature_definitions client_feature
        WHERE legacy_override.feature_id = legacy_feature.id
          AND legacy_feature.code LIKE '%customers%'
          AND client_feature.code = replace(legacy_feature.code, 'customers', 'clients')
    """)
    op.execute("""
        DELETE FROM feature_definitions legacy_feature
        USING feature_definitions client_feature
        WHERE legacy_feature.code LIKE '%customers%'
          AND client_feature.code = replace(legacy_feature.code, 'customers', 'clients')
    """)


def upgrade():
    op.rename_table("customers", "clients")
    op.alter_column("clients", "customer_number", new_column_name="client_number")
    op.rename_table("customer_media", "client_media")
    op.rename_table("salon_customer_profiles", "salon_client_profiles")

    for table in CLIENT_ID_TABLES:
        op.alter_column(table, "customer_id", new_column_name="client_id")

    _rename_schema_identifiers("customer", "client")

    # Access and entitlement identifiers are contracts, not display aliases.
    _merge_client_permissions()
    op.execute("UPDATE permissions SET code = replace(code, 'customers', 'clients'), label = replace(replace(label, 'Customer', 'Client'), 'customer', 'client'), module = replace(module, 'customers', 'clients') WHERE code LIKE '%customers%' OR module = 'customers'")
    _merge_client_features()
    op.execute("UPDATE feature_definitions SET code = replace(code, 'customers', 'clients'), name = replace(name, 'Customer', 'Client') WHERE code LIKE '%customers%'")
    op.execute("UPDATE access_scopes SET scope_type = 'client' WHERE scope_type = 'customer'")
    op.execute("UPDATE documents SET entity_type = 'client' WHERE entity_type = 'customer'")
    op.execute("UPDATE ai_intent_resolutions SET subject = 'clients' WHERE subject = 'customers'")

    _replace_json_text("organizations", "enabled_modules", '"customers"', '"clients"')
    _replace_json_text("chat_conversations", "context_state", '"customer"', '"client"')
    _replace_json_text("chat_messages", "blocks", '"customer"', '"client"')
    _replace_json_text("chat_messages", "meta", '"customer"', '"client"')
    _replace_json_text("ai_actions", "preview", '"customer"', '"client"')
    _replace_json_text("ai_actions", "payload", '"customer"', '"client"')
    _replace_json_text("ai_result_sessions", "query_spec", '"customers"', '"clients"')
    _replace_json_text("ai_saved_views", "query_spec", '"customers"', '"clients"')
    _replace_json_text("jobs", "payload", '"customer"', '"client"')

    op.create_table(
        "user_preferences",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("namespace", sa.String(length=80), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "namespace", name="uq_user_preference_namespace"),
    )
    op.create_index("ix_user_preferences_organization_id", "user_preferences", ["organization_id"])
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])

    op.create_table(
        "user_mfa_devices",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_used_step", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_user_mfa_device"),
    )
    op.create_index("ix_user_mfa_devices_organization_id", "user_mfa_devices", ["organization_id"])
    op.create_index("ix_user_mfa_devices_user_id", "user_mfa_devices", ["user_id"])

    op.create_table(
        "user_recovery_codes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_user_recovery_code"),
    )
    op.create_index("ix_user_recovery_codes_organization_id", "user_recovery_codes", ["organization_id"])
    op.create_index("ix_user_recovery_codes_user_id", "user_recovery_codes", ["user_id"])

    op.create_table(
        "industry_migration_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=False),
        sa.Column("current_industry", sa.String(length=30), nullable=False),
        sa.Column("requested_industry", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.Text()),
        sa.Column("reviewed_by_user_id", UUID),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_industry_migration_requests_organization_id", "industry_migration_requests", ["organization_id"])
    op.create_index("ix_industry_migration_requests_status", "industry_migration_requests", ["status"])


def downgrade():
    op.drop_table("industry_migration_requests")
    op.drop_table("user_recovery_codes")
    op.drop_table("user_mfa_devices")
    op.drop_table("user_preferences")

    op.execute("UPDATE access_scopes SET scope_type = 'customer' WHERE scope_type = 'client'")
    op.execute("UPDATE documents SET entity_type = 'customer' WHERE entity_type = 'client'")
    op.execute("UPDATE permissions SET code = replace(code, 'clients', 'customers'), module = replace(module, 'clients', 'customers') WHERE code LIKE 'clients.%' OR module = 'clients'")
    op.execute("UPDATE feature_definitions SET code = replace(code, 'clients', 'customers') WHERE code IN ('module.clients', 'limits.clients')")

    _rename_schema_identifiers("client", "customer")
    for table in reversed(CLIENT_ID_TABLES):
        op.alter_column(table, "client_id", new_column_name="customer_id")
    op.rename_table("salon_client_profiles", "salon_customer_profiles")
    op.rename_table("client_media", "customer_media")
    op.alter_column("clients", "client_number", new_column_name="customer_number")
    op.rename_table("clients", "customers")
