"""Permission-aware Team directory queries."""
from collections import defaultdict
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Appointment, Employee, EmployeeLocation, Location, Organization, Role, StaffSchedule,
    TrainerAssignment, User, UserRole,
)
from app.services.business_access import allowed_location_ids, ensure_location
from app.services.cursor_pagination import decode_cursor_or_legacy_id, encode_cursor
from app.services.rbac import get_user_permissions


def _scoped_employee_statement(db: Session, user: User, location_id: str | None = None):
    statement = select(Employee).where(Employee.organization_id == user.organization_id)
    allowed = allowed_location_ids(db, user)
    if location_id:
        ensure_location(db, user, location_id)
        allowed = {location_id}
    if allowed is not None:
        employee_ids = select(EmployeeLocation.employee_id).where(EmployeeLocation.location_id.in_(allowed))
        statement = statement.where(Employee.id.in_(employee_ids))
    return statement, allowed


def build_team_directory(
    db: Session,
    user: User,
    *,
    location_id: str | None,
    query: str | None,
    status: str | None,
    limit: int,
    cursor: str | None,
) -> dict:
    base, allowed = _scoped_employee_statement(db, user, location_id)
    summary_subquery = base.with_only_columns(Employee.id).subquery()
    scoped_ids = select(summary_subquery.c.id)
    permissions = get_user_permissions(db, user)

    organization = db.get(Organization, user.organization_id)
    local_now = datetime.now(ZoneInfo(organization.timezone or "Asia/Kolkata"))
    day_start = datetime.combine(local_now.date(), time.min, local_now.tzinfo).astimezone(timezone.utc)
    day_end = datetime.combine(local_now.date(), time.max, local_now.tzinfo).astimezone(timezone.utc)
    summary = {
        "team_members": int(db.scalar(select(func.count(Employee.id)).where(Employee.id.in_(scoped_ids))) or 0),
        "active": int(db.scalar(select(func.count(Employee.id)).where(Employee.id.in_(scoped_ids), Employee.status == "active")) or 0),
        "login_accounts": int(db.scalar(select(func.count(Employee.id)).where(Employee.id.in_(scoped_ids), Employee.user_id.is_not(None))) or 0),
        "available_today": int(db.scalar(select(func.count(func.distinct(StaffSchedule.employee_id))).where(
            StaffSchedule.organization_id == user.organization_id,
            StaffSchedule.employee_id.in_(scoped_ids),
            StaffSchedule.weekday == local_now.weekday(),
            StaffSchedule.is_available.is_(True),
        )) or 0),
    }

    statement = base
    if query:
        like = f"%{' '.join(query.casefold().split())}%"
        compact = f"%{''.join(character for character in query.casefold() if character.isalnum())}%"
        statement = statement.where(or_(
            func.lower(Employee.first_name + " " + Employee.last_name).like(like),
            func.lower(Employee.first_name + Employee.last_name).like(compact),
            func.lower(func.coalesce(Employee.email, "")).like(like),
            func.lower(func.coalesce(Employee.phone, "")).like(compact),
            func.lower(Employee.employee_number).like(like),
            func.lower(func.coalesce(Employee.designation, "")).like(like),
        ))
    if status:
        statement = statement.where(Employee.status == status)
    cursor_filters = {"location_id": location_id, "q": query, "status": status}
    cursor_values = decode_cursor_or_legacy_id(
        cursor, scope="team.directory", organization_id=user.organization_id,
        filters=cursor_filters,
    ) if cursor else None
    if cursor_values:
        if cursor_values.get("legacy"):
            pivot = db.get(Employee, cursor_values["id"])
            if not pivot or pivot.organization_id != user.organization_id:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid Team cursor")
            first, row_id = pivot.first_name.casefold(), pivot.id
        else:
            first = str(cursor_values.get("first") or "")
            row_id = str(cursor_values.get("id") or "")
        statement = statement.where(or_(
            func.lower(Employee.first_name) > first,
            and_(func.lower(Employee.first_name) == first, Employee.id > row_id),
        ))
    page_size = min(max(limit, 1), 100)
    employees = db.execute(statement.order_by(func.lower(Employee.first_name), Employee.id).limit(page_size + 1)).scalars().all()
    has_more = len(employees) > page_size
    employees = employees[:page_size]
    employee_ids = [row.id for row in employees]
    user_ids = [row.user_id for row in employees if row.user_id]

    locations_by_employee: dict[str, list[dict]] = defaultdict(list)
    if employee_ids:
        location_rows = db.execute(select(EmployeeLocation.employee_id, Location).join(
            Location, Location.id == EmployeeLocation.location_id,
        ).where(EmployeeLocation.employee_id.in_(employee_ids)).order_by(Location.name)).all()
        for employee_id, location in location_rows:
            if allowed is None or location.id in allowed:
                locations_by_employee[employee_id].append({"id": location.id, "name": location.name})

    roles_by_user: dict[str, list[str]] = defaultdict(list)
    if user_ids:
        for user_id, role_name in db.execute(select(UserRole.user_id, Role.name).join(Role, Role.id == UserRole.role_id).where(
            UserRole.user_id.in_(user_ids), Role.is_active.is_(True),
        )).all():
            roles_by_user[user_id].append(role_name)
    accounts = {row.id: row for row in db.execute(select(User).where(User.id.in_(user_ids))).scalars()} if user_ids else {}

    schedules = dict(db.execute(select(StaffSchedule.employee_id, func.count(StaffSchedule.id)).where(
        StaffSchedule.employee_id.in_(employee_ids), StaffSchedule.is_available.is_(True),
    ).group_by(StaffSchedule.employee_id)).all()) if employee_ids else {}
    appointments = {}
    if employee_ids and "appointments.view" in permissions:
        appointment_statement = select(Appointment.employee_id, func.count(Appointment.id)).where(
            Appointment.organization_id == user.organization_id,
            Appointment.employee_id.in_(employee_ids),
            Appointment.starts_at.between(day_start, day_end),
            Appointment.status.notin_(["cancelled", "no_show"]),
        )
        if allowed is not None:
            appointment_statement = appointment_statement.where(Appointment.location_id.in_(allowed))
        appointments = dict(db.execute(appointment_statement.group_by(Appointment.employee_id)).all())
    assigned_clients = dict(db.execute(select(TrainerAssignment.trainer_employee_id, func.count(func.distinct(TrainerAssignment.client_id))).where(
        TrainerAssignment.organization_id == user.organization_id,
        TrainerAssignment.trainer_employee_id.in_(employee_ids),
        TrainerAssignment.status == "active",
    ).group_by(TrainerAssignment.trainer_employee_id)).all()) if employee_ids and organization.industry.value == "gym" else {}

    return {
        "summary": summary,
        "items": [{
            "id": row.id,
            "employee_number": row.employee_number,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "email": row.email,
            "phone": row.phone,
            "designation": row.designation,
            "specialties": row.specialties,
            "joining_date": row.joining_date,
            "status": row.status,
            "version": row.version,
            "locations": locations_by_employee.get(row.id, []),
            "roles": roles_by_user.get(row.user_id, []) if row.user_id else [],
            "account": {
                "enabled": bool(row.user_id),
                "active": accounts[row.user_id].is_active if row.user_id in accounts else False,
                "verified": accounts[row.user_id].email_verified if row.user_id in accounts else False,
            },
            "schedule_days": int(schedules.get(row.id, 0)),
            "appointments_today": int(appointments.get(row.id, 0)) if "appointments.view" in permissions else None,
            "assigned_clients": int(assigned_clients.get(row.id, 0)) if organization.industry.value == "gym" else None,
        } for row in employees],
        "next_cursor": encode_cursor(
            scope="team.directory", organization_id=user.organization_id,
            filters=cursor_filters,
            values={"first": employees[-1].first_name.casefold(), "id": employees[-1].id},
        ) if has_more and employees else None,
        "has_more": has_more,
        "capabilities": {
            "manage": "employees.manage" in permissions,
            "view_compensation": "employees.compensation.view" in permissions,
            "manage_access": "roles.manage" in permissions,
        },
        "source": {"generated_at": datetime.now(timezone.utc), "timezone": organization.timezone},
    }
