"""Gym memberships, coaching, classes, wellness tracking, and equipment."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class MembershipPlan(TimestampMixin, Base):
    __tablename__ = "membership_plans"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    joining_fee_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    benefits: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        Index(
            "uq_memberships_current_per_client",
            "organization_id",
            "client_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'frozen')"),
        ),
        Index(
            "uq_memberships_scheduled_per_client",
            "organization_id",
            "client_id",
            unique=True,
            postgresql_where=text("status = 'scheduled'"),
        ),
    )
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="RESTRICT"), index=True)
    plan_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("membership_plans.id", ondelete="RESTRICT"), index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    invoice_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("sale_invoices.id", ondelete="SET NULL"), unique=True, index=True
    )
    previous_membership_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("memberships.id", ondelete="SET NULL"), index=True
    )
    frozen_from: Mapped[date | None] = mapped_column(Date)
    frozen_until: Mapped[date | None] = mapped_column(Date)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_effective_on: Mapped[date | None] = mapped_column(Date, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class GymCheckIn(TimestampMixin, Base):
    __tablename__ = "gym_check_ins"
    __table_args__ = (UniqueConstraint("membership_id", "checked_in_at", name="uq_membership_checkin_time"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    membership_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("memberships.id", ondelete="RESTRICT"), index=True)
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="RESTRICT"), index=True)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    method: Mapped[str] = mapped_column(String(30), default="staff", nullable=False)
    recorded_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(30), default="staff", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    corrected_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    correction_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class TrainerAssignment(TimestampMixin, Base):
    __tablename__ = "trainer_assignments"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    trainer_employee_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)


class FitnessMeasurement(TimestampMixin, Base):
    __tablename__ = "fitness_measurements"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    measured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class WorkoutPlan(TimestampMixin, Base):
    __tablename__ = "workout_plans"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    trainer_employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    schedule: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)


class DietPlan(TimestampMixin, Base):
    __tablename__ = "diet_plans"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    meals: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)


class GymClass(TimestampMixin, Base):
    __tablename__ = "gym_classes"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    trainer_employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", nullable=False)


class ClassBooking(TimestampMixin, Base):
    __tablename__ = "class_bookings"
    __table_args__ = (UniqueConstraint("gym_class_id", "client_id", name="uq_class_client"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    gym_class_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("gym_classes.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="booked", nullable=False)


class Equipment(TimestampMixin, Base):
    __tablename__ = "equipment"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="operational", nullable=False)
    purchased_on: Mapped[date | None] = mapped_column(Date)
    next_service_on: Mapped[date | None] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
