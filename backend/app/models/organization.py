"""Multi-tenant organizations and business locations."""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, tenant_fk, uuid_pk


class IndustryEnum(str, enum.Enum):
    gym = "gym"
    salon = "salon"
    clinic = "clinic"
    college = "college"
    restaurant = "restaurant"
    retail = "retail"
    grocery = "grocery"
    other = "other"


class OrganizationStatusEnum(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    trial = "trial"
    cancelled = "cancelled"


class SubscriptionPlanEnum(str, enum.Enum):
    trial = "trial"
    starter = "starter"
    growth = "growth"
    business = "business"
    enterprise = "enterprise"


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    industry: Mapped[IndustryEnum] = mapped_column(Enum(IndustryEnum, name="industry"), nullable=False)
    status: Mapped[OrganizationStatusEnum] = mapped_column(
        Enum(OrganizationStatusEnum, name="organization_status"), default=OrganizationStatusEnum.trial, nullable=False
    )
    plan: Mapped[SubscriptionPlanEnum] = mapped_column(
        Enum(SubscriptionPlanEnum, name="subscription_plan"), default=SubscriptionPlanEnum.trial, nullable=False
    )
    enabled_modules: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Kolkata", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(20))
    legal_name: Mapped[str | None] = mapped_column(String(220))
    invoice_prefix: Mapped[str] = mapped_column(String(20), default="INV", nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    ai_provider: Mapped[str] = mapped_column(String(30), default="openai", nullable=False)
    ai_model_override: Mapped[str | None] = mapped_column(String(80))
    onboarding_step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tax_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    operating_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    communication_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    security_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    privacy_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    locations: Mapped[list["Location"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Location(TimestampMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_location_org_code"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(12))
    phone: Mapped[str | None] = mapped_column(String(30))
    gstin: Mapped[str | None] = mapped_column(String(20))
    invoice_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="locations")


class IndustryMigrationRequest(TimestampMixin, Base):
    """A reviewed migration request; an organization's industry is never edited in place."""

    __tablename__ = "industry_migration_requests"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    requested_by_user_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    current_industry: Mapped[str] = mapped_column(String(30), nullable=False)
    requested_industry: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
