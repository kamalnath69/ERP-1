"""Platform control-plane models for plans, billing, wallet, security, and support."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk


class FeatureDefinition(TimestampMixin, Base):
    __tablename__ = "feature_definitions"
    id: Mapped[str] = uuid_pk()
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(30), default="boolean", nullable=False)
    industries: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    dependencies: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    metering: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PlanDefinition(TimestampMixin, Base):
    __tablename__ = "plan_definitions"
    id: Mapped[str] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PlanVersion(TimestampMixin, Base):
    __tablename__ = "plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_plan_version"),)
    id: Mapped[str] = uuid_pk()
    plan_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("plan_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    monthly_price_paise: Mapped[int | None] = mapped_column(BigInteger)
    annual_price_paise: Mapped[int | None] = mapped_column(BigInteger)
    annual_discount_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gst_rate_bps: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    included_ai_credits: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    support_level: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)
    ai_tier: Mapped[str] = mapped_column(String(40), default="basic", nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    version_lock: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SignupCheckout(TimestampMixin, Base):
    """Short-lived paid signup state; this is not an organization account."""

    __tablename__ = "signup_checkouts"
    __table_args__ = (
        Index("ix_signup_checkouts_slug_status_expiry", "organization_slug", "status", "expires_at"),
        Index("ix_signup_checkouts_status_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = uuid_pk()
    status: Mapped[str] = mapped_column(String(30), default="creating", nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    access_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    industry: Mapped[str] = mapped_column(String(30), nullable=False)
    admin_email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    admin_password_hash: Mapped[str | None] = mapped_column(String(300))
    admin_first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    admin_last_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    location_name: Mapped[str] = mapped_column(String(200), default="Main Location", nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    plan_version_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("plan_versions.id", ondelete="SET NULL"), index=True
    )
    plan_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(20), nullable=False)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gst_rate_bps: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_order_id: Mapped[str | None] = mapped_column(String(140), unique=True, index=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(140), unique=True, index=True)
    organization_id: Mapped[str | None] = mapped_column(
        UUID_STR, ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(240))


class PlanEntitlement(Base):
    __tablename__ = "plan_entitlements"
    __table_args__ = (UniqueConstraint("plan_version_id", "feature_id", name="uq_plan_entitlement"),)
    id: Mapped[str] = uuid_pk()
    plan_version_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("feature_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class OrganizationEntitlementOverride(TimestampMixin, Base):
    __tablename__ = "organization_entitlement_overrides"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("feature_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class BillingProfile(TimestampMixin, Base):
    __tablename__ = "billing_profiles"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_billing_profile_org"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(220))
    billing_email: Mapped[str | None] = mapped_column(String(200))
    billing_phone: Mapped[str | None] = mapped_column(String(40))
    gstin: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(12))
    purchase_order_reference: Mapped[str | None] = mapped_column(String(120))
    tax_exempt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tax_exemption_meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class PlatformPayment(TimestampMixin, Base):
    __tablename__ = "platform_payments"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("invoices.id", ondelete="SET NULL"), index=True)
    provider: Mapped[str] = mapped_column(String(30), default="razorpay", nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(String(140), unique=True, index=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(140), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="test", nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    method: Mapped[str | None] = mapped_column(String(40))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class PlatformRefund(TimestampMixin, Base):
    __tablename__ = "platform_refunds"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("platform_payments.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider_refund_id: Mapped[str | None] = mapped_column(String(140), unique=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="requested", nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class PlatformSettlement(TimestampMixin, Base):
    __tablename__ = "platform_settlements"
    id: Mapped[str] = uuid_pk()
    provider_settlement_id: Mapped[str | None] = mapped_column(String(140), unique=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AIWallet(TimestampMixin, Base):
    __tablename__ = "ai_wallets"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_ai_wallet_org"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    balance_credits: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reserved_credits: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cycle_grant_credits: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cycle_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cycle_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class WalletLedger(TimestampMixin, Base):
    __tablename__ = "wallet_ledger"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("ai_wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    credits_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(60))
    reference_id: Mapped[str | None] = mapped_column(String(140), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))


class WalletReservation(TimestampMixin, Base):
    __tablename__ = "wallet_reservations"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("ai_wallets.id", ondelete="CASCADE"), nullable=False)
    credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="reserved", nullable=False, index=True)
    settled_credits: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class RechargePack(TimestampMixin, Base):
    __tablename__ = "recharge_packs"
    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gst_rate_bps: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WalletCreditGrant(TimestampMixin, Base):
    __tablename__ = "wallet_credit_grants"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_wallet_credit_grant_key"),)
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("ai_wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(140), index=True)
    granted_credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remaining_credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)


class PlatformPermission(TimestampMixin, Base):
    __tablename__ = "platform_permissions"
    id: Mapped[str] = uuid_pk()
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)


class PlatformRole(TimestampMixin, Base):
    __tablename__ = "platform_roles"
    id: Mapped[str] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PlatformRolePermission(Base):
    __tablename__ = "platform_role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_platform_role_permission"),)
    id: Mapped[str] = uuid_pk()
    role_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("platform_roles.id", ondelete="CASCADE"), nullable=False)
    permission_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("platform_permissions.id", ondelete="CASCADE"), nullable=False)


class PlatformUserRole(Base):
    __tablename__ = "platform_user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_platform_user_role"),)
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("platform_roles.id", ondelete="CASCADE"), nullable=False)


class PlatformMFADevice(TimestampMixin, Base):
    __tablename__ = "platform_mfa_devices"
    __table_args__ = (UniqueConstraint("user_id", name="uq_platform_mfa_user"),)
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)


class PlatformRecoveryCode(TimestampMixin, Base):
    __tablename__ = "platform_recovery_codes"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalRequest(TimestampMixin, Base):
    __tablename__ = "approval_requests"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount_paise: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    requested_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decided_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SupportSession(TimestampMixin, Base):
    __tablename__ = "support_sessions"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    target_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    approval_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("approval_requests.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(30), default="read_only", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationDeletionRequest(TimestampMixin, Base):
    __tablename__ = "organization_deletion_requests"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    organization_name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", nullable=False, index=True)
    requested_by_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetentionArchive(TimestampMixin, Base):
    __tablename__ = "retention_archives"
    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    organization_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    record_type: Mapped[str] = mapped_column(String(80), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    retention_reason: Mapped[str] = mapped_column(Text, nullable=False)
    purge_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformSetting(TimestampMixin, Base):
    __tablename__ = "platform_settings"
    id: Mapped[str] = uuid_pk()
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
