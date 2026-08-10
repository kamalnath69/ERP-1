"""Salon workspace composition using shared scheduling, sales, and client records."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Appointment, CatalogItem, Client, ClientCommitment, ClientMedia, Employee,
    EmployeeLocation, SaleInvoice, SalonClientProfile, User,
)
from app.services.business_access import allowed_client_ids, allowed_location_ids, ensure_location, organization_for
from app.services.rbac import get_user_permissions


def _serialize(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def salon_workspace(db: Session, user: User, location_id: str | None, days: int) -> dict:
    org = organization_for(db, user)
    permissions = get_user_permissions(db, user)
    tz = ZoneInfo(org.timezone)
    local_now = datetime.now(tz)
    start = datetime.combine(local_now.date() - timedelta(days=days - 1), time.min, tzinfo=tz).astimezone(timezone.utc)
    today_start = datetime.combine(local_now.date(), time.min, tzinfo=tz).astimezone(timezone.utc)
    tomorrow = (datetime.combine(local_now.date(), time.min, tzinfo=tz) + timedelta(days=1)).astimezone(timezone.utc)
    locations = allowed_location_ids(db, user)
    if location_id:
        ensure_location(db, user, location_id)
        locations = {location_id}
    clients = allowed_client_ids(db, user)

    appointment_stmt = select(Appointment).where(
        Appointment.organization_id == user.organization_id,
        Appointment.starts_at >= start,
    )
    if locations is not None:
        appointment_stmt = appointment_stmt.where(Appointment.location_id.in_(locations))
    if clients is not None:
        appointment_stmt = appointment_stmt.where(Appointment.client_id.in_(clients))
    appointments = db.execute(appointment_stmt.order_by(Appointment.starts_at.desc()).limit(500)).scalars().all()
    client_ids = {row.client_id for row in appointments}
    client_rows = db.execute(select(Client).where(Client.organization_id == user.organization_id, Client.id.in_(client_ids))).scalars().all() if client_ids else []
    client_map = {row.id: row for row in client_rows}
    employee_ids = {row.employee_id for row in appointments if row.employee_id}
    employee_map = {row.id: row for row in db.execute(select(Employee).where(Employee.organization_id == user.organization_id, Employee.id.in_(employee_ids))).scalars()} if employee_ids else {}
    service_ids = {row.service_id for row in appointments if row.service_id}
    service_map = {row.id: row for row in db.execute(select(CatalogItem).where(CatalogItem.organization_id == user.organization_id, CatalogItem.id.in_(service_ids))).scalars()} if service_ids else {}
    avatars = {}
    if "clients.media.view" in permissions and client_ids:
        avatar_rows = db.execute(select(ClientMedia.client_id, func.max(ClientMedia.updated_at)).where(
            ClientMedia.organization_id == user.organization_id,
            ClientMedia.client_id.in_(client_ids), ClientMedia.is_profile.is_(True),
        ).group_by(ClientMedia.client_id)).all()
        avatars = {client_id: f"/clients/{client_id}/photo?v={int(updated.timestamp())}" for client_id, updated in avatar_rows}

    today_rows = [row for row in appointments if today_start <= row.starts_at < tomorrow]
    upcoming = [row for row in appointments if row.starts_at >= local_now.astimezone(timezone.utc) and row.status not in {"cancelled", "no_show", "completed"}]
    completed = [row for row in appointments if row.status == "completed"]
    walkins = [row for row in today_rows if row.source == "walk_in"]

    employee_stmt = select(func.count(func.distinct(Employee.id))).join(EmployeeLocation, EmployeeLocation.employee_id == Employee.id).where(
        Employee.organization_id == user.organization_id, Employee.status == "active",
    )
    if locations is not None:
        employee_stmt = employee_stmt.where(EmployeeLocation.location_id.in_(locations))
    staff_available = int(db.scalar(employee_stmt) or 0)

    rebooking = []
    if "clients.view" in permissions:
        profile_stmt = select(SalonClientProfile, Client).join(Client, Client.id == SalonClientProfile.client_id).where(
            SalonClientProfile.organization_id == user.organization_id,
            SalonClientProfile.visit_interval_days.is_not(None),
        )
        if locations is not None:
            profile_stmt = profile_stmt.where(Client.home_location_id.in_(locations))
        if clients is not None:
            profile_stmt = profile_stmt.where(Client.id.in_(clients))
        for profile, client in db.execute(profile_stmt).all():
            last = db.execute(select(Appointment).where(
                Appointment.organization_id == user.organization_id,
                Appointment.client_id == client.id, Appointment.status == "completed",
            ).order_by(Appointment.completed_at.desc().nullslast(), Appointment.starts_at.desc()).limit(1)).scalar_one_or_none()
            if not last:
                continue
            last_date = (last.completed_at or last.starts_at).astimezone(tz).date()
            due_date = last_date + timedelta(days=profile.visit_interval_days)
            delay = (local_now.date() - due_date).days
            if delay >= 0:
                rebooking.append({
                    "id": profile.id, "client": {"id": client.id, "name": f"{client.first_name} {client.last_name}".strip(), "avatar_url": avatars.get(client.id)},
                    "last_visit": last_date, "expected_on": due_date, "delay_days": delay,
                    "destination": {"kind": "client", "id": client.id},
                })
        rebooking.sort(key=lambda row: row["delay_days"], reverse=True)

    commitments = []
    if "clients.view" in permissions:
        commitment_stmt = select(ClientCommitment, Client).join(Client, Client.id == ClientCommitment.client_id).where(
            ClientCommitment.organization_id == user.organization_id,
            ClientCommitment.status == "open",
        )
        if clients is not None:
            commitment_stmt = commitment_stmt.where(ClientCommitment.client_id.in_(clients))
        if locations is not None:
            commitment_stmt = commitment_stmt.where(Client.home_location_id.in_(locations))
        commitments = db.execute(commitment_stmt.order_by(ClientCommitment.due_at.asc().nullslast()).limit(20)).all()

    sales_stmt = select(func.coalesce(func.sum(SaleInvoice.total_paise), 0)).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.created_at >= start,
        SaleInvoice.status.notin_(["draft", "void", "refunded"]),
    )
    if locations is not None:
        sales_stmt = sales_stmt.where(SaleInvoice.location_id.in_(locations))
    if clients is not None:
        sales_stmt = sales_stmt.where(SaleInvoice.client_id.in_(clients))
    revenue = int(db.scalar(sales_stmt) or 0) if "sales.view" in permissions else None

    return {
        "summary": {
            "bookings_today": len([row for row in today_rows if row.status not in {"cancelled", "no_show"}]),
            "walk_ins_today": len(walkins),
            "completed_today": len([row for row in today_rows if row.status == "completed"]),
            "staff_on_roster": staff_available,
            "rebooking_opportunities": len(rebooking),
            "revenue_paise": revenue,
        },
        "bookings": [_appointment(row, client_map, employee_map, service_map, avatars) for row in sorted(upcoming, key=lambda item: item.starts_at)[:100]],
        "recent_visits": [_appointment(row, client_map, employee_map, service_map, avatars) for row in sorted(completed, key=lambda item: item.completed_at or item.starts_at, reverse=True)[:100]],
        "rebooking": rebooking[:50],
        "follow_ups": [{
            "id": commitment.id, "title": commitment.title, "description": commitment.description,
            "due_at": commitment.due_at, "status": commitment.status,
            "client": {"id": client.id, "name": f"{client.first_name} {client.last_name}".strip(), "avatar_url": avatars.get(client.id)},
            "destination": {"kind": "client", "id": client.id},
        } for commitment, client in commitments],
        "generated_at": datetime.now(timezone.utc),
    }


def _appointment(row, clients, employees, services, avatars) -> dict:
    client = clients.get(row.client_id)
    employee = employees.get(row.employee_id)
    service = services.get(row.service_id)
    return {
        **_serialize(row),
        "client": {"id": client.id, "name": f"{client.first_name} {client.last_name}".strip(), "phone": client.phone, "avatar_url": avatars.get(client.id)} if client else None,
        "employee_name": f"{employee.first_name} {employee.last_name}".strip() if employee else None,
        "service_name": service.name if service else None,
        "profile_ref": {"kind": "client", "id": client.id} if client else None,
    }
