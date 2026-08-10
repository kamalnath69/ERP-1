"""Role-aware client workspaces, relationship memory, signals, media, and progress."""
import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.business import serialize
from app.core.config import ROOT_DIR, settings
from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    Allergy, Appointment, AuditLog, CatalogItem, ClientCommitment, ClientMemory, ClientSignal,
    CoachingNote, Client, ClientMedia, CollegeAssessment, CollegeAssessmentScore,
    CollegeAttendanceRecord, CollegeAttendanceSession, CollegeCohort, CollegeCourse,
    CollegeCourseOffering, CollegeDepartment, CollegeProgram, CollegeStudentProfile,
    CollegeTerm, DietPlan, Document, Employee, Encounter, FitnessGoal,
    FitnessMeasurement, GymCheckIn, Job, LabOrder, Location, Membership,
    MembershipPlan, Organization, PatientProfile, Prescription, SaleInvoice,
    SaleLine, SalePayment, SalonClientProfile, TrainerAssignment, User, Vital,
    WorkoutPlan, WorkoutSession,
)
from app.services.audit import log_action
from app.services.business_access import ensure_client_access, ensure_location, filter_clients, filter_locations, tenant_get
from app.services.rbac import get_user_permissions, get_user_roles
from app.services.gym import local_today, reconcile_memberships
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size

router = APIRouter(tags=["client-intelligence"])
STORAGE_DIR = ROOT_DIR / "storage"
MEDIA_TYPES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "video/mp4": ".mp4", "video/webm": ".webm",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/webm"}
MEMORY_VISIBILITY = {"team", "managers", "assigned_staff", "author_only", "clinical"}


class MemoryBody(BaseModel):
    category: str = Field(min_length=2, max_length=50)
    label: str = Field(min_length=2, max_length=120)
    value: str = Field(min_length=1, max_length=5000)
    visibility: str = "team"


class MemoryUpdate(MemoryBody):
    version: int


class CommitmentBody(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    description: str | None = None
    owner_user_id: str | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None


class CommitmentUpdate(BaseModel):
    status: str = Field(pattern="^(open|completed|cancelled)$")
    completion_note: str | None = None
    version: int


class SignalUpdate(BaseModel):
    action: str = Field(pattern="^(assign|snooze|resolve|dismiss|reopen)$")
    assigned_to_user_id: str | None = None
    snoozed_until: datetime | None = None
    note: str | None = None
    version: int


class GoalBody(BaseModel):
    metric_key: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=2, max_length=160)
    baseline_value: float | None = None
    target_value: float
    current_value: float | None = None
    unit: str = Field(min_length=1, max_length=40)
    starts_on: date = Field(default_factory=date.today)
    target_on: date | None = None


class GoalUpdate(BaseModel):
    current_value: float | None = None
    status: str | None = Field(default=None, pattern="^(active|completed|cancelled)$")
    version: int


class SessionBody(BaseModel):
    location_id: str
    workout_plan_id: str | None = None
    trainer_employee_id: str | None = None
    scheduled_for: datetime
    status: str = Field(default="planned", pattern="^(planned|in_progress|completed|skipped)$")
    exercise_results: list[dict] = []
    effort_rating: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = None


class SessionUpdate(BaseModel):
    status: str = Field(pattern="^(planned|in_progress|completed|skipped)$")
    exercise_results: list[dict] | None = None
    effort_rating: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = None
    version: int


class CoachingBody(BaseModel):
    trainer_employee_id: str | None = None
    note: str = Field(min_length=2, max_length=5000)
    visibility: str = "assigned_staff"


class SalonProfileBody(BaseModel):
    preferred_employee_id: str | None = None
    preferred_services: list[str] = []
    preferences: dict = {}
    sensitivities: str | None = None
    formulas: str | None = None
    visit_interval_days: int | None = Field(default=None, ge=1, le=730)
    version: int | None = None


class CheckInBody(BaseModel):
    location_id: str
    notes: str | None = None


class CheckInCorrection(BaseModel):
    checked_in_at: datetime
    checked_out_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)
    version: int


class ClientQuestion(BaseModel):
    message: str = Field(min_length=1, max_length=3000)


def _client(db: Session, user: User, client_id: str) -> Client:
    row = tenant_get(db, Client, client_id, user)
    return ensure_client_access(db, user, row)


def _role_slugs(db: Session, user: User) -> set[str]:
    return {role.slug for role in get_user_roles(db, user)}


def _employee_for_user(db: Session, user: User):
    return db.execute(select(Employee).where(Employee.organization_id == user.organization_id, Employee.user_id == user.id)).scalar_one_or_none()


def _is_actually_assigned(db: Session, user: User, client_id: str) -> bool:
    employee = _employee_for_user(db, user)
    if not employee:
        return False
    if db.execute(select(TrainerAssignment.id).where(TrainerAssignment.organization_id == user.organization_id, TrainerAssignment.client_id == client_id, TrainerAssignment.trainer_employee_id == employee.id, TrainerAssignment.status == "active")).first():
        return True
    if db.execute(select(Appointment.id).where(Appointment.organization_id == user.organization_id, Appointment.client_id == client_id, Appointment.employee_id == employee.id)).first():
        return True
    patient = db.execute(select(PatientProfile).where(PatientProfile.organization_id == user.organization_id, PatientProfile.client_id == client_id)).scalar_one_or_none()
    return bool(patient and db.execute(select(Encounter.id).where(Encounter.patient_id == patient.id, Encounter.practitioner_employee_id == employee.id)).first())


def _visible_memories(db: Session, user: User, client_id: str, permissions: set[str], roles: set[str]):
    if "client_memory.view" not in permissions:
        return []
    rows = db.execute(select(ClientMemory).where(ClientMemory.organization_id == user.organization_id, ClientMemory.client_id == client_id, ClientMemory.is_active.is_(True)).order_by(ClientMemory.updated_at.desc())).scalars().all()
    assigned = _is_actually_assigned(db, user, client_id)
    visible = []
    for row in rows:
        if row.visibility == "team": visible.append(row)
        elif row.visibility == "managers" and ({"owner", "manager"} & roles or "client_memory.manage" in permissions): visible.append(row)
        elif row.visibility == "assigned_staff" and (assigned or {"owner", "manager"} & roles): visible.append(row)
        elif row.visibility == "author_only" and row.created_by_user_id == user.id: visible.append(row)
        elif row.visibility == "clinical" and "clinical.view" in permissions: visible.append(row)
    return visible


def _json_safe_evidence(value):
    """Normalize database-native values before writing explainable evidence to JSONB."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_evidence(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_evidence(item) for item in value]
    return value


def _signal(db: Session, client: Client, signal_type: str, state: str, title: str, explanation: str, evidence: list, action: str | None):
    now = datetime.now(timezone.utc)
    evidence = _json_safe_evidence(evidence)
    row = db.execute(select(ClientSignal).where(ClientSignal.client_id == client.id, ClientSignal.signal_type == signal_type, ClientSignal.rule_version == "v1")).scalar_one_or_none()
    if not row:
        row = ClientSignal(organization_id=client.organization_id, location_id=client.home_location_id, client_id=client.id, signal_type=signal_type, pulse_state=state, title=title, explanation=explanation, evidence=evidence, recommended_action=action, generated_at=now, rule_version="v1")
        db.add(row)
    elif row.status not in {"resolved", "dismissed"}:
        row.pulse_state = state; row.title = title; row.explanation = explanation; row.evidence = evidence; row.recommended_action = action; row.generated_at = now; row.version += 1
    return row


def _refresh_signals(db: Session, user: User, client: Client, industry: str):
    active_types = set()
    now = datetime.now(timezone.utc)
    scoped_invoices = filter_locations(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.client_id == client.id,
        SaleInvoice.status.notin_(["void", "refunded"]),
    ), SaleInvoice, db, user).subquery()
    outstanding = int(db.scalar(select(func.coalesce(func.sum(scoped_invoices.c.total_paise - scoped_invoices.c.paid_paise), 0))) or 0)
    if outstanding > 0:
        active_types.add("outstanding_balance")
        _signal(db, client, "outstanding_balance", "watch", "Payment needs follow-up", f"INR {outstanding / 100:,.0f} remains unpaid.", [{"metric": "outstanding_paise", "value": outstanding}], "Review invoices or record payment")

    overdue = db.scalar(select(func.count(ClientCommitment.id)).where(ClientCommitment.client_id == client.id, ClientCommitment.status == "open", ClientCommitment.due_at < now)) or 0
    if overdue:
        active_types.add("overdue_commitment")
        _signal(db, client, "overdue_commitment", "action_needed", "A promise is overdue", f"{overdue} client commitment{'s are' if overdue != 1 else ' is'} past due.", [{"metric": "overdue_commitments", "value": overdue}], "Complete or reschedule the commitment")

    if client.date_of_birth:
        birthday = client.date_of_birth.replace(year=date.today().year)
        if birthday < date.today(): birthday = birthday.replace(year=date.today().year + 1)
        days = (birthday - date.today()).days
        if days <= 7:
            active_types.add("birthday")
            _signal(db, client, "birthday", "healthy", "Birthday coming up", f"Birthday is in {days} day{'s' if days != 1 else ''}.", [{"metric": "birthday", "value": birthday.isoformat()}], "Prepare a personal greeting")

    if industry == "gym":
        membership = db.execute(select(Membership).where(Membership.organization_id == user.organization_id, Membership.client_id == client.id, Membership.status.in_(["active", "frozen"])).order_by(Membership.ends_on.desc())).scalars().first()
        if membership:
            remaining = (membership.ends_on - date.today()).days
            if remaining <= 7:
                active_types.add("membership_expiry")
                _signal(db, client, "membership_expiry", "action_needed" if remaining <= 2 else "watch", "Membership renewal is near", f"The active membership expires in {max(remaining, 0)} days.", [{"metric": "days_remaining", "value": remaining}, {"record": "membership", "id": membership.id}], "Discuss renewal")
        current_start = now - timedelta(days=14); previous_start = now - timedelta(days=28)
        current = db.scalar(select(func.count(GymCheckIn.id)).where(GymCheckIn.client_id == client.id, GymCheckIn.checked_in_at >= current_start)) or 0
        previous = db.scalar(select(func.count(GymCheckIn.id)).where(GymCheckIn.client_id == client.id, GymCheckIn.checked_in_at >= previous_start, GymCheckIn.checked_in_at < current_start)) or 0
        if previous >= 3 and current <= previous / 2:
            active_types.add("attendance_drop")
            _signal(db, client, "attendance_drop", "watch", "Visit frequency has dropped", f"Check-ins changed from {previous} in the previous 14 days to {current} in the latest 14 days.", [{"metric": "previous_14_days", "value": previous}, {"metric": "latest_14_days", "value": current}], "Ask how training is going")
        stalled = db.scalar(select(func.count(FitnessGoal.id)).where(FitnessGoal.client_id == client.id, FitnessGoal.status == "active", FitnessGoal.target_on < date.today())) or 0
        if stalled:
            active_types.add("stalled_goal")
            _signal(db, client, "stalled_goal", "watch", "Fitness goal needs review", f"{stalled} active goal{'s have' if stalled != 1 else ' has'} passed the target date.", [{"metric": "stalled_goals", "value": stalled}], "Review the goal with the trainer")

    if industry == "salon":
        profile = db.execute(select(SalonClientProfile).where(SalonClientProfile.client_id == client.id)).scalar_one_or_none()
        completed = db.execute(select(Appointment).where(Appointment.client_id == client.id, Appointment.status == "completed").order_by(Appointment.completed_at.desc())).scalars().all()
        if completed:
            last_date = (completed[0].completed_at or completed[0].ends_at).date()
            interval = profile.visit_interval_days if profile and profile.visit_interval_days else 45
            gap = (date.today() - last_date).days
            if gap > interval + 7:
                active_types.add("rebooking_due")
                _signal(db, client, "rebooking_due", "watch", "Usual visit window has passed", f"Last visit was {gap} days ago; the expected interval is about {interval} days.", [{"metric": "days_since_visit", "value": gap}, {"metric": "usual_interval", "value": interval}], "Offer a relevant rebooking time")

    if industry == "clinic":
        patient = db.execute(select(PatientProfile).where(PatientProfile.client_id == client.id)).scalar_one_or_none()
        if patient:
            followups = db.scalar(select(func.count(Encounter.id)).where(Encounter.patient_id == patient.id, Encounter.follow_up_on < date.today())) or 0
            if followups:
                active_types.add("clinical_follow_up")
                _signal(db, client, "clinical_follow_up", "action_needed", "Clinical follow-up is due", f"{followups} documented follow-up{'s are' if followups != 1 else ' is'} due.", [{"metric": "due_followups", "value": followups}], "Review the care follow-up")

    rows = db.execute(select(ClientSignal).where(ClientSignal.client_id == client.id, ClientSignal.rule_version == "v1", ClientSignal.status.in_(["open", "snoozed"]))).scalars().all()
    for row in rows:
        if row.signal_type not in active_types and row.status == "open":
            row.status = "resolved"; row.resolved_at = now; row.resolution_note = "Condition no longer applies"; row.version += 1
    db.flush()


def _photo_media(db: Session, client_id: str):
    return db.execute(select(ClientMedia).where(ClientMedia.client_id == client_id, ClientMedia.is_profile.is_(True)).order_by(ClientMedia.updated_at.desc())).scalars().first()


def _common_data(db: Session, user: User, client: Client, start: datetime, *, include_sales: bool):
    appointments = db.execute(select(Appointment).where(Appointment.organization_id == user.organization_id, Appointment.client_id == client.id).order_by(Appointment.starts_at.desc()).limit(100)).scalars().all()
    sales_statement = filter_locations(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.client_id == client.id,
    ), SaleInvoice, db, user)
    sales = db.execute(sales_statement.order_by(SaleInvoice.created_at.desc()).limit(100)).scalars().all() if include_sales else []
    commitments = db.execute(select(ClientCommitment).where(ClientCommitment.organization_id == user.organization_id, ClientCommitment.client_id == client.id).order_by(ClientCommitment.created_at.desc()).limit(100)).scalars().all()
    return appointments, sales, commitments


def _sales_with_items(db: Session, organization_id: str, sales: list[SaleInvoice]) -> list[dict]:
    if not sales:
        return []
    invoice_ids = [sale.id for sale in sales]
    lines = db.execute(select(SaleLine).where(
        SaleLine.organization_id == organization_id,
        SaleLine.invoice_id.in_(invoice_ids),
    ).order_by(SaleLine.invoice_id, SaleLine.display_order, SaleLine.id)).scalars().all()
    by_invoice: dict[str, list[dict]] = {invoice_id: [] for invoice_id in invoice_ids}
    for line in lines:
        by_invoice[line.invoice_id].append({
            "id": line.id, "item_id": line.item_id, "name": line.item_name,
            "sku": line.sku, "quantity_milli": line.quantity_milli,
            "unit_price_paise": line.unit_price_paise,
            "discount_paise": line.discount_paise, "tax_paise": line.tax_paise,
            "total_paise": line.total_paise,
        })
    return [serialize(sale, {
        "items": by_invoice[sale.id],
        "item_names": [item["name"] for item in by_invoice[sale.id]],
        "item_count": len(by_invoice[sale.id]),
        "balance_paise": max(sale.total_paise - sale.paid_paise, 0),
        "voidable": sale.paid_paise == 0 and sale.status in {"draft", "issued"},
    }) for sale in sales]


def _billing_workspace(db: Session, user: User, client: Client, permissions: set[str]) -> dict:
    capabilities = {
        "view": "sales.view" in permissions,
        "record_payment": "payments.record" in permissions,
        "void_invoice": "sales.manage" in permissions,
    }
    if not capabilities["view"]:
        return {"summary": None, "open_invoices": [], "recent_invoices": [], "capabilities": capabilities}
    scoped_statement = filter_locations(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.client_id == client.id,
    ), SaleInvoice, db, user)
    scoped = scoped_statement.subquery()
    eligible = scoped.c.status.notin_(["void", "refunded"])
    invoice_count, invoiced, paid, outstanding = db.execute(select(
        func.coalesce(func.sum(case((eligible, 1), else_=0)), 0),
        func.coalesce(func.sum(case((eligible, scoped.c.total_paise), else_=0)), 0),
        func.coalesce(func.sum(case((eligible, scoped.c.paid_paise), else_=0)), 0),
        func.coalesce(func.sum(case((eligible, func.greatest(scoped.c.total_paise - scoped.c.paid_paise, 0)), else_=0)), 0),
    ).select_from(scoped)).one()
    open_statement = filter_locations(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.client_id == client.id,
        SaleInvoice.status.in_(["draft", "issued", "partially_paid"]),
        SaleInvoice.total_paise > SaleInvoice.paid_paise,
    ), SaleInvoice, db, user)
    open_rows = db.execute(open_statement.order_by(SaleInvoice.created_at.desc()).limit(100)).scalars().all()
    recent_statement = filter_locations(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.client_id == client.id,
    ), SaleInvoice, db, user)
    recent_rows = db.execute(recent_statement.order_by(SaleInvoice.created_at.desc()).limit(20)).scalars().all()
    return {
        "summary": {
            "invoice_count": int(invoice_count or 0),
            "invoiced_paise": int(invoiced or 0),
            "paid_paise": int(paid or 0),
            "outstanding_paise": int(outstanding or 0),
        },
        "open_invoices": _sales_with_items(db, user.organization_id, open_rows),
        "recent_invoices": _sales_with_items(db, user.organization_id, recent_rows),
        "capabilities": capabilities,
    }


def _briefing_role(roles: set[str], industry: str) -> str:
    priority = {
        "gym": ["trainer", "front-desk", "manager", "owner"],
        "salon": ["stylist", "front-desk", "manager", "owner"],
        "clinic": ["practitioner", "receptionist", "pharmacist", "manager", "owner"],
    }.get(industry, ["manager", "owner"])
    return next((role for role in priority if role in roles), next(iter(roles), "staff"))


def _role_brief(role: str, industry: str, metrics: dict, industry_data: dict) -> dict | None:
    if role in {"owner", "manager"}:
        return {
            "title": "Relationship and value context",
            "detail": f"Lifetime value is INR {metrics['lifetime_value_paise'] / 100:,.0f}; outstanding balance is INR {metrics['outstanding_paise'] / 100:,.0f}.",
            "evidence": [{"metric": "lifetime_value_paise", "value": metrics["lifetime_value_paise"]}, {"metric": "outstanding_paise", "value": metrics["outstanding_paise"]}],
            "tone": "context",
        }
    if industry == "gym" and role == "trainer":
        attendance = industry_data.get("attendance", {})
        goals = industry_data.get("goals", [])
        return {
            "title": "Training context",
            "detail": f"Recent frequency is {attendance.get('visits_per_week', 0)} visits per week with {len([goal for goal in goals if goal.get('status') == 'active'])} active goals.",
            "evidence": [{"metric": "visits_per_week", "value": attendance.get("visits_per_week", 0)}, {"metric": "active_goals", "value": len([goal for goal in goals if goal.get("status") == "active"])}],
            "tone": "context",
        }
    if industry == "gym" and role == "front-desk":
        membership = industry_data.get("active_membership")
        detail = "No active membership is available for check-in."
        evidence = []
        if membership:
            detail = f"Membership has {max(membership.get('days_remaining', 0), 0)} days remaining; the member is {'currently inside' if industry_data.get('open_checkin') else 'not checked in'}."
            evidence = [{"metric": "days_remaining", "value": membership.get("days_remaining")}, {"metric": "open_checkin", "value": bool(industry_data.get("open_checkin"))}]
        return {"title": "Front desk context", "detail": detail, "evidence": evidence, "tone": "context"}
    if industry == "salon" and role == "stylist":
        profile = industry_data.get("profile") or {}
        return {"title": "Service preference context", "detail": profile.get("formulas") or profile.get("sensitivities") or "No formula or sensitivity has been recorded yet.", "evidence": [{"record": "salon_profile", "id": profile.get("id")}] if profile else [], "tone": "context"}
    if industry == "clinic" and role in {"practitioner", "pharmacist"}:
        return {"title": "Authorized care context", "detail": f"{len(industry_data.get('allergies', []))} active allergies, {len(industry_data.get('prescriptions', []))} prescriptions, and {len(industry_data.get('labs', []))} lab orders are visible in your authorized scope.", "evidence": [{"metric": "active_allergies", "value": len(industry_data.get("allergies", []))}], "tone": "context"}
    return None


def _gym_workspace(db: Session, user: User, client: Client, start: datetime, permissions: set[str]):
    memberships = db.execute(select(Membership).where(Membership.organization_id == user.organization_id, Membership.client_id == client.id).order_by(Membership.created_at.desc())).scalars().all()
    plan_ids = {row.plan_id for row in memberships}
    plans = {row.id: row for row in db.execute(select(MembershipPlan).where(MembershipPlan.id.in_(plan_ids))).scalars()} if plan_ids else {}
    checkins = db.execute(select(GymCheckIn).where(GymCheckIn.organization_id == user.organization_id, GymCheckIn.client_id == client.id, GymCheckIn.checked_in_at >= start).order_by(GymCheckIn.checked_in_at.desc())).scalars().all() if "gym.attendance.view" in permissions else []
    assignments = db.execute(select(TrainerAssignment).where(TrainerAssignment.organization_id == user.organization_id, TrainerAssignment.client_id == client.id).order_by(TrainerAssignment.created_at.desc())).scalars().all()
    employee_ids = {row.trainer_employee_id for row in assignments}
    employees = {row.id: row for row in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars()} if employee_ids else {}
    measurements = db.execute(select(FitnessMeasurement).where(FitnessMeasurement.client_id == client.id).order_by(FitnessMeasurement.measured_on.desc()).limit(100)).scalars().all() if "gym.measurements.view" in permissions else []
    goals = db.execute(select(FitnessGoal).where(FitnessGoal.client_id == client.id).order_by(FitnessGoal.created_at.desc())).scalars().all() if "gym.measurements.view" in permissions else []
    sessions = db.execute(select(WorkoutSession).where(WorkoutSession.client_id == client.id).order_by(WorkoutSession.scheduled_for.desc()).limit(100)).scalars().all() if "gym.workouts.view" in permissions else []
    workouts = db.execute(select(WorkoutPlan).where(WorkoutPlan.client_id == client.id).order_by(WorkoutPlan.created_at.desc())).scalars().all() if "gym.workouts.view" in permissions else []
    diets = db.execute(select(DietPlan).where(DietPlan.client_id == client.id).order_by(DietPlan.created_at.desc())).scalars().all() if "gym.diets.view" in permissions else []
    notes = db.execute(select(CoachingNote).where(CoachingNote.client_id == client.id).order_by(CoachingNote.created_at.desc()).limit(100)).scalars().all() if "gym.coaching.view" in permissions else []
    invoice_ids = {row.invoice_id for row in memberships if row.invoice_id}
    linked_invoices = db.execute(select(SaleInvoice).where(SaleInvoice.id.in_(invoice_ids))).scalars().all() if invoice_ids and "sales.view" in permissions else []
    invoice_views = {item["id"]: item for item in _sales_with_items(db, user.organization_id, linked_invoices)}
    today = local_today(db, user)[0]

    def membership_view(row: Membership) -> dict:
        invoice = invoice_views.get(row.invoice_id)
        return serialize(row, {
            "plan": serialize(plans[row.plan_id]) if row.plan_id in plans else None,
            "days_remaining": max((row.ends_on - today).days + 1, 0) if row.status in {"active", "frozen"} else 0,
            "term_charge_paise": row.amount_paise,
            "invoice": invoice,
            "legacy_unlinked": row.invoice_id is None,
            "cancellation_pending": bool(row.cancellation_effective_on and row.cancellation_effective_on > today),
        })

    active = next((row for row in memberships if row.status in {"active", "frozen"}), None)
    scheduled = next((row for row in memberships if row.status == "scheduled"), None)
    open_checkin = next((row for row in checkins if not row.checked_out_at), None)
    days = max((datetime.now(timezone.utc) - start).days, 1)
    membership_views = [membership_view(row) for row in memberships]
    return {
        "memberships": membership_views,
        "active_membership": membership_view(active) if active else None,
        "current_membership": membership_view(active) if active else None,
        "scheduled_membership": membership_view(scheduled) if scheduled else None,
        "membership_history": [membership_view(row) for row in memberships if row.status not in {"active", "frozen", "scheduled"}],
        "checkins": [serialize(row) for row in checkins], "open_checkin": serialize(open_checkin) if open_checkin else None,
        "attendance": {"checkins": len(checkins), "active_days": len({row.checked_in_at.date() for row in checkins}), "visits_per_week": round(len(checkins) / days * 7, 1)},
        "trainers": [serialize(row, {"employee": serialize(employees[row.trainer_employee_id]) if row.trainer_employee_id in employees else None}) for row in assignments],
        "measurements": [serialize(row) for row in measurements], "goals": [serialize(row) for row in goals],
        "workout_sessions": [serialize(row) for row in sessions], "workouts": [serialize(row) for row in workouts],
        "diets": [serialize(row) for row in diets], "coaching_notes": [serialize(row) for row in notes],
    }


def _salon_workspace(db: Session, user: User, client: Client, appointments, sales, permissions):
    profile = db.execute(select(SalonClientProfile).where(SalonClientProfile.client_id == client.id)).scalar_one_or_none()
    service_ids = {row.service_id for row in appointments if row.service_id}
    services = {row.id: row for row in db.execute(select(CatalogItem).where(CatalogItem.id.in_(service_ids))).scalars()} if service_ids else {}
    visits = [row for row in appointments if row.status == "completed"]
    upcoming = [row for row in appointments if row.status in {"scheduled", "confirmed"} and row.starts_at >= datetime.now(timezone.utc)]
    return {
        "profile": serialize(profile) if profile and "salon.notes.view" in permissions else None,
        "upcoming": serialize(sorted(upcoming, key=lambda row: row.starts_at)[0]) if upcoming else None,
        "visits": [serialize(row, {"service": serialize(services[row.service_id]) if row.service_id in services else None}) for row in visits],
        "visit_count": len(visits), "no_shows": sum(row.status == "no_show" for row in appointments),
        "average_spend_paise": round(sum(row.total_paise for row in sales) / len(visits)) if visits else 0,
    }


def _clinic_workspace(db: Session, user: User, client: Client, permissions):
    patient = db.execute(select(PatientProfile).where(PatientProfile.client_id == client.id)).scalar_one_or_none()
    if not patient or "clinical.view" not in permissions:
        return {"patient": serialize(patient) if patient else None, "clinical_access": False}
    encounters = db.execute(select(Encounter).where(Encounter.patient_id == patient.id).order_by(Encounter.created_at.desc()).limit(50)).scalars().all()
    encounter_ids = {row.id for row in encounters}
    allergies = db.execute(select(Allergy).where(Allergy.patient_id == patient.id, Allergy.status == "active")).scalars().all()
    vitals = db.execute(select(Vital).where(Vital.encounter_id.in_(encounter_ids)).order_by(Vital.created_at.desc()).limit(30)).scalars().all() if encounter_ids else []
    prescriptions = db.execute(select(Prescription).where(Prescription.encounter_id.in_(encounter_ids)).order_by(Prescription.created_at.desc()).limit(30)).scalars().all() if encounter_ids else []
    labs = db.execute(select(LabOrder).where(LabOrder.encounter_id.in_(encounter_ids)).order_by(LabOrder.created_at.desc()).limit(30)).scalars().all() if encounter_ids else []
    return {"clinical_access": True, "patient": serialize(patient), "allergies": [serialize(row) for row in allergies], "encounters": [serialize(row) for row in encounters], "vitals": [serialize(row) for row in vitals], "prescriptions": [serialize(row) for row in prescriptions], "labs": [serialize(row) for row in labs]}


def _college_workspace(db: Session, user: User, client: Client, start: datetime, permissions: set[str]) -> dict:
    can_view_student = bool({"college.students.view", "college.students.manage"} & permissions)
    if not can_view_student:
        return {"academic_access": False, "profile": None, "attendance": [], "assessments": []}
    profile = db.execute(select(CollegeStudentProfile).where(
        CollegeStudentProfile.organization_id == user.organization_id,
        CollegeStudentProfile.client_id == client.id,
    )).scalar_one_or_none()
    if not profile:
        return {"academic_access": True, "profile": None, "attendance": [], "assessments": []}

    program = db.get(CollegeProgram, profile.program_id)
    cohort = db.get(CollegeCohort, profile.cohort_id)
    department = db.get(CollegeDepartment, program.department_id) if program else None
    attendance = []
    attendance_total = 0
    attendance_present = 0
    if {"college.attendance.view", "college.attendance.mark"} & permissions:
        attendance_rows = db.execute(select(
            CollegeAttendanceRecord,
            CollegeAttendanceSession,
            CollegeCourseOffering,
            CollegeCourse,
        ).join(
            CollegeAttendanceSession, CollegeAttendanceSession.id == CollegeAttendanceRecord.session_id,
        ).join(
            CollegeCourseOffering, CollegeCourseOffering.id == CollegeAttendanceSession.offering_id,
        ).join(
            CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id,
        ).where(
            CollegeAttendanceRecord.organization_id == user.organization_id,
            CollegeAttendanceRecord.student_profile_id == profile.id,
            CollegeAttendanceSession.held_on >= start.date(),
        ).order_by(
            CollegeAttendanceSession.held_on.desc(),
            CollegeAttendanceSession.starts_at.desc(),
        ).limit(100)).all()
        attendance_total = len(attendance_rows)
        attendance_present = sum(record.status in {"present", "late"} for record, _session, _offering, _course in attendance_rows)
        attendance = [{
            **serialize(record),
            "held_on": session.held_on,
            "starts_at": session.starts_at,
            "topic": session.topic,
            "course_id": course.id,
            "course_code": course.code,
            "course_name": course.name,
        } for record, session, _offering, course in attendance_rows]

    assessments = []
    if {"college.assessments.view", "college.assessments.manage"} & permissions:
        score_rows = db.execute(select(
            CollegeAssessmentScore,
            CollegeAssessment,
            CollegeCourseOffering,
            CollegeCourse,
        ).join(
            CollegeAssessment, CollegeAssessment.id == CollegeAssessmentScore.assessment_id,
        ).join(
            CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id,
        ).join(
            CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id,
        ).where(
            CollegeAssessmentScore.organization_id == user.organization_id,
            CollegeAssessmentScore.student_profile_id == profile.id,
        ).order_by(CollegeAssessment.due_on.desc().nullslast()).limit(100)).all()
        assessments = [{
            **serialize(score),
            "assessment_id": assessment.id,
            "title": assessment.title,
            "assessment_type": assessment.assessment_type,
            "max_marks": float(assessment.max_marks),
            "due_on": assessment.due_on,
            "assessment_status": assessment.status,
            "course_code": course.code,
            "course_name": course.name,
        } for score, assessment, _offering, course in score_rows]

    offerings = db.execute(select(
        CollegeCourseOffering,
        CollegeCourse,
        CollegeTerm,
    ).join(
        CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id,
    ).join(
        CollegeTerm, CollegeTerm.id == CollegeCourseOffering.term_id,
    ).where(
        CollegeCourseOffering.organization_id == user.organization_id,
        CollegeCourseOffering.cohort_id == profile.cohort_id,
        CollegeCourseOffering.status == "active",
    ).order_by(CollegeCourse.code).limit(50)).all()
    return {
        "academic_access": True,
        "profile": serialize(profile),
        "program": serialize(program) if program else None,
        "cohort": serialize(cohort) if cohort else None,
        "department": serialize(department) if department else None,
        "attendance": attendance,
        "attendance_summary": {
            "total_classes": attendance_total,
            "present_classes": attendance_present,
            "percentage": round(attendance_present * 100 / attendance_total, 1) if attendance_total else None,
        },
        "assessments": assessments,
        "courses": [{
            **serialize(offering),
            "course_code": course.code,
            "course_name": course.name,
            "term_name": term.name,
            "academic_year": term.academic_year,
        } for offering, course, term in offerings],
    }


@router.get("/clients/{client_id}/workspace")
def client_workspace(client_id: str, range: str = "30d", user: User = Depends(require_permissions("clients.view")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id)
    org = db.get(Organization, user.organization_id); industry = org.industry.value
    days = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}.get(range, 30)
    start = datetime.now(timezone.utc) - timedelta(days=days)
    permissions = get_user_permissions(db, user); roles = _role_slugs(db, user)
    if industry == "gym":
        reconcile_memberships(db, user, client_id=client.id, lock=True)
    appointments, sales, commitments = _common_data(
        db, user, client, start, include_sales="sales.view" in permissions,
    )
    memories = _visible_memories(db, user, client.id, permissions, roles)
    _refresh_signals(db, user, client, industry)
    signals = db.execute(select(ClientSignal).where(ClientSignal.client_id == client.id, ClientSignal.status.in_(["open", "snoozed"])).order_by(ClientSignal.pulse_state, ClientSignal.generated_at.desc())).scalars().all() if "client_signals.view" in permissions else []
    state = "action_needed" if any(row.pulse_state == "action_needed" for row in signals) else "watch" if any(row.pulse_state == "watch" for row in signals) else "healthy"
    photo = _photo_media(db, client.id) if "clients.media.view" in permissions else None
    location = db.get(Location, client.home_location_id) if client.home_location_id else None
    billing = _billing_workspace(db, user, client, permissions)
    billing_summary = billing.get("summary") or {}
    lifetime = int(billing_summary.get("paid_paise") or 0)
    outstanding = int(billing_summary.get("outstanding_paise") or 0)
    metrics = {"lifetime_value_paise": lifetime, "outstanding_paise": outstanding, "appointments": len(appointments), "completed_visits": sum(row.status == "completed" for row in appointments)}
    if industry == "gym": industry_data = _gym_workspace(db, user, client, start, permissions)
    elif industry == "salon": industry_data = _salon_workspace(db, user, client, appointments, sales, permissions)
    elif industry == "clinic": industry_data = _clinic_workspace(db, user, client, permissions)
    elif industry == "college": industry_data = _college_workspace(db, user, client, start, permissions)
    else: industry_data = {}
    briefing_role = _briefing_role(roles, industry)
    brief = [{"title": row.title, "detail": row.explanation, "evidence": row.evidence, "tone": row.pulse_state} for row in signals[:4]]
    role_context = _role_brief(briefing_role, industry, metrics, industry_data)
    if role_context:
        brief.insert(0, role_context)
    for memory in memories[:3]:
        brief.append({"title": memory.label, "detail": memory.value, "evidence": [{"record": "memory", "id": memory.id}], "tone": "context"})
    open_commitments = [row for row in commitments if row.status == "open"]
    if open_commitments:
        brief.append({"title": "Keep the promise", "detail": open_commitments[0].title, "evidence": [{"record": "commitment", "id": open_commitments[0].id}], "tone": "context"})
    if not brief:
        brief = [{"title": "Relationship is ready to build", "detail": "Add a preference, goal, or commitment after the next conversation.", "evidence": [], "tone": "healthy"}]
    actions = {
        "edit_client": "clients.manage" in permissions, "manage_memory": "client_memory.manage" in permissions,
        "manage_signals": "client_signals.manage" in permissions, "view_media": "clients.media.view" in permissions,
        "manage_media": "clients.media.manage" in permissions, "mark_attendance": "gym.attendance.mark" in permissions,
        "correct_attendance": "gym.attendance.correct" in permissions, "manage_membership": "gym.memberships.manage" in permissions,
        "manage_coaching": "gym.coaching.manage" in permissions, "manage_measurements": "gym.measurements.manage" in permissions,
        "manage_workouts": "gym.workouts.manage" in permissions, "manage_diets": "gym.diets.manage" in permissions,
        "manage_salon_notes": "salon.notes.manage" in permissions, "clinical_write": "clinical.write" in permissions,
        "view_academics": "college.students.view" in permissions or "college.students.manage" in permissions,
        "view_billing": "sales.view" in permissions, "record_payment": "payments.record" in permissions,
        "void_invoice": "sales.manage" in permissions,
    }
    # API requests persist immediately; AI tools run this workspace inside a
    # savepoint and commit it atomically with the completed AI response.
    if db.in_nested_transaction(): db.flush()
    else: db.commit()
    return {
        "client": serialize(client), "industry": industry, "location": serialize(location) if location else None,
        "profile_photo_url": f"/clients/{client.id}/photo?v={int(photo.updated_at.timestamp())}" if photo else None,
        "pulse": {"state": state, "open_signals": len(signals)}, "brief": brief, "signals": [serialize(row) for row in signals],
        "metrics": metrics, "briefing_role": briefing_role,
        "memory": [serialize(row) for row in memories], "commitments": [serialize(row) for row in commitments],
        "appointments": [serialize(row) for row in appointments],
        "sales": _sales_with_items(db, user.organization_id, sales),
        "billing": billing,
        "actions": actions, "industry_data": industry_data, "range": range,
    }


@router.get("/clients/attention")
def attention_queue(user: User = Depends(require_permissions("client_signals.view")), db: Session = Depends(get_db)):
    org = db.get(Organization, user.organization_id)
    clients = db.execute(filter_clients(select(Client).where(Client.organization_id == user.organization_id, Client.status == "active"), db, user).limit(250)).scalars().all()
    for client in clients:
        _refresh_signals(db, user, client, org.industry.value)
    client_ids = {row.id for row in clients}
    now = datetime.now(timezone.utc)
    rows = db.execute(select(ClientSignal, Client).join(Client, Client.id == ClientSignal.client_id).where(ClientSignal.client_id.in_(client_ids), ClientSignal.status.in_(["open", "snoozed"]), or_(ClientSignal.snoozed_until.is_(None), ClientSignal.snoozed_until <= now)).order_by(ClientSignal.pulse_state, ClientSignal.generated_at.desc())).all() if client_ids else []
    db.commit()
    return [{"signal": serialize(signal), "client": serialize(client)} for signal, client in rows]


@router.get("/clients/{client_id}/timeline")
def client_timeline(
    client_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    event_type: str | None = Query(default=None, max_length=40),
    user: User = Depends(require_permissions("clients.view")),
    db: Session = Depends(get_db),
):
    client = _client(db, user, client_id)
    permissions = get_user_permissions(db, user)
    query_limit = page_size(limit, default=50)
    cursor_filters = {"client_id": client.id, "event_type": event_type}
    cursor_values = decode_cursor(
        cursor,
        scope="clients.timeline",
        organization_id=user.organization_id,
        filters=cursor_filters,
    )
    cursor_at = datetime.fromisoformat(str(cursor_values["at"])) if cursor_values else None
    cursor_id = str(cursor_values["id"]) if cursor_values else None
    source_limit = query_limit + 1
    events = []
    appointment_statement = select(Appointment).where(
        Appointment.organization_id == user.organization_id,
        Appointment.client_id == client.id,
    )
    if cursor_at:
        appointment_statement = appointment_statement.where(Appointment.starts_at <= cursor_at)
    appointments = db.execute(appointment_statement.order_by(
        Appointment.starts_at.desc(), Appointment.id.desc(),
    ).limit(source_limit)).scalars().all()
    service_ids = {row.service_id for row in appointments if row.service_id}
    employee_ids = {row.employee_id for row in appointments if row.employee_id}
    services = {row.id: row for row in db.execute(select(CatalogItem).where(CatalogItem.id.in_(service_ids))).scalars()} if service_ids else {}
    employees = {row.id: row for row in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars()} if employee_ids else {}
    for row in appointments:
        service = services.get(row.service_id)
        employee = employees.get(row.employee_id)
        events.append({
            "id": f"appointment:{row.id}", "record_id": row.id, "type": "appointment", "category": "operations",
            "title": service.name if service else "Appointment",
            "occurred_at": row.starts_at, "status": row.status,
            "detail": row.notes or row.status.replace("_", " ").title(),
            "actor": ({"id": employee.id, "name": f"{employee.first_name} {employee.last_name}".strip(), "kind": "employee"} if employee else None),
            "target": {"kind": "appointment", "id": row.id},
        })

    invoices = []
    payments = []
    if "sales.view" in permissions:
        invoice_statement = filter_locations(select(SaleInvoice).where(
            SaleInvoice.organization_id == user.organization_id,
            SaleInvoice.client_id == client.id,
        ), SaleInvoice, db, user)
        if cursor_at:
            invoice_statement = invoice_statement.where(SaleInvoice.created_at <= cursor_at)
        invoices = db.execute(invoice_statement.order_by(
            SaleInvoice.created_at.desc(), SaleInvoice.id.desc(),
        ).limit(source_limit)).scalars().all()
        invoice_views = {item["id"]: item for item in _sales_with_items(db, user.organization_id, invoices)}
        payment_statement = select(SalePayment, SaleInvoice).join(
            SaleInvoice, SaleInvoice.id == SalePayment.invoice_id,
        ).where(
            SalePayment.organization_id == user.organization_id,
            SaleInvoice.organization_id == user.organization_id,
            SaleInvoice.client_id == client.id,
        )
        payment_statement = filter_locations(payment_statement, SaleInvoice, db, user)
        if cursor_at:
            payment_statement = payment_statement.where(SalePayment.created_at <= cursor_at)
        payment_rows = db.execute(payment_statement.order_by(
            SalePayment.created_at.desc(), SalePayment.id.desc(),
        ).limit(source_limit)).all()
        payments = [payment for payment, _invoice in payment_rows]
        payment_invoices = {payment.id: invoice for payment, invoice in payment_rows}
        for row in invoices:
            view = invoice_views[row.id]
            item_text = ", ".join(view["item_names"][:3]) or "No item description"
            events.append({
                "id": f"invoice:{row.id}", "record_id": row.id, "type": "invoice", "category": "billing",
                "title": row.invoice_number, "occurred_at": row.created_at, "status": row.status,
                "detail": item_text, "amount_paise": row.total_paise,
                "balance_paise": max(row.total_paise - row.paid_paise, 0),
                "actor": None, "target": {"kind": "invoice", "id": row.id},
            })

    checkins = []
    if "gym.attendance.view" in permissions:
        checkin_statement = select(GymCheckIn).where(
            GymCheckIn.organization_id == user.organization_id,
            GymCheckIn.client_id == client.id,
        )
        if cursor_at:
            checkin_statement = checkin_statement.where(GymCheckIn.checked_in_at <= cursor_at)
        checkins = db.execute(checkin_statement.order_by(
            GymCheckIn.checked_in_at.desc(), GymCheckIn.id.desc(),
        ).limit(source_limit)).scalars().all()

    memberships = []
    if "gym.memberships.view" in permissions:
        if reconcile_memberships(db, user, client_id=client.id):
            db.commit()
        membership_statement = select(Membership).where(
            Membership.organization_id == user.organization_id,
            Membership.client_id == client.id,
        )
        if cursor_at:
            membership_statement = membership_statement.where(Membership.created_at <= cursor_at)
        memberships = db.execute(membership_statement.order_by(
            Membership.created_at.desc(), Membership.id.desc(),
        ).limit(source_limit)).scalars().all()
        plan_ids = {row.plan_id for row in memberships}
        plans = {row.id: row for row in db.execute(select(MembershipPlan).where(MembershipPlan.id.in_(plan_ids))).scalars()} if plan_ids else {}
    else:
        plans = {}

    resource_ids = select(cast(Membership.id, String)).where(
        Membership.organization_id == user.organization_id,
        Membership.client_id == client.id,
    ).union(select(cast(SaleInvoice.id, String)).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.client_id == client.id,
    ))
    audit_statement = select(AuditLog).where(
        AuditLog.organization_id == user.organization_id,
        AuditLog.resource_id.in_(resource_ids),
        AuditLog.action.in_(["membership.create", "membership.renew", "membership.cancel", "membership.cancellation_revoke", "sale.void"]),
    )
    if cursor_at:
        audit_statement = audit_statement.where(AuditLog.created_at <= cursor_at)
    audits = db.execute(audit_statement.order_by(
        AuditLog.created_at.desc(), AuditLog.id.desc(),
    ).limit(source_limit * 2)).scalars().all()
    actor_ids = {row.received_by_user_id for row in payments} | {row.recorded_by_user_id for row in checkins if row.recorded_by_user_id} | {row.user_id for row in audits if row.user_id}
    users = {row.id: row for row in db.execute(select(User).where(User.id.in_(actor_ids))).scalars()} if actor_ids else {}

    def user_actor(user_id: str | None):
        actor = users.get(user_id)
        return {"id": actor.id, "name": f"{actor.first_name} {actor.last_name}".strip(), "kind": "user"} if actor else None

    audit_by_resource = {}
    for audit in audits:
        if audit.action in {"membership.create", "membership.renew"}:
            audit_by_resource.setdefault(audit.resource_id, audit)
    for row in memberships:
        plan = plans.get(row.plan_id)
        audit = audit_by_resource.get(row.id)
        events.append({
            "id": f"membership:{row.id}", "record_id": row.id,
            "type": "renewal" if row.previous_membership_id else "membership", "category": "membership",
            "title": "Membership renewed" if row.previous_membership_id else "Membership activated",
            "occurred_at": row.created_at, "status": row.status,
            "detail": f"{plan.name if plan else 'Membership'} - {row.starts_on.strftime('%d %b %Y')} to {row.ends_on.strftime('%d %b %Y')}",
            "amount_paise": row.amount_paise, "actor": user_actor(audit.user_id if audit else None),
            "target": {"kind": "membership", "id": row.id},
        })
    for row in payments:
        invoice = payment_invoices.get(row.id)
        events.append({
            "id": f"payment:{row.id}", "record_id": row.id, "type": "payment", "category": "billing",
            "title": f"Payment recorded{f' for {invoice.invoice_number}' if invoice else ''}",
            "occurred_at": row.created_at, "status": row.status, "detail": row.method.upper(),
            "amount_paise": row.amount_paise, "actor": user_actor(row.received_by_user_id),
            "target": {"kind": "invoice", "id": row.invoice_id},
        })
    for row in checkins:
        duration = None
        if row.checked_out_at:
            duration = max(int((row.checked_out_at - row.checked_in_at).total_seconds() // 60), 0)
        events.append({
            "id": f"visit:{row.id}", "record_id": row.id, "type": "visit", "category": "attendance",
            "title": "Gym visit", "occurred_at": row.checked_in_at,
            "status": "completed" if row.checked_out_at else "inside",
            "detail": f"{duration} minutes" if duration is not None else "Currently checked in",
            "actor": user_actor(row.recorded_by_user_id), "target": {"kind": "check_in", "id": row.id},
        })
    for audit in audits:
        if audit.action not in {"membership.cancel", "membership.cancellation_revoke", "sale.void"}:
            continue
        changes = (audit.meta or {}).get("changes") or {}
        is_void = audit.action == "sale.void"
        is_reversal = audit.action == "membership.cancellation_revoke"
        events.append({
            "id": f"audit:{audit.id}", "record_id": audit.resource_id,
            "type": "invoice_void" if is_void else "cancellation_reversal" if is_reversal else "cancellation",
            "category": "billing" if is_void else "membership",
            "title": "Invoice voided" if is_void else "Cancellation reversed" if is_reversal else "Membership cancellation recorded",
            "occurred_at": audit.created_at, "status": "void" if is_void else "reversed" if is_reversal else changes.get("timing", "cancelled"),
            "detail": changes.get("reason") or (f"Previously effective {changes.get('previous_effective_on')}" if changes.get("previous_effective_on") else None),
            "actor": user_actor(audit.user_id),
            "target": {"kind": "invoice" if is_void else "membership", "id": audit.resource_id},
        })
    if cursor_at:
        events = [item for item in events if (
            item["occurred_at"] < cursor_at
            or (item["occurred_at"] == cursor_at and item["id"] < cursor_id)
        )]
    if event_type:
        events = [item for item in events if item["type"] == event_type]
    ordered = sorted(events, key=lambda item: (item["occurred_at"], item["id"]), reverse=True)
    has_more = len(ordered) > query_limit
    page = ordered[:query_limit]
    next_cursor = encode_cursor(
        scope="clients.timeline",
        organization_id=user.organization_id,
        filters=cursor_filters,
        values={"at": page[-1]["occurred_at"].isoformat(), "id": page[-1]["id"]},
    ) if has_more and page else None
    return {"items": page, "next_cursor": next_cursor, "has_more": has_more}


@router.post("/clients/{client_id}/memory", status_code=201)
def add_memory(client_id: str, body: MemoryBody, user: User = Depends(require_permissions("client_memory.manage")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id)
    if body.visibility not in MEMORY_VISIBILITY: raise HTTPException(422, "Invalid memory visibility")
    if body.visibility == "clinical" and "clinical.write" not in get_user_permissions(db, user): raise HTTPException(403, "Clinical permission is required")
    row = ClientMemory(organization_id=user.organization_id, client_id=client.id, created_by_user_id=user.id, **body.model_dump())
    db.add(row); db.flush(); log_action(db, organization_id=user.organization_id, user_id=user.id, action="client_memory.create", resource_type="client_memory", resource_id=row.id); db.commit(); db.refresh(row); return serialize(row)


@router.patch("/clients/{client_id}/memory/{memory_id}")
def update_memory(client_id: str, memory_id: str, body: MemoryUpdate, user: User = Depends(require_permissions("client_memory.manage")), db: Session = Depends(get_db)):
    _client(db, user, client_id); row = tenant_get(db, ClientMemory, memory_id, user)
    if row.client_id != client_id: raise HTTPException(404, "Memory not found")
    if row.version != body.version: raise HTTPException(409, "Memory was changed by another user")
    if body.visibility not in MEMORY_VISIBILITY: raise HTTPException(422, "Invalid memory visibility")
    for key, value in body.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.updated_by_user_id = user.id; row.version += 1; db.commit(); return serialize(row)


@router.delete("/clients/{client_id}/memory/{memory_id}")
def delete_memory(client_id: str, memory_id: str, user: User = Depends(require_permissions("client_memory.manage")), db: Session = Depends(get_db)):
    _client(db, user, client_id); row = tenant_get(db, ClientMemory, memory_id, user)
    if row.client_id != client_id: raise HTTPException(404, "Memory not found")
    row.is_active = False; row.updated_by_user_id = user.id; row.version += 1; log_action(db, organization_id=user.organization_id, user_id=user.id, action="client_memory.delete", resource_type="client_memory", resource_id=row.id); db.commit(); return {"ok": True}


@router.post("/clients/{client_id}/commitments", status_code=201)
def add_commitment(client_id: str, body: CommitmentBody, user: User = Depends(require_permissions("client_memory.manage")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id)
    if body.owner_user_id:
        owner = db.get(User, body.owner_user_id)
        if not owner or owner.organization_id != user.organization_id: raise HTTPException(422, "Commitment owner is invalid")
    row = ClientCommitment(organization_id=user.organization_id, client_id=client.id, created_by_user_id=user.id, **body.model_dump())
    db.add(row); db.commit(); db.refresh(row); return serialize(row)


@router.patch("/clients/{client_id}/commitments/{commitment_id}")
def update_commitment(client_id: str, commitment_id: str, body: CommitmentUpdate, user: User = Depends(require_permissions("client_memory.manage")), db: Session = Depends(get_db)):
    _client(db, user, client_id); row = tenant_get(db, ClientCommitment, commitment_id, user)
    if row.client_id != client_id or row.version != body.version: raise HTTPException(409, "Commitment is stale or unavailable")
    row.status = body.status; row.completion_note = body.completion_note; row.completed_at = datetime.now(timezone.utc) if body.status == "completed" else None; row.version += 1; db.commit(); return serialize(row)


@router.patch("/client-signals/{signal_id}")
def update_signal(signal_id: str, body: SignalUpdate, user: User = Depends(require_permissions("client_signals.manage")), db: Session = Depends(get_db)):
    row = tenant_get(db, ClientSignal, signal_id, user); _client(db, user, row.client_id)
    if row.version != body.version: raise HTTPException(409, "Signal was changed by another user")
    now = datetime.now(timezone.utc)
    if body.action == "assign":
        if body.assigned_to_user_id:
            assignee = db.get(User, body.assigned_to_user_id)
            if not assignee or assignee.organization_id != user.organization_id: raise HTTPException(422, "Assignee is invalid")
        row.assigned_to_user_id = body.assigned_to_user_id
    elif body.action == "snooze": row.status = "snoozed"; row.snoozed_until = body.snoozed_until or now + timedelta(days=7)
    elif body.action in {"resolve", "dismiss"}: row.status = "resolved" if body.action == "resolve" else "dismissed"; row.resolved_at = now; row.resolution_note = body.note
    elif body.action == "reopen": row.status = "open"; row.resolved_at = None; row.resolution_note = None; row.snoozed_until = None
    row.version += 1; log_action(db, organization_id=user.organization_id, user_id=user.id, action=f"client_signal.{body.action}", resource_type="client_signal", resource_id=row.id, changes={"note": body.note}); db.commit(); return serialize(row)


def _media_response(row: ClientMedia, document: Document):
    return serialize(row, {"document": serialize(document, {"object_key": None, "extracted_text": None}), "content_url": f"/client-media/{row.id}/content"})


@router.get("/clients/{client_id}/media")
def client_media(client_id: str, user: User = Depends(require_permissions("clients.media.view")), db: Session = Depends(get_db)):
    _client(db, user, client_id)
    rows = db.execute(select(ClientMedia, Document).join(Document, Document.id == ClientMedia.document_id).where(ClientMedia.organization_id == user.organization_id, ClientMedia.client_id == client_id).order_by(ClientMedia.created_at.desc())).all()
    permissions = get_user_permissions(db, user)
    return [_media_response(media, document) for media, document in rows if media.visibility != "clinical" or "clinical.view" in permissions]


@router.post("/clients/{client_id}/media", status_code=201)
async def upload_client_media(
    client_id: str, file: UploadFile = File(...), media_kind: str = Form("attachment"), caption: str | None = Form(None),
    visibility: str = Form("team"), captured_at: datetime | None = Form(None), location_id: str | None = Form(None),
    user: User = Depends(require_permissions("clients.media.manage")), db: Session = Depends(get_db),
):
    client = _client(db, user, client_id)
    content_type = (file.content_type or "").lower()
    if content_type not in MEDIA_TYPES: raise HTTPException(415, "Supported formats are JPG, PNG, WebP, MP4, WebM, PDF, DOCX, and TXT")
    if visibility not in MEMORY_VISIBILITY: raise HTTPException(422, "Invalid media visibility")
    permissions = get_user_permissions(db, user)
    if visibility == "clinical" and "clinical.write" not in permissions: raise HTTPException(403, "Clinical permission is required")
    if media_kind == "profile_photo" and content_type not in IMAGE_TYPES: raise HTTPException(415, "A profile photo must be JPG, PNG, or WebP")
    maximum = 5 * 1024 * 1024 if media_kind == "profile_photo" else 100 * 1024 * 1024 if content_type in VIDEO_TYPES else 20 * 1024 * 1024
    content = await file.read(maximum + 1)
    if not content: raise HTTPException(400, "File is empty")
    if len(content) > maximum: raise HTTPException(413, f"File exceeds the {maximum // (1024 * 1024)} MB limit")
    if content.startswith((b"MZ", b"\x7fELF")): raise HTTPException(400, "Executable content is not allowed")
    location_id = location_id or client.home_location_id
    if location_id: ensure_location(db, user, location_id)
    safe_name = Path(file.filename or f"client{MEDIA_TYPES[content_type]}").name
    object_key = f"{user.organization_id}/clients/{client.id}/{secrets.token_hex(12)}{MEDIA_TYPES[content_type]}"
    if settings.S3_ENDPOINT_URL and not settings.PROVIDER_MOCK_MODE:
        import boto3
        boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL, aws_access_key_id=settings.S3_ACCESS_KEY_ID, aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY).put_object(Bucket=settings.S3_BUCKET, Key=object_key, Body=content, ContentType=content_type)
    else:
        target = STORAGE_DIR / object_key; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    document = Document(organization_id=user.organization_id, location_id=location_id, uploaded_by_user_id=user.id, entity_type="client", entity_id=client.id, name=safe_name, object_key=object_key, content_type=content_type, size_bytes=len(content), checksum=hashlib.sha256(content).hexdigest(), status="ready" if content_type in IMAGE_TYPES | VIDEO_TYPES else "pending")
    db.add(document); db.flush()
    is_profile = media_kind == "profile_photo"
    if is_profile:
        db.query(ClientMedia).filter(ClientMedia.client_id == client.id, ClientMedia.is_profile.is_(True)).update({ClientMedia.is_profile: False})
    media = ClientMedia(organization_id=user.organization_id, location_id=location_id, client_id=client.id, document_id=document.id, media_kind=media_kind, caption=caption, captured_at=captured_at, visibility=visibility, is_profile=is_profile, uploaded_by_user_id=user.id)
    db.add(media); db.flush()
    if document.status == "pending": db.add(Job(organization_id=user.organization_id, kind="process_document", payload={"document_id": document.id}, run_at=datetime.now(timezone.utc), idempotency_key=f"document-{document.id}"))
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="client_media.upload", resource_type="client_media", resource_id=media.id, changes={"kind": media_kind, "content_type": content_type})
    db.commit(); db.refresh(media); return _media_response(media, document)


def _serve_document(document: Document):
    if settings.S3_ENDPOINT_URL and not settings.PROVIDER_MOCK_MODE:
        import boto3
        url = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL, aws_access_key_id=settings.S3_ACCESS_KEY_ID, aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY).generate_presigned_url("get_object", Params={"Bucket": settings.S3_BUCKET, "Key": document.object_key}, ExpiresIn=300)
        return RedirectResponse(url)
    path = (STORAGE_DIR / document.object_key).resolve()
    if STORAGE_DIR.resolve() not in path.parents or not path.exists(): raise HTTPException(404, "Stored media is unavailable")
    return FileResponse(path, media_type=document.content_type, filename=document.name)


@router.get("/clients/{client_id}/photo")
def client_photo(client_id: str, user: User = Depends(require_permissions("clients.view", "clients.media.view")), db: Session = Depends(get_db)):
    _client(db, user, client_id); media = _photo_media(db, client_id)
    if not media: raise HTTPException(404, "Client has no profile photo")
    return _serve_document(db.get(Document, media.document_id))


@router.get("/client-media/{media_id}/content")
def media_content(media_id: str, user: User = Depends(require_permissions("clients.media.view")), db: Session = Depends(get_db)):
    media = tenant_get(db, ClientMedia, media_id, user); _client(db, user, media.client_id)
    if media.visibility == "clinical" and "clinical.view" not in get_user_permissions(db, user): raise HTTPException(403, "Clinical permission is required")
    return _serve_document(db.get(Document, media.document_id))


@router.delete("/client-media/{media_id}")
def delete_media(media_id: str, user: User = Depends(require_permissions("clients.media.manage")), db: Session = Depends(get_db)):
    media = tenant_get(db, ClientMedia, media_id, user); _client(db, user, media.client_id)
    if media.visibility == "clinical" and "clinical.write" not in get_user_permissions(db, user): raise HTTPException(403, "Clinical permission is required")
    document = db.get(Document, media.document_id)
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="client_media.delete", resource_type="client_media", resource_id=media.id)
    db.delete(media); db.flush()
    if document: db.delete(document)
    db.commit(); return {"ok": True}


@router.post("/gym/members/{client_id}/check-in", status_code=201)
def member_check_in(client_id: str, body: CheckInBody, user: User = Depends(require_permissions("gym.attendance.mark")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id); ensure_location(db, user, body.location_id)
    reconcile_memberships(db, user, client_id=client.id, lock=True)
    today = local_today(db, user)[0]
    membership = db.execute(select(Membership).where(Membership.organization_id == user.organization_id, Membership.client_id == client.id, Membership.location_id == body.location_id, Membership.status == "active", Membership.starts_on <= today, Membership.ends_on >= today).order_by(Membership.ends_on.desc())).scalars().first()
    if not membership: raise HTTPException(409, "Member has no active membership at this location")
    open_visit = db.execute(select(GymCheckIn).where(GymCheckIn.organization_id == user.organization_id, GymCheckIn.client_id == client.id, GymCheckIn.checked_out_at.is_(None))).scalar_one_or_none()
    if open_visit: raise HTTPException(409, "Member is already checked in")
    row = GymCheckIn(organization_id=user.organization_id, location_id=body.location_id, membership_id=membership.id, client_id=client.id, checked_in_at=datetime.now(timezone.utc), method="staff", source="client_workspace", notes=body.notes, recorded_by_user_id=user.id)
    client.last_visit_at = row.checked_in_at; db.add(row); db.commit(); db.refresh(row); return serialize(row)


@router.post("/gym/members/{client_id}/check-out")
def member_check_out(client_id: str, user: User = Depends(require_permissions("gym.attendance.mark")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id)
    row = db.execute(select(GymCheckIn).where(GymCheckIn.organization_id == user.organization_id, GymCheckIn.client_id == client.id, GymCheckIn.checked_out_at.is_(None)).with_for_update()).scalar_one_or_none()
    if not row: raise HTTPException(409, "Member is not currently checked in")
    ensure_location(db, user, row.location_id); row.checked_out_at = datetime.now(timezone.utc); row.version += 1; db.commit(); return serialize(row)


@router.patch("/gym/check-ins/{checkin_id}/correct")
def correct_check_in(checkin_id: str, body: CheckInCorrection, user: User = Depends(require_permissions("gym.attendance.correct")), db: Session = Depends(get_db)):
    row = tenant_get(db, GymCheckIn, checkin_id, user, location_field="location_id"); _client(db, user, row.client_id)
    if row.version != body.version: raise HTTPException(409, "Check-in was changed by another user")
    if body.checked_out_at and body.checked_out_at < body.checked_in_at: raise HTTPException(422, "Checkout cannot be before check-in")
    before = {"checked_in_at": row.checked_in_at.isoformat(), "checked_out_at": row.checked_out_at.isoformat() if row.checked_out_at else None}
    row.checked_in_at = body.checked_in_at; row.checked_out_at = body.checked_out_at; row.corrected_by_user_id = user.id; row.correction_reason = body.reason; row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="gym.checkin.correct", resource_type="gym_check_in", resource_id=row.id, changes={"before": before, "reason": body.reason}); db.commit(); return serialize(row)


@router.post("/gym/members/{client_id}/goals", status_code=201)
def add_goal(client_id: str, body: GoalBody, user: User = Depends(require_permissions("gym.measurements.manage")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id); row = FitnessGoal(organization_id=user.organization_id, client_id=client.id, created_by_user_id=user.id, **body.model_dump()); db.add(row); db.commit(); db.refresh(row); return serialize(row)


@router.patch("/gym/goals/{goal_id}")
def update_goal(goal_id: str, body: GoalUpdate, user: User = Depends(require_permissions("gym.measurements.manage")), db: Session = Depends(get_db)):
    row = tenant_get(db, FitnessGoal, goal_id, user); _client(db, user, row.client_id)
    if row.version != body.version: raise HTTPException(409, "Goal was changed by another user")
    for key, value in body.model_dump(exclude={"version"}, exclude_none=True).items(): setattr(row, key, value)
    row.version += 1; db.commit(); return serialize(row)


@router.post("/gym/members/{client_id}/workout-sessions", status_code=201)
def add_workout_session(client_id: str, body: SessionBody, user: User = Depends(require_permissions("gym.workouts.manage")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id); ensure_location(db, user, body.location_id)
    if body.workout_plan_id:
        plan = tenant_get(db, WorkoutPlan, body.workout_plan_id, user)
        if plan.client_id != client.id: raise HTTPException(422, "Workout plan belongs to another member")
    if body.trainer_employee_id: tenant_get(db, Employee, body.trainer_employee_id, user)
    now = datetime.now(timezone.utc); payload = body.model_dump()
    row = WorkoutSession(organization_id=user.organization_id, client_id=client.id, recorded_by_user_id=user.id, started_at=now if body.status in {"in_progress", "completed"} else None, completed_at=now if body.status == "completed" else None, **payload)
    db.add(row); db.commit(); db.refresh(row); return serialize(row)


@router.patch("/gym/workout-sessions/{session_id}")
def update_workout_session(session_id: str, body: SessionUpdate, user: User = Depends(require_permissions("gym.workouts.manage")), db: Session = Depends(get_db)):
    row = tenant_get(db, WorkoutSession, session_id, user, location_field="location_id"); _client(db, user, row.client_id)
    if row.version != body.version: raise HTTPException(409, "Workout session was changed by another user")
    now = datetime.now(timezone.utc)
    for key, value in body.model_dump(exclude={"version"}, exclude_none=True).items(): setattr(row, key, value)
    if body.status in {"in_progress", "completed"} and not row.started_at: row.started_at = now
    if body.status == "completed": row.completed_at = now
    row.version += 1; db.commit(); return serialize(row)


@router.post("/gym/members/{client_id}/coaching-notes", status_code=201)
def add_coaching_note(client_id: str, body: CoachingBody, user: User = Depends(require_permissions("gym.coaching.manage")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id)
    if body.visibility not in {"team", "managers", "assigned_staff", "author_only"}: raise HTTPException(422, "Invalid note visibility")
    if body.trainer_employee_id: tenant_get(db, Employee, body.trainer_employee_id, user)
    row = CoachingNote(organization_id=user.organization_id, client_id=client.id, recorded_by_user_id=user.id, **body.model_dump()); db.add(row); db.commit(); db.refresh(row); return serialize(row)


@router.put("/salon/clients/{client_id}/profile")
def save_salon_profile(client_id: str, body: SalonProfileBody, user: User = Depends(require_permissions("salon.notes.manage")), db: Session = Depends(get_db)):
    client = _client(db, user, client_id)
    row = db.execute(select(SalonClientProfile).where(SalonClientProfile.client_id == client.id)).scalar_one_or_none()
    if body.preferred_employee_id: tenant_get(db, Employee, body.preferred_employee_id, user)
    if not row:
        row = SalonClientProfile(organization_id=user.organization_id, client_id=client.id); db.add(row)
    elif body.version is not None and row.version != body.version: raise HTTPException(409, "Salon profile was changed by another user")
    for key, value in body.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.version += 1; db.commit(); db.refresh(row); return serialize(row)


@router.post("/ai/clients/{client_id}/chat")
async def client_copilot(client_id: str, body: ClientQuestion, user: User = Depends(require_permissions("ai.use")), db: Session = Depends(get_db)):
    workspace = client_workspace(client_id, "30d", user, db)
    from app.api.v1.ai import _process_chat
    from app.schemas import ChatRequest
    result = await _process_chat(
        ChatRequest(message=body.message.strip(), context={"kind": "client", "id": client_id},
                    idempotency_key=f"client:{client_id}:{secrets.token_hex(12)}"), user, db,
    )
    message = result["message"]
    return {"content": message["content"], "blocks": message.get("blocks", []),
            "evidence": message.get("citations", []), "pulse": workspace["pulse"],
            "suggested_actions": [item.get("recommended_action") for item in workspace["signals"] if item.get("recommended_action")][:3]}

    # Legacy fallback retained temporarily for migrations created before unified orchestration.
    evidence = []
    for item in workspace["brief"][:5]: evidence.extend(item.get("evidence") or [])
    client = workspace["client"]; industry = workspace["industry"]
    facts = [f"Client: {client['first_name']} {client['last_name']}", f"Industry: {industry}", f"Pulse: {workspace['pulse']['state']}"]
    facts.extend(f"{item['title']}: {item['detail']}" for item in workspace["brief"][:6])
    question = body.message.strip(); tamil = any("\u0b80" <= char <= "\u0bff" for char in question)
    if settings.AI_API_KEY:
        try:
            from openai import OpenAI
            from app.ai.orchestrator import selected_model
            prompt = "You are Edvatiq's client copilot. Answer only from the supplied facts. Be concise, preserve the user's language, explain uncertainty, and never diagnose or prescribe.\n\n" + "\n".join(facts) + f"\n\nQuestion: {question}"
            response = OpenAI(api_key=settings.AI_API_KEY, base_url=settings.OPENAI_BASE_URL or None).responses.create(model=selected_model(db, user), input=prompt)
            content = response.output_text
        except Exception:
            content = None
    else: content = None
    if not content:
        summary = " ".join(item["detail"] for item in workspace["brief"][:3])
        content = ("கிடைக்கக்கூடிய பதிவுகளின் அடிப்படையில்: " if tamil else "Based on the available records: ") + summary
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="ai.client_chat", resource_type="client", resource_id=client_id, question=question, tool="client_workspace")
    db.commit(); return {"content": content, "evidence": evidence[:12], "pulse": workspace["pulse"], "suggested_actions": [item.get("recommended_action") for item in workspace["signals"] if item.get("recommended_action")][:3]}
