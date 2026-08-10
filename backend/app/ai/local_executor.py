"""Allowlisted, permission-scoped execution for local business queries."""
from datetime import date, datetime, timedelta, timezone
from time import perf_counter

from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.ai.contracts import AIResponseV1, ResponseBlock, compose_response
from app.ai.local_contracts import BusinessQueryV1, QueryClarification
from app.ai.personalization import AssistantPreferences, style_deterministic_summary
from app.ai.record_serializers import sale_invoice_context, serialize_sale_invoice
from app.models import (
    Allergy, Appointment, CatalogItem, ClassBooking, ClientCommitment, ClientMemory, ClientSignal,
    CoachingNote, Client, Diagnosis, DietPlan, Dispense, Employee, EmployeeLocation, Encounter,
    Equipment, FitnessGoal, FitnessMeasurement, GymCheckIn, GymClass, LabOrder, LabResult, LabTest,
    Location, Membership, MembershipPlan, Notification, Organization, OutboundMessage, PatientProfile,
    Prescription, SaleInvoice, SaleLine, SalePayment, SalonClientProfile, StockLevel,
    StockMovement, Task, TrainerAssignment, User, Vital, WorkoutPlan, WorkoutSession,
)
from app.services.business_access import allowed_client_ids, allowed_location_ids, filter_clients
from app.services.rbac import get_user_roles, user_has_permissions


SUBJECT_PERMISSIONS = {
    "clients": "clients.view", "employees": "employees.view", "catalog": "catalog.view",
    "inventory": "inventory.view", "stock_movements": "inventory.view",
    "appointments": "appointments.view", "invoices": "sales.view", "payments": "sales.view",
    "purchases": "sales.view", "tasks": "dashboard.view", "memberships": "gym.memberships.view",
    "checkins": "gym.attendance.view", "classes": "gym.classes.view", "equipment": "gym.equipment.view",
    "measurements": "gym.measurements.view", "goals": "gym.measurements.view",
    "workouts": "gym.workouts.view", "diets": "gym.diets.view", "coaching": "gym.coaching.view",
    "signals": "client_signals.view", "commitments": "client_memory.view",
    "memories": "client_memory.view", "class_bookings": "gym.classes.view",
    "salon_profiles": "salon.notes.view", "patients": "clinical.view", "encounters": "clinical.view",
    "prescriptions": "clinical.view", "lab_orders": "clinical.view",
    "vitals": "clinical.view", "allergies": "clinical.view", "diagnoses": "clinical.view",
    "lab_results": "clinical.view", "dispenses": "clinical.view",
    "communications": "notifications.send", "notifications": "ai.use", "locations": "dashboard.view",
}

OPERATION_PERMISSIONS = {
    ("catalog", "rank"): "sales.view",
    ("clients", "rank"): "sales.view",
}

SUBJECT_MODULES = {
    **{subject: "gym" for subject in {
        "memberships", "checkins", "classes", "class_bookings", "equipment", "measurements",
        "goals", "workouts", "diets", "coaching",
    }},
    "salon_profiles": "salon",
    **{subject: "clinic" for subject in {
        "patients", "encounters", "vitals", "allergies", "diagnoses", "prescriptions",
        "lab_orders", "lab_results", "dispenses",
    }},
}

SUBJECT_MODEL = {
    "clients": Client, "employees": Employee, "catalog": CatalogItem, "inventory": StockLevel,
    "stock_movements": StockMovement, "appointments": Appointment, "invoices": SaleInvoice,
    "payments": SalePayment, "purchases": SaleLine, "tasks": Task, "memberships": Membership, "checkins": GymCheckIn,
    "classes": GymClass, "equipment": Equipment, "measurements": FitnessMeasurement,
    "goals": FitnessGoal, "workouts": WorkoutSession, "diets": DietPlan, "coaching": CoachingNote,
    "signals": ClientSignal, "commitments": ClientCommitment, "salon_profiles": SalonClientProfile,
    "memories": ClientMemory, "class_bookings": ClassBooking,
    "patients": PatientProfile, "encounters": Encounter, "prescriptions": Prescription,
    "lab_orders": LabOrder, "vitals": Vital, "allergies": Allergy, "diagnoses": Diagnosis,
    "lab_results": LabResult, "dispenses": Dispense,
    "communications": OutboundMessage, "notifications": Notification,
    "locations": Location,
}

DATE_FIELD = {
    "clients": Client.created_at, "employees": Employee.created_at, "catalog": CatalogItem.created_at,
    "inventory": StockLevel.updated_at, "stock_movements": StockMovement.created_at,
    "appointments": Appointment.starts_at, "invoices": SaleInvoice.created_at,
    "payments": SalePayment.created_at, "purchases": SaleInvoice.created_at,
    "tasks": Task.due_at, "memberships": Membership.ends_on,
    "checkins": GymCheckIn.checked_in_at, "classes": GymClass.starts_at,
    "equipment": Equipment.next_service_on, "measurements": FitnessMeasurement.measured_on,
    "goals": FitnessGoal.created_at, "workouts": WorkoutSession.scheduled_for,
    "diets": DietPlan.starts_on, "coaching": CoachingNote.created_at, "signals": ClientSignal.generated_at,
    "commitments": ClientCommitment.due_at, "salon_profiles": SalonClientProfile.updated_at,
    "memories": ClientMemory.updated_at, "class_bookings": ClassBooking.created_at,
    "patients": PatientProfile.created_at, "encounters": Encounter.created_at,
    "prescriptions": Prescription.created_at, "lab_orders": LabOrder.created_at,
    "vitals": Vital.created_at, "allergies": Allergy.created_at, "diagnoses": Diagnosis.created_at,
    "lab_results": LabResult.created_at, "dispenses": Dispense.dispensed_at,
    "communications": OutboundMessage.created_at, "notifications": Notification.created_at,
    "locations": Location.created_at,
}

STATUS_FIELD = {
    "clients": Client.status, "employees": Employee.status, "appointments": Appointment.status,
    "invoices": SaleInvoice.status, "payments": SalePayment.status, "tasks": Task.status,
    "memberships": Membership.status, "classes": GymClass.status, "equipment": Equipment.status,
    "goals": FitnessGoal.status, "workouts": WorkoutSession.status, "signals": ClientSignal.status,
    "commitments": ClientCommitment.status, "encounters": Encounter.status,
    "allergies": Allergy.status,
    "prescriptions": Prescription.status, "lab_orders": LabOrder.status,
    "communications": OutboundMessage.status,
}

TITLES = {
    "clients": "Clients", "employees": "Team", "catalog": "Products and services",
    "inventory": "Inventory", "stock_movements": "Stock history", "appointments": "Appointments",
    "invoices": "Invoices", "payments": "Payments", "purchases": "Purchases", "tasks": "Tasks", "memberships": "Memberships",
    "checkins": "Check-ins", "classes": "Classes", "equipment": "Equipment",
    "measurements": "Measurements", "goals": "Goals", "workouts": "Workouts", "diets": "Diet plans",
    "coaching": "Coaching notes", "signals": "Clients needing attention", "commitments": "Commitments",
    "memories": "Client memory", "class_bookings": "Class bookings",
    "salon_profiles": "Salon preferences", "patients": "Patients", "encounters": "Encounters",
    "prescriptions": "Prescriptions", "lab_orders": "Lab orders", "communications": "Communications",
    "vitals": "Vitals", "allergies": "Allergies", "diagnoses": "Diagnoses",
    "lab_results": "Lab results", "dispenses": "Pharmacy dispensing",
    "notifications": "Notifications", "locations": "Locations",
}


def execute_local_query(
    db: Session,
    user: User,
    query: BusinessQueryV1,
    conversation_id: str,
    preferences: AssistantPreferences | None = None,
) -> dict:
    started = perf_counter()
    access_error = _query_access_error(db, user, query)
    if access_error:
        result = access_error
    elif query.operation in {"aggregate", "count", "compare", "trend", "group", "rank"}:
        result = _execute_metric(db, user, query)
    elif query.operation == "buyers":
        result = _execute_buyers(db, user, query, 0, query.limit)
    elif query.operation == "relationship":
        result = _execute_relationship(db, user, query)
    elif query.operation == "detail" or query.operation == "reverse_lookup":
        result = _execute_detail(db, user, query)
    else:
        result = _execute_records(db, user, query, 0, query.limit)

    if result.get("count", 0) > query.limit and not result.get("result_session_id"):
        from app.models import AIResultSession
        session = AIResultSession(
            organization_id=user.organization_id, user_id=user.id, conversation_id=conversation_id,
            tool_name="local_query", query_spec=query.model_dump(mode="json"), result_type=query.subject,
            total_count=result["count"], expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        db.add(session); db.flush(); result["result_session_id"] = session.id
    summary = style_deterministic_summary(_summary(query, result), query.language, preferences)
    response = _compose(summary, result)
    return {
        "content": summary,
        "tool_calls": [{"name": "local_query", "arguments": query.model_dump(mode="json"), "result": result}],
        "model": "database", "route": "business", "response": response.model_dump(mode="json"),
        "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
                  "embedding_tokens": 0, "provider_requests": 0, "tool_calls": 1,
                  "tool_latency_ms": int((perf_counter() - started) * 1000),
                  "latency_ms": int((perf_counter() - started) * 1000)},
    }


def clarification_response(clarification: QueryClarification) -> dict:
    result = {
        "count": len(clarification.candidates),
        "items": clarification.candidates,
        "presentation": {"display": "cards", "title": "Choose a matching record"},
    }
    response = compose_response(
        clarification.message,
        [{"name": "local_clarification", "result": result}],
    )
    return {
        "content": clarification.message,
        "tool_calls": [{"name": "local_clarification", "arguments": {}, "result": result}],
        "model": "database", "route": "business", "response": response.model_dump(mode="json"),
        "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
                  "embedding_tokens": 0, "provider_requests": 0, "tool_calls": 0,
                  "tool_latency_ms": 0, "latency_ms": 0},
    }


def run_local_result_page(db: Session, user: User, spec: dict, offset=0, limit=25) -> dict:
    query = BusinessQueryV1.model_validate(spec)
    access_error = _query_access_error(db, user, query)
    if access_error:
        return access_error
    if query.operation == "buyers":
        return _execute_buyers(db, user, query, offset, limit)
    return _execute_records(db, user, query, offset, limit)


def _query_access_error(db, user, query):
    permission = SUBJECT_PERMISSIONS.get(query.subject)
    organization = db.get(Organization, user.organization_id)
    required_module = SUBJECT_MODULES.get(query.subject)
    permissions = [permission, OPERATION_PERMISSIONS.get((query.subject, query.operation))]
    if required_module and (not organization or required_module not in (organization.enabled_modules or [])):
        return {"access_denied": True, "message": "That workspace is not enabled for this business."}
    if not permission or not user_has_permissions(db, user, [item for item in permissions if item]):
        return {"access_denied": True, "message": "You do not have access to that business information."}
    return None


def _execute_records(db: Session, user: User, query: BusinessQueryV1, offset: int, limit: int) -> dict:
    permission = SUBJECT_PERMISSIONS.get(query.subject)
    model = SUBJECT_MODEL.get(query.subject)
    if not permission or not model:
        return {"error": "This business query is not supported."}
    if not user_has_permissions(db, user, [permission]):
        return {"access_denied": True, "message": "You do not have access to that business information."}
    stmt = _scoped_statement(db, user, query.subject, model)
    stmt = _selected_location(stmt, query, model)
    stmt = _apply_record_filters(stmt, query, model)
    if query.subject == "purchases" and query.sort == "latest_invoice":
        latest_invoice_id = db.scalar(
            stmt.with_only_columns(SaleLine.invoice_id)
            .order_by(SaleInvoice.created_at.desc(), SaleInvoice.id.desc()).limit(1)
        )
        stmt = stmt.where(SaleLine.invoice_id == latest_invoice_id) if latest_invoice_id else stmt.where(false())
    count = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    order = DATE_FIELD.get(query.subject)
    if order is None:
        order = model.created_at
    direction = order.asc() if query.direction == "asc" else order.desc()
    rows = db.execute(stmt.order_by(direction).offset(offset).limit(min(limit, 100))).scalars().all()
    serialization_context = (
        sale_invoice_context(db, user, rows) if query.subject == "invoices" else None
    )
    items = [
        _serialize(db, user, query.subject, row, serialization_context)
        for row in rows
    ]
    columns = (
        ["invoice_number", "customer_name", "item_names", "status", "total_paise", "pending_paise"]
        if query.subject == "invoices" else []
    )
    return {
        "count": count, "items": items,
        "next_offset": offset + len(items) if offset + len(items) < count else None,
        "query_spec": query.model_dump(mode="json"),
        "presentation": {"display": "cards" if _profile_kind(query.subject) else "table",
                         "title": TITLES.get(query.subject, query.subject.replace("_", " ").title()),
                         "entity_kind": _profile_kind(query.subject), "columns": columns},
    }


def _scoped_statement(db, user, subject, model):
    if subject == "clients":
        return filter_clients(select(Client), db, user)
    if subject == "employees":
        stmt = select(Employee).where(Employee.organization_id == user.organization_id)
        locations = allowed_location_ids(db, user)
        if locations is not None:
            stmt = stmt.where(Employee.id.in_(select(EmployeeLocation.employee_id).where(EmployeeLocation.location_id.in_(locations))))
        return stmt
    if subject == "patients":
        return filter_clients(select(PatientProfile).join(Client, Client.id == PatientProfile.client_id), db, user, Client)
    if subject == "payments":
        stmt = select(SalePayment).join(SaleInvoice, SaleInvoice.id == SalePayment.invoice_id).where(
            SalePayment.organization_id == user.organization_id
        )
        return _invoice_scopes(stmt, db, user)
    if subject == "purchases":
        stmt = select(SaleLine).join(SaleInvoice, SaleInvoice.id == SaleLine.invoice_id).where(
            SaleLine.organization_id == user.organization_id,
            SaleInvoice.status.in_(["issued", "partially_paid", "paid"]),
        )
        return _invoice_scopes(stmt, db, user)
    if subject == "class_bookings":
        stmt = select(ClassBooking).join(GymClass, GymClass.id == ClassBooking.gym_class_id).join(
            Client, Client.id == ClassBooking.client_id
        ).where(ClassBooking.organization_id == user.organization_id)
        stmt = filter_clients(stmt, db, user, Client)
        return _scope_location(stmt, db, user, GymClass)
    if subject == "encounters":
        stmt = select(Encounter).join(PatientProfile, PatientProfile.id == Encounter.patient_id).join(Client, Client.id == PatientProfile.client_id)
        stmt = filter_clients(stmt, db, user, Client).where(Encounter.organization_id == user.organization_id)
        return _scope_location(stmt, db, user, Encounter)
    if subject in {"prescriptions", "lab_orders"}:
        child = Prescription if subject == "prescriptions" else LabOrder
        stmt = select(child).join(Encounter, Encounter.id == child.encounter_id).join(PatientProfile, PatientProfile.id == Encounter.patient_id).join(Client, Client.id == PatientProfile.client_id)
        stmt = filter_clients(stmt, db, user, Client).where(child.organization_id == user.organization_id)
        return _scope_location(stmt, db, user, Encounter)
    if subject in {"vitals", "diagnoses"}:
        child = Vital if subject == "vitals" else Diagnosis
        stmt = select(child).join(Encounter, Encounter.id == child.encounter_id).join(
            PatientProfile, PatientProfile.id == Encounter.patient_id
        ).join(Client, Client.id == PatientProfile.client_id).where(
            child.organization_id == user.organization_id
        )
        stmt = filter_clients(stmt, db, user, Client)
        return _scope_location(stmt, db, user, Encounter)
    if subject == "allergies":
        stmt = select(Allergy).join(PatientProfile, PatientProfile.id == Allergy.patient_id).join(
            Client, Client.id == PatientProfile.client_id
        ).where(Allergy.organization_id == user.organization_id)
        return filter_clients(stmt, db, user, Client)
    if subject == "lab_results":
        stmt = select(LabResult).join(LabOrder, LabOrder.id == LabResult.order_id).join(
            Encounter, Encounter.id == LabOrder.encounter_id
        ).join(PatientProfile, PatientProfile.id == Encounter.patient_id).join(
            Client, Client.id == PatientProfile.client_id
        ).where(LabResult.organization_id == user.organization_id)
        stmt = filter_clients(stmt, db, user, Client)
        return _scope_location(stmt, db, user, Encounter)
    if subject == "dispenses":
        stmt = select(Dispense).join(Prescription, Prescription.id == Dispense.prescription_id).join(
            Encounter, Encounter.id == Prescription.encounter_id
        ).join(PatientProfile, PatientProfile.id == Encounter.patient_id).join(
            Client, Client.id == PatientProfile.client_id
        ).where(Dispense.organization_id == user.organization_id)
        stmt = filter_clients(stmt, db, user, Client)
        return _scope_location(stmt, db, user, Dispense)
    if subject == "memories":
        stmt = select(ClientMemory).where(
            ClientMemory.organization_id == user.organization_id,
            ClientMemory.is_active.is_(True),
        )
        roles = {role.slug for role in get_user_roles(db, user)}
        employee = db.execute(select(Employee).where(
            Employee.organization_id == user.organization_id, Employee.user_id == user.id,
        )).scalar_one_or_none()
        assigned_clients = select(TrainerAssignment.client_id).where(
            TrainerAssignment.organization_id == user.organization_id,
            TrainerAssignment.trainer_employee_id == employee.id if employee else false(),
            TrainerAssignment.status == "active",
        )
        visibility = [ClientMemory.visibility == "team", ClientMemory.created_by_user_id == user.id]
        if {"owner", "manager"} & roles or user_has_permissions(db, user, ["client_memory.manage"]):
            visibility.append(ClientMemory.visibility == "managers")
        if {"owner", "manager"} & roles:
            visibility.append(ClientMemory.visibility == "assigned_staff")
        else:
            visibility.append(and_(ClientMemory.visibility == "assigned_staff", ClientMemory.client_id.in_(assigned_clients)))
        if user_has_permissions(db, user, ["clinical.view"]):
            visibility.append(ClientMemory.visibility == "clinical")
        stmt = stmt.where(or_(*visibility))
        allowed = allowed_client_ids(db, user)
        if allowed is not None:
            stmt = stmt.where(ClientMemory.client_id.in_(allowed) if allowed else false())
        return stmt
    if subject == "coaching":
        stmt = select(CoachingNote).where(CoachingNote.organization_id == user.organization_id)
        roles = {role.slug for role in get_user_roles(db, user)}
        if not ({"owner", "manager"} & roles):
            employee = db.execute(select(Employee).where(
                Employee.organization_id == user.organization_id, Employee.user_id == user.id,
            )).scalar_one_or_none()
            assigned_clients = select(TrainerAssignment.client_id).where(
                TrainerAssignment.organization_id == user.organization_id,
                TrainerAssignment.trainer_employee_id == employee.id if employee else false(),
                TrainerAssignment.status == "active",
            )
            stmt = stmt.where(or_(
                CoachingNote.recorded_by_user_id == user.id,
                and_(CoachingNote.visibility == "assigned_staff", CoachingNote.client_id.in_(assigned_clients)),
            ))
        allowed = allowed_client_ids(db, user)
        if allowed is not None:
            stmt = stmt.where(CoachingNote.client_id.in_(allowed) if allowed else false())
        return stmt
    stmt = select(model).where(model.organization_id == user.organization_id)
    if subject == "notifications":
        return stmt.where(Notification.user_id == user.id)
    if hasattr(model, "location_id"):
        stmt = _scope_location(stmt, db, user, model)
    if hasattr(model, "client_id"):
        allowed = allowed_client_ids(db, user)
        if allowed is not None:
            stmt = stmt.where(model.client_id.in_(allowed) if allowed else false())
    return stmt


def _scope_location(stmt, db, user, model):
    locations = allowed_location_ids(db, user)
    if locations is not None:
        stmt = stmt.where(model.location_id.in_(locations))
    return stmt


def _selected_location(stmt, query, model):
    if not query.location_id:
        return stmt
    if query.subject == "clients":
        return stmt.where(Client.home_location_id == query.location_id)
    if query.subject in {"patients", "allergies", "memories"}:
        return stmt.where(Client.home_location_id == query.location_id)
    if query.subject == "employees":
        return stmt.where(Employee.id.in_(select(EmployeeLocation.employee_id).where(
            EmployeeLocation.location_id == query.location_id
        )))
    if hasattr(model, "location_id"):
        return stmt.where(model.location_id == query.location_id)
    if query.subject in {"prescriptions", "lab_orders"}:
        return stmt.where(Encounter.location_id == query.location_id)
    if query.subject in {"vitals", "diagnoses", "lab_results"}:
        return stmt.where(Encounter.location_id == query.location_id)
    if query.subject == "class_bookings":
        return stmt.where(GymClass.location_id == query.location_id)
    if query.subject == "payments":
        return stmt.where(SaleInvoice.location_id == query.location_id)
    if query.subject == "purchases":
        return stmt.where(SaleInvoice.location_id == query.location_id)
    return stmt


def _apply_record_filters(stmt, query, model):
    entities = query.entities
    entity = entities[0] if entities else None
    if entities:
        entity_ids = [item.id for item in entities]
        client_ids = [item.id for item in entities if item.kind in {"client", "patient"}]
        if query.subject in {"clients", "employees", "catalog", "locations", "equipment", "classes"}:
            stmt = stmt.where(model.id.in_(entity_ids))
        elif query.subject == "purchases" and any(item.kind == "invoice" for item in entities):
            invoice_ids = [item.id for item in entities if item.kind == "invoice"]
            stmt = stmt.where(SaleLine.invoice_id.in_(invoice_ids))
        elif query.subject == "purchases" and client_ids:
            stmt = stmt.where(SaleInvoice.client_id.in_(client_ids))
        elif hasattr(model, "client_id") and client_ids:
            stmt = stmt.where(model.client_id.in_(client_ids))
        elif entity.kind == "patient" and query.subject in {
            "encounters", "prescriptions", "lab_orders", "vitals", "diagnoses", "lab_results", "dispenses",
        }:
            stmt = stmt.where(PatientProfile.id == entity.id)
        elif query.subject == "allergies" and entity.kind == "patient":
            stmt = stmt.where(Allergy.patient_id == entity.id)
        elif query.subject == "diagnoses" and entity.kind == "encounter":
            stmt = stmt.where(Diagnosis.encounter_id == entity.id)
        elif query.subject == "lab_results" and entity.kind == "lab_order":
            stmt = stmt.where(LabResult.order_id == entity.id)
        elif query.subject == "dispenses" and entity.kind == "prescription":
            stmt = stmt.where(Dispense.prescription_id == entity.id)
        elif query.subject == "invoices" and entity.kind == "invoice":
            stmt = stmt.where(SaleInvoice.id == entity.id)
        elif query.subject == "payments" and entity.kind == "payment":
            stmt = stmt.where(SalePayment.id == entity.id)
    if query.query_text:
        value = query.query_text.casefold()
        if query.subject == "clients":
            stmt = stmt.where(or_(
                func.lower(Client.first_name).contains(value),
                func.lower(Client.last_name).contains(value),
                func.lower(func.coalesce(Client.phone, "")).contains(value),
                func.lower(func.coalesce(Client.email, "")).contains(value),
                func.lower(Client.client_number).contains(value),
            ))
        elif query.subject == "employees":
            stmt = stmt.where(or_(
                func.lower(Employee.first_name).contains(value),
                func.lower(Employee.last_name).contains(value),
                func.lower(func.coalesce(Employee.designation, "")).contains(value),
            ))
        elif query.subject == "catalog":
            stmt = stmt.where(or_(
                func.lower(CatalogItem.name).contains(value),
                func.lower(CatalogItem.sku).contains(value),
            ))
        elif query.subject == "invoices":
            stmt = stmt.where(func.lower(SaleInvoice.invoice_number).contains(value))
        elif query.subject == "purchases":
            stmt = stmt.where(or_(
                func.lower(SaleLine.item_name).contains(value),
                func.lower(func.coalesce(SaleLine.sku, "")).contains(value),
            ))
    if query.date_range and query.subject in DATE_FIELD:
        field = DATE_FIELD[query.subject]
        if hasattr(field.type, "python_type") and field.type.python_type is date:
            stmt = stmt.where(field >= query.date_range.start.date(), field < query.date_range.end.date())
        else:
            stmt = stmt.where(field >= query.date_range.start, field < query.date_range.end)
    status_field = STATUS_FIELD.get(query.subject)
    special_status = (
        (query.status == "overdue" and query.subject in {"invoices", "tasks", "equipment"})
        or (query.status in {"expiring", "expired"} and query.subject == "memberships")
    )
    if query.status and status_field is not None and not special_status:
        stmt = stmt.where(status_field == query.status)
    if query.status == "overdue" and query.subject == "invoices":
        stmt = stmt.where(SaleInvoice.total_paise > SaleInvoice.paid_paise, SaleInvoice.status.notin_(["void", "refunded"]))
    if query.status == "expiring" and query.subject == "memberships":
        today = datetime.now(timezone.utc).date()
        stmt = stmt.where(Membership.status == "active", Membership.ends_on.between(today, today + timedelta(days=7)))
    if query.status == "expired" and query.subject == "memberships":
        stmt = stmt.where(Membership.ends_on < datetime.now(timezone.utc).date())
    if query.status == "low" and query.subject == "inventory":
        stmt = stmt.where(StockLevel.quantity_milli <= StockLevel.reorder_level_milli)
    if query.status == "out" and query.subject == "inventory":
        stmt = stmt.where(StockLevel.quantity_milli <= 0)
    if query.status == "expiring" and query.subject == "inventory":
        today = datetime.now(timezone.utc).date()
        stmt = stmt.where(StockLevel.expires_on.between(today, today + timedelta(days=30)))
    if query.status == "expired" and query.subject == "inventory":
        stmt = stmt.where(StockLevel.expires_on < datetime.now(timezone.utc).date())
    if query.status == "current" and query.subject == "checkins":
        stmt = stmt.where(GymCheckIn.checked_out_at.is_(None))
    if query.status in {"active", "inactive"} and query.subject == "catalog":
        stmt = stmt.where(CatalogItem.is_active.is_(query.status == "active"))
    if query.status in {"active", "inactive"} and query.subject == "locations":
        stmt = stmt.where(Location.is_active.is_(query.status == "active"))
    if query.status == "overdue" and query.subject == "tasks":
        stmt = stmt.where(Task.due_at < datetime.now(timezone.utc), Task.status.notin_(["completed", "cancelled"]))
    if query.status == "overdue" and query.subject == "equipment":
        stmt = stmt.where(Equipment.next_service_on < datetime.now(timezone.utc).date())
    amount_field = {
        "catalog": CatalogItem.price_paise, "invoices": SaleInvoice.total_paise,
        "payments": SalePayment.amount_paise, "memberships": Membership.amount_paise,
    }.get(query.subject)
    if amount_field is not None:
        if query.min_amount_paise is not None:
            stmt = stmt.where(amount_field >= query.min_amount_paise)
        if query.max_amount_paise is not None:
            stmt = stmt.where(amount_field <= query.max_amount_paise)
    return stmt


def _execute_buyers(db, user, query, offset, limit):
    if not user_has_permissions(db, user, ["sales.view"]):
        return {"access_denied": True, "message": "You do not have access to sales information."}
    stmt = select(
        SaleInvoice.client_id.label("client_id"),
        func.count(func.distinct(SaleInvoice.id)).label("purchase_count"),
        func.coalesce(func.sum(SaleLine.quantity_milli), 0).label("quantity_milli"),
        func.coalesce(func.sum(SaleLine.total_paise), 0).label("total_paise"),
        func.max(SaleInvoice.created_at).label("last_purchased_at"),
    ).join(SaleInvoice, SaleInvoice.id == SaleLine.invoice_id).where(
        SaleLine.organization_id == user.organization_id,
        SaleInvoice.status.in_(["issued", "partially_paid", "paid"]),
    )
    locations = allowed_location_ids(db, user)
    clients = allowed_client_ids(db, user)
    if locations is not None: stmt = stmt.where(SaleInvoice.location_id.in_(locations))
    if clients is not None: stmt = stmt.where(SaleInvoice.client_id.in_(clients) if clients else false())
    if query.location_id: stmt = stmt.where(SaleInvoice.location_id == query.location_id)
    if query.date_range: stmt = stmt.where(SaleInvoice.created_at >= query.date_range.start, SaleInvoice.created_at < query.date_range.end)
    entity = query.entities[0] if query.entities else None
    if entity and entity.kind == "catalog": stmt = stmt.where(SaleLine.item_id == entity.id)
    elif query.query_text: stmt = stmt.where(or_(func.lower(SaleLine.item_name).contains(query.query_text.casefold()), func.lower(func.coalesce(SaleLine.sku, "")).contains(query.query_text.casefold())))
    grouped = stmt.group_by(SaleInvoice.client_id)
    count = db.scalar(select(func.count()).select_from(grouped.subquery())) or 0
    rows = db.execute(grouped.order_by(func.max(SaleInvoice.created_at).desc()).offset(offset).limit(min(limit, 100))).all()
    client_ids = [row.client_id for row in rows if row.client_id]
    client_rows = db.execute(filter_clients(select(Client).where(Client.id.in_(client_ids)), db, user)).scalars().all() if client_ids else []
    by_id = {row.id: row for row in client_rows}
    items = []
    for row in rows:
        client = by_id.get(row.client_id)
        name = f"{client.first_name} {client.last_name}".strip() if client else "Walk-in sales"
        items.append({"id": row.client_id or "walk-in", "display_name": name,
                      "display_meta": f"{row.purchase_count} purchase{'s' if row.purchase_count != 1 else ''}",
                      "purchase_count": row.purchase_count, "quantity_milli": row.quantity_milli,
                      "total_paise": row.total_paise, "last_purchased_at": row.last_purchased_at,
                      "profile_ref": {"kind": "client", "id": row.client_id} if client else None})
    return {"count": count, "items": items, "next_offset": offset + len(items) if offset + len(items) < count else None,
            "query_spec": query.model_dump(mode="json"),
            "presentation": {"display": "cards", "title": "Clients who purchased", "entity_kind": "client"}}


def _execute_metric(db, user, query):
    permission = SUBJECT_PERMISSIONS.get(query.subject)
    permissions = [permission, OPERATION_PERMISSIONS.get((query.subject, query.operation))]
    if not permission or not user_has_permissions(db, user, [item for item in permissions if item]):
        return {"access_denied": True, "message": "You do not have access to that business information."}
    if query.operation == "rank":
        return _rank_records(db, user, query)
    if query.operation == "group":
        return _group_records(db, user, query)
    if query.operation == "trend":
        return _trend(db, user, query)
    primary = _metric_value(db, user, query, query.date_range)
    if query.operation == "compare":
        comparison = _metric_value(db, user, query, query.comparison_range)
        delta = primary - comparison
        return {"metric": query.metric or query.subject, "primary": primary, "comparison": comparison, "delta": delta,
                "presentation": {"type": "kpi", "title": "Business comparison",
                                 "items": [{"label": query.date_range.label if query.date_range else "Current", "value": primary, "format": _metric_format(query)},
                                           {"label": query.comparison_range.label if query.comparison_range else "Previous", "value": comparison, "format": _metric_format(query)},
                                           {"label": "Difference", "value": delta, "format": _metric_format(query)}]}}
    label = (query.metric or query.subject).replace("_", " ").title()
    if query.metric == "revenue" and query.date_range:
        label = f"{query.date_range.label.title()} revenue"
    return {"metric": query.metric or query.subject, "value": primary,
            "presentation": {"type": "kpi", "title": "Live business result",
                             "items": [{"label": label, "value": primary, "format": _metric_format(query)}]}}


def _metric_value(db, user, query, window):
    start, end = _window(window)
    if query.metric == "revenue" or query.subject == "payments":
        stmt = select(func.coalesce(func.sum(SalePayment.amount_paise), 0)).join(SaleInvoice, SaleInvoice.id == SalePayment.invoice_id).where(
            SalePayment.organization_id == user.organization_id, SalePayment.status == "captured",
            SalePayment.created_at >= start, SalePayment.created_at < end)
        stmt = _invoice_scopes(stmt, db, user, query.location_id)
        return int(db.scalar(stmt) or 0)
    model = SUBJECT_MODEL.get(query.subject)
    if not model: return 0
    stmt = _scoped_statement(db, user, query.subject, model)
    field = DATE_FIELD.get(query.subject)
    if field is not None and window is not None:
        if field.type.python_type is date: stmt = stmt.where(field >= start.date(), field < end.date())
        else: stmt = stmt.where(field >= start, field < end)
    stmt = _apply_record_filters(stmt, query.model_copy(update={"date_range": None}), model)
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _trend(db, user, query):
    start, end = _window(query.date_range)
    if query.metric == "revenue" or query.subject == "payments":
        field = SalePayment.created_at
        bucket = func.date_trunc(query.granularity, field)
        stmt = select(bucket.label("label"), func.coalesce(func.sum(SalePayment.amount_paise), 0).label("value")).join(SaleInvoice, SaleInvoice.id == SalePayment.invoice_id).where(
            SalePayment.organization_id == user.organization_id, SalePayment.status == "captured", field >= start, field < end)
        stmt = _invoice_scopes(stmt, db, user, query.location_id).group_by(bucket).order_by(bucket)
    else:
        model = SUBJECT_MODEL.get(query.subject); field = DATE_FIELD.get(query.subject)
        if not model or field is None: return {"error": "This trend is not supported."}
        base = _scoped_statement(db, user, query.subject, model).where(field >= start, field < end).subquery()
        timestamp = base.c.get(field.key)
        bucket = func.date_trunc(query.granularity, timestamp)
        stmt = select(bucket.label("label"), func.count().label("value")).select_from(base).group_by(bucket).order_by(bucket)
    rows = db.execute(stmt).all()
    return {"rows": [{"label": str(row.label), "value": int(row.value)} for row in rows],
            "presentation": {"type": "chart", "chart_type": "line", "title": "Trend",
                             "series": [{"key": "value", "label": (query.metric or query.subject).title(), "format": _metric_format(query)}]}}


def _rank_products(db, user, query):
    start, end = _window(query.date_range)
    stmt = select(SaleLine.item_name.label("label"), func.coalesce(func.sum(SaleLine.total_paise), 0).label("value")).join(SaleInvoice, SaleInvoice.id == SaleLine.invoice_id).where(
        SaleLine.organization_id == user.organization_id, SaleInvoice.created_at >= start,
        SaleInvoice.created_at < end, SaleInvoice.status.in_(["issued", "partially_paid", "paid"]))
    stmt = _invoice_scopes(stmt, db, user, query.location_id)
    total = func.sum(SaleLine.total_paise)
    order = total.asc() if query.direction == "asc" else total.desc()
    rows = db.execute(stmt.group_by(SaleLine.item_name).order_by(order).limit(12)).all()
    return {"rows": [{"label": row.label, "value": int(row.value)} for row in rows],
            "presentation": {"type": "chart", "chart_type": "bar", "title": "Top products",
                             "series": [{"key": "value", "label": "Sales", "format": "money"}]}}


def _rank_records(db, user, query):
    if query.subject in {"purchases", "catalog"}:
        return _rank_products(db, user, query)
    start, end = _window(query.date_range)
    if query.subject == "clients":
        stmt = select(Client.id, func.trim(Client.first_name + " " + Client.last_name).label("label"),
                      func.coalesce(func.sum(SaleInvoice.total_paise), 0).label("value")).join(
            SaleInvoice, SaleInvoice.client_id == Client.id
        ).where(Client.organization_id == user.organization_id, SaleInvoice.created_at >= start,
                SaleInvoice.created_at < end, SaleInvoice.status.in_(["issued", "partially_paid", "paid"]))
        stmt = filter_clients(stmt, db, user, Client)
        stmt = _invoice_scopes(stmt, db, user, query.location_id)
        rows = db.execute(stmt.group_by(Client.id).order_by(func.sum(SaleInvoice.total_paise).desc()).limit(12)).all()
        return {"rows": [{"id": row.id, "label": row.label, "value": int(row.value),
                           "profile_ref": {"kind": "client", "id": row.id}} for row in rows],
                "presentation": {"type": "chart", "chart_type": "bar", "title": "Top clients",
                                 "series": [{"key": "value", "label": "Sales", "format": "money"}]}}
    return {"error": "That ranking is not available as an exact business query yet."}


def _group_revenue(db, user, query):
    start, end = _window(query.date_range)
    stmt = select(Location.name.label("label"), func.coalesce(func.sum(SalePayment.amount_paise), 0).label("value")).join(SaleInvoice, SaleInvoice.location_id == Location.id).join(SalePayment, SalePayment.invoice_id == SaleInvoice.id).where(
        SalePayment.organization_id == user.organization_id, SalePayment.status == "captured",
        SalePayment.created_at >= start, SalePayment.created_at < end)
    locations = allowed_location_ids(db, user)
    if locations is not None: stmt = stmt.where(Location.id.in_(locations))
    rows = db.execute(stmt.group_by(Location.name).order_by(func.sum(SalePayment.amount_paise).desc())).all()
    return {"rows": [{"label": row.label, "value": int(row.value)} for row in rows],
            "presentation": {"type": "chart", "chart_type": "bar", "title": "Revenue by location",
                             "series": [{"key": "value", "label": "Revenue", "format": "money"}]}}


def _group_records(db, user, query):
    if query.metric == "revenue" or query.subject == "payments":
        return _group_revenue(db, user, query)
    model = SUBJECT_MODEL.get(query.subject)
    if not model:
        return {"error": "That grouping is not available as an exact business query yet."}
    location_field = Client.home_location_id if query.subject == "clients" else getattr(model, "location_id", None)
    if location_field is None:
        return {"error": "That grouping is not available as an exact business query yet."}
    base = _scoped_statement(db, user, query.subject, model)
    base = _apply_record_filters(base, query.model_copy(update={"location_id": None}), model).subquery()
    location_column = base.c.get(location_field.key)
    rows = db.execute(select(Location.name.label("label"), func.count().label("value")).select_from(base).join(
        Location, Location.id == location_column
    ).group_by(Location.name).order_by(func.count().desc())).all()
    return {"rows": [{"label": row.label, "value": int(row.value)} for row in rows],
            "presentation": {"type": "chart", "chart_type": "bar",
                             "title": f"{TITLES.get(query.subject, query.subject.title())} by location",
                             "series": [{"key": "value", "label": "Records", "format": "number"}]}}


def _execute_relationship(db, user, query):
    if not query.entities: return {"error": "A client is required."}
    client_id = query.entities[0].id
    items = []
    if user_has_permissions(db, user, ["gym.coaching.view"]):
        rows = db.execute(select(TrainerAssignment, Employee).join(Employee, Employee.id == TrainerAssignment.trainer_employee_id).where(
            TrainerAssignment.organization_id == user.organization_id, TrainerAssignment.client_id == client_id,
            TrainerAssignment.status == "active")).all()
        items.extend({"id": employee.id, "display_name": f"{employee.first_name} {employee.last_name}".strip(),
                      "display_meta": "Trainer", "profile_ref": {"kind": "employee", "id": employee.id}} for _, employee in rows)
    if user_has_permissions(db, user, ["salon.notes.view"]):
        row = db.execute(select(SalonClientProfile, Employee).join(Employee, Employee.id == SalonClientProfile.preferred_employee_id).where(
            SalonClientProfile.organization_id == user.organization_id, SalonClientProfile.client_id == client_id)).first()
        if row:
            employee = row[1]; items.append({"id": employee.id, "display_name": f"{employee.first_name} {employee.last_name}".strip(),
                                             "display_meta": "Preferred stylist", "profile_ref": {"kind": "employee", "id": employee.id}})
    return {"count": len(items), "items": items,
            "presentation": {"display": "cards", "title": "Assigned team", "entity_kind": "employee"}}


def _execute_detail(db, user, query):
    if not query.entities: return {"error": "A business record is required."}
    entity = query.entities[0]
    if entity.kind in {"catalog", "inventory"} or (entity.profile_ref or {}).get("kind") == "catalog":
        item_id = (entity.profile_ref or {}).get("id")
        if not item_id and entity.kind == "catalog":
            item_id = entity.id
        if not item_id and entity.kind == "inventory":
            level = db.execute(select(StockLevel).where(
                StockLevel.id == entity.id,
                StockLevel.organization_id == user.organization_id,
            )).scalar_one_or_none()
            item_id = level.item_id if level else None
        item = db.execute(select(CatalogItem).where(
            CatalogItem.id == item_id,
            CatalogItem.organization_id == user.organization_id,
        )).scalar_one_or_none()
        if not item:
            return {"count": 0, "items": [], "presentation": {"display": "cards", "title": "Matching business record", "entity_kind": "catalog"}}
        card = _serialize(db, user, "catalog", item)
        if item.track_stock and user_has_permissions(db, user, ["inventory.view"]):
            levels_stmt = select(StockLevel).where(
                StockLevel.organization_id == user.organization_id,
                StockLevel.item_id == item.id,
            )
            locations = allowed_location_ids(db, user)
            if locations is not None:
                levels_stmt = levels_stmt.where(StockLevel.location_id.in_(locations))
            if query.location_id:
                levels_stmt = levels_stmt.where(StockLevel.location_id == query.location_id)
            levels = db.execute(levels_stmt).scalars().all()
            card.update({
                "stock_quantity_milli": sum(level.quantity_milli for level in levels),
                "stock_levels": len(levels),
                "low_stock_levels": sum(level.quantity_milli <= level.reorder_level_milli for level in levels),
            })
        return {"count": 1, "items": [card],
                "presentation": {"display": "cards", "title": "Catalog item", "entity_kind": "catalog"}}
    return {"count": 1, "items": [{"id": entity.id, "display_name": entity.display_name,
                                    "display_meta": entity.kind.replace("_", " ").title(),
                                    "profile_ref": entity.profile_ref}],
            "presentation": {"display": "cards", "title": "Matching business record", "entity_kind": entity.kind}}


def _serialize(db, user, subject, row, context=None):
    if subject == "clients":
        name = f"{row.first_name} {row.last_name}".strip()
        return {"id": row.id, "display_name": name, "display_meta": row.phone or row.client_number,
                "status": row.status, "last_visit_at": row.last_visit_at, "profile_ref": {"kind": "client", "id": row.id}}
    if subject == "employees":
        name = f"{row.first_name} {row.last_name}".strip()
        return {"id": row.id, "display_name": name, "display_meta": row.designation or row.employee_number,
                "status": row.status, "profile_ref": {"kind": "employee", "id": row.id}}
    if subject == "catalog":
        return {"id": row.id, "display_name": row.name, "display_meta": row.sku, "type": row.item_type,
                "price_paise": row.price_paise, "active": row.is_active, "profile_ref": {"kind": "catalog", "id": row.id}}
    if subject == "inventory":
        item = db.get(CatalogItem, row.item_id)
        return {"id": row.id, "display_name": item.name if item else "Catalog item", "display_meta": item.sku if item else row.batch_number,
                "quantity_milli": row.quantity_milli, "reorder_level_milli": row.reorder_level_milli,
                "batch": row.batch_number, "expires_on": row.expires_on,
                "profile_ref": {"kind": "catalog", "id": row.item_id}}
    if subject == "invoices":
        return serialize_sale_invoice(row, context)
    if subject == "purchases":
        invoice = db.get(SaleInvoice, row.invoice_id)
        client = db.get(Client, invoice.client_id) if invoice and invoice.client_id else None
        client_name = f"{client.first_name} {client.last_name}".strip() if client else "Walk-in client"
        return {
            "id": row.id, "display_name": row.item_name, "display_meta": row.sku,
            "item": row.item_name, "sku": row.sku, "quantity": row.quantity_milli / 1000,
            "quantity_milli": row.quantity_milli,
            "unit_price_paise": row.unit_price_paise, "line_total_paise": row.total_paise,
            "invoice_number": invoice.invoice_number if invoice else None,
            "invoice_total_paise": invoice.total_paise if invoice else None,
            "purchase_status": invoice.status if invoice else None,
            "purchased_at": invoice.created_at if invoice else None,
            "client": client_name,
            "profile_ref": {"kind": "client", "id": client.id} if client else None,
        }
    if subject == "memberships":
        client = db.get(Client, row.client_id); plan = db.get(MembershipPlan, row.plan_id)
        name = f"{client.first_name} {client.last_name}".strip() if client else "Client"
        return {"id": row.id, "display_name": name, "display_meta": plan.name if plan else "Membership",
                "status": row.status, "starts_on": row.starts_on, "ends_on": row.ends_on,
                "profile_ref": {"kind": "client", "id": row.client_id}}
    if subject == "class_bookings":
        client = db.get(Client, row.client_id); gym_class = db.get(GymClass, row.gym_class_id)
        name = f"{client.first_name} {client.last_name}".strip() if client else "Client"
        return {"id": row.id, "display_name": name,
                "display_meta": gym_class.name if gym_class else "Class booking", "status": row.status,
                "profile_ref": {"kind": "client", "id": row.client_id}}
    if subject == "memories":
        client = db.get(Client, row.client_id)
        name = f"{client.first_name} {client.last_name}".strip() if client else "Client"
        return {"id": row.id, "display_name": row.label, "display_meta": name,
                "category": row.category, "value": row.value,
                "profile_ref": {"kind": "client", "id": row.client_id}}
    if subject == "vitals":
        client_id = _clinical_client_id(db, encounter_id=row.encounter_id)
        return {"id": row.id, "display_name": "Vitals", "display_meta": str(row.created_at),
                "values": row.values, "profile_ref": {"kind": "client", "id": client_id} if client_id else None}
    if subject == "allergies":
        patient = db.get(PatientProfile, row.patient_id)
        return {"id": row.id, "display_name": row.substance, "display_meta": row.severity,
                "status": row.status, "reaction": row.reaction,
                "profile_ref": {"kind": "client", "id": patient.client_id} if patient else None}
    if subject == "diagnoses":
        client_id = _clinical_client_id(db, encounter_id=row.encounter_id)
        return {"id": row.id, "display_name": row.description, "display_meta": row.code,
                "primary": row.is_primary,
                "profile_ref": {"kind": "client", "id": client_id} if client_id else None}
    if subject == "lab_results":
        order = db.get(LabOrder, row.order_id)
        client_id = _clinical_client_id(db, encounter_id=order.encounter_id) if order else None
        return {"id": row.id, "display_name": "Lab result", "display_meta": str(row.reported_at or row.created_at),
                "values": row.values, "interpretation": row.interpretation,
                "profile_ref": {"kind": "client", "id": client_id} if client_id else None}
    if subject == "dispenses":
        prescription = db.get(Prescription, row.prescription_id)
        client_id = _clinical_client_id(db, encounter_id=prescription.encounter_id) if prescription else None
        return {"id": row.id, "display_name": "Pharmacy dispensing", "display_meta": str(row.dispensed_at),
                "items": row.items,
                "profile_ref": {"kind": "client", "id": client_id} if client_id else None}
    if subject == "patients":
        client = db.get(Client, row.client_id); name = f"{client.first_name} {client.last_name}".strip() if client else "Patient"
        return {"id": row.id, "display_name": name, "display_meta": row.abha_number or row.blood_group or "Patient",
                "profile_ref": {"kind": "client", "id": row.client_id}}
    if subject == "locations": return {"id": row.id, "display_name": row.name, "display_meta": row.city or row.code, "status": "active" if row.is_active else "inactive"}
    if subject == "equipment": return {"id": row.id, "display_name": row.name, "display_meta": row.asset_code, "status": row.status, "next_service_on": row.next_service_on}
    if subject == "classes": return {"id": row.id, "display_name": row.name, "display_meta": str(row.starts_at), "status": row.status, "capacity": row.capacity}
    fields = {"id": row.id}
    for name in ["status", "title", "priority", "invoice_number", "amount_paise", "method", "reference", "starts_at", "ends_at", "checked_in_at", "checked_out_at", "due_at", "signal_type", "pulse_state", "label", "measured_on", "scheduled_for", "name", "channel", "recipient", "sent_at", "next_service_on", "follow_up_on"]:
        if hasattr(row, name): fields[name] = getattr(row, name)
    fields["display_name"] = fields.get("title") or fields.get("invoice_number") or fields.get("name") or TITLES.get(subject, subject.title())
    fields["display_meta"] = fields.get("status") or fields.get("method") or fields.get("channel")
    client_id = getattr(row, "client_id", None)
    if client_id: fields["profile_ref"] = {"kind": "client", "id": client_id}
    return fields


def _clinical_client_id(db, encounter_id):
    return db.execute(select(PatientProfile.client_id).join(
        Encounter, Encounter.patient_id == PatientProfile.id
    ).where(Encounter.id == encounter_id)).scalar_one_or_none()


def _invoice_scopes(stmt, db, user, location_id=None):
    locations = allowed_location_ids(db, user); clients = allowed_client_ids(db, user)
    if locations is not None: stmt = stmt.where(SaleInvoice.location_id.in_(locations))
    if clients is not None: stmt = stmt.where(SaleInvoice.client_id.in_(clients) if clients else false())
    if location_id: stmt = stmt.where(SaleInvoice.location_id == location_id)
    return stmt


def _window(window):
    if window: return window.start, window.end
    now = datetime.now(timezone.utc); return now - timedelta(days=30), now


def _metric_format(query): return "money" if query.metric == "revenue" or query.subject == "payments" else "number"
def _profile_kind(subject): return {
    "clients": "client", "employees": "employee", "catalog": "catalog", "inventory": "catalog",
    "patients": "client", "memberships": "client", "purchases": "client", "class_bookings": "client",
    "memories": "client", "vitals": "client", "allergies": "client",
    "diagnoses": "client", "lab_results": "client", "dispenses": "client",
}.get(subject)


def _summary(query, result):
    if result.get("access_denied") or result.get("error"):
        if query.language == "tanglish":
            return "Indha business information paakka ungalukku access illa."
        if query.language == "ta":
            return "இந்த வணிகத் தகவலைப் பார்க்க உங்களுக்கு அனுமதி இல்லை."
        return result.get("message") or result.get("error")
    if query.operation == "compare":
        value = _display_value(result.get("delta", 0), _metric_format(query))
        if query.language == "tanglish": return f"Difference {value}."
        if query.language == "ta": return f"வேறுபாடு {value}."
        return f"The difference is {value}."
    if query.operation in {"aggregate", "count"} and "value" in result:
        value = _display_value(result["value"], _metric_format(query))
        if query.subject == "clients" and query.operation == "count":
            qualifier = "active " if query.status == "active" else ""
            if query.language == "tanglish": return f"Ippo {value} {qualifier}clients irukaanga."
            if query.language == "ta": return f"தற்போது {value} {('செயலில் உள்ள ' if qualifier else '')}வாடிக்கையாளர்கள் உள்ளனர்."
            return f"There are {value} {qualifier}clients."
        if query.language == "tanglish": return f"Ippo result {value}."
        if query.language == "ta": return f"தற்போதைய முடிவு {value}."
        return f"The current result is {value}."
    if "rows" in result:
        count = len(result["rows"])
        if query.language == "tanglish": return f"Indha {query.operation}-ku {count} results kidaichirukku."
        if query.language == "ta": return f"இந்த {query.operation}-க்கு {count} முடிவுகள் கிடைத்துள்ளன."
        return f"I found {count} result{'s' if count != 1 else ''} for this {query.operation}."
    if query.subject == "purchases" and query.operation in {"history", "find"} and result.get("items"):
        items = result["items"]
        names = ", ".join(dict.fromkeys(item["item"] for item in items))
        first = items[0]
        invoice = first.get("invoice_number") or "the latest invoice"
        amount = first.get("invoice_total_paise")
        amount_text = f" for INR {amount / 100:,.2f}" if amount is not None else ""
        more = int(result.get("count", len(items))) - len(items)
        more_text = f" and {more} more item{'s' if more != 1 else ''}" if more > 0 else ""
        if query.language == "tanglish":
            return f"{first['client']} oda kadaisi purchase: {names}{more_text}. Invoice {invoice}{amount_text}."
        if query.language == "ta":
            return f"{first['client']} அவர்களின் சமீபத்திய வாங்குதல்: {names}{more_text}. ரசீது {invoice}{amount_text}."
        return f"{first['client']}'s latest purchase was {names}{more_text} on invoice {invoice}{amount_text}."
    count = int(result.get("count", len(result.get("items", []))))
    label = TITLES.get(query.subject, query.subject.replace("_", " ")).lower()
    if query.language == "tanglish":
        return f"{count} {label} kidaichirukku." if count else f"Matching {label} edhuvum kidaikkala."
    if query.language == "ta":
        return f"{count} {label} கிடைத்துள்ளன." if count else f"பொருந்தும் {label} எதுவும் கிடைக்கவில்லை."
    return f"I found {count} {label}." if count != 1 else f"I found 1 matching record."


def _display_value(value, format_name):
    return f"INR {value / 100:,.2f}" if format_name == "money" else f"{value:,}"


def _compose(summary, result):
    presentation = result.get("presentation") or {}
    if presentation.get("type") == "kpi":
        return AIResponseV1(summary=summary, blocks=[ResponseBlock(id="local-kpi", type="kpi_grid", title=presentation.get("title"), data={"items": presentation.get("items", [])})])
    return compose_response(summary, [{"name": "local_query", "result": result}])
