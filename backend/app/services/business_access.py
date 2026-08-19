"""Central tenant, plan, and location-boundary enforcement."""
from fastapi import HTTPException, status
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.models import AccessScope, Location, Organization, User
from app.services.entitlements import resolve_entitlements


def organization_for(db: Session, user: User) -> Organization:
    if not user.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No organization context")
    org = db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.status.value in {"suspended", "cancelled"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is not active")
    return org


def allowed_location_ids(db: Session, user: User) -> set[str] | None:
    """None means all tenant locations; a set is an explicit location boundary."""
    from app.models import Organization
    from app.services.access_policy import college_policy_applies, resolve_policy_context
    from app.services.rbac import is_system_owner

    if is_system_owner(db, user):
        return None

    organization = db.get(Organization, user.organization_id) if user.organization_id else None
    if (
        organization
        and getattr(organization.industry, "value", organization.industry) == "college"
        and college_policy_applies(db, user.organization_id)
    ):
        context = resolve_policy_context(db, user)
        if not context.active:
            return set()
        if context.maximum_scope.unrestricted:
            return None
        return set(context.maximum_scope.location_ids)

    rows = db.execute(select(AccessScope).where(
        AccessScope.organization_id == user.organization_id,
        AccessScope.user_id == user.id,
        AccessScope.scope_type == "location",
    )).scalars().all()
    mode = db.execute(select(AccessScope.scope_value).where(
        AccessScope.organization_id == user.organization_id,
        AccessScope.user_id == user.id,
        AccessScope.scope_type == "location_mode",
    )).scalar_one_or_none()
    if mode == "full":
        return None
    if mode == "restricted":
        return {row.scope_value for row in rows}
    return {row.scope_value for row in rows} if rows else None


def client_scope_mode(db: Session, user: User) -> str:
    row = db.execute(select(AccessScope).where(
        AccessScope.organization_id == user.organization_id,
        AccessScope.user_id == user.id,
        AccessScope.scope_type == "client_mode",
    )).scalar_one_or_none()
    return row.scope_value if row and row.scope_value in {"all", "assigned", "selected"} else "all"


def allowed_client_ids(db: Session, user: User) -> set[str] | None:
    """None means all clients in allowed locations; a set is an explicit boundary."""
    from app.models import CollegeStudentProfile, Organization
    from app.services.access_policy import college_policy_applies, resolve_policy_context
    from app.services.rbac import is_system_owner

    if is_system_owner(db, user):
        return None

    organization = db.get(Organization, user.organization_id) if user.organization_id else None
    if (
        organization
        and getattr(organization.industry, "value", organization.industry) == "college"
        and college_policy_applies(db, user.organization_id)
    ):
        context = resolve_policy_context(db, user)
        if not context.active:
            return set()
        if context.maximum_scope.unrestricted:
            return None
        if not context.maximum_scope.student_ids:
            return set()
        return set(db.execute(select(CollegeStudentProfile.client_id).where(
            CollegeStudentProfile.organization_id == user.organization_id,
            CollegeStudentProfile.id.in_(context.maximum_scope.student_ids),
        )).scalars())

    mode = client_scope_mode(db, user)
    if mode == "all":
        return None
    if mode == "selected":
        return set(db.execute(select(AccessScope.scope_value).where(
            AccessScope.organization_id == user.organization_id,
            AccessScope.user_id == user.id,
            AccessScope.scope_type == "client",
        )).scalars())

    from app.models import Appointment, Employee, Encounter, PatientProfile, TrainerAssignment
    employee = db.execute(select(Employee).where(
        Employee.organization_id == user.organization_id, Employee.user_id == user.id,
    )).scalar_one_or_none()
    if not employee:
        return set()
    client_ids = set(db.execute(select(TrainerAssignment.client_id).where(
        TrainerAssignment.organization_id == user.organization_id,
        TrainerAssignment.trainer_employee_id == employee.id,
        TrainerAssignment.status == "active",
    )).scalars())
    client_ids.update(db.execute(select(Appointment.client_id).where(
        Appointment.organization_id == user.organization_id,
        Appointment.employee_id == employee.id,
    )).scalars())
    client_ids.update(db.execute(
        select(PatientProfile.client_id).join(Encounter, Encounter.patient_id == PatientProfile.id).where(
            Encounter.organization_id == user.organization_id,
            Encounter.practitioner_employee_id == employee.id,
        )
    ).scalars())
    return client_ids


def ensure_location(db: Session, user: User, location_id: str) -> Location:
    from app.services.access_policy import college_policy_applies

    location = db.execute(select(Location).where(
        Location.id == location_id, Location.organization_id == user.organization_id, Location.is_active.is_(True)
    )).scalar_one_or_none()
    if not location:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    allowed = allowed_location_ids(db, user)
    if allowed is not None and location.id not in allowed:
        organization = db.get(Organization, user.organization_id)
        is_college_policy = (
            organization
            and getattr(organization.industry, "value", organization.industry) == "college"
            and college_policy_applies(db, user.organization_id)
        )
        if is_college_policy:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Location is outside your access")
    return location


def ensure_client_access(db: Session, user: User, client):
    if client.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    from app.models import CollegeStudentProfile, Organization
    from app.services.access_policy import college_policy_applies, resolve_policy_context

    organization = db.get(Organization, user.organization_id) if user.organization_id else None
    if (
        organization
        and getattr(organization.industry, "value", organization.industry) == "college"
        and college_policy_applies(db, user.organization_id)
    ):
        context = resolve_policy_context(db, user)
        scope = context.scope("students")
        profile = db.execute(select(CollegeStudentProfile).where(
            CollegeStudentProfile.organization_id == user.organization_id,
            CollegeStudentProfile.client_id == client.id,
        )).scalar_one_or_none()
        if not context.active or context.level("students") == "none" or not profile or not scope.contains("student", profile.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
        return client
    if client.home_location_id:
        ensure_location(db, user, client.home_location_id)
    allowed = allowed_client_ids(db, user)
    if allowed is not None and client.id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Client is outside your assigned access")
    return client


def filter_clients(statement, db: Session, user: User, model=None):
    from app.models import Client, CollegeStudentProfile, Organization
    from app.services.access_policy import college_policy_applies, resolve_policy_context
    model = model or Client
    # Tenant isolation is mandatory here so callers cannot accidentally rely on
    # location/client scopes as a substitute for the organization boundary.
    statement = statement.where(model.organization_id == user.organization_id)
    organization = db.get(Organization, user.organization_id) if user.organization_id else None
    if (
        organization
        and getattr(organization.industry, "value", organization.industry) == "college"
        and college_policy_applies(db, user.organization_id)
    ):
        context = resolve_policy_context(db, user)
        if not context.active or context.level("students") == "none":
            return statement.where(false())
        scope = context.scope("students")
        if not scope.unrestricted:
            statement = statement.where(model.id.in_(select(CollegeStudentProfile.client_id).where(
                CollegeStudentProfile.organization_id == user.organization_id,
                CollegeStudentProfile.id.in_(scope.student_ids) if scope.student_ids else false(),
            )))
        return statement
    locations = allowed_location_ids(db, user)
    if locations is not None:
        statement = statement.where(or_(model.home_location_id.in_(locations), model.home_location_id.is_(None)))
    clients = allowed_client_ids(db, user)
    if clients is not None:
        statement = statement.where(model.id.in_(clients) if clients else false())
    return statement


def tenant_get(db: Session, model, row_id: str, user: User, *, location_field: str | None = None):
    row = db.get(model, row_id)
    if not row or getattr(row, "organization_id", None) != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    if location_field:
        location_id = getattr(row, location_field, None)
        if location_id:
            ensure_location(db, user, location_id)
    return row


def enforce_plan_limit(db: Session, user: User, resource: str, current_count: int) -> None:
    org = organization_for(db, user)
    resolved = resolve_entitlements(db, org)
    limit = resolved["values"].get(f"limits.{resource}")
    if limit is not None and current_count >= limit:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, f"{resource.title()} limit reached for the current plan")


def filter_locations(statement, model, db: Session, user: User, field: str = "location_id"):
    allowed = allowed_location_ids(db, user)
    if allowed is not None:
        statement = statement.where(getattr(model, field).in_(allowed))
    return statement
