"""Shared API request and response contracts."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Literal

from app.schemas.validation import RequestModel, valid_phone

COMMON_PASSWORDS = {"password", "password123", "qwerty123", "admin123", "welcome123", "letmein123"}


def validate_strong_password(value: str) -> str:
    if not any(char.islower() for char in value) or not any(char.isupper() for char in value) or not any(char.isdigit() for char in value):
        raise ValueError("Password must include uppercase, lowercase, and a number")
    if value.lower() in COMMON_PASSWORDS:
        raise ValueError("Choose a less common password")
    return value


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LegalAcceptanceRequest(RequestModel):
    accepted: Literal[True]
    terms_document_id: str = Field(min_length=1, max_length=100)
    privacy_document_id: str = Field(min_length=1, max_length=100)
    refund_document_id: str = Field(min_length=1, max_length=100)


class SignupEmailVerificationProof(RequestModel):
    challenge_id: str = Field(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    )
    proof: str = Field(min_length=32, max_length=200)


class SignupEmailChallengeRequest(RequestModel):
    email: EmailStr


class SignupEmailChallengeVerifyRequest(RequestModel):
    challenge_token: str = Field(min_length=32, max_length=200)
    code: str = Field(pattern=r"^\d{6}$")


class RegisterOrgRequest(RequestModel):
    organization_name: str = Field(min_length=2, max_length=200)
    organization_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    industry: Literal["gym", "salon", "clinic", "college", "restaurant", "retail", "grocery", "other"]
    admin_email: EmailStr
    admin_password: str = Field(min_length=10, max_length=128)
    admin_first_name: str = Field(min_length=1, max_length=100)
    admin_last_name: str = Field(default="", max_length=100)
    admin_phone: str | None = Field(default=None, max_length=40)
    location_name: str = Field(default="Main Location", min_length=2, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=100)
    legal_acceptance: LegalAcceptanceRequest
    email_verification: SignupEmailVerificationProof

    @field_validator("admin_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_strong_password(value)

    @field_validator("admin_phone")
    @classmethod
    def phone_number(cls, value: str | None) -> str | None:
        return valid_phone(value)


class PaidSignupCheckoutRequest(RegisterOrgRequest):
    plan: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")
    billing_interval: str = Field(default="monthly", pattern=r"^(monthly|annual)$")
    idempotency_key: str = Field(min_length=8, max_length=160)
    checkout_token: str | None = Field(default=None, min_length=20, max_length=200)


class PaidSignupVerifyRequest(RequestModel):
    checkout_id: str = Field(min_length=1, max_length=100)
    checkout_token: str = Field(min_length=20, max_length=200)
    razorpay_order_id: str | None = Field(default=None, min_length=1, max_length=200)
    razorpay_payment_id: str | None = Field(default=None, min_length=1, max_length=200)
    razorpay_signature: str | None = Field(default=None, min_length=16, max_length=500)


class PaidSignupAccessRequest(RequestModel):
    checkout_token: str = Field(min_length=20, max_length=200)


class LoginRequest(RequestModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    org_slug: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    mfa_code: str | None = Field(default=None, min_length=6, max_length=12)


class LoginResponse(BaseModel):
    user: dict
    csrf_token: str


class RefreshRequest(RequestModel):
    refresh_token: str | None = Field(default=None, max_length=4096)


class CodeRequest(RequestModel):
    email: EmailStr
    org_slug: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class VerifyEmailRequest(CodeRequest):
    code: str = Field(pattern=r"^\d{6}$")


class ResetPasswordRequest(VerifyEmailRequest):
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_strong_password(value)


class UserOut(ORMBase):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    is_active: bool
    is_super_admin: bool
    organization_id: str | None = None
    avatar_url: str | None = None
    avatar_base64: str | None = None
    bio: str | None = None
    designation: str | None = None
    email_verified: bool = False
    action_preferences: dict = {}
    access_version: int = 1


class UserCreate(RequestModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    password: str = Field(min_length=10, max_length=128)
    phone: str | None = Field(default=None, max_length=30)
    role_ids: list[str] = Field(default_factory=list, max_length=100)
    location_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_strong_password(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        return valid_phone(value)


class UserUpdate(RequestModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    is_active: bool | None = None
    bio: str | None = Field(default=None, max_length=5000)
    designation: str | None = Field(default=None, max_length=200)
    avatar_base64: str | None = Field(default=None, max_length=500_000, pattern=r"^data:image/(jpeg|png|webp);base64,")
    action_preferences: dict | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        return valid_phone(value)


class ProfileUpdate(RequestModel):
    first_name: str = Field(default="", min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    bio: str | None = Field(default=None, max_length=5000)
    designation: str | None = Field(default=None, max_length=200)
    avatar_base64: str | None = Field(default=None, max_length=500_000, pattern=r"^data:image/(jpeg|png|webp);base64,")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        return valid_phone(value)


class PasswordChange(RequestModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_strong_password(value)


class OverrideEntry(RequestModel):
    permission_id: str = Field(min_length=1, max_length=100)
    granted: bool


class UserOverridesUpdate(RequestModel):
    overrides: list[OverrideEntry] = Field(max_length=500)


class PermissionOut(ORMBase):
    id: str
    code: str
    label: str
    module: str
    description: str | None = None


class RoleOut(ORMBase):
    id: str
    name: str
    slug: str
    description: str | None = None
    is_system: bool
    is_active: bool
    version: int = 1


class RoleCreate(RequestModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    permission_ids: list[str] = Field(default_factory=list, max_length=500)


class RoleUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    permission_ids: list[str] | None = Field(default=None, max_length=500)
    version: int | None = Field(default=None, ge=1)


class AssignRolesRequest(RequestModel):
    role_ids: list[str] = Field(max_length=100)


class ChatRequest(RequestModel):
    conversation_id: str | None = Field(default=None, max_length=100)
    message: str = Field(min_length=1, max_length=5000)
    location_id: str | None = Field(default=None, max_length=100)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    context: dict | None = Field(default=None, max_length=100)


class ChatMessageOut(ORMBase):
    id: str
    conversation_id: str
    turn_id: str
    role: str
    content: str
    response_schema_version: int = 1
    blocks: list = []
    citations: list = []
    feedback_rating: str | None = None
    created_at: datetime


class ConversationOut(ORMBase):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    preview: str | None = None
    turn_count: int = 0
    active_stream: bool = False
    pinned_at: datetime | None = None
    archived_at: datetime | None = None


class CreateOrderRequest(RequestModel):
    plan: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")
    billing_interval: str = Field(default="monthly", pattern="^(monthly|annual)$")


class VerifyRazorpayPaymentRequest(RequestModel):
    invoice_id: str = Field(min_length=1, max_length=100)
    razorpay_order_id: str | None = Field(default=None, min_length=1, max_length=200)
    razorpay_payment_id: str | None = Field(default=None, min_length=1, max_length=200)
    razorpay_signature: str | None = Field(default=None, min_length=16, max_length=500)


class WebhookEvent(BaseModel):
    event: str
    payload: dict


class NotificationOut(ORMBase):
    id: str
    title: str
    body: str | None
    is_read: bool
    kind: str
    link: str | None
    created_at: datetime
