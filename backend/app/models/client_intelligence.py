"""Client relationship intelligence, media, and vertical progress records."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class ClientMedia(TimestampMixin, Base):
    __tablename__ = "client_media"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("documents.id", ondelete="CASCADE"), unique=True, index=True)
    media_kind: Mapped[str] = mapped_column(String(40), default="attachment", nullable=False, index=True)
    caption: Mapped[str | None] = mapped_column(String(500))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    visibility: Mapped[str] = mapped_column(String(30), default="team", nullable=False)
    is_profile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    uploaded_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ClientMemory(TimestampMixin, Base):
    __tablename__ = "client_memories"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(30), default="team", nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    updated_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ClientCommitment(TimestampMixin, Base):
    __tablename__ = "client_commitments"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    completion_note: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ClientSignal(TimestampMixin, Base):
    __tablename__ = "client_signals"
    __table_args__ = (UniqueConstraint("client_id", "signal_type", "rule_version", name="uq_client_signal_rule"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    signal_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    pulse_state: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(30), default="v1", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class FitnessGoal(TimestampMixin, Base):
    __tablename__ = "fitness_goals"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    current_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    target_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class WorkoutSession(TimestampMixin, Base):
    __tablename__ = "workout_sessions"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    workout_plan_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("workout_plans.id", ondelete="SET NULL"), index=True)
    trainer_employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="planned", nullable=False, index=True)
    exercise_results: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    effort_rating: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CoachingNote(TimestampMixin, Base):
    __tablename__ = "coaching_notes"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    trainer_employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(30), default="assigned_staff", nullable=False)
    recorded_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))


class SalonClientProfile(TimestampMixin, Base):
    __tablename__ = "salon_client_profiles"
    __table_args__ = (UniqueConstraint("organization_id", "client_id", name="uq_salon_client_profile"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    preferred_employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"))
    preferred_services: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sensitivities: Mapped[str | None] = mapped_column(Text)
    formulas: Mapped[str | None] = mapped_column(Text)
    visit_interval_days: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
