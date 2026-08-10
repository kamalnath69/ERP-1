"""Shared CRM, workforce, catalog, appointments, stock, sales, and tasks."""
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text,
    Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("organization_id", "employee_number", name="uq_employee_org_number"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    employee_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), index=True)
    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    designation: Mapped[str | None] = mapped_column(String(120))
    specialties: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    salary_paise: Mapped[int | None] = mapped_column(BigInteger)
    joining_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class EmployeeLocation(Base):
    __tablename__ = "employee_locations"
    __table_args__ = (UniqueConstraint("employee_id", "location_id", name="uq_employee_location"),)

    id: Mapped[str] = uuid_pk()
    employee_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StaffSchedule(TimestampMixin, Base):
    __tablename__ = "staff_schedules"
    __table_args__ = (UniqueConstraint("employee_id", "location_id", "weekday", name="uq_staff_schedule_day"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[time] = mapped_column(Time, nullable=False)
    ends_at: Mapped[time] = mapped_column(Time, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Client(TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("organization_id", "client_number", name="uq_client_org_number"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    home_location_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    client_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    email: Mapped[str | None] = mapped_column(String(200), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(30))
    joined_on: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    last_visit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    whatsapp_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whatsapp_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    whatsapp_consent_source: Mapped[str | None] = mapped_column(String(50))
    email_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_category_org_name"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="product", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CatalogItem(TimestampMixin, Base):
    __tablename__ = "catalog_items"
    __table_args__ = (UniqueConstraint("organization_id", "sku", name="uq_catalog_org_sku"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    category_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    item_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # product/service/medicine/lab_test
    description: Mapped[str | None] = mapped_column(Text)
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    price_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cost_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tax_rate_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_inclusive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(30), default="unit", nullable=False)
    track_stock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class StockLevel(TimestampMixin, Base):
    __tablename__ = "stock_levels"
    __table_args__ = (UniqueConstraint("location_id", "item_id", "batch_number", name="uq_stock_location_item_batch"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("catalog_items.id", ondelete="CASCADE"), index=True)
    quantity_milli: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reorder_level_milli: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    batch_number: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class StockMovement(TimestampMixin, Base):
    __tablename__ = "stock_movements"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("catalog_items.id", ondelete="RESTRICT"), index=True)
    stock_level_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("stock_levels.id", ondelete="RESTRICT"), index=True)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity_delta_milli: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[str | None] = mapped_column(UUID_STR, index=True)
    performed_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), index=True)


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    client_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="RESTRICT"), index=True)
    employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    service_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("catalog_items.id", ondelete="SET NULL"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), default="staff", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SaleInvoice(TimestampMixin, Base):
    __tablename__ = "sale_invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number", name="uq_sale_org_number"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_sale_org_idempotency"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    client_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    employee_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    discount_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    igst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tax_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SaleLine(Base):
    __tablename__ = "sale_lines"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    invoice_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("sale_invoices.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("catalog_items.id", ondelete="SET NULL"), index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    item_name: Mapped[str] = mapped_column(String(180), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(80))
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    quantity_milli: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tax_rate_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SalePayment(TimestampMixin, Base):
    __tablename__ = "sale_payments"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_payment_org_idempotency"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    invoice_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("sale_invoices.id", ondelete="RESTRICT"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="captured", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    received_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"))


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    location_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    client_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
