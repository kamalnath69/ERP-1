"""Subscriptions, invoices, and provider-neutral payment events."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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
    razorpay_plan_id: Mapped[str | None] = mapped_column(String(120))
    plan_version_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("plan_versions.id", ondelete="SET NULL"), index=True)
    billing_interval: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="razorpay", nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(20), default="test", nullable=False)
    cancel_at_cycle_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scheduled_plan_version_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("plan_versions.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    seats: Mapped[int] = mapped_column(Integer, default=100)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("uq_invoice_provider_order", "provider", "provider_order_id", unique=True, postgresql_where=text("provider_order_id IS NOT NULL")),
        Index("uq_invoice_provider_payment", "provider", "provider_payment_id", unique=True, postgresql_where=text("provider_payment_id IS NOT NULL")),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    razorpay_order_id: Mapped[str | None] = mapped_column(String(120))
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(30), default="razorpay", nullable=False)
    provider_order_id: Mapped[str | None] = mapped_column(String(140))
    provider_payment_id: Mapped[str | None] = mapped_column(String(140))
    provider_session_id: Mapped[str | None] = mapped_column(Text)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    discount_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tax_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    igst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tax_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gst_rate_bps: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    purchase_type: Mapped[str] = mapped_column(String(30), default="plan", nullable=False, index=True)
    billing_interval: Mapped[str | None] = mapped_column(String(20))
    fulfillment_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    provider_mode: Mapped[str] = mapped_column(String(20), default="test", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="created")  # created/paid/failed
    description: Mapped[str | None] = mapped_column(Text)
    invoice_number: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    billing_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    plan_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class PaymentEvent(TimestampMixin, Base):
    __tablename__ = "payment_events"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="razorpay", nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    provider_mode: Mapped[str] = mapped_column(String(20), default="test", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="processed", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class ProviderPlanMapping(TimestampMixin, Base):
    __tablename__ = "provider_plan_mappings"
    __table_args__ = (UniqueConstraint(
        "plan_version_id", "billing_interval", "provider", "provider_mode", "amount_paise",
        name="uq_provider_plan_price",
    ),)
    id: Mapped[str] = uuid_pk()
    plan_version_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    billing_interval: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="razorpay", nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider_plan_id: Mapped[str | None] = mapped_column(String(140), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BillingCheckoutAttempt(TimestampMixin, Base):
    __tablename__ = "billing_checkout_attempts"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_billing_checkout_key"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    invoice_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("invoices.id", ondelete="SET NULL"), index=True)
    subscription_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True)
    purchase_type: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="razorpay", nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="creating", nullable=False, index=True)
    provider_reference: Mapped[str | None] = mapped_column(String(140), index=True)
    error_code: Mapped[str | None] = mapped_column(String(100))


class SubscriptionSchedule(TimestampMixin, Base):
    __tablename__ = "subscription_schedules"
    __table_args__ = (Index("uq_subscription_schedule_active", "subscription_id", unique=True, postgresql_where=text("status = 'scheduled'")),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    subscription_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    target_plan_version_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("plan_versions.id", ondelete="SET NULL"), index=True)
    billing_interval: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", nullable=False, index=True)
    provider_reference: Mapped[str | None] = mapped_column(String(140))
    reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
