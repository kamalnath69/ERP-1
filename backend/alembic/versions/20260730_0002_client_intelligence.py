"""client intelligence workspace

Revision ID: 20260730_0002
Revises: 20260730_0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260730_0002"
down_revision: Union[str, None] = "20260730_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = sa.UUID(as_uuid=False)


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("gym_check_ins", sa.Column("recorded_by_user_id", UUID, nullable=True))
    op.add_column("gym_check_ins", sa.Column("source", sa.String(30), server_default="staff", nullable=False))
    op.add_column("gym_check_ins", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("gym_check_ins", sa.Column("corrected_by_user_id", UUID, nullable=True))
    op.add_column("gym_check_ins", sa.Column("correction_reason", sa.Text(), nullable=True))
    op.add_column("gym_check_ins", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.create_foreign_key("fk_checkin_recorded_user", "gym_check_ins", "users", ["recorded_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_checkin_corrected_user", "gym_check_ins", "users", ["corrected_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_gym_check_ins_recorded_by_user_id", "gym_check_ins", ["recorded_by_user_id"])

    op.create_table(
        "customer_media",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("location_id", UUID), sa.Column("customer_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False, unique=True), sa.Column("media_kind", sa.String(40), nullable=False),
        sa.Column("caption", sa.String(500)), sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("visibility", sa.String(30), nullable=False), sa.Column("is_profile", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by_user_id", UUID, nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for column in ["organization_id", "location_id", "customer_id", "document_id", "media_kind", "is_profile", "uploaded_by_user_id"]:
        op.create_index(f"ix_customer_media_{column}", "customer_media", [column])

    op.create_table(
        "client_memories",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=False), sa.Column("category", sa.String(50), nullable=False),
        sa.Column("label", sa.String(120), nullable=False), sa.Column("value", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(30), nullable=False), sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("updated_by_user_id", UUID), sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in ["organization_id", "customer_id", "category", "visibility", "created_by_user_id"]:
        op.create_index(f"ix_client_memories_{column}", "client_memories", [column])

    op.create_table(
        "client_commitments",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=False), sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()), sa.Column("owner_user_id", UUID),
        sa.Column("due_at", sa.DateTime(timezone=True)), sa.Column("reminder_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("completion_note", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for column in ["organization_id", "customer_id", "owner_user_id", "due_at", "reminder_at", "status"]:
        op.create_index(f"ix_client_commitments_{column}", "client_commitments", [column])

    op.create_table(
        "client_signals",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("location_id", UUID), sa.Column("customer_id", UUID, nullable=False),
        sa.Column("signal_type", sa.String(80), nullable=False), sa.Column("pulse_state", sa.String(30), nullable=False),
        sa.Column("title", sa.String(240), nullable=False), sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False), sa.Column("recommended_action", sa.String(500)),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("assigned_to_user_id", UUID),
        sa.Column("snoozed_until", sa.DateTime(timezone=True)), sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_note", sa.Text()), sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_version", sa.String(30), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("customer_id", "signal_type", "rule_version", name="uq_client_signal_rule"),
    )
    for column in ["organization_id", "location_id", "customer_id", "signal_type", "pulse_state", "status", "assigned_to_user_id"]:
        op.create_index(f"ix_client_signals_{column}", "client_signals", [column])

    op.create_table(
        "fitness_goals",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=False), sa.Column("metric_key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(160), nullable=False), sa.Column("baseline_value", sa.Float()),
        sa.Column("target_value", sa.Float(), nullable=False), sa.Column("current_value", sa.Float()),
        sa.Column("unit", sa.String(40), nullable=False), sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("target_on", sa.Date()), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for column in ["organization_id", "customer_id", "status"]:
        op.create_index(f"ix_fitness_goals_{column}", "fitness_goals", [column])

    op.create_table(
        "workout_sessions",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("location_id", UUID, nullable=False), sa.Column("customer_id", UUID, nullable=False),
        sa.Column("workout_plan_id", UUID), sa.Column("trainer_employee_id", UUID),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("exercise_results", postgresql.JSONB(), nullable=False),
        sa.Column("effort_rating", sa.Integer()), sa.Column("notes", sa.Text()),
        sa.Column("recorded_by_user_id", UUID, nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workout_plan_id"], ["workout_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trainer_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for column in ["organization_id", "location_id", "customer_id", "workout_plan_id", "trainer_employee_id", "scheduled_for", "status"]:
        op.create_index(f"ix_workout_sessions_{column}", "workout_sessions", [column])

    op.create_table(
        "coaching_notes",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=False), sa.Column("trainer_employee_id", UUID),
        sa.Column("note", sa.Text(), nullable=False), sa.Column("visibility", sa.String(30), nullable=False),
        sa.Column("recorded_by_user_id", UUID, nullable=False), *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trainer_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for column in ["organization_id", "customer_id", "trainer_employee_id"]:
        op.create_index(f"ix_coaching_notes_{column}", "coaching_notes", [column])

    op.create_table(
        "salon_customer_profiles",
        sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=False), sa.Column("preferred_employee_id", UUID),
        sa.Column("preferred_services", postgresql.JSONB(), nullable=False),
        sa.Column("preferences", postgresql.JSONB(), nullable=False), sa.Column("sensitivities", sa.Text()),
        sa.Column("formulas", sa.Text()), sa.Column("visit_interval_days", sa.Integer()),
        sa.Column("version", sa.Integer(), nullable=False), *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preferred_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "customer_id", name="uq_salon_customer_profile"),
    )
    op.create_index("ix_salon_customer_profiles_organization_id", "salon_customer_profiles", ["organization_id"])
    op.create_index("ix_salon_customer_profiles_customer_id", "salon_customer_profiles", ["customer_id"])


def downgrade() -> None:
    for table in ["salon_customer_profiles", "coaching_notes", "workout_sessions", "fitness_goals", "client_signals", "client_commitments", "client_memories", "customer_media"]:
        op.drop_table(table)
    op.drop_index("ix_gym_check_ins_recorded_by_user_id", table_name="gym_check_ins")
    op.drop_constraint("fk_checkin_corrected_user", "gym_check_ins", type_="foreignkey")
    op.drop_constraint("fk_checkin_recorded_user", "gym_check_ins", type_="foreignkey")
    for column in ["version", "correction_reason", "corrected_by_user_id", "notes", "source", "recorded_by_user_id"]:
        op.drop_column("gym_check_ins", column)
