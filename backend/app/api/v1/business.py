"""Shared multi-industry business operations."""
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_any_permission, require_permissions
from app.core.security import hash_password
from app.models import (
    AccessScope, Appointment, CatalogItem, Category, Client, ClientMedia, Document, Employee, EmployeeLocation,
    Encounter, FitnessMeasurement, GymCheckIn, Location, Membership, Notification, Organization, PatientProfile,
    SaleInvoice, SaleLine, SalePayment, StaffSchedule, StockLevel, StockMovement, Task,
    Permission, Role, RolePermission, TrainerAssignment, User, UserPreference, UserRole,
)
from app.services.audit import log_action
from app.services.business_access import (
    allowed_client_ids, allowed_location_ids, enforce_plan_limit, ensure_client_access, ensure_location,
    filter_clients, filter_locations, organization_for, tenant_get,
)
from app.services.entitlements import resolve_entitlements
from app.services.communications import queue_whatsapp_template
from app.services.rbac import get_user_permissions
from app.services.wallet import ensure_wallet, wallet_summary
from app.services.entity_resolution import resolve_entities
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size
from app.schemas import validate_strong_password

router = APIRouter(tags=["business"])


class LocationBody(BaseModel):
    name: str
    code: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    gstin: str | None = None
    is_primary: bool = False


class EmployeeBody(BaseModel):
    employee_number: str | None = None
    first_name: str
    last_name: str = ""
    email: EmailStr | None = None
    phone: str | None = None
    designation: str | None = None
    specialties: list[str] = Field(default_factory=list)
    salary_paise: int | None = Field(default=None, ge=0)
    joining_date: date | None = None
    location_ids: list[str] = Field(min_length=1)
    create_login: bool = False
    password: str | None = None
    role_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_login(self):
        if self.create_login:
            if not self.email or not self.password:
                raise ValueError("Email and a temporary password are required for login access")
            validate_strong_password(self.password)
        return self


class ClientBody(BaseModel):
    first_name: str
    last_name: str = ""
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    home_location_id: str | None = None
    notes: str | None = None
    tags: list[str] = []
    whatsapp_consent: bool = False
    email_consent: bool = False

    @model_validator(mode="after")
    def consent_requires_phone(self):
        if self.whatsapp_consent and not self.phone:
            raise ValueError("A phone number is required for WhatsApp reminders")
        return self


class CategoryBody(BaseModel):
    name: str
    kind: str = "product"


class CatalogBody(BaseModel):
    name: str
    sku: str
    item_type: str
    category_id: str | None = None
    description: str | None = None
    hsn_sac: str | None = None
    price_paise: int = Field(default=0, ge=0)
    cost_paise: int = Field(default=0, ge=0)
    tax_rate_bps: int = Field(default=0, ge=0, le=10000)
    tax_inclusive: bool = False
    duration_minutes: int | None = Field(default=None, ge=1)
    unit: str = "unit"
    track_stock: bool = False


class StockAdjustBody(BaseModel):
    location_id: str
    item_id: str
    quantity_delta_milli: int
    reason: str = Field(min_length=3)
    batch_number: str = ""
    expires_on: date | None = None
    reorder_level_milli: int | None = Field(default=None, ge=0)


class AppointmentBody(BaseModel):
    location_id: str
    client_id: str
    employee_id: str | None = None
    service_id: str | None = None
    starts_at: datetime
    ends_at: datetime
    status: str = "scheduled"
    source: str = "staff"
    notes: str | None = None


class AppointmentStatusBody(BaseModel):
    status: str
    version: int


class AppointmentUpdateBody(BaseModel):
    starts_at: datetime
    ends_at: datetime
    employee_id: str | None = None
    service_id: str | None = None
    location_id: str
    notes: str | None = None
    version: int


class TaskBody(BaseModel):
    title: str
    description: str | None = None
    location_id: str | None = None
    client_id: str | None = None
    assigned_to_user_id: str | None = None
    due_at: datetime | None = None
    priority: str = "normal"


def serialize(row, extra: dict | None = None) -> dict:
    data = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        data[column.name] = value.value if hasattr(value, "value") else value
    if extra:
        data.update(extra)
    return data


def paged(db: Session, statement, model, limit: int, cursor: str | None):
    limit = min(max(limit, 1), 100)
    if cursor:
        pivot = db.get(model, cursor)
        if pivot:
            statement = statement.where(
                or_(model.created_at < pivot.created_at, and_(model.created_at == pivot.created_at, model.id < pivot.id))
            )
    rows = db.execute(statement.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)).scalars().all()
    return rows[:limit], rows[limit - 1].id if len(rows) > limit else None


def _normalized_search(value: str) -> tuple[str, str]:
    words = " ".join(value.casefold().split())
    return words, re.sub(r"[\W_]+", "", words, flags=re.UNICODE)


def _search_parts(name_expression, other_expressions: tuple, query: str, compact_query: str):
    searchable_source = name_expression
    for expression in other_expressions:
        searchable_source = searchable_source + " " + func.coalesce(expression, "")
    searchable = func.lower(searchable_source)
    compact_name = func.regexp_replace(func.lower(name_expression), r"[^[:alnum:]]+", "", "g")
    compact_searchable = func.regexp_replace(searchable, r"[^[:alnum:]]+", "", "g")
    similarity = func.greatest(
        func.similarity(compact_name, compact_query),
        func.similarity(searchable, query),
    )
    words = [word for word in query.split(" ") if word]
    matches = or_(
        searchable.contains(query),
        compact_searchable.contains(compact_query),
        and_(*(searchable.contains(word) for word in words)),
        similarity >= 0.24,
    )
    score = case(
        (func.lower(name_expression) == query, 100),
        (compact_name == compact_query, 96),
        (compact_name.startswith(compact_query), 86),
        (compact_name.contains(compact_query), 76),
        (searchable.startswith(query), 68),
        (searchable.contains(query), 60),
        else_=similarity * 50,
    ).label("search_score")
    return matches, score


def _client_avatar_urls(db: Session, user, client_ids: list[str]) -> dict[str, str]:
    if not client_ids or "clients.media.view" not in get_user_permissions(db, user):
        return {}
    rows = db.execute(select(
        ClientMedia.client_id, func.max(ClientMedia.updated_at),
    ).where(
        ClientMedia.organization_id == user.organization_id,
        ClientMedia.client_id.in_(client_ids),
        ClientMedia.is_profile.is_(True),
    ).group_by(ClientMedia.client_id)).all()
    return {
        client_id: f"/clients/{client_id}/photo?v={int(updated_at.timestamp())}"
        for client_id, updated_at in rows if updated_at
    }


@router.get("/organization/context")
def organization_context(user=Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.rbac import get_user_permissions, get_user_roles
    org = organization_for(db, user)
    allowed = allowed_location_ids(db, user)
    locations = db.execute(select(Location).where(
        Location.organization_id == org.id, Location.is_active.is_(True)
    ).order_by(Location.is_primary.desc(), Location.name)).scalars().all()
    if allowed is not None:
        locations = [loc for loc in locations if loc.id in allowed]
    entitlements = resolve_entitlements(db, org)
    wallet = ensure_wallet(db, org)
    usage = {
        "employees": db.scalar(select(func.count(Employee.id)).where(Employee.organization_id == org.id)) or 0,
        "clients": db.scalar(select(func.count(Client.id)).where(Client.organization_id == org.id)) or 0,
        "locations": db.scalar(select(func.count(Location.id)).where(Location.organization_id == org.id, Location.is_active.is_(True))) or 0,
        "storage_bytes": db.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.organization_id == org.id)) or 0,
    }
    preference_rows = db.execute(select(UserPreference).where(UserPreference.user_id == user.id)).scalars().all()
    db.commit()
    return {
        "organization": serialize(org), "locations": [serialize(loc) for loc in locations],
        "permissions": sorted(get_user_permissions(db, user)),
        "roles": [serialize(role) for role in get_user_roles(db, user)],
        "location_restricted": allowed is not None,
        "entitlements": entitlements,
        "usage": usage,
        "ai_wallet": wallet_summary(wallet),
        "preferences": {row.namespace: {"value": row.value, "version": row.version} for row in preference_rows},
    }


@router.patch("/organization")
def update_organization(body: dict, user=Depends(require_permissions("settings.manage")), db: Session = Depends(get_db)):
    org = organization_for(db, user)
    allowed = {"name", "legal_name", "gstin", "timezone", "contact_email", "contact_phone", "logo_url", "invoice_prefix", "onboarding_complete", "onboarding_step"}
    for key, value in body.items():
        if key in allowed:
            setattr(org, key, value)
    log_action(db, organization_id=org.id, user_id=user.id, action="organization.update", resource_type="organization", resource_id=org.id)
    db.commit()
    return serialize(org)


@router.get("/locations")
def list_locations(user=Depends(get_current_user), db: Session = Depends(get_db)):
    organization_for(db, user)
    stmt = select(Location).where(Location.organization_id == user.organization_id, Location.is_active.is_(True))
    allowed = allowed_location_ids(db, user)
    if allowed is not None:
        stmt = stmt.where(Location.id.in_(allowed))
    return [serialize(row) for row in db.execute(stmt.order_by(Location.is_primary.desc(), Location.name)).scalars()]


@router.post("/locations", status_code=status.HTTP_201_CREATED)
def create_location(body: LocationBody, user=Depends(require_any_permission("settings.manage", "settings.locations.manage")), db: Session = Depends(get_db)):
    organization_for(db, user)
    count = db.scalar(select(func.count(Location.id)).where(Location.organization_id == user.organization_id, Location.is_active.is_(True))) or 0
    enforce_plan_limit(db, user, "locations", count)
    if body.is_primary:
        db.query(Location).filter(Location.organization_id == user.organization_id).update({Location.is_primary: False})
    row = Location(organization_id=user.organization_id, **body.model_dump())
    db.add(row)
    db.flush()
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="location.create",
        resource_type="location",
        resource_id=row.id,
        changes={"name": row.name, "code": row.code},
    )
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.patch("/locations/{location_id}")
def update_location(location_id: str, body: dict, user=Depends(require_any_permission("settings.manage", "settings.locations.manage")), db: Session = Depends(get_db)):
    row = ensure_location(db, user, location_id)
    expected = body.pop("version", None)
    if expected is None or expected != row.version:
        raise HTTPException(409, "Location settings changed on another device")
    allowed = {"name", "address", "city", "state", "postal_code", "phone", "gstin", "is_active"}
    for key, value in body.items():
        if key in allowed:
            setattr(row, key, value)
    row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="location.update", resource_type="location", resource_id=row.id)
    db.commit()
    return serialize(row)


@router.get("/employees")
def list_employees(q: str | None = None, limit: int = 50, cursor: str | None = None, user=Depends(require_permissions("employees.view")), db: Session = Depends(get_db)):
    stmt = select(Employee).where(Employee.organization_id == user.organization_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Employee.first_name).like(like), func.lower(Employee.last_name).like(like), func.lower(Employee.email).like(like), func.lower(Employee.phone).like(like)))
    allowed = allowed_location_ids(db, user)
    if allowed is not None:
        employee_ids = select(EmployeeLocation.employee_id).where(EmployeeLocation.location_id.in_(allowed))
        stmt = stmt.where(Employee.id.in_(employee_ids))
    rows, next_cursor = paged(db, stmt, Employee, limit, cursor)
    result = []
    can_view_compensation = "employees.compensation.view" in get_user_permissions(db, user)
    for row in rows:
        location_ids = list(db.execute(select(EmployeeLocation.location_id).where(EmployeeLocation.employee_id == row.id)).scalars())
        item = serialize(row, {"location_ids": location_ids})
        if not can_view_compensation:
            item.pop("salary_paise", None)
        result.append(item)
    return {"items": result, "next_cursor": next_cursor}


@router.post("/employees", status_code=status.HTTP_201_CREATED)
def create_employee(body: EmployeeBody, user=Depends(require_permissions("employees.manage")), db: Session = Depends(get_db)):
    db.execute(select(Organization.id).where(Organization.id == user.organization_id).with_for_update()).scalar_one()
    count = db.scalar(select(func.count(Employee.id)).where(Employee.organization_id == user.organization_id)) or 0
    enforce_plan_limit(db, user, "employees", count)
    if body.salary_paise is not None and "employees.compensation.view" not in get_user_permissions(db, user):
        raise HTTPException(403, "Compensation access is required to set salary")
    location_ids = list(dict.fromkeys(body.location_ids))
    for location_id in location_ids:
        ensure_location(db, user, location_id)
    roles = db.execute(select(Role).where(
        Role.organization_id == user.organization_id,
        Role.id.in_(body.role_ids),
        Role.is_active.is_(True),
    )).scalars().all() if body.role_ids else []
    if {role.id for role in roles} != set(body.role_ids):
        raise HTTPException(422, "One or more roles are invalid or inactive")
    actor_permissions = get_user_permissions(db, user)
    role_codes = set(db.execute(select(Permission.code).join(
        RolePermission, RolePermission.permission_id == Permission.id,
    ).where(RolePermission.role_id.in_(body.role_ids))).scalars()) if body.role_ids else set()
    if not role_codes.issubset(actor_permissions):
        raise HTTPException(403, "Cannot assign a role with capabilities outside your own access")
    login_user = None
    if body.create_login:
        if db.execute(select(User.id).where(User.organization_id == user.organization_id, User.email == str(body.email).lower())).scalar_one_or_none():
            raise HTTPException(409, "This email already has an account in your organization")
        login_user = User(
            organization_id=user.organization_id, email=str(body.email).lower(), hashed_password=hash_password(body.password),
            first_name=body.first_name, last_name=body.last_name, phone=body.phone, designation=body.designation,
        )
        db.add(login_user)
        db.flush()
        for role in roles:
            db.add(UserRole(user_id=login_user.id, role_id=role.id))
    payload = body.model_dump(exclude={"location_ids", "create_login", "password", "role_ids"})
    payload["email"] = str(body.email).lower() if body.email else None
    next_number = count + 1
    generated_number = f"EMP-{next_number:04d}"
    while db.execute(select(Employee.id).where(Employee.organization_id == user.organization_id, Employee.employee_number == generated_number)).scalar_one_or_none():
        next_number += 1
        generated_number = f"EMP-{next_number:04d}"
    payload["employee_number"] = body.employee_number or generated_number
    row = Employee(organization_id=user.organization_id, user_id=login_user.id if login_user else None, **payload)
    db.add(row)
    db.flush()
    for index, location_id in enumerate(location_ids):
        db.add(EmployeeLocation(employee_id=row.id, location_id=location_id, is_primary=index == 0))
        if login_user:
            db.add(AccessScope(organization_id=user.organization_id, user_id=login_user.id, scope_type="location", scope_value=location_id, meta={}))
    if login_user:
        db.add(AccessScope(organization_id=user.organization_id, user_id=login_user.id, scope_type="location_mode", scope_value="restricted", meta={}))
        db.add(AccessScope(organization_id=user.organization_id, user_id=login_user.id, scope_type="client_mode", scope_value="all", meta={}))
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="employee.create", resource_type="employee", resource_id=row.id, permission="employees.manage", meta={"login_created": bool(login_user), "location_count": len(location_ids)})
    db.commit()
    return serialize(row, {"location_ids": location_ids})


@router.get("/employees/{employee_id}/profile")
def employee_profile(employee_id: str, user=Depends(require_permissions("employees.view")), db: Session = Depends(get_db)):
    row = tenant_get(db, Employee, employee_id, user)
    permissions = get_user_permissions(db, user)
    capabilities = {
        "view_compensation": "employees.compensation.view" in permissions,
        "view_account": "users.view" in permissions,
        "view_appointments": "appointments.view" in permissions,
        "view_sales": "sales.view" in permissions,
        "manage": "employees.manage" in permissions,
    }
    location_rows = db.execute(
        select(Location, EmployeeLocation.is_primary)
        .join(EmployeeLocation, EmployeeLocation.location_id == Location.id)
        .where(EmployeeLocation.employee_id == row.id)
        .order_by(EmployeeLocation.is_primary.desc(), Location.name)
    ).all()
    allowed = allowed_location_ids(db, user)
    if allowed is not None and not any(location.id in allowed for location, _ in location_rows):
        raise HTTPException(403, "Employee is outside your location access")
    if allowed is not None:
        location_rows = [(location, primary) for location, primary in location_rows if location.id in allowed]
    location_ids = [location.id for location, _ in location_rows]
    appointments_stmt = select(Appointment).where(Appointment.organization_id == user.organization_id, Appointment.employee_id == row.id)
    sales_stmt = select(SaleInvoice).where(SaleInvoice.organization_id == user.organization_id, SaleInvoice.employee_id == row.id)
    if allowed is not None:
        appointments_stmt = appointments_stmt.where(Appointment.location_id.in_(allowed))
        sales_stmt = sales_stmt.where(SaleInvoice.location_id.in_(allowed))
    appointments = db.execute(appointments_stmt.order_by(Appointment.starts_at.desc()).limit(50)).scalars().all() if capabilities["view_appointments"] else []
    sales = db.execute(sales_stmt.order_by(SaleInvoice.created_at.desc()).limit(50)).scalars().all() if capabilities["view_sales"] else []
    schedules_stmt = select(StaffSchedule).where(StaffSchedule.organization_id == user.organization_id, StaffSchedule.employee_id == row.id)
    if allowed is not None:
        schedules_stmt = schedules_stmt.where(StaffSchedule.location_id.in_(allowed))
    schedules = db.execute(schedules_stmt.order_by(StaffSchedule.weekday)).scalars().all()
    account = db.get(User, row.user_id) if row.user_id and capabilities["view_account"] else None
    available_stmt = select(Location).where(Location.organization_id == user.organization_id, Location.is_active.is_(True)).order_by(Location.name)
    if allowed is not None:
        available_stmt = available_stmt.where(Location.id.in_(allowed))
    available_locations = db.execute(available_stmt).scalars().all() if capabilities["manage"] else []
    employee_data = serialize(row, {"location_ids": location_ids})
    if not capabilities["view_compensation"]:
        employee_data.pop("salary_paise", None)
    return {
        "employee": employee_data,
        "locations": [serialize(location, {"is_primary": primary}) for location, primary in location_rows],
        "available_locations": [serialize(location) for location in available_locations],
        "account": {
            "id": account.id, "email": account.email, "is_active": account.is_active,
            "last_login": account.last_login, "email_verified": account.email_verified,
        } if account else None,
        "appointments": [serialize(item) for item in appointments],
        "sales": [serialize(item) for item in sales],
        "schedules": [serialize(item) for item in schedules],
        "metrics": {
            "appointment_count": len(appointments) if capabilities["view_appointments"] else None,
            "completed_appointments": sum(item.status == "completed" for item in appointments) if capabilities["view_appointments"] else None,
            "sales_paise": sum(item.total_paise for item in sales if item.status not in {"void", "refunded"}) if capabilities["view_sales"] else None,
        },
        "capabilities": capabilities,
    }


@router.patch("/employees/{employee_id}")
def update_employee(employee_id: str, body: dict, user=Depends(require_permissions("employees.manage")), db: Session = Depends(get_db)):
    row = tenant_get(db, Employee, employee_id, user)
    if "salary_paise" in body and "employees.compensation.view" not in get_user_permissions(db, user):
        raise HTTPException(403, "Compensation access is required to change salary")
    expected = body.pop("version", None)
    if expected is None or expected != row.version:
        raise HTTPException(409, "Employee was changed by another user")
    location_ids = body.pop("location_ids", None)
    if location_ids is not None:
        for location_id in location_ids:
            ensure_location(db, user, location_id)
        allowed_locations = allowed_location_ids(db, user)
        preserved_location_ids = []
        if allowed_locations is not None:
            existing_location_ids = db.execute(
                select(EmployeeLocation.location_id).where(EmployeeLocation.employee_id == row.id)
            ).scalars().all()
            preserved_location_ids = [location_id for location_id in existing_location_ids if location_id not in allowed_locations]
        location_ids = list(dict.fromkeys([*preserved_location_ids, *location_ids]))
        db.query(EmployeeLocation).filter(EmployeeLocation.employee_id == row.id).delete()
        for index, location_id in enumerate(location_ids):
            db.add(EmployeeLocation(employee_id=row.id, location_id=location_id, is_primary=index == 0))
    allowed = {"first_name", "last_name", "email", "phone", "designation", "specialties", "salary_paise", "joining_date", "status"}
    for key, value in body.items():
        if key in allowed:
            setattr(row, key, value)
    row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="employee.update", resource_type="employee", resource_id=row.id)
    db.commit()
    return serialize(row, {"location_ids": location_ids if location_ids is not None else list(db.execute(select(EmployeeLocation.location_id).where(EmployeeLocation.employee_id == row.id)).scalars())})


@router.get("/clients")
def list_clients(q: str | None = None, status_filter: str | None = Query(None, alias="status"), location_id: str | None = None, limit: int = 50, cursor: str | None = None, user=Depends(require_permissions("clients.view")), db: Session = Depends(get_db)):
    stmt = select(Client).where(Client.organization_id == user.organization_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Client.first_name).like(like), func.lower(Client.last_name).like(like), func.lower(Client.phone).like(like), func.lower(Client.email).like(like), func.lower(Client.client_number).like(like)))
    if status_filter:
        stmt = stmt.where(Client.status == status_filter)
    if location_id:
        ensure_location(db, user, location_id)
        stmt = stmt.where(Client.home_location_id == location_id)
    stmt = filter_clients(stmt, db, user)
    rows, next_cursor = paged(db, stmt, Client, limit, cursor)
    return {"items": [serialize(row) for row in rows], "next_cursor": next_cursor}


@router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(body: ClientBody, user=Depends(require_permissions("clients.manage")), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(Client.id)).where(Client.organization_id == user.organization_id)) or 0
    enforce_plan_limit(db, user, "clients", count)
    if body.home_location_id:
        ensure_location(db, user, body.home_location_id)
    values = body.model_dump()
    if values["whatsapp_consent"]:
        values.update(whatsapp_consent_at=datetime.now(timezone.utc), whatsapp_consent_source="staff_recorded")
    row = Client(organization_id=user.organization_id, client_number=f"CLI-{count + 1:06d}", **values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row)


@router.get("/clients/{client_id}")
def get_client(client_id: str, user=Depends(require_permissions("clients.view")), db: Session = Depends(get_db)):
    row = tenant_get(db, Client, client_id, user)
    ensure_client_access(db, user, row)
    return serialize(row)


@router.get("/clients/{client_id}/profile")
def client_profile(client_id: str, user=Depends(require_permissions("clients.view")), db: Session = Depends(get_db)):
    row = tenant_get(db, Client, client_id, user)
    ensure_client_access(db, user, row)
    permissions = get_user_permissions(db, user)
    capabilities = {
        "view_appointments": "appointments.view" in permissions,
        "view_sales": "sales.view" in permissions,
        "view_memberships": "gym.memberships.view" in permissions,
        "view_checkins": "gym.attendance.view" in permissions,
        "view_measurements": "gym.measurements.view" in permissions,
        "view_clinical": "clinical.view" in permissions,
        "view_documents": "documents.view" in permissions,
    }
    allowed = allowed_location_ids(db, user)
    appointments_stmt = select(Appointment).where(Appointment.organization_id == user.organization_id, Appointment.client_id == row.id)
    sales_stmt = select(SaleInvoice).where(SaleInvoice.organization_id == user.organization_id, SaleInvoice.client_id == row.id)
    if allowed is not None:
        appointments_stmt = appointments_stmt.where(Appointment.location_id.in_(allowed))
        sales_stmt = sales_stmt.where(SaleInvoice.location_id.in_(allowed))
    appointments = db.execute(appointments_stmt.order_by(Appointment.starts_at.desc()).limit(100)).scalars().all() if capabilities["view_appointments"] else []
    sales = db.execute(sales_stmt.order_by(SaleInvoice.created_at.desc()).limit(100)).scalars().all() if capabilities["view_sales"] else []
    memberships_stmt = select(Membership).where(Membership.organization_id == user.organization_id, Membership.client_id == row.id)
    checkins_stmt = select(GymCheckIn).where(GymCheckIn.organization_id == user.organization_id, GymCheckIn.client_id == row.id)
    if allowed is not None:
        memberships_stmt = memberships_stmt.where(Membership.location_id.in_(allowed))
        checkins_stmt = checkins_stmt.where(GymCheckIn.location_id.in_(allowed))
    memberships = db.execute(memberships_stmt.order_by(Membership.created_at.desc())).scalars().all() if capabilities["view_memberships"] else []
    checkins = db.execute(checkins_stmt.order_by(GymCheckIn.checked_in_at.desc()).limit(50)).scalars().all() if capabilities["view_checkins"] else []
    assignments = db.execute(select(TrainerAssignment).where(TrainerAssignment.organization_id == user.organization_id, TrainerAssignment.client_id == row.id).order_by(TrainerAssignment.created_at.desc())).scalars().all() if capabilities["view_memberships"] else []
    measurements = db.execute(select(FitnessMeasurement).where(FitnessMeasurement.organization_id == user.organization_id, FitnessMeasurement.client_id == row.id).order_by(FitnessMeasurement.measured_on.desc()).limit(20)).scalars().all() if capabilities["view_measurements"] else []
    patient = db.execute(select(PatientProfile).where(PatientProfile.organization_id == user.organization_id, PatientProfile.client_id == row.id)).scalar_one_or_none() if capabilities["view_clinical"] else None
    encounters_stmt = select(Encounter).where(Encounter.organization_id == user.organization_id, Encounter.patient_id == patient.id) if patient else None
    documents_stmt = select(Document).where(Document.organization_id == user.organization_id, Document.entity_type == "client", Document.entity_id == row.id)
    if capabilities["view_documents"]:
        from app.ai.retrieval import document_access_conditions
        documents_stmt = documents_stmt.where(*document_access_conditions(db, user))
    if allowed is not None:
        if encounters_stmt is not None:
            encounters_stmt = encounters_stmt.where(Encounter.location_id.in_(allowed))
        documents_stmt = documents_stmt.where(or_(Document.location_id.in_(allowed), Document.location_id.is_(None)))
    encounters = db.execute(encounters_stmt.order_by(Encounter.created_at.desc()).limit(30)).scalars().all() if encounters_stmt is not None else []
    documents = db.execute(documents_stmt.order_by(Document.created_at.desc())).scalars().all() if capabilities["view_documents"] else []
    return {
        "client": serialize(row),
        "appointments": [serialize(item) for item in appointments],
        "sales": [serialize(item) for item in sales],
        "memberships": [serialize(item) for item in memberships],
        "checkins": [serialize(item) for item in checkins],
        "trainer_assignments": [serialize(item) for item in assignments],
        "measurements": [serialize(item) for item in measurements],
        "patient": serialize(patient) if patient else None,
        "encounters": [serialize(item) for item in encounters],
        "documents": [serialize(item, {"object_key": None}) for item in documents],
        "metrics": {
            "lifetime_value_paise": sum(item.paid_paise for item in sales) if capabilities["view_sales"] else None,
            "outstanding_paise": sum(max(item.total_paise - item.paid_paise, 0) for item in sales if item.status not in {"void", "refunded"}) if capabilities["view_sales"] else None,
            "visits": len([item for item in appointments if item.status == "completed"]) + len(checkins) if capabilities["view_appointments"] or capabilities["view_checkins"] else None,
        },
        "capabilities": capabilities,
    }


@router.patch("/clients/{client_id}")
def update_client(client_id: str, body: dict, user=Depends(require_permissions("clients.manage")), db: Session = Depends(get_db)):
    row = tenant_get(db, Client, client_id, user)
    expected = body.pop("version", None)
    if expected is None or expected != row.version:
        raise HTTPException(409, "Client was changed by another user")
    allowed = {"first_name", "last_name", "phone", "email", "address", "date_of_birth", "gender", "home_location_id", "notes", "tags", "whatsapp_consent", "email_consent", "status"}
    if body.get("home_location_id"):
        ensure_location(db, user, body["home_location_id"])
    if body.get("whatsapp_consent") and not (body.get("phone") or row.phone):
        raise HTTPException(422, "A phone number is required for WhatsApp reminders")
    consent_changed = "whatsapp_consent" in body and bool(body["whatsapp_consent"]) != row.whatsapp_consent
    if consent_changed:
        row.whatsapp_consent_at = datetime.now(timezone.utc) if body["whatsapp_consent"] else None
        row.whatsapp_consent_source = "staff_recorded" if body["whatsapp_consent"] else None
    for key, value in body.items():
        if key in allowed:
            setattr(row, key, value)
    row.version += 1
    if consent_changed:
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action="client.whatsapp_consent_changed", resource_type="client", resource_id=row.id,
            changes={"enabled": bool(body["whatsapp_consent"]), "source": row.whatsapp_consent_source},
        )
    db.commit()
    return serialize(row)


@router.get("/categories")
def list_categories(user=Depends(require_permissions("catalog.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(Category).where(Category.organization_id == user.organization_id, Category.is_active.is_(True)).order_by(Category.name)).scalars()
    return [serialize(row) for row in rows]


@router.post("/categories", status_code=201)
def create_category(body: CategoryBody, user=Depends(require_permissions("catalog.manage")), db: Session = Depends(get_db)):
    row = Category(organization_id=user.organization_id, **body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return serialize(row)


@router.get("/catalog")
def list_catalog(q: str | None = None, item_type: str | None = None, user=Depends(require_permissions("catalog.view")), db: Session = Depends(get_db)):
    stmt = select(CatalogItem).where(CatalogItem.organization_id == user.organization_id, CatalogItem.is_active.is_(True))
    if q:
        like = f"%{q.lower()}%"; stmt = stmt.where(or_(func.lower(CatalogItem.name).like(like), func.lower(CatalogItem.sku).like(like)))
    if item_type:
        stmt = stmt.where(CatalogItem.item_type == item_type)
    return [serialize(row) for row in db.execute(stmt.order_by(CatalogItem.name)).scalars()]


@router.get("/catalog/page")
def catalog_page(
    q: str | None = Query(default=None, max_length=100),
    item_type: str | None = Query(default=None, pattern="^(product|service|medicine|lab_test)$"),
    state: str = Query(default="active", pattern="^(active|inactive|all)$"),
    track_stock: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    user=Depends(require_permissions("catalog.view")),
    db: Session = Depends(get_db),
):
    normalized_query = " ".join((q or "").casefold().split())
    filters = {
        "q": normalized_query,
        "item_type": item_type,
        "state": state,
        "track_stock": track_stock,
    }
    values = decode_cursor(
        cursor,
        scope="catalog.directory",
        organization_id=user.organization_id,
        filters=filters,
    )
    statement = select(CatalogItem).where(CatalogItem.organization_id == user.organization_id)
    if state != "all":
        statement = statement.where(CatalogItem.is_active.is_(state == "active"))
    if item_type:
        statement = statement.where(CatalogItem.item_type == item_type)
    if track_stock is not None:
        statement = statement.where(CatalogItem.track_stock.is_(track_stock))
    if normalized_query:
        term = f"%{normalized_query}%"
        statement = statement.where(or_(
            func.lower(CatalogItem.name).like(term),
            func.lower(CatalogItem.sku).like(term),
            func.lower(func.coalesce(CatalogItem.hsn_sac, "")).like(term),
            func.lower(func.coalesce(CatalogItem.description, "")).like(term),
        ))
    name_key = func.lower(CatalogItem.name)
    if values:
        statement = statement.where(or_(
            name_key > str(values["name"]),
            and_(name_key == str(values["name"]), CatalogItem.id > str(values["id"])),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(name_key, CatalogItem.id).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="catalog.directory",
        organization_id=user.organization_id,
        filters=filters,
        values={"name": rows[-1].name.casefold(), "id": rows[-1].id},
    ) if has_more and rows else None
    summary = db.execute(select(
        func.count(CatalogItem.id),
        func.coalesce(func.sum(case((CatalogItem.item_type.in_(("product", "medicine")), 1), else_=0)), 0),
        func.coalesce(func.sum(case((CatalogItem.item_type.in_(("service", "lab_test")), 1), else_=0)), 0),
        func.coalesce(func.sum(case((CatalogItem.track_stock.is_(True), 1), else_=0)), 0),
    ).where(
        CatalogItem.organization_id == user.organization_id,
        CatalogItem.is_active.is_(True),
    )).one()
    return {
        "items": [serialize(row) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "summary": {
            "catalog_items": int(summary[0] or 0),
            "products": int(summary[1] or 0),
            "services": int(summary[2] or 0),
            "stock_tracked": int(summary[3] or 0),
        },
    }


@router.post("/catalog", status_code=201)
def create_catalog_item(body: CatalogBody, user=Depends(require_permissions("catalog.manage")), db: Session = Depends(get_db)):
    if body.category_id:
        tenant_get(db, Category, body.category_id, user)
    row = CatalogItem(organization_id=user.organization_id, **body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return serialize(row)


@router.get("/catalog/{item_id}/profile")
def catalog_profile(item_id: str, location_id: str | None = None,
                    user=Depends(require_permissions("catalog.view")), db: Session = Depends(get_db)):
    row = tenant_get(db, CatalogItem, item_id, user)
    selected_location = ensure_location(db, user, location_id) if location_id else None
    permissions = get_user_permissions(db, user)
    capabilities = {
        "view_inventory": "inventory.view" in permissions,
        "view_appointments": "appointments.view" in permissions,
        "view_sales": "sales.view" in permissions,
        "manage": "catalog.manage" in permissions,
        "adjust_inventory": "inventory.adjust" in permissions,
    }
    allowed = allowed_location_ids(db, user)
    levels_stmt = select(StockLevel).where(StockLevel.organization_id == user.organization_id, StockLevel.item_id == row.id)
    movements_stmt = select(StockMovement).where(StockMovement.organization_id == user.organization_id, StockMovement.item_id == row.id)
    appointments_stmt = select(Appointment).where(Appointment.organization_id == user.organization_id, Appointment.service_id == row.id)
    sales_stmt = select(SaleLine, SaleInvoice).join(SaleInvoice, SaleInvoice.id == SaleLine.invoice_id).where(SaleLine.organization_id == user.organization_id, SaleLine.item_id == row.id)
    if selected_location:
        levels_stmt = levels_stmt.where(StockLevel.location_id == selected_location.id)
        movements_stmt = movements_stmt.where(StockMovement.location_id == selected_location.id)
        appointments_stmt = appointments_stmt.where(Appointment.location_id == selected_location.id)
        sales_stmt = sales_stmt.where(SaleInvoice.location_id == selected_location.id)
    if allowed is not None:
        levels_stmt = levels_stmt.where(StockLevel.location_id.in_(allowed))
        movements_stmt = movements_stmt.where(StockMovement.location_id.in_(allowed))
        appointments_stmt = appointments_stmt.where(Appointment.location_id.in_(allowed))
        sales_stmt = sales_stmt.where(SaleInvoice.location_id.in_(allowed))
    levels = db.execute(levels_stmt.order_by(StockLevel.updated_at.desc())).scalars().all() if capabilities["view_inventory"] else []
    movements = db.execute(movements_stmt.order_by(StockMovement.created_at.desc()).limit(100)).scalars().all() if capabilities["view_inventory"] else []
    appointments = db.execute(appointments_stmt.order_by(Appointment.starts_at.desc()).limit(50)).scalars().all() if capabilities["view_appointments"] else []
    sales = db.execute(sales_stmt.order_by(SaleInvoice.created_at.desc()).limit(100)).all() if capabilities["view_sales"] else []
    location_ids = {level.location_id for level in levels}
    locations = {item.id: item for item in db.execute(select(Location).where(Location.id.in_(location_ids))).scalars()} if location_ids else {}
    return {
        "item": serialize(row),
        "stock": [serialize(level, {"location": serialize(locations[level.location_id])}) for level in levels],
        "movements": [serialize(item) for item in movements],
        "appointments": [serialize(item) for item in appointments],
        "sales": [{"line": serialize(line), "invoice": serialize(invoice)} for line, invoice in sales],
        "metrics": {
            "stock_milli": sum(level.quantity_milli for level in levels) if capabilities["view_inventory"] else None,
            "units_sold_milli": sum(line.quantity_milli for line, invoice in sales if invoice.status not in {"void", "refunded"}) if capabilities["view_sales"] else None,
            "revenue_paise": sum(line.total_paise for line, invoice in sales if invoice.status not in {"void", "refunded"}) if capabilities["view_sales"] else None,
            "bookings": len(appointments) if capabilities["view_appointments"] else None,
        },
        "scope": {"location": serialize(selected_location) if selected_location else None},
        "capabilities": capabilities,
    }


@router.patch("/catalog/{item_id}")
def update_catalog_item(item_id: str, body: dict, user=Depends(require_permissions("catalog.manage")), db: Session = Depends(get_db)):
    row = tenant_get(db, CatalogItem, item_id, user)
    expected = body.pop("version", None)
    if expected is None or expected != row.version:
        raise HTTPException(409, "Catalog item was changed by another user")
    allowed = {"name", "category_id", "description", "hsn_sac", "price_paise", "cost_paise", "tax_rate_bps", "tax_inclusive", "duration_minutes", "unit", "track_stock", "is_active"}
    if body.get("category_id"):
        tenant_get(db, Category, body["category_id"], user)
    for key, value in body.items():
        if key in allowed:
            setattr(row, key, value)
    row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="catalog.update", resource_type="catalog_item", resource_id=row.id)
    db.commit()
    return serialize(row)


@router.get("/inventory")
def list_inventory(location_id: str | None = None, low_stock: bool = False, user=Depends(require_permissions("inventory.view")), db: Session = Depends(get_db)):
    stmt = select(StockLevel).where(StockLevel.organization_id == user.organization_id)
    stmt = filter_locations(stmt, StockLevel, db, user)
    if location_id:
        ensure_location(db, user, location_id); stmt = stmt.where(StockLevel.location_id == location_id)
    if low_stock:
        stmt = stmt.where(StockLevel.quantity_milli <= StockLevel.reorder_level_milli)
    rows = db.execute(stmt.order_by(StockLevel.updated_at.desc())).scalars().all()
    item_ids = {row.item_id for row in rows}
    items = {row.id: row for row in db.execute(select(CatalogItem).where(CatalogItem.id.in_(item_ids))).scalars()} if item_ids else {}
    return [serialize(row, {"item": serialize(items[row.item_id])}) for row in rows]


@router.post("/inventory/adjust", status_code=201)
def adjust_stock(body: StockAdjustBody, user=Depends(require_permissions("inventory.adjust")), db: Session = Depends(get_db)):
    ensure_location(db, user, body.location_id)
    item = tenant_get(db, CatalogItem, body.item_id, user)
    if not item.track_stock:
        raise HTTPException(400, "This item does not track stock")
    stmt = select(StockLevel).where(
        StockLevel.organization_id == user.organization_id, StockLevel.location_id == body.location_id,
        StockLevel.item_id == body.item_id, StockLevel.batch_number == body.batch_number,
    ).with_for_update()
    level = db.execute(stmt).scalar_one_or_none()
    if not level:
        level = StockLevel(
            organization_id=user.organization_id, location_id=body.location_id, item_id=body.item_id,
            batch_number=body.batch_number, expires_on=body.expires_on, quantity_milli=0,
        )
        db.add(level); db.flush()
    if level.quantity_milli + body.quantity_delta_milli < 0:
        raise HTTPException(409, "Insufficient stock")
    level.quantity_milli += body.quantity_delta_milli
    if body.reorder_level_milli is not None:
        level.reorder_level_milli = body.reorder_level_milli
    level.version += 1
    movement = StockMovement(
        organization_id=user.organization_id, location_id=body.location_id, item_id=item.id,
        stock_level_id=level.id, movement_type="adjustment", quantity_delta_milli=body.quantity_delta_milli,
        reason=body.reason, performed_by_user_id=user.id,
    )
    db.add(movement)
    if level.quantity_milli <= level.reorder_level_milli:
        db.add(Notification(
            organization_id=user.organization_id, user_id=user.id, kind="warning",
            title=f"Low stock: {item.name}",
            body=f"Available quantity is {level.quantity_milli / 1000:g} {item.unit} at this location.",
            link=f"/app/catalog/{item.id}",
        ))
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="inventory.adjust", resource_type="stock_level", resource_id=level.id, changes={"delta_milli": body.quantity_delta_milli, "reason": body.reason})
    db.commit()
    return serialize(level)


@router.get("/appointments")
def list_appointments(start: datetime | None = None, end: datetime | None = None, location_id: str | None = None, employee_id: str | None = None, user=Depends(require_permissions("appointments.view")), db: Session = Depends(get_db)):
    stmt = select(Appointment).where(Appointment.organization_id == user.organization_id)
    stmt = filter_locations(stmt, Appointment, db, user)
    if location_id:
        ensure_location(db, user, location_id); stmt = stmt.where(Appointment.location_id == location_id)
    if start: stmt = stmt.where(Appointment.ends_at > start)
    if end: stmt = stmt.where(Appointment.starts_at < end)
    if employee_id: stmt = stmt.where(Appointment.employee_id == employee_id)
    clients = allowed_client_ids(db, user)
    if clients is not None:
        stmt = stmt.where(Appointment.client_id.in_(clients))
    rows = list(db.execute(stmt.order_by(Appointment.starts_at).limit(500)).scalars())
    client_ids = {row.client_id for row in rows if row.client_id}
    employee_ids = {row.employee_id for row in rows if row.employee_id}
    service_ids = {row.service_id for row in rows if row.service_id}
    clients_by_id = {row.id: row for row in db.execute(select(Client).where(
        Client.organization_id == user.organization_id,
        Client.id.in_(client_ids),
    )).scalars()} if client_ids else {}
    employees_by_id = {row.id: row for row in db.execute(select(Employee).where(
        Employee.organization_id == user.organization_id,
        Employee.id.in_(employee_ids),
    )).scalars()} if employee_ids else {}
    services_by_id = {row.id: row for row in db.execute(select(CatalogItem).where(
        CatalogItem.organization_id == user.organization_id,
        CatalogItem.id.in_(service_ids),
    )).scalars()} if service_ids else {}
    return [{
        **serialize(row),
        "client": ({
            "id": clients_by_id[row.client_id].id,
            "first_name": clients_by_id[row.client_id].first_name,
            "last_name": clients_by_id[row.client_id].last_name,
            "client_number": clients_by_id[row.client_id].client_number,
        } if row.client_id in clients_by_id else None),
        "employee": ({
            "id": employees_by_id[row.employee_id].id,
            "first_name": employees_by_id[row.employee_id].first_name,
            "last_name": employees_by_id[row.employee_id].last_name,
            "designation": employees_by_id[row.employee_id].designation,
        } if row.employee_id in employees_by_id else None),
        "service": ({
            "id": services_by_id[row.service_id].id,
            "name": services_by_id[row.service_id].name,
            "duration_minutes": services_by_id[row.service_id].duration_minutes,
        } if row.service_id in services_by_id else None),
    } for row in rows]


@router.post("/appointments", status_code=201)
def create_appointment(body: AppointmentBody, user=Depends(require_permissions("appointments.manage")), db: Session = Depends(get_db)):
    location = ensure_location(db, user, body.location_id); client = ensure_client_access(db, user, tenant_get(db, Client, body.client_id, user))
    if body.ends_at <= body.starts_at:
        raise HTTPException(400, "Appointment end must be after start")
    if body.employee_id:
        employee = tenant_get(db, Employee, body.employee_id, user)
        conflict = db.execute(select(Appointment.id).where(
            Appointment.organization_id == user.organization_id, Appointment.employee_id == employee.id,
            Appointment.status.notin_(["cancelled", "no_show"]),
            Appointment.starts_at < body.ends_at, Appointment.ends_at > body.starts_at,
        )).first()
        if conflict:
            raise HTTPException(409, "Employee already has an appointment in this time slot")
    if body.service_id:
        tenant_get(db, CatalogItem, body.service_id, user)
    row = Appointment(organization_id=user.organization_id, **body.model_dump())
    db.add(row); db.flush()
    organization = organization_for(db, user)
    try: local_start = row.starts_at.astimezone(ZoneInfo(organization.timezone))
    except Exception: local_start = row.starts_at
    queue_whatsapp_template(
        db, organization=organization, client=client, location_id=location.id,
        template=settings.WHATSAPP_TEMPLATE_APPOINTMENT_CONFIRMATION,
        variables=[client.first_name, organization.name, local_start.strftime("%d %b %Y"), local_start.strftime("%I:%M %p"), location.name],
        body=f"Appointment booked for {local_start.strftime('%d %b %Y at %I:%M %p')} at {location.name}",
        idempotency_key=f"wa-appointment:{row.id}:confirmation",
    )
    db.commit(); db.refresh(row)
    return serialize(row)


@router.patch("/appointments/{appointment_id}/status")
def update_appointment_status(appointment_id: str, body: AppointmentStatusBody, user=Depends(require_permissions("appointments.manage")), db: Session = Depends(get_db)):
    row = tenant_get(db, Appointment, appointment_id, user, location_field="location_id")
    ensure_client_access(db, user, tenant_get(db, Client, row.client_id, user))
    if row.version != body.version:
        raise HTTPException(409, "Appointment was changed by another user")
    transitions = {
        "scheduled": {"confirmed", "checked_in", "cancelled", "no_show"}, "confirmed": {"checked_in", "cancelled", "no_show"},
        "checked_in": {"in_progress", "cancelled"}, "in_progress": {"completed", "cancelled"}, "completed": set(),
    }
    if body.status not in transitions.get(row.status, set()):
        raise HTTPException(409, f"Cannot move appointment from {row.status} to {body.status}")
    row.status = body.status; row.version += 1
    now = datetime.now(timezone.utc)
    if body.status == "checked_in": row.checked_in_at = now
    if body.status == "completed": row.completed_at = now
    if body.status in {"confirmed", "cancelled"}:
        client = tenant_get(db, Client, row.client_id, user)
        location = ensure_location(db, user, row.location_id)
        organization = organization_for(db, user)
        try: local_start = row.starts_at.astimezone(ZoneInfo(organization.timezone))
        except Exception: local_start = row.starts_at
        queue_whatsapp_template(
            db, organization=organization, client=client, location_id=location.id,
            template=settings.WHATSAPP_TEMPLATE_APPOINTMENT_STATUS,
            variables=[client.first_name, organization.name, body.status.replace("_", " ").title(), local_start.strftime("%d %b %Y"), local_start.strftime("%I:%M %p")],
            body=f"Appointment status updated to {body.status.replace('_', ' ')}",
            idempotency_key=f"wa-appointment:{row.id}:status:{body.status}",
        )
    db.commit()
    return serialize(row)


@router.patch("/appointments/{appointment_id}")
def reschedule_appointment(appointment_id: str, body: AppointmentUpdateBody, user=Depends(require_permissions("appointments.manage")), db: Session = Depends(get_db)):
    row = tenant_get(db, Appointment, appointment_id, user, location_field="location_id")
    ensure_client_access(db, user, tenant_get(db, Client, row.client_id, user))
    if row.version != body.version:
        raise HTTPException(409, "Appointment was changed by another user")
    if body.ends_at <= body.starts_at:
        raise HTTPException(400, "Appointment end must be after start")
    ensure_location(db, user, body.location_id)
    if body.employee_id:
        employee = tenant_get(db, Employee, body.employee_id, user)
        conflict = db.execute(select(Appointment.id).where(
            Appointment.organization_id == user.organization_id,
            Appointment.employee_id == employee.id,
            Appointment.id != row.id,
            Appointment.status.notin_(["cancelled", "no_show"]),
            Appointment.starts_at < body.ends_at,
            Appointment.ends_at > body.starts_at,
        )).first()
        if conflict:
            raise HTTPException(409, "Employee already has an appointment in this time slot")
    if body.service_id:
        tenant_get(db, CatalogItem, body.service_id, user)
    previous = {"starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(), "employee_id": row.employee_id, "location_id": row.location_id}
    row.starts_at = body.starts_at
    row.ends_at = body.ends_at
    row.employee_id = body.employee_id
    row.service_id = body.service_id
    row.location_id = body.location_id
    row.notes = body.notes
    row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="appointment.rescheduled", resource_type="appointment", resource_id=row.id, permission="appointments.manage", meta={"previous": previous})
    db.commit()
    return serialize(row)


@router.get("/tasks")
def list_tasks(user=Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Task).where(Task.organization_id == user.organization_id, Task.status != "done")
    allowed = allowed_location_ids(db, user)
    if allowed is not None: stmt = stmt.where(or_(Task.location_id.in_(allowed), Task.location_id.is_(None)))
    return [serialize(row) for row in db.execute(stmt.order_by(Task.due_at.asc().nullslast()).limit(100)).scalars()]


@router.post("/tasks", status_code=201)
def create_task(body: TaskBody, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if body.location_id: ensure_location(db, user, body.location_id)
    if body.client_id: tenant_get(db, Client, body.client_id, user)
    row = Task(organization_id=user.organization_id, source="manual", **body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return serialize(row)


@router.get("/dashboard")
def dashboard(location_id: str | None = None, user=Depends(require_permissions("dashboard.view")), db: Session = Depends(get_db)):
    org = organization_for(db, user)
    if location_id: ensure_location(db, user, location_id)
    now = datetime.now(timezone.utc); today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    sales = select(func.coalesce(func.sum(SaleInvoice.paid_paise), 0)).where(SaleInvoice.organization_id == org.id, SaleInvoice.status.in_(["paid", "partially_paid"]))
    today_sales = sales.where(SaleInvoice.created_at >= today_start); month_sales = sales.where(SaleInvoice.created_at >= month_start)
    appt = select(func.count(Appointment.id)).where(Appointment.organization_id == org.id, Appointment.starts_at >= today_start, Appointment.starts_at < today_start + timedelta(days=1), Appointment.status.notin_(["cancelled", "no_show"]))
    low = select(func.count(StockLevel.id)).where(StockLevel.organization_id == org.id, StockLevel.quantity_milli <= StockLevel.reorder_level_milli)
    if location_id:
        today_sales = today_sales.where(SaleInvoice.location_id == location_id); month_sales = month_sales.where(SaleInvoice.location_id == location_id)
        appt = appt.where(Appointment.location_id == location_id); low = low.where(StockLevel.location_id == location_id)
    expiring = 0
    if org.industry.value == "gym":
        expiring = db.scalar(select(func.count(Membership.id)).where(Membership.organization_id == org.id, Membership.status == "active", Membership.ends_on.between(now.date(), now.date() + timedelta(days=7)))) or 0
    return {
        "industry": org.industry.value,
        "kpis": {
            "today_revenue_paise": db.scalar(today_sales) or 0, "month_revenue_paise": db.scalar(month_sales) or 0,
            "active_clients": db.scalar(select(func.count(Client.id)).where(Client.organization_id == org.id, Client.status == "active")) or 0,
            "new_clients_month": db.scalar(select(func.count(Client.id)).where(Client.organization_id == org.id, Client.created_at >= month_start)) or 0,
            "appointments_today": db.scalar(appt) or 0, "low_stock_items": db.scalar(low) or 0,
            "employee_count": db.scalar(select(func.count(Employee.id)).where(Employee.organization_id == org.id, Employee.status == "active")) or 0,
            "pending_renewals": expiring,
        },
        "generated_at": now,
    }


@router.get("/search")
def global_search(q: str = Query(min_length=2, max_length=100), user=Depends(get_current_user), db: Session = Depends(get_db)):
    grouped = {kind: resolve_entities(db, user, q, [kind], 8)["items"] for kind in ["client", "employee", "catalog"]}
    return {
        "clients": grouped["client"], "employees": grouped["employee"], "catalog": grouped["catalog"],
    }
