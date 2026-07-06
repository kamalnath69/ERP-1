"""Organizations, campuses, subscription-related enums."""
import enum

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, uuid_pk, tenant_fk


class OrganizationTypeEnum(str, enum.Enum):
    school = "school"
    college = "college"
    university = "university"
    training_institute = "training_institute"
    coaching_centre = "coaching_centre"


class OrganizationStatusEnum(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    trial = "trial"
    cancelled = "cancelled"


class SubscriptionPlanEnum(str, enum.Enum):
    trial = "trial"
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    org_type: Mapped[OrganizationTypeEnum] = mapped_column(
        Enum(OrganizationTypeEnum, name="organization_type"), nullable=False
    )
    status: Mapped[OrganizationStatusEnum] = mapped_column(
        Enum(OrganizationStatusEnum, name="organization_status"),
        nullable=False,
        default=OrganizationStatusEnum.trial,
    )
    plan: Mapped[SubscriptionPlanEnum] = mapped_column(
        Enum(SubscriptionPlanEnum, name="subscription_plan"),
        nullable=False,
        default=SubscriptionPlanEnum.trial,
    )
    logo_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    ai_provider: Mapped[str] = mapped_column(String(30), default="openai", nullable=False)
    ai_model: Mapped[str] = mapped_column(String(80), default="gpt-5.4", nullable=False)

    campuses: Mapped[list["Campus"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Campus(TimestampMixin, Base):
    __tablename__ = "campuses"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    organization: Mapped[Organization] = relationship(back_populates="campuses")
