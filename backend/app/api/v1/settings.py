"""Thin, typed business settings API."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import EmailStr, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.validation import RequestModel
from app.core.deps import require_any_permission
from app.models import User
from app.services.organization_settings import request_industry_migration, settings_workspace, update_section

router = APIRouter(prefix="/settings", tags=["settings"])


class VersionedBody(RequestModel):
    version: int = Field(ge=1)


class IdentityBody(VersionedBody):
    name: str = Field(min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=220)
    gstin: str | None = Field(default=None, max_length=20)
    timezone: str = Field(default="Asia/Kolkata", min_length=3, max_length=80)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=3000)
    invoice_prefix: str = Field(default="INV", pattern=r"^[A-Za-z0-9-]{1,20}$")


class TaxBody(VersionedBody):
    prices_include_tax: bool = False
    default_tax_rate_bps: int = Field(default=0, ge=0, le=10000)


class OperationsBody(VersionedBody):
    values: dict


class CommunicationsBody(VersionedBody):
    appointment_reminders: bool = True
    payment_reminders: bool = True
    membership_reminders: bool = True
    follow_up_reminders: bool = True


class SecurityBody(VersionedBody):
    mfa_policy: Literal["optional", "privileged", "all"] = "optional"


class PrivacyBody(VersionedBody):
    conversation_retention_days: int = Field(default=90, ge=30, le=3650)


class IndustryRequestBody(RequestModel):
    requested_industry: Literal["gym", "salon", "clinic", "college"]
    reason: str = Field(min_length=20, max_length=2000)


SETTINGS_PERMISSIONS = (
    "settings.view", "settings.manage", "settings.identity.manage", "settings.locations.manage",
    "settings.tax.manage", "settings.operations.manage", "settings.communication.manage",
    "settings.security.manage", "settings.privacy.manage", "settings.audit.view",
)


@router.get("/workspace")
def workspace(
    user: User = Depends(require_any_permission(*SETTINGS_PERMISSIONS)),
    db: Session = Depends(get_db),
):
    return settings_workspace(db, user)


@router.put("/identity")
def save_identity(body: IdentityBody, user: User = Depends(require_any_permission("settings.manage", "settings.identity.manage")), db: Session = Depends(get_db)):
    values = body.model_dump(exclude={"version"})
    return update_section(db, user, "identity", values, body.version)


@router.put("/tax")
def save_tax(body: TaxBody, user: User = Depends(require_any_permission("settings.manage", "settings.tax.manage")), db: Session = Depends(get_db)):
    return update_section(db, user, "tax", body.model_dump(exclude={"version"}), body.version)


@router.put("/operations")
def save_operations(body: OperationsBody, user: User = Depends(require_any_permission("settings.manage", "settings.operations.manage")), db: Session = Depends(get_db)):
    return update_section(db, user, "operations", body.values, body.version)


@router.put("/communications")
def save_communications(body: CommunicationsBody, user: User = Depends(require_any_permission("settings.manage", "settings.communication.manage")), db: Session = Depends(get_db)):
    return update_section(db, user, "communications", body.model_dump(exclude={"version"}), body.version)


@router.put("/security")
def save_security(body: SecurityBody, user: User = Depends(require_any_permission("settings.manage", "settings.security.manage")), db: Session = Depends(get_db)):
    return update_section(db, user, "security", body.model_dump(exclude={"version"}), body.version)


@router.put("/privacy")
def save_privacy(body: PrivacyBody, user: User = Depends(require_any_permission("settings.manage", "settings.privacy.manage")), db: Session = Depends(get_db)):
    return update_section(db, user, "privacy", body.model_dump(exclude={"version"}), body.version)


@router.post("/industry-migration-request", status_code=201)
def industry_request(body: IndustryRequestBody, user: User = Depends(require_any_permission("settings.manage", "settings.identity.manage")), db: Session = Depends(get_db)):
    return request_industry_migration(db, user, body.requested_industry, body.reason)
