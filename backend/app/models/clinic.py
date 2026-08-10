"""Outpatient clinical records, prescriptions, laboratory, and dispensing."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class PatientProfile(TimestampMixin, Base):
    __tablename__ = "patient_profiles"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="CASCADE"), unique=True, index=True)
    abha_number: Mapped[str | None] = mapped_column(String(30), index=True)
    blood_group: Mapped[str | None] = mapped_column(String(10))
    emergency_contact: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    consent: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    medical_summary: Mapped[str | None] = mapped_column(Text)


class Encounter(TimestampMixin, Base):
    __tablename__ = "encounters"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    patient_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("patient_profiles.id", ondelete="RESTRICT"), index=True)
    appointment_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("appointments.id", ondelete="SET NULL"), index=True)
    practitioner_employee_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    clinical_notes: Mapped[str | None] = mapped_column(Text)
    assessment: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str | None] = mapped_column(Text)
    follow_up_on: Mapped[date | None] = mapped_column(Date)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Vital(TimestampMixin, Base):
    __tablename__ = "vitals"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    encounter_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    values: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Allergy(TimestampMixin, Base):
    __tablename__ = "allergies"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    patient_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True)
    substance: Mapped[str] = mapped_column(String(160), nullable=False)
    reaction: Mapped[str | None] = mapped_column(String(250))
    severity: Mapped[str] = mapped_column(String(30), default="unknown", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)


class Diagnosis(TimestampMixin, Base):
    __tablename__ = "diagnoses"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    encounter_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    code: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_suggested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Prescription(TimestampMixin, Base):
    __tablename__ = "prescriptions"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    encounter_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("encounters.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    ai_drafted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    prescription_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True)
    medicine_item_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("catalog_items.id", ondelete="SET NULL"))
    medicine_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dosage: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(String(100), nullable=False)
    duration: Mapped[str] = mapped_column(String(100), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)


class LabTest(TimestampMixin, Base):
    __tablename__ = "lab_tests"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reference_ranges: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LabOrder(TimestampMixin, Base):
    __tablename__ = "lab_orders"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    encounter_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("encounters.id", ondelete="RESTRICT"), index=True)
    test_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("lab_tests.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="ordered", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))


class LabResult(TimestampMixin, Base):
    __tablename__ = "lab_results"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    order_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("lab_orders.id", ondelete="RESTRICT"), unique=True, index=True)
    values: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    interpretation: Mapped[str | None] = mapped_column(Text)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))


class Dispense(TimestampMixin, Base):
    __tablename__ = "dispenses"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    prescription_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("prescriptions.id", ondelete="RESTRICT"), index=True)
    items: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    dispensed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispensed_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))
