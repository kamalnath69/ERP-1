"""Advanced gym operations with lifecycle validation."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    ClassBooking, Client, DietPlan, Employee, Equipment, FitnessMeasurement, GymCheckIn,
    GymClass, Membership, MembershipPlan, SaleInvoice, SalePayment, TrainerAssignment, WorkoutPlan,
)
from app.services.audit import log_action
from app.services.business_access import allowed_client_ids, allowed_location_ids, ensure_client_access, ensure_location, filter_locations, organization_for, tenant_get
from app.services.communications import queue_whatsapp_template
from app.services.rbac import get_user_permissions
from app.api.v1.business import serialize
from app.services.gym import (
    checkin_directory, class_directory, coaching_directory, equipment_directory,
    gym_summary, local_today, membership_directory, membership_for_user,
    reconcile_memberships,
)
from app.services.sales import (
    apply_invoice_payment,
    create_membership_invoice,
    invoice_detail,
    membership_invoice_quote,
    void_unpaid_invoice,
)

router = APIRouter(prefix="/gym", tags=["gym"])


def require_gym(db, user):
    org = organization_for(db, user)
    if org.industry.value != "gym" and "gym" not in org.enabled_modules:
        raise HTTPException(404, "Gym module is not enabled")
    return org


def _queue_membership_update(db, user, client, plan, membership, status_label):
    organization = organization_for(db, user)
    queue_whatsapp_template(
        db, organization=organization, client=client, location_id=membership.location_id,
        template=settings.WHATSAPP_TEMPLATE_MEMBERSHIP_UPDATE,
        variables=[client.first_name, plan.name, organization.name, status_label, membership.ends_on.strftime("%d %b %Y")],
        body=f"Membership update: {plan.name} is {status_label.lower()} through {membership.ends_on.strftime('%d %b %Y')}",
        idempotency_key=f"wa-membership:{membership.id}:status:{status_label.lower().replace(' ', '-')}",
    )


class PlanBody(BaseModel):
    name: str
    duration_days: int = Field(gt=0)
    price_paise: int = Field(ge=0)
    joining_fee_paise: int = Field(default=0, ge=0)
    benefits: list[str] = Field(default_factory=list)


class MembershipBody(BaseModel):
    location_id: str
    client_id: str
    plan_id: str
    starts_on: date
    payment_option: Literal["full", "partial", "later"] = "later"
    partial_payment_paise: int | None = Field(default=None, gt=0)
    payment_method: Literal["cash", "upi", "card", "bank"] | None = None
    payment_reference: str | None = Field(default=None, max_length=120)
    interstate: bool = False
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=90)
    # Retained only to reject stale callers attempting to override the quote.
    amount_paise: int | None = Field(default=None, ge=0)


class RenewalBody(BaseModel):
    plan_id: str | None = None
    payment_option: Literal["full", "partial", "later"] = "later"
    partial_payment_paise: int | None = Field(default=None, gt=0)
    payment_method: Literal["cash", "upi", "card", "bank"] | None = None
    payment_reference: str | None = Field(default=None, max_length=120)
    interstate: bool = False
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=90)


class FreezeBody(BaseModel):
    frozen_from: date
    frozen_until: date
    version: int


class CancelBody(BaseModel):
    reason: str = Field(min_length=3)
    version: int
    timing: Literal["now", "term_end"] = "now"
    cancel_scheduled_renewal: bool = True


class CancellationRevokeBody(BaseModel):
    version: int


class CheckInBody(BaseModel):
    location_id: str
    membership_id: str
    method: str = "staff"


class TrainerBody(BaseModel):
    client_id: str
    trainer_employee_id: str
    starts_on: date = Field(default_factory=date.today)
    ends_on: date | None = None


class MeasurementBody(BaseModel):
    client_id: str
    measured_on: date = Field(default_factory=date.today)
    metrics: dict
    notes: str | None = None


class WorkoutBody(BaseModel):
    client_id: str
    trainer_employee_id: str | None = None
    name: str
    schedule: list[dict]
    starts_on: date = Field(default_factory=date.today)
    ends_on: date | None = None


class DietBody(BaseModel):
    client_id: str
    name: str
    meals: list[dict]
    notes: str | None = None
    starts_on: date = Field(default_factory=date.today)
    ends_on: date | None = None


class ClassBody(BaseModel):
    location_id: str
    trainer_employee_id: str | None = None
    name: str
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(gt=0)


class BookingBody(BaseModel):
    client_id: str


class EquipmentBody(BaseModel):
    location_id: str
    name: str
    asset_code: str
    purchased_on: date | None = None
    next_service_on: date | None = None
    notes: str | None = None


def _payment_for_response(payment: SalePayment | None) -> dict | None:
    return serialize(payment) if payment else None


def _membership_response(db: Session, user, row: Membership, payment: SalePayment | None = None) -> dict:
    result = serialize(row)
    plan = db.get(MembershipPlan, row.plan_id)
    result["plan"] = serialize(plan) if plan else None
    result["invoice"] = invoice_detail(db, user, row.invoice_id) if row.invoice_id else None
    result["payment"] = _payment_for_response(payment)
    result["legacy_unlinked"] = row.invoice_id is None
    today = local_today(db, user)[0]
    result["days_remaining"] = max((row.ends_on - today).days + 1, 0) if row.status in {"active", "frozen"} else 0
    return result


def _payment_amount(body, total_paise: int, permissions: set[str]) -> int:
    if body.payment_option == "later" or total_paise == 0:
        return 0
    if "payments.record" not in permissions:
        raise HTTPException(403, "Payment recording permission is required for this checkout option")
    if not body.payment_method:
        raise HTTPException(422, "Choose a payment method")
    if body.payment_option == "full":
        return total_paise
    amount = body.partial_payment_paise or 0
    if amount <= 0 or amount >= total_paise:
        raise HTTPException(422, "A partial payment must be greater than zero and less than the invoice total")
    return amount


def _linked_payment(
    db: Session,
    user,
    invoice: SaleInvoice,
    body,
    idempotency_key: str,
) -> SalePayment | None:
    amount = _payment_amount(body, invoice.total_paise, get_user_permissions(db, user))
    if not amount:
        return None
    return apply_invoice_payment(
        db,
        user,
        invoice,
        amount_paise=amount,
        method=body.payment_method,
        reference=body.payment_reference,
        idempotency_key=f"{idempotency_key}:payment",
        permission="payments.record",
    )


def _scheduled_for_client(db: Session, user, client_id: str, *, exclude_id: str | None = None) -> Membership | None:
    statement = select(Membership).where(
        Membership.organization_id == user.organization_id,
        Membership.client_id == client_id,
        Membership.status == "scheduled",
    )
    if exclude_id:
        statement = statement.where(Membership.id != exclude_id)
    return db.execute(statement.with_for_update()).scalar_one_or_none()


def _cancel_scheduled_term(db: Session, user, row: Membership, reason: str) -> None:
    invoice = db.execute(select(SaleInvoice).where(SaleInvoice.id == row.invoice_id).with_for_update()).scalar_one_or_none() if row.invoice_id else None
    if invoice and (invoice.paid_paise or invoice.status == "partially_paid"):
        raise HTTPException(409, "A paid scheduled renewal cannot be cancelled until refund support is available")
    if invoice and invoice.status in {"draft", "issued"}:
        void_unpaid_invoice(
            db,
            user,
            invoice,
            reason=f"Scheduled membership cancelled: {reason}",
            permission="gym.memberships.manage",
        )
    row.status = "cancelled"
    row.cancellation_reason = reason
    row.cancellation_requested_at = datetime.now(timezone.utc)
    row.cancellation_effective_on = local_today(db, user)[0]
    row.version += 1


def _align_scheduled_term(db: Session, user, current: Membership) -> None:
    scheduled = _scheduled_for_client(db, user, current.client_id, exclude_id=current.id)
    if not scheduled or scheduled.starts_on > current.ends_on:
        return
    term_length = scheduled.ends_on - scheduled.starts_on
    scheduled.starts_on = current.ends_on + timedelta(days=1)
    scheduled.ends_on = scheduled.starts_on + term_length
    scheduled.version += 1


@router.get("/summary")
def summary(location_id: str | None = None, user=Depends(require_permissions("gym.dashboard.view")), db: Session = Depends(get_db)):
    require_gym(db, user)
    return gym_summary(db, user, location_id)


@router.get("/plans")
def plans(user=Depends(require_permissions("gym.memberships.view")), db: Session = Depends(get_db)):
    require_gym(db, user)
    return [serialize(row) for row in db.execute(select(MembershipPlan).where(MembershipPlan.organization_id == user.organization_id, MembershipPlan.is_active.is_(True)).order_by(MembershipPlan.name)).scalars()]


@router.get("/membership-quote")
def membership_quote(
    plan_id: str,
    client_id: str | None = None,
    kind: Literal["activation", "renewal"] = "activation",
    interstate: bool = False,
    user=Depends(require_permissions("gym.memberships.view")),
    db: Session = Depends(get_db),
):
    require_gym(db, user)
    plan = tenant_get(db, MembershipPlan, plan_id, user)
    include_joining_fee = kind == "activation"
    if client_id:
        client = ensure_client_access(db, user, tenant_get(db, Client, client_id, user))
        has_history = bool(db.scalar(select(func.count(Membership.id)).where(
            Membership.organization_id == user.organization_id,
            Membership.client_id == client.id,
        )))
        include_joining_fee = include_joining_fee and not has_history
    return {
        **membership_invoice_quote(
            db,
            user,
            plan,
            include_joining_fee=include_joining_fee,
            interstate=interstate,
        ),
        "kind": kind,
        "duration_days": plan.duration_days,
        "joining_fee_applied": include_joining_fee and bool(plan.joining_fee_paise),
    }


@router.post("/plans", status_code=201)
def create_plan(body: PlanBody, user=Depends(require_permissions("gym.memberships.manage")), db: Session = Depends(get_db)):
    require_gym(db, user)
    duplicate = db.scalar(select(func.count(MembershipPlan.id)).where(
        MembershipPlan.organization_id == user.organization_id,
        func.lower(MembershipPlan.name) == body.name.strip().lower(),
        MembershipPlan.is_active.is_(True),
    )) or 0
    if duplicate:
        raise HTTPException(409, "An active membership plan already uses this name")
    row = MembershipPlan(organization_id=user.organization_id, **body.model_dump())
    db.add(row); db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="membership_plan.create", resource_type="membership_plan", resource_id=row.id, permission="gym.memberships.manage")
    db.commit(); db.refresh(row); return serialize(row)


@router.get("/memberships")
def memberships(location_id: str | None = None, status_filter: str | None = None, user=Depends(require_permissions("gym.memberships.view")), db: Session = Depends(get_db)):
    require_gym(db, user)
    return membership_directory(db, user, location_id, status_filter)


@router.post("/memberships", status_code=201)
def create_membership(body: MembershipBody, user=Depends(require_permissions("gym.memberships.manage")), db: Session = Depends(get_db)):
    require_gym(db, user)
    ensure_location(db, user, body.location_id)
    client = ensure_client_access(db, user, tenant_get(db, Client, body.client_id, user))
    plan = tenant_get(db, MembershipPlan, body.plan_id, user)
    idempotency_key = body.idempotency_key or f"membership:{uuid4()}"
    existing_invoice = db.execute(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
    if existing_invoice:
        existing_membership = db.execute(select(Membership).where(Membership.invoice_id == existing_invoice.id)).scalar_one_or_none()
        if not existing_membership or existing_membership.client_id != client.id:
            raise HTTPException(409, "This idempotency key belongs to another checkout")
        payment = db.execute(select(SalePayment).where(SalePayment.invoice_id == existing_invoice.id).order_by(SalePayment.created_at.desc())).scalars().first()
        return _membership_response(db, user, existing_membership, payment)

    db.execute(select(Client.id).where(Client.id == client.id).with_for_update()).scalar_one()
    reconcile_memberships(db, user, client_id=client.id, lock=True)
    existing_term = db.execute(select(Membership).where(
        Membership.organization_id == user.organization_id,
        Membership.client_id == client.id,
        Membership.status.in_(["active", "frozen", "scheduled"]),
    )).scalar_one_or_none()
    if existing_term:
        raise HTTPException(409, "Client already has a current or scheduled membership; use renewal instead")
    today = local_today(db, user)[0]
    if body.starts_on < today:
        raise HTTPException(422, "Membership start date cannot be in the past")
    history_count = int(db.scalar(select(func.count(Membership.id)).where(
        Membership.organization_id == user.organization_id,
        Membership.client_id == client.id,
    )) or 0)
    invoice, _, _ = create_membership_invoice(
        db,
        user,
        location_id=body.location_id,
        client_id=client.id,
        plan=plan,
        include_joining_fee=history_count == 0,
        interstate=body.interstate,
        idempotency_key=idempotency_key,
        notes=f"Membership activation: {plan.name}",
    )
    if body.amount_paise is not None and body.amount_paise != invoice.total_paise:
        raise HTTPException(409, "Membership amount changed; use the current authoritative quote")
    row = Membership(
        organization_id=user.organization_id, location_id=body.location_id, client_id=client.id, plan_id=plan.id,
        starts_on=body.starts_on, ends_on=body.starts_on + timedelta(days=plan.duration_days - 1),
        amount_paise=invoice.total_paise, status="active" if body.starts_on <= today else "scheduled",
        invoice_id=invoice.id,
    )
    db.add(row)
    db.flush()
    payment = _linked_payment(db, user, invoice, body, idempotency_key)
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="membership.create", resource_type="membership", resource_id=row.id, permission="gym.memberships.manage", changes={"plan_id": plan.id, "amount_paise": row.amount_paise, "invoice_id": invoice.id, "payment_option": body.payment_option})
    _queue_membership_update(db, user, client, plan, row, "Active" if row.status == "active" else "Scheduled")
    db.commit()
    db.refresh(row)
    return _membership_response(db, user, row, payment)


@router.post("/memberships/{membership_id}/freeze")
def freeze_membership(membership_id: str, body: FreezeBody, user=Depends(require_permissions("gym.memberships.manage")), db: Session = Depends(get_db)):
    row = membership_for_user(db, user, membership_id, lock=True)
    client = ensure_client_access(db, user, tenant_get(db, Client, row.client_id, user))
    if row.status != "active" or row.version != body.version or row.cancellation_effective_on: raise HTTPException(409, "Membership is not an editable active membership")
    if body.frozen_until < body.frozen_from: raise HTTPException(400, "Freeze end must be after start")
    today = local_today(db, user)[0]
    if body.frozen_until < today: raise HTTPException(422, "Freeze end cannot be in the past")
    row.status = "frozen"; row.frozen_from = body.frozen_from; row.frozen_until = body.frozen_until; row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="membership.freeze", resource_type="membership", resource_id=row.id, permission="gym.memberships.manage", changes={"frozen_from": str(body.frozen_from), "frozen_until": str(body.frozen_until)})
    _queue_membership_update(db, user, client, tenant_get(db, MembershipPlan, row.plan_id, user), row, f"Frozen until {body.frozen_until.strftime('%d %b %Y')}")
    db.commit(); return serialize(row)


@router.post("/memberships/{membership_id}/resume")
def resume_membership(membership_id: str, user=Depends(require_permissions("gym.memberships.manage")), db: Session = Depends(get_db)):
    row = membership_for_user(db, user, membership_id, lock=True)
    client = ensure_client_access(db, user, tenant_get(db, Client, row.client_id, user))
    if row.status != "frozen": raise HTTPException(409, "Membership is not frozen")
    if row.frozen_from and row.frozen_until:
        today = local_today(db, user)[0]
        actual_frozen_until = min(today, row.frozen_until)
        row.ends_on += max(actual_frozen_until - row.frozen_from, timedelta(0))
        _align_scheduled_term(db, user, row)
    row.status = "active"; row.frozen_from = None; row.frozen_until = None; row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="membership.resume", resource_type="membership", resource_id=row.id, permission="gym.memberships.manage")
    _queue_membership_update(db, user, client, tenant_get(db, MembershipPlan, row.plan_id, user), row, "Active")
    db.commit(); return serialize(row)


@router.post("/memberships/{membership_id}/cancel")
def cancel_membership(membership_id: str, body: CancelBody, user=Depends(require_permissions("gym.memberships.manage")), db: Session = Depends(get_db)):
    row = membership_for_user(db, user, membership_id, lock=True)
    client = ensure_client_access(db, user, tenant_get(db, Client, row.client_id, user))
    if row.status not in {"active", "frozen", "scheduled"} or row.version != body.version:
        raise HTTPException(409, "Membership changed or cannot be cancelled")
    reason = " ".join(body.reason.split())
    scheduled = _scheduled_for_client(db, user, row.client_id, exclude_id=row.id)
    if body.cancel_scheduled_renewal and scheduled:
        _cancel_scheduled_term(db, user, scheduled, reason)

    previous_status = row.status
    effective_timing = body.timing
    if row.status == "scheduled":
        _cancel_scheduled_term(db, user, row, reason)
        effective_timing = "now"
    elif body.timing == "term_end":
        row.cancellation_reason = reason
        row.cancellation_requested_at = datetime.now(timezone.utc)
        row.cancellation_effective_on = row.ends_on + timedelta(days=1)
        row.version += 1
    else:
        row.status = "cancelled"
        row.cancellation_reason = reason
        row.cancellation_requested_at = datetime.now(timezone.utc)
        row.cancellation_effective_on = local_today(db, user)[0]
        row.version += 1
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="membership.cancel",
        resource_type="membership",
        resource_id=row.id,
        permission="gym.memberships.manage",
        changes={
            "from_status": previous_status,
            "timing": effective_timing,
            "effective_on": str(row.cancellation_effective_on),
            "reason": reason,
            "scheduled_renewal_cancelled": bool(scheduled and body.cancel_scheduled_renewal),
        },
    )
    status_label = "Cancellation scheduled" if effective_timing == "term_end" else "Cancelled"
    _queue_membership_update(db, user, client, tenant_get(db, MembershipPlan, row.plan_id, user), row, status_label)
    db.commit()
    return _membership_response(db, user, row)


@router.post("/memberships/{membership_id}/cancellation/revoke")
def revoke_membership_cancellation(
    membership_id: str,
    body: CancellationRevokeBody,
    user=Depends(require_permissions("gym.memberships.manage")),
    db: Session = Depends(get_db),
):
    row = membership_for_user(db, user, membership_id, lock=True)
    today = local_today(db, user)[0]
    if row.version != body.version:
        raise HTTPException(409, "Membership changed since you opened it")
    if row.status not in {"active", "frozen"} or not row.cancellation_effective_on or row.cancellation_effective_on <= today:
        raise HTTPException(409, "This cancellation can no longer be reversed")
    previous_effective_on = row.cancellation_effective_on
    row.cancellation_reason = None
    row.cancellation_requested_at = None
    row.cancellation_effective_on = None
    row.version += 1
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="membership.cancellation_revoke",
        resource_type="membership",
        resource_id=row.id,
        permission="gym.memberships.manage",
        changes={"previous_effective_on": str(previous_effective_on)},
    )
    db.commit()
    return _membership_response(db, user, row)


@router.post("/memberships/{membership_id}/renew", status_code=201)
def renew_membership(
    membership_id: str,
    body: RenewalBody | None = None,
    plan_id: str | None = None,
    user=Depends(require_permissions("gym.memberships.manage")),
    db: Session = Depends(get_db),
):
    body = body or RenewalBody(plan_id=plan_id)
    old = membership_for_user(db, user, membership_id, lock=True)
    client = ensure_client_access(db, user, tenant_get(db, Client, old.client_id, user))
    if old.status not in {"active", "frozen", "expired", "renewed", "cancelled"}:
        raise HTTPException(409, "This membership cannot be renewed")
    if old.cancellation_effective_on:
        raise HTTPException(409, "Reverse the pending cancellation before renewing this membership")
    plan = tenant_get(db, MembershipPlan, body.plan_id or plan_id or old.plan_id, user)
    idempotency_key = body.idempotency_key or f"membership-renewal:{uuid4()}"
    existing_invoice = db.execute(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
    if existing_invoice:
        existing_membership = db.execute(select(Membership).where(Membership.invoice_id == existing_invoice.id)).scalar_one_or_none()
        if not existing_membership or existing_membership.client_id != old.client_id:
            raise HTTPException(409, "This idempotency key belongs to another checkout")
        payment = db.execute(select(SalePayment).where(SalePayment.invoice_id == existing_invoice.id).order_by(SalePayment.created_at.desc())).scalars().first()
        return _membership_response(db, user, existing_membership, payment)
    if _scheduled_for_client(db, user, old.client_id):
        raise HTTPException(409, "Client already has a scheduled renewal")
    current = db.execute(select(Membership).where(
        Membership.organization_id == user.organization_id,
        Membership.client_id == old.client_id,
        Membership.status.in_(["active", "frozen"]),
    ).with_for_update()).scalar_one_or_none()
    if current and current.id != old.id:
        raise HTTPException(409, "Renew the client's current membership instead")
    today = local_today(db, user)[0]
    starts = old.ends_on + timedelta(days=1) if old.status in {"active", "frozen"} else today
    status_value = "scheduled" if starts > today else "active"
    invoice, _, _ = create_membership_invoice(
        db,
        user,
        location_id=old.location_id,
        client_id=old.client_id,
        plan=plan,
        include_joining_fee=False,
        interstate=body.interstate,
        idempotency_key=idempotency_key,
        notes=f"Membership renewal: {plan.name}",
    )
    row = Membership(
        organization_id=user.organization_id,
        location_id=old.location_id,
        client_id=old.client_id,
        plan_id=plan.id,
        starts_on=starts,
        ends_on=starts + timedelta(days=plan.duration_days - 1),
        amount_paise=invoice.total_paise,
        status=status_value,
        invoice_id=invoice.id,
        previous_membership_id=old.id,
    )
    if old.status == "expired" and status_value == "active":
        old.status = "renewed"
        old.version += 1
    db.add(row)
    db.flush()
    payment = _linked_payment(db, user, invoice, body, idempotency_key)
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="membership.renew", resource_type="membership", resource_id=row.id, permission="gym.memberships.manage", changes={"previous_membership_id": old.id, "plan_id": plan.id, "invoice_id": invoice.id, "payment_option": body.payment_option, "status": status_value})
    _queue_membership_update(db, user, client, plan, row, "Scheduled renewal" if status_value == "scheduled" else "Renewed")
    db.commit()
    db.refresh(row)
    return _membership_response(db, user, row, payment)


@router.post("/check-ins", status_code=201)
def check_in(body: CheckInBody, user=Depends(require_permissions("gym.attendance.mark")), db: Session = Depends(get_db)):
    require_gym(db, user); ensure_location(db, user, body.location_id)
    membership = membership_for_user(db, user, body.membership_id, lock=True)
    ensure_client_access(db, user, tenant_get(db, Client, membership.client_id, user))
    if membership.location_id != body.location_id: raise HTTPException(422, "Membership belongs to another location")
    today = local_today(db, user)[0]
    if membership.status != "active" or not (membership.starts_on <= today <= membership.ends_on): raise HTTPException(409, "Membership is not active today")
    open_visit = db.execute(select(GymCheckIn).where(GymCheckIn.organization_id == user.organization_id, GymCheckIn.client_id == membership.client_id, GymCheckIn.checked_out_at.is_(None))).scalar_one_or_none()
    if open_visit: raise HTTPException(409, "Member is already checked in")
    row = GymCheckIn(organization_id=user.organization_id, location_id=body.location_id, membership_id=membership.id, client_id=membership.client_id, checked_in_at=datetime.now(timezone.utc), method=body.method, source="gym_operations", recorded_by_user_id=user.id)
    db.add(row); db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="gym.check_in", resource_type="gym_check_in", resource_id=row.id, permission="gym.attendance.mark", changes={"source": row.source})
    db.commit(); db.refresh(row); return serialize(row)


@router.get("/check-ins")
def list_check_ins(location_id: str | None = None, user=Depends(require_permissions("gym.attendance.view")), db: Session = Depends(get_db)):
    require_gym(db, user)
    return checkin_directory(db, user, location_id)


@router.post("/check-ins/{checkin_id}/checkout")
def check_out(checkin_id: str, user=Depends(require_permissions("gym.attendance.mark")), db: Session = Depends(get_db)):
    existing = tenant_get(db, GymCheckIn, checkin_id, user, location_field="location_id")
    row = db.execute(select(GymCheckIn).where(GymCheckIn.id == existing.id).with_for_update()).scalar_one()
    ensure_client_access(db, user, tenant_get(db, Client, row.client_id, user))
    if row.checked_out_at: raise HTTPException(409, "Member is already checked out")
    row.checked_out_at = datetime.now(timezone.utc); row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="gym.check_out", resource_type="gym_check_in", resource_id=row.id, permission="gym.attendance.mark")
    db.commit(); return serialize(row)


@router.post("/trainers", status_code=201)
def assign_trainer(body: TrainerBody, user=Depends(require_permissions("gym.coaching.manage")), db: Session = Depends(get_db)):
    client = ensure_client_access(db, user, tenant_get(db, Client, body.client_id, user)); tenant_get(db, Employee, body.trainer_employee_id, user)
    db.execute(select(Client.id).where(Client.id == client.id).with_for_update()).scalar_one()
    current = db.execute(select(TrainerAssignment).where(
        TrainerAssignment.organization_id == user.organization_id,
        TrainerAssignment.client_id == body.client_id,
        TrainerAssignment.status == "active",
    ).with_for_update()).scalars().all()
    for assignment in current:
        assignment.status = "reassigned"
        assignment.ends_on = body.starts_on - timedelta(days=1)
    row = TrainerAssignment(organization_id=user.organization_id, **body.model_dump()); db.add(row); db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="trainer.assign", resource_type="trainer_assignment", resource_id=row.id, permission="gym.coaching.manage", changes={"client_id": body.client_id, "trainer_employee_id": body.trainer_employee_id})
    db.commit(); db.refresh(row); return serialize(row)


@router.get("/coaching")
def coaching(section: str = "trainers", client_id: str | None = None, user=Depends(require_permissions("gym.coaching.view")), db: Session = Depends(get_db)):
    require_gym(db, user)
    return coaching_directory(db, user, section, client_id)


@router.post("/measurements", status_code=201)
def add_measurement(body: MeasurementBody, user=Depends(require_permissions("gym.measurements.manage")), db: Session = Depends(get_db)):
    ensure_client_access(db, user, tenant_get(db, Client, body.client_id, user)); row = FitnessMeasurement(organization_id=user.organization_id, **body.model_dump())
    db.add(row); db.flush(); log_action(db, organization_id=user.organization_id, user_id=user.id, action="measurement.create", resource_type="fitness_measurement", resource_id=row.id, permission="gym.measurements.manage")
    db.commit(); db.refresh(row); return serialize(row)


@router.post("/workouts", status_code=201)
def add_workout(body: WorkoutBody, user=Depends(require_permissions("gym.workouts.manage")), db: Session = Depends(get_db)):
    ensure_client_access(db, user, tenant_get(db, Client, body.client_id, user))
    if body.trainer_employee_id: tenant_get(db, Employee, body.trainer_employee_id, user)
    row = WorkoutPlan(organization_id=user.organization_id, **body.model_dump()); db.add(row); db.flush(); log_action(db, organization_id=user.organization_id, user_id=user.id, action="workout_plan.create", resource_type="workout_plan", resource_id=row.id, permission="gym.workouts.manage")
    db.commit(); db.refresh(row); return serialize(row)


@router.post("/diets", status_code=201)
def add_diet(body: DietBody, user=Depends(require_permissions("gym.diets.manage")), db: Session = Depends(get_db)):
    ensure_client_access(db, user, tenant_get(db, Client, body.client_id, user)); row = DietPlan(organization_id=user.organization_id, **body.model_dump())
    db.add(row); db.flush(); log_action(db, organization_id=user.organization_id, user_id=user.id, action="diet_plan.create", resource_type="diet_plan", resource_id=row.id, permission="gym.diets.manage")
    db.commit(); db.refresh(row); return serialize(row)


@router.get("/classes")
def list_classes(location_id: str | None = None, user=Depends(require_permissions("gym.classes.view")), db: Session = Depends(get_db)):
    require_gym(db, user)
    return class_directory(db, user, location_id)


@router.post("/classes", status_code=201)
def create_class(body: ClassBody, user=Depends(require_permissions("gym.classes.manage")), db: Session = Depends(get_db)):
    ensure_location(db, user, body.location_id)
    if body.trainer_employee_id:
        tenant_get(db, Employee, body.trainer_employee_id, user)
    if body.ends_at <= body.starts_at: raise HTTPException(400, "Class end must be after start")
    # A location may host simultaneous classes. Only an assigned trainer must
    # be protected from overlapping sessions until room-level booking exists.
    if body.trainer_employee_id:
        conflict = db.scalar(select(func.count(GymClass.id)).where(
            GymClass.organization_id == user.organization_id,
            GymClass.trainer_employee_id == body.trainer_employee_id,
            GymClass.status != "cancelled",
            GymClass.starts_at < body.ends_at,
            GymClass.ends_at > body.starts_at,
        )) or 0
        if conflict:
            raise HTTPException(409, "Trainer already has a class in this time slot")
    row = GymClass(organization_id=user.organization_id, **body.model_dump()); db.add(row); db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="gym_class.create", resource_type="gym_class", resource_id=row.id, permission="gym.classes.manage")
    db.commit(); db.refresh(row); return serialize(row)


@router.post("/classes/{class_id}/book", status_code=201)
def book_class(class_id: str, body: BookingBody, user=Depends(require_permissions("gym.classes.manage")), db: Session = Depends(get_db)):
    existing_class = tenant_get(db, GymClass, class_id, user, location_field="location_id")
    gym_class = db.execute(select(GymClass).where(GymClass.id == existing_class.id).with_for_update()).scalar_one()
    ensure_client_access(db, user, tenant_get(db, Client, body.client_id, user))
    duplicate = db.scalar(select(func.count(ClassBooking.id)).where(
        ClassBooking.gym_class_id == class_id,
        ClassBooking.client_id == body.client_id,
        ClassBooking.status == "booked",
    )) or 0
    if duplicate: raise HTTPException(409, "Client is already booked into this class")
    booked = db.scalar(select(func.count(ClassBooking.id)).where(ClassBooking.gym_class_id == class_id, ClassBooking.status == "booked")) or 0
    if booked >= gym_class.capacity: raise HTTPException(409, "Class is full")
    row = ClassBooking(organization_id=user.organization_id, gym_class_id=class_id, client_id=body.client_id)
    db.add(row); db.flush(); log_action(db, organization_id=user.organization_id, user_id=user.id, action="gym_class.book", resource_type="class_booking", resource_id=row.id, permission="gym.classes.manage", changes={"class_id": class_id, "client_id": body.client_id})
    db.commit(); db.refresh(row); return serialize(row)


@router.get("/equipment")
def list_equipment(location_id: str | None = None, user=Depends(require_permissions("gym.equipment.view")), db: Session = Depends(get_db)):
    require_gym(db, user)
    return equipment_directory(db, user, location_id)


@router.post("/equipment", status_code=201)
def create_equipment(body: EquipmentBody, user=Depends(require_permissions("gym.equipment.manage")), db: Session = Depends(get_db)):
    ensure_location(db, user, body.location_id); row = Equipment(organization_id=user.organization_id, **body.model_dump())
    db.add(row); db.flush(); log_action(db, organization_id=user.organization_id, user_id=user.id, action="equipment.create", resource_type="equipment", resource_id=row.id, permission="gym.equipment.manage")
    db.commit(); db.refresh(row); return serialize(row)
