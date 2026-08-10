"""Role-aware dashboard composition from permission-scoped operational data."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Appointment, Client, ClientSignal, Employee, Encounter, GymCheckIn, LabOrder,
    CollegeAssessment, CollegeAttendanceRecord, CollegeAttendanceSession,
    CollegeCohort, CollegeCourseOffering, CollegeDepartment, CollegeProgram,
    CollegeStudentProfile, Location, Membership, PatientProfile, Prescription,
    SaleInvoice, SalePayment, StockLevel, Task, TrainerAssignment, User,
)
from app.services.business_access import allowed_client_ids, allowed_location_ids, organization_for
from app.services.rbac import get_user_permissions, get_user_roles


RANGES = {7: "7d", 30: "30d", 90: "90d"}
ROLE_ORDER = (
    "owner", "manager", "academic-admin", "faculty", "admissions", "trainer",
    "front-desk", "stylist", "practitioner", "receptionist", "pharmacist",
    "accountant", "inventory-staff", "staff",
)


def _window(org_timezone: str, days: int) -> dict:
    tz = ZoneInfo(org_timezone)
    local_now = datetime.now(tz)
    local_end = local_now
    local_start = datetime.combine(local_now.date() - timedelta(days=days - 1), time.min, tzinfo=tz)
    prior_start = local_start - timedelta(days=days)
    today_start = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    tomorrow_start = today_start + timedelta(days=1)
    return {
        "tz": tz,
        "now": local_now,
        "start": local_start.astimezone(timezone.utc),
        "end": local_end.astimezone(timezone.utc),
        "prior_start": prior_start.astimezone(timezone.utc),
        "today_start": today_start.astimezone(timezone.utc),
        "tomorrow_start": tomorrow_start.astimezone(timezone.utc),
        "local_start_date": local_start.date(),
        "local_today": local_now.date(),
    }


def _percent(current: int, previous: int) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) * 100 / previous, 1)


def _location_clause(model, location_ids: set[str] | None):
    if location_ids is None:
        return None
    if not location_ids:
        return model.location_id.in_([])
    return model.location_id.in_(location_ids)


def _client_clause(model, client_ids: set[str] | None):
    if client_ids is None:
        return None
    if not client_ids:
        return model.client_id.in_([])
    return model.client_id.in_(client_ids)


def _scopes(db: Session, user: User, location_id: str | None) -> tuple[set[str] | None, set[str] | None]:
    locations = allowed_location_ids(db, user)
    if location_id:
        if locations is not None and location_id not in locations:
            return set(), set()
        locations = {location_id}
    clients = allowed_client_ids(db, user)
    return locations, clients


def _sum(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def _count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def _roles(db: Session, user: User) -> list[str]:
    present = {role.slug for role in get_user_roles(db, user)}
    return [role for role in ROLE_ORDER if role in present] or sorted(present)


def _metric(identifier: str, label: str, value, *, format: str = "number", previous=None, href=None, tone="neutral") -> dict:
    comparison = None
    if previous is not None:
        comparison = {"previous": previous, "change_percent": _percent(int(value), int(previous))}
    return {
        "id": identifier, "label": label, "value": value, "format": format,
        "comparison": comparison, "destination": href, "tone": tone,
    }


def _daily_collections(db: Session, user: User, window: dict, locations: set[str] | None, clients: set[str] | None) -> list[dict]:
    statement = (
        select(SalePayment.created_at, SalePayment.amount_paise)
        .join(SaleInvoice, SaleInvoice.id == SalePayment.invoice_id)
        .where(
            SalePayment.organization_id == user.organization_id,
            SalePayment.status == "captured",
            SalePayment.created_at >= window["start"],
            SalePayment.created_at <= window["end"],
        )
    )
    location_filter = _location_clause(SaleInvoice, locations)
    client_filter = _client_clause(SaleInvoice, clients)
    if location_filter is not None:
        statement = statement.where(location_filter)
    if client_filter is not None:
        statement = statement.where(client_filter)
    grouped: dict[date, int] = defaultdict(int)
    for occurred_at, amount in db.execute(statement):
        grouped[occurred_at.astimezone(window["tz"]).date()] += int(amount)
    points = []
    cursor = window["local_start_date"]
    while cursor <= window["local_today"]:
        points.append({"date": cursor.isoformat(), "value_paise": grouped[cursor]})
        cursor += timedelta(days=1)
    return points


def _sales_status_breakdown(db: Session, user: User, window: dict, locations: set[str] | None, clients: set[str] | None) -> list[dict]:
    statement = select(
        SaleInvoice.status,
        func.coalesce(func.sum(SaleInvoice.total_paise), 0),
    ).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.created_at >= window["start"],
        SaleInvoice.created_at <= window["end"],
        SaleInvoice.status.notin_(["draft", "void", "refunded"]),
    )
    for clause in (_location_clause(SaleInvoice, locations), _client_clause(SaleInvoice, clients)):
        if clause is not None:
            statement = statement.where(clause)
    rows = db.execute(statement.group_by(SaleInvoice.status)).all()
    labels = {
        "paid": "Paid",
        "partially_paid": "Partially paid",
        "issued": "Unpaid",
        "overdue": "Overdue",
        "cancelled": "Cancelled",
    }
    order = {"paid": 0, "partially_paid": 1, "issued": 2, "overdue": 3, "cancelled": 4}
    return [{
        "label": labels.get(status, str(status).replace("_", " ").title()),
        "value_paise": int(value or 0),
        "status": status,
    } for status, value in sorted(rows, key=lambda row: order.get(row[0], 99)) if int(value or 0) > 0]


def _financial_widgets(db: Session, user: User, permissions: set[str], window: dict, locations, clients, industry: str) -> tuple[list[dict], list[dict]]:
    if "sales.view" not in permissions:
        return [], []
    base_payment = (
        select(func.coalesce(func.sum(SalePayment.amount_paise), 0))
        .join(SaleInvoice, SaleInvoice.id == SalePayment.invoice_id)
        .where(SalePayment.organization_id == user.organization_id, SalePayment.status == "captured")
    )
    base_invoice = select(func.coalesce(func.sum(SaleInvoice.total_paise), 0)).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.status.notin_(["draft", "void", "refunded"]),
    )
    location_filter = _location_clause(SaleInvoice, locations)
    client_filter = _client_clause(SaleInvoice, clients)
    for clause in (location_filter, client_filter):
        if clause is not None:
            base_payment = base_payment.where(clause)
            base_invoice = base_invoice.where(clause)

    current_collections = _sum(db, base_payment.where(SalePayment.created_at.between(window["start"], window["end"])))
    prior_collections = _sum(db, base_payment.where(SalePayment.created_at.between(window["prior_start"], window["start"])))
    today_collections = _sum(db, base_payment.where(SalePayment.created_at.between(window["today_start"], window["tomorrow_start"])))
    current_revenue = _sum(db, base_invoice.where(SaleInvoice.created_at.between(window["start"], window["end"])))
    prior_revenue = _sum(db, base_invoice.where(SaleInvoice.created_at.between(window["prior_start"], window["start"])))
    outstanding = _sum(db, select(func.coalesce(func.sum(SaleInvoice.total_paise - SaleInvoice.paid_paise), 0)).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.status.in_(["issued", "partially_paid"]),
        *([location_filter] if location_filter is not None else []),
        *([client_filter] if client_filter is not None else []),
    ))
    invoice_label = "Fees invoiced" if industry == "college" else "Invoiced revenue"
    outstanding_label = "Fees outstanding" if industry == "college" else "Outstanding"
    metrics = [
        _metric("collections_today", "Collected today", today_collections, format="money", href={"route": "sales", "filter": "paid_today"}),
        _metric("collections_period", "Collections", current_collections, format="money", previous=prior_collections, href={"route": "sales"}),
        _metric("revenue_period", invoice_label, current_revenue, format="money", previous=prior_revenue, href={"route": "sales"}),
        _metric("outstanding", outstanding_label, outstanding, format="money", href={"route": "sales", "filter": "outstanding"}, tone="warning" if outstanding else "neutral"),
    ]
    widgets = [
        {
            "id": "collections_trend", "kind": "line_chart", "title": "Collections trend",
            "subtitle": "Captured payments in the selected period", "data": _daily_collections(db, user, window, locations, clients),
            "format": "money", "destination": {"route": "sales"}, "size": "wide",
        },
        {
            "id": "sales_status_mix", "kind": "donut_chart", "title": "Fee payment mix" if industry == "college" else "Sales payment mix",
            "subtitle": "Fee value by payment status" if industry == "college" else "Invoiced value by payment status", "data": _sales_status_breakdown(db, user, window, locations, clients),
            "x_key": "label", "series": [{"key": "value_paise", "label": "Invoiced value"}],
            "format": "money", "destination": {"route": "sales"}, "size": "compact",
            "empty": {
                "title": "No issued fees in this period" if industry == "college" else "No issued sales in this period",
                "message": "Paid and outstanding invoice value will appear here.",
            },
        },
    ]
    return metrics, widgets


def _daily_new_clients(db: Session, user: User, window: dict, locations: set[str] | None, clients: set[str] | None, industry: str) -> list[dict]:
    if industry == "college":
        statement = select(CollegeStudentProfile.admitted_on).join(
            Client, Client.id == CollegeStudentProfile.client_id,
        ).where(
            CollegeStudentProfile.organization_id == user.organization_id,
            CollegeStudentProfile.admitted_on >= window["local_start_date"],
            CollegeStudentProfile.admitted_on <= window["local_today"],
        )
    else:
        statement = select(Client.created_at).where(
            Client.organization_id == user.organization_id,
            Client.created_at >= window["start"],
            Client.created_at <= window["end"],
        )
    if locations is not None:
        statement = statement.where(Client.home_location_id.in_(locations))
    if clients is not None:
        statement = statement.where(Client.id.in_(clients))
    grouped: dict[date, int] = defaultdict(int)
    for occurred_at in db.scalars(statement):
        if isinstance(occurred_at, datetime):
            timestamp = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=timezone.utc)
            occurred_on = timestamp.astimezone(window["tz"]).date()
        else:
            occurred_on = occurred_at
        grouped[occurred_on] += 1
    points = []
    cursor = window["local_start_date"]
    while cursor <= window["local_today"]:
        points.append({"date": cursor.isoformat(), "value": grouped[cursor]})
        cursor += timedelta(days=1)
    return points


def _client_widgets(db: Session, user: User, permissions: set[str], window: dict, locations, clients, industry: str) -> tuple[list[dict], list[dict]]:
    can_view = "clients.view" in permissions
    if industry == "college":
        can_view = can_view or bool({"college.students.view", "college.students.manage"} & permissions)
    if not can_view:
        return [], []
    if industry == "college":
        base = select(func.count(CollegeStudentProfile.id)).join(
            Client, Client.id == CollegeStudentProfile.client_id,
        ).where(CollegeStudentProfile.organization_id == user.organization_id)
        active_clause = CollegeStudentProfile.status == "active"
        created_at = CollegeStudentProfile.admitted_on
    else:
        base = select(func.count(Client.id)).where(Client.organization_id == user.organization_id)
        active_clause = Client.status == "active"
        created_at = Client.created_at
    if locations is not None:
        base = base.where(Client.home_location_id.in_(locations))
    if clients is not None:
        base = base.where(Client.id.in_(clients))
    active = _count(db, base.where(active_clause))
    if industry == "college":
        prior_start = window["prior_start"].astimezone(window["tz"]).date()
        prior_end = window["local_start_date"] - timedelta(days=1)
        current_new = _count(db, base.where(created_at.between(window["local_start_date"], window["local_today"])))
        prior_new = _count(db, base.where(created_at.between(prior_start, prior_end)))
    else:
        current_new = _count(db, base.where(created_at.between(window["start"], window["end"])))
        prior_new = _count(db, base.where(created_at.between(window["prior_start"], window["start"])))
    noun = "students" if industry == "college" else "clients"
    route = {"route": "college", "section": "students"} if industry == "college" else {"route": "clients"}
    metrics = [
        _metric(f"active_{noun}", f"Active {noun}", active, href={**route, "filter": "active"}),
        _metric(f"new_{noun}", f"New {noun}", current_new, previous=prior_new, href={**route, "filter": "new"}),
    ]
    widgets = [{
        "id": "student_growth" if industry == "college" else "client_growth",
        "kind": "bar_chart", "title": "Student growth" if industry == "college" else "New-client growth",
        "subtitle": "Students admitted in the selected period" if industry == "college" else "Clients added in the selected period",
        "data": _daily_new_clients(db, user, window, locations, clients, industry),
        "format": "number", "destination": {**route, "filter": "new"}, "size": "wide",
        "empty": {
            "title": f"No new {noun} in this period",
            "message": f"New {noun[:-1]} registrations will appear here.",
        },
    }]
    return metrics, widgets


def _operations_widgets(db: Session, user: User, permissions: set[str], window: dict, locations, clients, roles: list[str], industry: str) -> tuple[list[dict], list[dict]]:
    metrics: list[dict] = []
    widgets: list[dict] = []
    if industry != "college" and "appointments.view" in permissions:
        appointment = select(func.count(Appointment.id)).where(
            Appointment.organization_id == user.organization_id,
            Appointment.starts_at >= window["today_start"], Appointment.starts_at < window["tomorrow_start"],
            Appointment.status.notin_(["cancelled", "no_show"]),
        )
        for clause in (_location_clause(Appointment, locations), _client_clause(Appointment, clients)):
            if clause is not None:
                appointment = appointment.where(clause)
        metrics.append(_metric("appointments_today", "Appointments today", _count(db, appointment), href={"route": "calendar", "date": "today"}))

    if industry != "college" and "inventory.view" in permissions:
        stock = select(func.count(StockLevel.id)).where(
            StockLevel.organization_id == user.organization_id,
            StockLevel.quantity_milli <= StockLevel.reorder_level_milli,
        )
        location_filter = _location_clause(StockLevel, locations)
        if location_filter is not None:
            stock = stock.where(location_filter)
        low = _count(db, stock)
        metrics.append(_metric("stock_risk", "Stock risks", low, href={"route": "inventory", "filter": "low"}, tone="warning" if low else "neutral"))

    if industry == "gym" and "gym.attendance.view" in permissions:
        checkins = select(func.count(GymCheckIn.id)).where(
            GymCheckIn.organization_id == user.organization_id,
            GymCheckIn.checked_in_at >= window["today_start"], GymCheckIn.checked_in_at < window["tomorrow_start"],
        )
        occupancy = select(func.count(GymCheckIn.id)).where(
            GymCheckIn.organization_id == user.organization_id,
            GymCheckIn.checked_out_at.is_(None),
        )
        for clause in (_location_clause(GymCheckIn, locations), _client_clause(GymCheckIn, clients)):
            if clause is not None:
                checkins = checkins.where(clause)
                occupancy = occupancy.where(clause)
        metrics.extend([
            _metric("checkins_today", "Check-ins today", _count(db, checkins), href={"route": "gym", "section": "attendance"}),
            _metric("current_occupancy", "Currently inside", _count(db, occupancy), href={"route": "gym", "section": "attendance"}),
        ])
        expiring = select(func.count(Membership.id)).where(
            Membership.organization_id == user.organization_id, Membership.status == "active",
            Membership.ends_on.between(window["local_today"], window["local_today"] + timedelta(days=7)),
        )
        for clause in (_location_clause(Membership, locations), _client_clause(Membership, clients)):
            if clause is not None:
                expiring = expiring.where(clause)
        metrics.append(_metric("renewals_due", "Renewals due", _count(db, expiring), href={"route": "gym", "section": "memberships", "filter": "expiring"}, tone="warning"))

    if industry == "clinic" and "clinic.view" in permissions:
        queue = select(func.count(Appointment.id)).where(
            Appointment.organization_id == user.organization_id,
            Appointment.starts_at >= window["today_start"], Appointment.starts_at < window["tomorrow_start"],
            Appointment.status.in_(["checked_in", "in_progress"]),
        )
        for clause in (_location_clause(Appointment, locations), _client_clause(Appointment, clients)):
            if clause is not None:
                queue = queue.where(clause)
        metrics.append(_metric("patient_queue", "Patient queue", _count(db, queue), href={"route": "clinic", "section": "queue"}))
        if "clinical.view" in permissions:
            unsigned = select(func.count(Encounter.id)).where(
                Encounter.organization_id == user.organization_id, Encounter.status == "open",
            )
            pending_labs = select(func.count(LabOrder.id)).where(
                LabOrder.organization_id == user.organization_id, LabOrder.status.in_(["ordered", "collected", "processing"]),
            )
            metrics.extend([
                _metric("unsigned_encounters", "Unsigned encounters", _count(db, unsigned), href={"route": "clinic", "section": "encounters"}, tone="warning"),
                _metric("pending_labs", "Pending labs", _count(db, pending_labs), href={"route": "clinic", "section": "labs"}),
            ])
        if "pharmacist" in roles or "pharmacy.dispense" in permissions:
            prescriptions = select(func.count(Prescription.id)).where(
                Prescription.organization_id == user.organization_id, Prescription.status == "signed",
            )
            metrics.append(_metric("awaiting_dispense", "Awaiting dispensing", _count(db, prescriptions), href={"route": "clinic", "section": "pharmacy"}))

    if industry == "college" and "college.view" in permissions:
        department_scope = None
        if locations is not None:
            department_scope = CollegeDepartment.id.in_([]) if not locations else or_(
                CollegeDepartment.location_id.is_(None),
                CollegeDepartment.location_id.in_(locations),
            )
        programs = select(func.count(CollegeProgram.id)).join(
            CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id,
        ).where(
            CollegeProgram.organization_id == user.organization_id,
            CollegeProgram.is_active.is_(True),
        )
        if department_scope is not None:
            programs = programs.where(department_scope)
        metrics.append(_metric(
            "active_programs", "Active programs", _count(db, programs),
            href={"route": "college", "section": "academics"},
        ))

        classes = select(func.count(CollegeAttendanceSession.id)).join(
            CollegeCourseOffering, CollegeCourseOffering.id == CollegeAttendanceSession.offering_id,
        ).join(
            CollegeCohort, CollegeCohort.id == CollegeCourseOffering.cohort_id,
        ).join(
            CollegeProgram, CollegeProgram.id == CollegeCohort.program_id,
        ).join(
            CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id,
        ).where(
            CollegeAttendanceSession.organization_id == user.organization_id,
            CollegeAttendanceSession.held_on == window["local_today"],
        )
        if department_scope is not None:
            classes = classes.where(department_scope)
        metrics.append(_metric(
            "classes_today", "Classes recorded today", _count(db, classes),
            href={"route": "college", "section": "attendance"},
        ))

        if "college.attendance.view" in permissions or "college.attendance.mark" in permissions:
            attendance = select(
                func.count(CollegeAttendanceRecord.id),
                func.sum(case((CollegeAttendanceRecord.status.in_(["present", "late"]), 1), else_=0)),
            ).join(
                CollegeAttendanceSession, CollegeAttendanceSession.id == CollegeAttendanceRecord.session_id,
            ).join(
                CollegeStudentProfile, CollegeStudentProfile.id == CollegeAttendanceRecord.student_profile_id,
            ).join(
                Client, Client.id == CollegeStudentProfile.client_id,
            ).where(
                CollegeAttendanceRecord.organization_id == user.organization_id,
                CollegeAttendanceSession.held_on >= window["local_start_date"],
                CollegeAttendanceSession.held_on <= window["local_today"],
            )
            if locations is not None:
                attendance = attendance.where(Client.home_location_id.in_(locations))
            if clients is not None:
                attendance = attendance.where(Client.id.in_(clients))
            total, present = db.execute(attendance).one()
            percentage = round(int(present or 0) * 100 / int(total), 1) if total else 0
            metrics.append(_metric(
                "student_attendance", "Student attendance", percentage, format="percent",
                href={"route": "college", "section": "attendance"},
                tone="warning" if total and percentage < 75 else "neutral",
            ))

        if "college.assessments.view" in permissions or "college.assessments.manage" in permissions:
            assessments = select(func.count(CollegeAssessment.id)).join(
                CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id,
            ).join(
                CollegeCohort, CollegeCohort.id == CollegeCourseOffering.cohort_id,
            ).join(
                CollegeProgram, CollegeProgram.id == CollegeCohort.program_id,
            ).join(
                CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id,
            ).where(
                CollegeAssessment.organization_id == user.organization_id,
                CollegeAssessment.status.in_(["draft", "published"]),
                CollegeAssessment.due_on.between(window["local_today"], window["local_today"] + timedelta(days=14)),
            )
            if department_scope is not None:
                assessments = assessments.where(department_scope)
            due = _count(db, assessments)
            metrics.append(_metric(
                "assessments_due", "Assessments due", due,
                href={"route": "college", "section": "assessments"},
                tone="warning" if due else "neutral",
            ))
    return metrics, widgets


def _attention_widget(db: Session, user: User, permissions: set[str], locations, clients, industry: str) -> dict | None:
    if "client_signals.view" not in permissions:
        return None
    statement = select(ClientSignal, Client).join(Client, Client.id == ClientSignal.client_id).where(
        ClientSignal.organization_id == user.organization_id,
        ClientSignal.status.in_(["open", "snoozed"]),
        or_(ClientSignal.snoozed_until.is_(None), ClientSignal.snoozed_until <= datetime.now(timezone.utc)),
    )
    if locations is not None:
        statement = statement.where(or_(ClientSignal.location_id.is_(None), ClientSignal.location_id.in_(locations)))
    if clients is not None:
        statement = statement.where(ClientSignal.client_id.in_(clients))
    rows = db.execute(statement.order_by(
        ClientSignal.pulse_state.desc(), ClientSignal.generated_at.desc(),
    ).limit(6)).all()
    noun = "Students" if industry == "college" else "Clients"
    return {
        "id": "student_attention" if industry == "college" else "client_attention",
        "kind": "attention", "title": f"{noun} needing attention",
        "subtitle": "Explainable signals from current operational data", "size": "wide",
        "data": [{
            "id": signal.id, "state": signal.pulse_state, "title": signal.title,
            "reason": signal.explanation, "client": {
                "id": client.id, "name": f"{client.first_name} {client.last_name}".strip(),
                "client_number": client.client_number,
            },
            "destination": {"kind": "client", "id": client.id},
        } for signal, client in rows],
        "empty": {"title": f"No urgent {noun.lower()} signals", "message": "There is nothing requiring attention in this scope."},
    }


def _my_work_widget(db: Session, user: User, permissions: set[str], window: dict, locations, clients, roles: list[str], industry: str) -> dict:
    work: list[dict] = []
    task_statement = select(Task).where(
        Task.organization_id == user.organization_id, Task.status != "done",
        or_(Task.assigned_to_user_id == user.id, Task.assigned_to_user_id.is_(None)),
    )
    if locations is not None:
        task_statement = task_statement.where(or_(Task.location_id.is_(None), Task.location_id.in_(locations)))
    if clients is not None:
        task_statement = task_statement.where(or_(Task.client_id.is_(None), Task.client_id.in_(clients)))
    for task in db.execute(task_statement.order_by(Task.due_at.asc().nullslast()).limit(6)).scalars():
        work.append({
            "id": task.id, "source": "Task", "title": task.title,
            "reason": task.description or "Assigned work", "due_at": task.due_at,
            "status": task.status, "priority": task.priority,
            "destination": {"route": "home", "drawer": "tasks", "id": task.id},
        })

    employee = db.execute(select(Employee).where(Employee.user_id == user.id, Employee.organization_id == user.organization_id)).scalar_one_or_none()
    if employee and "appointments.view" in permissions:
        appointments = select(Appointment, Client).join(Client, Client.id == Appointment.client_id).where(
            Appointment.organization_id == user.organization_id,
            Appointment.employee_id == employee.id,
            Appointment.starts_at >= window["now"].astimezone(timezone.utc),
            Appointment.starts_at < window["tomorrow_start"] + timedelta(days=1),
            Appointment.status.in_(["scheduled", "confirmed", "checked_in"]),
        )
        for clause in (_location_clause(Appointment, locations), _client_clause(Appointment, clients)):
            if clause is not None:
                appointments = appointments.where(clause)
        for appointment, client in db.execute(appointments.order_by(Appointment.starts_at).limit(max(0, 8 - len(work)))).all():
            work.append({
                "id": appointment.id, "source": "Calendar", "title": f"{client.first_name} {client.last_name}".strip(),
                "reason": "Upcoming appointment", "due_at": appointment.starts_at,
                "status": appointment.status, "priority": "normal",
                "destination": {"route": "calendar", "id": appointment.id},
            })
    return {
        "id": "my_work", "kind": "work_queue", "title": "My work",
        "subtitle": "Your assigned and time-sensitive work", "size": "wide", "data": work[:8],
        "empty": {"title": "You are all caught up", "message": "No assigned or time-sensitive work is open."},
    }


def _quick_actions(permissions: set[str], industry: str) -> list[dict]:
    actions = []
    if industry == "college":
        candidates = [
            ("college.students.manage", "admit_student", "Admit student", {"route": "college", "section": "students", "action": "new"}),
            ("college.attendance.mark", "record_attendance", "Record attendance", {"route": "college", "section": "attendance", "action": "new"}),
            ("college.assessments.manage", "new_assessment", "New assessment", {"route": "college", "section": "assessments", "action": "new"}),
            ("college.fees.manage", "assign_student_fee", "Assign student fee", {"route": "college", "section": "fees", "action": "assign"}),
        ]
    else:
        candidates = [
            ("clients.manage", "new_client", "Add client", {"route": "clients", "action": "new"}),
            ("appointments.manage", "new_appointment", "Book appointment", {"route": "calendar", "action": "new"}),
            ("sales.manage", "new_sale", "New sale", {"route": "sales", "action": "new"}),
            ("inventory.adjust", "stock_adjustment", "Adjust stock", {"route": "inventory", "action": "adjust"}),
        ]
    if industry == "gym":
        candidates.insert(1, ("gym.attendance.mark", "member_checkin", "Check in client", {"route": "gym", "section": "attendance", "action": "checkin"}))
    elif industry == "clinic":
        candidates.insert(1, ("appointments.manage", "patient_checkin", "Check in patient", {"route": "clinic", "section": "queue", "action": "checkin"}))
    elif industry == "salon":
        candidates.insert(1, ("appointments.manage", "walkin", "Start walk-in", {"route": "salon", "section": "walkins", "action": "new"}))
    for permission, identifier, label, destination in candidates:
        if permission in permissions:
            actions.append({"id": identifier, "label": label, "destination": destination})
    return actions[:5]


def build_dashboard_workspace(db: Session, user: User, location_id: str | None, days: int) -> dict:
    org = organization_for(db, user)
    permissions = get_user_permissions(db, user)
    roles = _roles(db, user)
    window = _window(org.timezone, days)
    locations, clients = _scopes(db, user, location_id)
    generated_at = datetime.now(timezone.utc)

    financial_metrics, financial_widgets = _financial_widgets(db, user, permissions, window, locations, clients, org.industry.value)
    client_metrics, client_widgets = _client_widgets(db, user, permissions, window, locations, clients, org.industry.value)
    operation_metrics, operation_widgets = _operations_widgets(
        db, user, permissions, window, locations, clients, roles, org.industry.value,
    )
    widgets = [
        _my_work_widget(db, user, permissions, window, locations, clients, roles, org.industry.value),
        *financial_widgets, *client_widgets, *operation_widgets,
    ]
    attention = _attention_widget(db, user, permissions, locations, clients, org.industry.value)
    if attention:
        widgets.append(attention)
    metrics = [*financial_metrics, *client_metrics, *operation_metrics]
    series = [{
        "id": widget["id"], "title": widget["title"], "type": "bar" if widget.get("kind") == "bar_chart" else "area",
        "format": widget.get("format", "number"), "points": widget.get("data", []),
        "destination": widget.get("destination"),
    } for widget in widgets if widget.get("kind") in {"line_chart", "bar_chart"}]
    breakdowns = [{
        "id": widget["id"], "title": widget["title"], "type": "donut",
        "format": widget.get("format", "number"), "items": widget.get("data", []),
        "destination": widget.get("destination"),
    } for widget in widgets if widget.get("kind") == "donut_chart"]
    queues = [{
        "id": widget["id"], "title": widget["title"], "items": widget.get("data", []),
    } for widget in widgets if widget.get("kind") == "work_queue"]
    alerts = [{
        "id": item["id"], "severity": item["state"], "title": item["title"],
        "evidence": item["reason"], "entity": item["client"], "destination": item["destination"],
    } for widget in widgets if widget.get("kind") == "attention" for item in widget.get("data", [])]
    return {
        "schema_version": 2,
        "industry": org.industry.value,
        "roles": roles,
        "range": RANGES[days],
        "scope": {"location_id": location_id, "location_restricted": locations is not None},
        "metrics": metrics,
        "series": series,
        "breakdowns": breakdowns,
        "queues": queues,
        "alerts": alerts,
        "widgets": widgets,
        "quick_actions": _quick_actions(permissions, org.industry.value),
        "capabilities": {
            "customize_layout": True,
            "view_financials": "sales.view" in permissions,
            "view_client_signals": "client_signals.view" in permissions,
            "view_team": "employees.view" in permissions,
        },
        "source": {"generated_at": generated_at, "timezone": org.timezone, "is_live": True, "freshness": "live"},
    }
