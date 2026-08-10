"""Shared API request and response contracts."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

COMMON_PASSWORDS = {"password", "password123", "qwerty123", "admin123", "welcome123", "letmein123"}


def validate_strong_password(value: str) -> str:
    if not any(char.islower() for char in value) or not any(char.isupper() for char in value) or not any(char.isdigit() for char in value):
        raise ValueError("Password must include uppercase, lowercase, and a number")
    if value.lower() in COMMON_PASSWORDS:
        raise ValueError("Choose a less common password")
    return value


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterOrgRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    organization_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    industry: str
    admin_email: EmailStr
    admin_password: str = Field(min_length=10, max_length=128)
    admin_first_name: str
    admin_last_name: str = ""
    location_name: str = "Main Location"
    city: str | None = None
    state: str | None = Field(default=None, max_length=100)

    @field_validator("admin_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_strong_password(value)


class PaidSignupCheckoutRequest(RegisterOrgRequest):
    plan: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")
    billing_interval: str = Field(default="monthly", pattern=r"^(monthly|annual)$")
    idempotency_key: str = Field(min_length=8, max_length=160)
    checkout_token: str | None = Field(default=None, min_length=20, max_length=200)


class PaidSignupVerifyRequest(BaseModel):
    checkout_id: str
    checkout_token: str = Field(min_length=20, max_length=200)
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaidSignupAccessRequest(BaseModel):
    checkout_token: str = Field(min_length=20, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    org_slug: str | None = None
    mfa_code: str | None = Field(default=None, min_length=6, max_length=12)


class LoginResponse(BaseModel):
    user: dict
    csrf_token: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class CodeRequest(BaseModel):
    email: EmailStr
    org_slug: str | None = None


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


class UserCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str = ""
    password: str = Field(min_length=10, max_length=128)
    phone: str | None = None
    role_ids: list[str] = []
    location_ids: list[str] = []

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_strong_password(value)


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    bio: str | None = None
    designation: str | None = None
    avatar_base64: str | None = None
    action_preferences: dict | None = None


class ProfileUpdate(UserUpdate):
    pass


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_strong_password(value)


class OverrideEntry(BaseModel):
    permission_id: str
    granted: bool


class UserOverridesUpdate(BaseModel):
    overrides: list[OverrideEntry]


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


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    permission_ids: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    permission_ids: list[str] | None = None
    version: int | None = Field(default=None, ge=1)


class AssignRolesRequest(BaseModel):
    role_ids: list[str]


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=5000)
    location_id: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    context: dict | None = None


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


class CreateOrderRequest(BaseModel):
    plan: str
    billing_interval: str = Field(default="monthly", pattern="^(monthly|annual)$")


class VerifyRazorpayPaymentRequest(BaseModel):
    invoice_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


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
