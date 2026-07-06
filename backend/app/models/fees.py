"""Fees: structure, invoices, payments."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class FeeStructure(TimestampMixin, Base):
    __tablename__ = "fee_structures"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g. "Term 1 · Year 2 CSE"
    level_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("academic_levels.id", ondelete="SET NULL"))
    department_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("departments.id", ondelete="SET NULL"))
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # rupees (not paise)
    due_date: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FeeInvoice(TimestampMixin, Base):
    __tablename__ = "fee_invoices"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    structure_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("fee_structures.id", ondelete="SET NULL"))
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending / partial / paid / waived
    due_date: Mapped[str | None] = mapped_column(String(20))
    razorpay_order_id: Mapped[str | None] = mapped_column(String(120))
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(120))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
