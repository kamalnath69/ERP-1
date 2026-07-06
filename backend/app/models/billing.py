"""Subscription, invoices, payment events (Razorpay)."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="trial")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="trialing")  # trialing/active/past_due/cancelled
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(120))
    seats: Mapped[int] = mapped_column(Integer, default=100)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    razorpay_order_id: Mapped[str | None] = mapped_column(String(120))
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="created")  # created/paid/failed
    description: Mapped[str | None] = mapped_column(Text)


class PaymentEvent(TimestampMixin, Base):
    __tablename__ = "payment_events"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
