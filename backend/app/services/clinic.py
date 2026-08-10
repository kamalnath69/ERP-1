"""Scoped outpatient Clinic reads and clinical record access checks."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    CatalogItem,
    Client,
    Employee,
    Encounter,
    LabOrder,
    LabTest,
    Location,
    PatientProfile,
    Prescription,
    PrescriptionItem,
    User,
)
from app.services.business_access import (
    allowed_client_ids,
    ensure_client_access,
    ensure_location,
    filter_clients,
    filter_locations,
    organization_for,
)
from app.services.rbac import get_user_permissions


def serialize(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def local_day_window(db: Session, user: User) -> tuple[datetime, datetime]:
    organization = organization_for(db, user)
    try:
        zone = ZoneInfo(organization.timezone or "Asia/Kolkata")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Kolkata")
    local_today = datetime.now(timezone.utc).astimezone(zone).date()
    start = datetime.combine(local_today, time.min, tzinfo=zone).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def scoped_patient_statement(db: Session, user: User, *, location_id: str | None = None):
    statement = select(PatientProfile).join(Client, Client.id == PatientProfile.client_id).where(
        PatientProfile.organization_id == user.organization_id,
    )
    statement = filter_clients(statement, db, user, Client)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(Client.home_location_id == location_id)
    return statement


def patient_for_user(db: Session, user: User, patient_id: str) -> tuple[PatientProfile, Client]:
    patient = db.execute(scoped_patient_statement(db, user).where(PatientProfile.id == patient_id)).scalar_one_or_none()
    if not patient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    client = db.get(Client, patient.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient identity not found")
    ensure_client_access(db, user, client)
    return patient, client


def scoped_encounter_statement(db: Session, user: User, *, location_id: str | None = None):
    statement = select(Encounter).join(PatientProfile, PatientProfile.id == Encounter.patient_id).join(
        Client, Client.id == PatientProfile.client_id,
    ).where(Encounter.organization_id == user.organization_id)
    statement = filter_locations(statement, Encounter, db, user)
    statement = filter_clients(statement, db, user, Client)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(Encounter.location_id == location_id)
    return statement


def encounter_for_user(db: Session, user: User, encounter_id: str, *, lock: bool = False) -> Encounter:
    statement = scoped_encounter_statement(db, user).where(Encounter.id == encounter_id)
    if lock:
        statement = statement.with_for_update()
    encounter = db.execute(statement).scalar_one_or_none()
    if not encounter:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encounter not found")
    return encounter


def prescription_for_user(db: Session, user: User, prescription_id: str, *, lock: bool = False) -> Prescription:
    statement = select(Prescription).join(Encounter, Encounter.id == Prescription.encounter_id).join(
        PatientProfile, PatientProfile.id == Encounter.patient_id,
    ).join(Client, Client.id == PatientProfile.client_id).where(
        Prescription.organization_id == user.organization_id,
        Prescription.id == prescription_id,
    )
    statement = filter_locations(statement, Encounter, db, user)
    statement = filter_clients(statement, db, user, Client)
    if lock:
        statement = statement.with_for_update()
    prescription = db.execute(statement).scalar_one_or_none()
    if not prescription:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
    return prescription


def lab_order_for_user(db: Session, user: User, order_id: str, *, lock: bool = False) -> LabOrder:
    statement = select(LabOrder).join(Encounter, Encounter.id == LabOrder.encounter_id).join(
        PatientProfile, PatientProfile.id == Encounter.patient_id,
    ).join(Client, Client.id == PatientProfile.client_id).where(
        LabOrder.organization_id == user.organization_id,
        LabOrder.id == order_id,
    )
    statement = filter_locations(statement, Encounter, db, user)
    statement = filter_clients(statement, db, user, Client)
    if lock:
        statement = statement.with_for_update()
    order = db.execute(statement).scalar_one_or_none()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lab order not found")
    return order


def _patient_references(db: Session, patient_ids: set[str]):
    patients = {row.id: row for row in db.execute(select(PatientProfile).where(PatientProfile.id.in_(patient_ids))).scalars()} if patient_ids else {}
    client_ids = {row.client_id for row in patients.values()}
    clients = {row.id: row for row in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()} if client_ids else {}
    return patients, clients


def _patient_identity(patient: PatientProfile | None, clients: dict[str, Client]) -> dict | None:
    client = clients.get(patient.client_id) if patient else None
    if not client:
        return None
    return {
        "patient_id": patient.id,
        "client_id": client.id,
        "display_name": f"{client.first_name} {client.last_name}".strip(),
        "client_number": client.client_number,
        "phone": client.phone,
    }


def clinic_summary(db: Session, user: User, location_id: str | None) -> dict:
    start, end = local_day_window(db, user)
    if location_id:
        ensure_location(db, user, location_id)
    client_ids = allowed_client_ids(db, user)

    appointments = select(func.count(Appointment.id)).where(
        Appointment.organization_id == user.organization_id,
        Appointment.starts_at >= start,
        Appointment.starts_at < end,
        Appointment.status.notin_(["cancelled", "no_show"]),
    )
    waiting = select(func.count(Appointment.id)).where(
        Appointment.organization_id == user.organization_id,
        Appointment.starts_at >= start,
        Appointment.starts_at < end,
        Appointment.status == "checked_in",
    )
    appointments = filter_locations(appointments, Appointment, db, user)
    waiting = filter_locations(waiting, Appointment, db, user)
    if location_id:
        appointments = appointments.where(Appointment.location_id == location_id)
        waiting = waiting.where(Appointment.location_id == location_id)
    if client_ids is not None:
        appointments = appointments.where(Appointment.client_id.in_(client_ids))
        waiting = waiting.where(Appointment.client_id.in_(client_ids))

    encounters = scoped_encounter_statement(db, user, location_id=location_id).subquery()
    open_encounters = db.scalar(select(func.count(encounters.c.id)).where(encounters.c.status == "open")) or 0

    lab_statement = select(LabOrder).join(Encounter, Encounter.id == LabOrder.encounter_id).join(
        PatientProfile, PatientProfile.id == Encounter.patient_id,
    ).join(Client, Client.id == PatientProfile.client_id).where(
        LabOrder.organization_id == user.organization_id,
        LabOrder.status.in_(["ordered", "collected"]),
    )
    lab_statement = filter_locations(lab_statement, Encounter, db, user)
    lab_statement = filter_clients(lab_statement, db, user, Client)
    if location_id:
        lab_statement = lab_statement.where(Encounter.location_id == location_id)
    lab_orders = lab_statement.subquery()
    permissions = get_user_permissions(db, user)
    return {
        "appointments_today": int(db.scalar(appointments) or 0),
        "waiting": int(db.scalar(waiting) or 0),
        "open_encounters": int(open_encounters),
        "lab_orders_pending": int(db.scalar(select(func.count(lab_orders.c.id))) or 0) if "clinical.view" in permissions else None,
        "generated_at": datetime.now(timezone.utc),
    }


def clinic_queue(db: Session, user: User, location_id: str | None) -> list[dict]:
    start, end = local_day_window(db, user)
    statement = select(Appointment).where(
        Appointment.organization_id == user.organization_id,
        Appointment.starts_at >= start,
        Appointment.starts_at < end,
        Appointment.status.notin_(["cancelled", "no_show", "completed"]),
    )
    statement = filter_locations(statement, Appointment, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(Appointment.location_id == location_id)
    client_ids = allowed_client_ids(db, user)
    if client_ids is not None:
        statement = statement.where(Appointment.client_id.in_(client_ids))
    rows = db.execute(statement.order_by(Appointment.starts_at, Appointment.id)).scalars().all()
    ids = {row.client_id for row in rows}
    clients = {row.id: row for row in db.execute(select(Client).where(
        Client.organization_id == user.organization_id,
        Client.id.in_(ids),
    )).scalars()} if ids else {}
    employee_ids = {row.employee_id for row in rows if row.employee_id}
    employees = {row.id: row for row in db.execute(select(Employee).where(
        Employee.organization_id == user.organization_id,
        Employee.id.in_(employee_ids),
    )).scalars()} if employee_ids else {}
    service_ids = {row.service_id for row in rows if row.service_id}
    services = {row.id: row for row in db.execute(select(CatalogItem).where(
        CatalogItem.organization_id == user.organization_id,
        CatalogItem.id.in_(service_ids),
    )).scalars()} if service_ids else {}
    return [{
        **serialize(row),
        "patient": ({
            "client_id": client.id,
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "client_number": client.client_number,
        } if (client := clients.get(row.client_id)) else None),
        "practitioner_name": (
            f"{employees[row.employee_id].first_name} {employees[row.employee_id].last_name}".strip()
            if row.employee_id in employees else None
        ),
        "service_name": services[row.service_id].name if row.service_id in services else None,
    } for row in rows]


def patient_directory(db: Session, user: User, location_id: str | None) -> list[dict]:
    rows = db.execute(scoped_patient_statement(db, user, location_id=location_id).order_by(
        PatientProfile.created_at.desc(), PatientProfile.id.desc(),
    ).limit(500)).scalars().all()
    client_ids = {row.client_id for row in rows}
    clients = {row.id: row for row in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()} if client_ids else {}
    return [{
        **serialize(row),
        "client": ({
            "id": client.id,
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "client_number": client.client_number,
            "phone": client.phone,
            "email": client.email,
            "status": client.status,
        } if (client := clients.get(row.client_id)) else None),
    } for row in rows]


def encounter_directory(db: Session, user: User, location_id: str | None, status_filter: str | None) -> list[dict]:
    statement = scoped_encounter_statement(db, user, location_id=location_id)
    if status_filter:
        statement = statement.where(Encounter.status == status_filter)
    rows = db.execute(statement.order_by(Encounter.created_at.desc(), Encounter.id.desc()).limit(300)).scalars().unique().all()
    patients, clients = _patient_references(db, {row.patient_id for row in rows})
    employee_ids = {row.practitioner_employee_id for row in rows}
    employees = {row.id: row for row in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars()} if employee_ids else {}
    locations = {row.id: row for row in db.execute(select(Location).where(Location.id.in_({row.location_id for row in rows}))).scalars()} if rows else {}
    return [{
        **serialize(row),
        "patient": _patient_identity(patients.get(row.patient_id), clients),
        "practitioner_name": (
            f"{employees[row.practitioner_employee_id].first_name} {employees[row.practitioner_employee_id].last_name}".strip()
            if row.practitioner_employee_id in employees else None
        ),
        "location_name": locations[row.location_id].name if row.location_id in locations else None,
    } for row in rows]


def prescription_directory(db: Session, user: User, location_id: str | None) -> list[dict]:
    statement = select(Prescription, Encounter).join(Encounter, Encounter.id == Prescription.encounter_id).join(
        PatientProfile, PatientProfile.id == Encounter.patient_id,
    ).join(Client, Client.id == PatientProfile.client_id).where(Prescription.organization_id == user.organization_id)
    statement = filter_locations(statement, Encounter, db, user)
    statement = filter_clients(statement, db, user, Client)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(Encounter.location_id == location_id)
    rows = db.execute(statement.order_by(Prescription.created_at.desc()).limit(300)).all()
    patients, clients = _patient_references(db, {encounter.patient_id for _, encounter in rows})
    prescription_ids = {prescription.id for prescription, _ in rows}
    item_rows = db.execute(select(PrescriptionItem).where(PrescriptionItem.prescription_id.in_(prescription_ids)).order_by(PrescriptionItem.id)).scalars().all() if prescription_ids else []
    items: dict[str, list[dict]] = {}
    for item in item_rows:
        items.setdefault(item.prescription_id, []).append(serialize(item))
    return [{
        **serialize(prescription),
        "items": items.get(prescription.id, []),
        "patient": _patient_identity(patients.get(encounter.patient_id), clients),
        "encounter_status": encounter.status,
    } for prescription, encounter in rows]


def lab_order_directory(db: Session, user: User, location_id: str | None) -> list[dict]:
    statement = select(LabOrder, Encounter).join(Encounter, Encounter.id == LabOrder.encounter_id).join(
        PatientProfile, PatientProfile.id == Encounter.patient_id,
    ).join(Client, Client.id == PatientProfile.client_id).where(LabOrder.organization_id == user.organization_id)
    statement = filter_locations(statement, Encounter, db, user)
    statement = filter_clients(statement, db, user, Client)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(Encounter.location_id == location_id)
    rows = db.execute(statement.order_by(LabOrder.created_at.desc()).limit(300)).all()
    patients, clients = _patient_references(db, {encounter.patient_id for _, encounter in rows})
    test_ids = {order.test_id for order, _ in rows}
    tests = {row.id: row for row in db.execute(select(LabTest).where(LabTest.id.in_(test_ids))).scalars()} if test_ids else {}
    return [{
        **serialize(order),
        "test": ({"id": tests[order.test_id].id, "name": tests[order.test_id].name, "code": tests[order.test_id].code} if order.test_id in tests else None),
        "patient": _patient_identity(patients.get(encounter.patient_id), clients),
        "encounter_status": encounter.status,
    } for order, encounter in rows]
