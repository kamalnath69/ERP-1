"""Typed, permission-checked, idempotent AI action registry."""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AIAction, Appointment, Client, Employee, GymCheckIn, Job, Membership,
    OutboundMessage, Organization, Task, TrainerAssignment, User,
)
from app.services.audit import log_action
from app.services.access_policy import college_policy_applies, resolve_policy_context
from app.services.business_access import ensure_client_access, ensure_location, enforce_plan_limit, tenant_get
from app.services.entitlements import entitlement_value
from app.services.rbac import user_has_permissions


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskPayload(StrictPayload):
    title: str = Field(min_length=1, max_length=250)
    description: str | None = None
    location_id: str | None = None
    client_id: str | None = None
    assigned_to_user_id: str | None = None
    due_at: datetime | None = None
    priority: str = "normal"


class ClientPayload(StrictPayload):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = ""
    phone: str | None = None
    email: str | None = None
    home_location_id: str | None = None
    notes: str | None = None
    whatsapp_consent: bool = False
    email_consent: bool = False


class AppointmentPayload(StrictPayload):
    location_id: str
    client_id: str
    starts_at: datetime
    ends_at: datetime
    employee_id: str | None = None
    service_id: str | None = None
    notes: str | None = None


class MessagePayload(StrictPayload):
    client_id: str
    body: str = Field(min_length=1, max_length=800)
    subject: str | None = None


class TrainerPayload(StrictPayload):
    client_id: str
    trainer_employee_id: str
    starts_on: date = Field(default_factory=date.today)


class CheckInPayload(StrictPayload):
    client_id: str
    membership_id: str
    location_id: str
    notes: str | None = None


@dataclass(frozen=True)
class ActionDefinition:
    permission: str
    risk: str
    payload_model: type[BaseModel]
    title: str
    execute: Callable
    undo: Callable | None = None


def _task(db, user, data, action):
    if data.location_id: ensure_location(db, user, data.location_id)
    if data.client_id: ensure_client_access(db, user, tenant_get(db, Client, data.client_id, user))
    row = Task(organization_id=user.organization_id, source="ai", **data.model_dump())
    db.add(row); db.flush()
    return {"resource_type": "task", "id": row.id}, {"resource_type": "task", "id": row.id}


def _client(db, user, data, action):
    count = db.scalar(select(func.count(Client.id)).where(Client.organization_id == user.organization_id)) or 0
    enforce_plan_limit(db, user, "clients", count)
    if data.home_location_id: ensure_location(db, user, data.home_location_id)
    row = Client(organization_id=user.organization_id, client_number=f"CLI-{count + 1:06d}", **data.model_dump())
    db.add(row); db.flush()
    return {"resource_type": "client", "id": row.id}, {"resource_type": "client", "id": row.id, "version": row.version}


def _appointment(db, user, data, action):
    ensure_location(db, user, data.location_id)
    ensure_client_access(db, user, tenant_get(db, Client, data.client_id, user))
    if data.ends_at <= data.starts_at: raise HTTPException(400, "Appointment end must be after start")
    if data.employee_id:
        employee = tenant_get(db, Employee, data.employee_id, user)
        conflict = db.execute(select(Appointment.id).where(
            Appointment.organization_id == user.organization_id, Appointment.employee_id == employee.id,
            Appointment.status.notin_(["cancelled", "no_show"]), Appointment.starts_at < data.ends_at,
            Appointment.ends_at > data.starts_at,
        )).first()
        if conflict: raise HTTPException(409, "Employee has a conflicting appointment")
    row = Appointment(organization_id=user.organization_id, source="ai", **data.model_dump())
    db.add(row); db.flush()
    return {"resource_type": "appointment", "id": row.id}, {"resource_type": "appointment", "id": row.id, "version": row.version}


def _message(db, user, data, action):
    from app.core.config import settings
    client = ensure_client_access(db, user, tenant_get(db, Client, data.client_id, user))
    if not client.whatsapp_consent or not client.phone:
        raise HTTPException(409, "WhatsApp consent and phone are required")
    organization = db.get(Organization, user.organization_id)
    row = OutboundMessage(
        organization_id=user.organization_id, location_id=client.home_location_id, client_id=client.id,
        channel="whatsapp", recipient=client.phone, template=settings.WHATSAPP_TEMPLATE_CLIENT_UPDATE,
        template_language=settings.WHATSAPP_TEMPLATE_LANGUAGE,
        template_variables=[client.first_name, data.body, organization.name], subject=data.subject,
        body=data.body, idempotency_key=action.idempotency_key, scheduled_for=datetime.now(timezone.utc),
    )
    db.add(row); db.flush()
    db.add(Job(organization_id=user.organization_id, kind="send_message", payload={"message_id": row.id},
               run_at=datetime.now(timezone.utc), idempotency_key=f"send-{row.id}"))
    return {"resource_type": "outbound_message", "id": row.id, "status": "queued"}, None


def _trainer(db, user, data, action):
    ensure_client_access(db, user, tenant_get(db, Client, data.client_id, user))
    tenant_get(db, Employee, data.trainer_employee_id, user)
    db.query(TrainerAssignment).filter(
        TrainerAssignment.organization_id == user.organization_id,
        TrainerAssignment.client_id == data.client_id,
        TrainerAssignment.status == "active",
    ).update({TrainerAssignment.status: "inactive", TrainerAssignment.ends_on: date.today()})
    row = TrainerAssignment(organization_id=user.organization_id, **data.model_dump())
    db.add(row); db.flush()
    return {"resource_type": "trainer_assignment", "id": row.id}, None


def _check_in(db, user, data, action):
    ensure_location(db, user, data.location_id)
    ensure_client_access(db, user, tenant_get(db, Client, data.client_id, user))
    membership = tenant_get(db, Membership, data.membership_id, user, location_field="location_id")
    if membership.client_id != data.client_id or membership.status != "active":
        raise HTTPException(409, "An active membership is required")
    open_visit = db.execute(select(GymCheckIn).where(
        GymCheckIn.organization_id == user.organization_id, GymCheckIn.client_id == data.client_id,
        GymCheckIn.checked_out_at.is_(None),
    )).scalar_one_or_none()
    if open_visit: raise HTTPException(409, "Client is already checked in")
    row = GymCheckIn(organization_id=user.organization_id, checked_in_at=datetime.now(timezone.utc),
                     recorded_by_user_id=user.id, source="ai", method="staff", **data.model_dump())
    db.add(row); db.flush()
    return {"resource_type": "gym_check_in", "id": row.id}, {"resource_type": "gym_check_in", "id": row.id, "version": row.version}


def _undo(db, user, payload):
    kind, row_id = payload["resource_type"], payload["id"]
    models = {"task": Task, "client": Client, "appointment": Appointment,
              "trainer_assignment": TrainerAssignment, "gym_check_in": GymCheckIn}
    row = tenant_get(db, models[kind], row_id, user)
    expected = payload.get("version")
    if expected is not None and getattr(row, "version", expected) != expected:
        raise HTTPException(409, "This record changed after the AI action and cannot be undone safely")
    if kind == "task": db.delete(row)
    elif kind == "client": row.status = "inactive"; row.version += 1
    elif kind == "appointment": row.status = "cancelled"; row.version += 1
    elif kind == "trainer_assignment": row.status = "inactive"; row.ends_on = date.today()
    elif kind == "gym_check_in":
        if row.checked_out_at: raise HTTPException(409, "A completed visit cannot be undone")
        db.delete(row)
    return {"resource_type": kind, "id": row_id, "undone": True}


ACTION_REGISTRY = {
    "create_task": ActionDefinition("dashboard.view", "low", TaskPayload, "Create a task", _task, _undo),
    "create_client": ActionDefinition("clients.manage", "low", ClientPayload, "Create a client", _client, _undo),
    "schedule_appointment": ActionDefinition("appointments.manage", "low", AppointmentPayload, "Schedule an appointment", _appointment, _undo),
    "assign_trainer": ActionDefinition("gym.coaching.manage", "low", TrainerPayload, "Assign a trainer", _trainer),
    "check_in": ActionDefinition("gym.attendance.mark", "low", CheckInPayload, "Check in a member", _check_in, _undo),
    "send_message": ActionDefinition("notifications.send", "high", MessagePayload, "Send a client message", _message),
}


def prepare_action(
    db: Session,
    user: User,
    action_type: str,
    payload: dict,
    conversation_id: str | None,
    *,
    idempotency_key: str | None = None,
) -> dict:
    if not user_has_permissions(db, user, ["ai.actions"]):
        return {"access_denied": True, "message": "AI-assisted actions are not included in your access."}
    if not entitlement_value(db, db.get(Organization, user.organization_id), "ai.actions", False):
        return {"access_denied": True, "message": "AI-assisted actions are not included in the current plan."}
    definition = ACTION_REGISTRY.get(action_type)
    if not definition: return {"error": "This action is not supported"}
    if not user_has_permissions(db, user, [definition.permission]):
        return {"access_denied": True, "message": "You do not have permission to perform this action."}
    try: validated = definition.payload_model.model_validate(payload)
    except Exception as exc: return {"error": str(exc)}
    normalized_payload = validated.model_dump(mode="json")
    action_key = idempotency_key or f"ai-{secrets.token_hex(16)}"
    existing = db.execute(select(AIAction).where(
        AIAction.organization_id == user.organization_id,
        AIAction.idempotency_key == action_key,
    )).scalar_one_or_none()
    if existing:
        if (
            existing.user_id != user.id
            or existing.action_type != action_type
            or existing.payload != normalized_payload
        ):
            raise HTTPException(409, "That idempotency key was already used for a different action")
        if existing.status != "pending_confirmation":
            return serialize_action(existing)
        token = secrets.token_urlsafe(24)
        existing.confirmation_token_hash = hashlib.sha256(token.encode()).hexdigest()
        existing.confirmation_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        db.flush()
        return {**serialize_action(existing), "confirmation_token": token}

    now = datetime.now(timezone.utc); token = secrets.token_urlsafe(24)
    policy_context = resolve_policy_context(db, user) if college_policy_applies(db, user.organization_id) else None
    if policy_context and not policy_context.active:
        return {"access_denied": True, "message": "Your data access must be reviewed before using AI actions."}
    action = AIAction(
        organization_id=user.organization_id, user_id=user.id, conversation_id=conversation_id,
        action_type=action_type, risk_level=definition.risk, required_permission=definition.permission,
        preview={
            "title": definition.title,
            "changes": normalized_payload,
            "requires_confirmation": True,
            "access_version": user.access_version,
            "policy_version": policy_context.policy_version if policy_context else 0,
        },
        payload=normalized_payload, status="pending_confirmation",
        confirmation_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        confirmation_expires_at=now + timedelta(minutes=10),
        idempotency_key=action_key,
        access_version=user.access_version,
    )
    db.add(action); db.flush()
    return {**serialize_action(action), "confirmation_token": token}


def _execute(db, user, action, definition):
    if not user_has_permissions(db, user, [definition.permission]):
        raise HTTPException(403, "Your access changed and this action is no longer allowed")
    if college_policy_applies(db, user.organization_id):
        context = resolve_policy_context(db, user)
        expected_access_version = (action.preview or {}).get("access_version")
        expected_policy_version = (action.preview or {}).get("policy_version", 0)
        if (
            not context.active
            or context.policy_version != expected_policy_version
            or expected_access_version != user.access_version
        ):
            raise HTTPException(409, "Your access changed. Review and create this action again.")
    elif action.access_version != user.access_version:
        raise HTTPException(409, "Your access changed. Review and create this action again.")
    data = definition.payload_model.model_validate(action.payload)
    return definition.execute(db, user, data, action)


def confirm_action(db: Session, user: User, action: AIAction, token: str | None) -> dict:
    if action.user_id != user.id: raise HTTPException(403, "This action belongs to another user")
    if action.status == "completed": return serialize_action(action)
    if action.status != "pending_confirmation": raise HTTPException(409, f"Action is {action.status}")
    now = datetime.now(timezone.utc)
    if not token or hashlib.sha256(token.encode()).hexdigest() != action.confirmation_token_hash:
        raise HTTPException(403, "Invalid confirmation")
    if not action.confirmation_expires_at or action.confirmation_expires_at < now:
        raise HTTPException(410, "Confirmation has expired")
    definition = ACTION_REGISTRY[action.action_type]
    result, undo_payload = _execute(db, user, action, definition)
    action.status = "completed"; action.result = result; action.executed_at = now; action.undo_payload = undo_payload
    if undo_payload:
        action.undo_expires_at = now + timedelta(seconds=30)
    log_action(db, organization_id=user.organization_id, user_id=user.id, action=f"ai_action.{action.action_type}",
               resource_type="ai_action", resource_id=action.id, changes=action.payload)
    return serialize_action(action)


def undo_action(db: Session, user: User, action: AIAction) -> dict:
    now = datetime.now(timezone.utc)
    if action.user_id != user.id: raise HTTPException(403, "This action belongs to another user")
    if action.status != "completed" or not action.undo_payload or action.undone_at:
        raise HTTPException(409, "This action cannot be undone")
    if not action.undo_expires_at or action.undo_expires_at < now:
        raise HTTPException(410, "The undo period has ended")
    definition = ACTION_REGISTRY[action.action_type]
    if not user_has_permissions(db, user, [definition.permission]): raise HTTPException(403, "Access denied")
    result = definition.undo(db, user, action.undo_payload)
    action.status = "undone"; action.undone_at = now; action.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action=f"ai_action.undo.{action.action_type}",
               resource_type="ai_action", resource_id=action.id, changes=action.undo_payload)
    return {**serialize_action(action), "result": result}


def serialize_action(action):
    return {"action_id": action.id, "status": action.status, "risk_level": action.risk_level,
            "preview": action.preview, "result": action.result, "undo_expires_at": action.undo_expires_at}
