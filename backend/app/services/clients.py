"""Permission-scoped Client directory queries and presentation models."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, case, false, func, or_, select, true
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    Client,
    ClientMedia,
    ClientSignal,
    CollegeCohort,
    CollegeProgram,
    CollegeStudentProfile,
    Location,
    Membership,
    Organization,
    SaleInvoice,
    User,
)
from app.services.business_access import ensure_location, filter_clients
from app.services.access_policy import policy_v2_enabled, require_policy_domain
from app.services.cursor_pagination import decode_cursor_or_legacy_id, encode_cursor
from app.services.rbac import get_user_permissions


DIRECTORY_SEGMENTS = {"all", "active", "inactive", "new", "attention", "member", "product_only", "balance"}


def _scoped_client_ids(db: Session, user: User, location_id: str | None):
    statement = select(Client.id).where(Client.organization_id == user.organization_id)
    organization = db.get(Organization, user.organization_id)
    if organization and organization.industry.value == "college":
        statement = statement.join(
            CollegeStudentProfile,
            CollegeStudentProfile.client_id == Client.id,
        ).where(CollegeStudentProfile.organization_id == user.organization_id)
    if location_id:
        statement = statement.where(Client.home_location_id == location_id)
    return filter_clients(statement, db, user).subquery()


def _summary(
    db: Session,
    user: User,
    location_id: str | None,
    now: datetime,
    *,
    can_view_financial: bool = True,
    financial_client_ids: set[str] | None = None,
) -> dict:
    scoped = _scoped_client_ids(db, user, location_id)
    organization = db.get(Organization, user.organization_id)
    is_college = bool(organization and organization.industry.value == "college")
    if is_college:
        base = select(
            Client.id,
            CollegeStudentProfile.status.label("status"),
            CollegeStudentProfile.admitted_on.label("created_at"),
        ).join(
            CollegeStudentProfile,
            CollegeStudentProfile.client_id == Client.id,
        ).where(
            Client.id.in_(select(scoped.c.id)),
            CollegeStudentProfile.organization_id == user.organization_id,
        ).subquery()
    else:
        base = select(Client).where(Client.id.in_(select(scoped.c.id))).subquery()
    recent_since = now - timedelta(days=30)
    total, active, recent = db.execute(select(
        func.count(base.c.id),
        func.coalesce(func.sum(case((base.c.status == "active", 1), else_=0)), 0),
        func.coalesce(func.sum(case((base.c.created_at >= (recent_since.date() if is_college else recent_since), 1), else_=0)), 0),
    )).one()
    attention = 0 if is_college else db.scalar(select(func.count(func.distinct(ClientSignal.client_id))).where(
        ClientSignal.organization_id == user.organization_id,
        ClientSignal.client_id.in_(select(scoped.c.id)),
        ClientSignal.status.in_(["open", "snoozed"]),
        or_(ClientSignal.snoozed_until.is_(None), ClientSignal.snoozed_until <= now),
    )) or 0
    members = 0 if is_college else db.scalar(select(func.count(func.distinct(Membership.client_id))).where(
        Membership.organization_id == user.organization_id,
        Membership.client_id.in_(select(scoped.c.id)),
        Membership.status.in_(["active", "frozen"]),
    )) or 0
    outstanding = db.scalar(select(func.coalesce(func.sum(SaleInvoice.total_paise - SaleInvoice.paid_paise), 0)).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.client_id.in_(select(scoped.c.id)),
        (
            true()
            if financial_client_ids is None
            else SaleInvoice.client_id.in_(financial_client_ids) if financial_client_ids else false()
        ),
        SaleInvoice.status.notin_(["void", "refunded"]),
        SaleInvoice.total_paise > SaleInvoice.paid_paise,
    )) or 0 if can_view_financial else 0
    return {
        "total": int(total or 0),
        "active": int(active or 0),
        "new_30d": int(recent or 0),
        "attention": int(attention),
        "active_members": int(members),
        "outstanding_paise": int(outstanding),
    }


def _aggregates(
    user: User,
    now: datetime,
    *,
    include_financial: bool = True,
    include_operations: bool = True,
    financial_client_ids: set[str] | None = None,
):
    sales = select(
        SaleInvoice.client_id.label("client_id"),
        func.coalesce(func.sum(SaleInvoice.paid_paise), 0).label("lifetime_value_paise"),
        func.coalesce(func.sum(case(
            (SaleInvoice.status.notin_(["void", "refunded"]), func.greatest(SaleInvoice.total_paise - SaleInvoice.paid_paise, 0)),
            else_=0,
        )), 0).label("outstanding_paise"),
        func.count(SaleInvoice.id).label("invoice_count"),
    ).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.client_id.is_not(None),
        true() if include_financial else false(),
        (
            true()
            if financial_client_ids is None
            else SaleInvoice.client_id.in_(financial_client_ids) if financial_client_ids else false()
        ),
    ).group_by(SaleInvoice.client_id).subquery()

    memberships = select(
        Membership.client_id.label("client_id"),
        func.max(Membership.ends_on).label("membership_ends_on"),
    ).where(
        Membership.organization_id == user.organization_id,
        Membership.status.in_(["active", "frozen"]),
        true() if include_operations else false(),
    ).group_by(Membership.client_id).subquery()

    appointments = select(
        Appointment.client_id.label("client_id"),
        func.min(Appointment.starts_at).label("next_appointment_at"),
    ).where(
        Appointment.organization_id == user.organization_id,
        Appointment.starts_at >= now,
        Appointment.status.in_(["scheduled", "confirmed", "checked_in"]),
        true() if include_operations else false(),
    ).group_by(Appointment.client_id).subquery()

    signals = select(
        ClientSignal.client_id.label("client_id"),
        func.count(ClientSignal.id).label("open_signal_count"),
    ).where(
        ClientSignal.organization_id == user.organization_id,
        ClientSignal.status.in_(["open", "snoozed"]),
        or_(ClientSignal.snoozed_until.is_(None), ClientSignal.snoozed_until <= now),
        true() if include_operations else false(),
    ).group_by(ClientSignal.client_id).subquery()

    photos = select(
        ClientMedia.client_id.label("client_id"),
        func.max(ClientMedia.updated_at).label("photo_updated_at"),
    ).where(
        ClientMedia.organization_id == user.organization_id,
        ClientMedia.is_profile.is_(True),
    ).group_by(ClientMedia.client_id).subquery()
    return sales, memberships, appointments, signals, photos


def client_directory(
    db: Session,
    user: User,
    *,
    location_id: str | None = None,
    query: str | None = None,
    segment: str = "all",
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    if segment not in DIRECTORY_SEGMENTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown Client segment")
    if location_id:
        ensure_location(db, user, location_id)
    now = datetime.now(timezone.utc)
    org = db.get(Organization, user.organization_id)
    permissions = get_user_permissions(db, user)
    is_college = bool(org and org.industry.value == "college")
    context = None
    if is_college and policy_v2_enabled(db, user.organization_id):
        context = require_policy_domain(db, user, "students", "view")
    can_view_contact = not context or context.has_sensitive("college.students.contact.view")
    can_view_financial = not context or (
        context.level("clearance") != "none"
        and context.has_sensitive("college.fees.view")
    )
    financial_profile_ids: set[str] | None = None
    financial_client_ids: set[str] | None = None
    if context and can_view_financial:
        clearance_scope = context.scope("clearance")
        if not clearance_scope.unrestricted:
            financial_profile_ids = set(clearance_scope.full_student_ids)
            financial_client_ids = set(db.execute(select(CollegeStudentProfile.client_id).where(
                CollegeStudentProfile.organization_id == user.organization_id,
                CollegeStudentProfile.id.in_(financial_profile_ids) if financial_profile_ids else false(),
            )).scalars())
    can_view_photos = "clients.media.view" in permissions and (
        not context or context.has_sensitive("college.protected_fields.view")
    )
    sales, memberships, appointments, signals, photos = _aggregates(
        user,
        now,
        include_financial=can_view_financial,
        include_operations=not is_college,
        financial_client_ids=financial_client_ids,
    )

    statement = select(
        Client,
        Location.name.label("location_name"),
        sales.c.lifetime_value_paise,
        sales.c.outstanding_paise,
        sales.c.invoice_count,
        memberships.c.membership_ends_on,
        appointments.c.next_appointment_at,
        signals.c.open_signal_count,
        photos.c.photo_updated_at,
        CollegeStudentProfile.admission_number,
        CollegeStudentProfile.roll_number,
        CollegeStudentProfile.current_semester,
        CollegeStudentProfile.status.label("student_status"),
        CollegeStudentProfile.id.label("student_profile_id"),
        CollegeProgram.name.label("program_name"),
        CollegeCohort.name.label("cohort_name"),
    ).outerjoin(Location, Location.id == Client.home_location_id)
    statement = statement.outerjoin(CollegeStudentProfile, CollegeStudentProfile.client_id == Client.id)
    statement = statement.outerjoin(CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id)
    statement = statement.outerjoin(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id)
    statement = statement.outerjoin(sales, sales.c.client_id == Client.id)
    statement = statement.outerjoin(memberships, memberships.c.client_id == Client.id)
    statement = statement.outerjoin(appointments, appointments.c.client_id == Client.id)
    statement = statement.outerjoin(signals, signals.c.client_id == Client.id)
    statement = statement.outerjoin(photos, photos.c.client_id == Client.id)
    statement = filter_clients(statement.where(Client.organization_id == user.organization_id), db, user)
    if is_college:
        statement = statement.where(
            CollegeStudentProfile.id.is_not(None),
            CollegeStudentProfile.organization_id == user.organization_id,
        )

    if location_id:
        statement = statement.where(Client.home_location_id == location_id)
    if query:
        normalized = " ".join(query.casefold().split())
        compact = "".join(character for character in normalized if character.isalnum())
        searchable_fields = [
            Client.first_name, Client.last_name, Client.client_number,
            CollegeStudentProfile.admission_number, CollegeStudentProfile.roll_number,
        ]
        if can_view_contact:
            searchable_fields.extend([Client.phone, Client.email])
        searchable = func.lower(func.concat_ws(" ", *searchable_fields))
        compact_name = func.regexp_replace(func.lower(func.concat(Client.first_name, Client.last_name)), r"[^[:alnum:]]+", "", "g")
        terms = [term for term in normalized.split(" ") if term]
        clauses = [searchable.contains(normalized)]
        if compact:
            clauses.append(compact_name.contains(compact))
        if terms:
            clauses.append(and_(*(searchable.contains(term) for term in terms)))
        statement = statement.where(or_(*clauses))

    relationship_status = CollegeStudentProfile.status if is_college else Client.status
    joined_at = CollegeStudentProfile.admitted_on if is_college else Client.created_at
    if segment == "active":
        statement = statement.where(relationship_status == "active")
    elif segment == "inactive":
        statement = statement.where(relationship_status != "active")
    elif segment == "new":
        recent_cutoff = now - timedelta(days=30)
        statement = statement.where(joined_at >= (recent_cutoff.date() if is_college else recent_cutoff))
    elif segment == "attention":
        statement = statement.where(func.coalesce(signals.c.open_signal_count, 0) > 0)
    elif segment == "member":
        statement = statement.where(memberships.c.membership_ends_on.is_not(None))
    elif segment == "product_only":
        statement = statement.where(memberships.c.membership_ends_on.is_(None), func.coalesce(sales.c.invoice_count, 0) > 0)
    elif segment == "balance":
        statement = statement.where(func.coalesce(sales.c.outstanding_paise, 0) > 0)

    cursor_filters = {"location_id": location_id, "q": query, "segment": segment}
    cursor_values = decode_cursor_or_legacy_id(
        cursor, scope="clients.directory", organization_id=user.organization_id,
        filters=cursor_filters,
    ) if cursor else None
    if cursor_values:
        if cursor_values.get("legacy"):
            pivot = db.get(Client, cursor_values["id"])
            if not pivot or pivot.organization_id != user.organization_id:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid Client cursor")
            pivot_at, pivot_id = pivot.created_at, pivot.id
        else:
            pivot_at = datetime.fromisoformat(str(cursor_values.get("at")))
            pivot_id = str(cursor_values.get("id") or "")
        statement = statement.where(or_(
                Client.created_at < pivot_at,
                and_(Client.created_at == pivot_at, Client.id < pivot_id),
            ))
    page_size = min(max(limit, 1), 100)
    rows = db.execute(statement.order_by(Client.created_at.desc(), Client.id.desc()).limit(page_size + 1)).all()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    items = []
    for row in rows:
        client = row[0]
        photo_updated_at = row.photo_updated_at
        row_can_view_financial = can_view_financial and (
            financial_profile_ids is None or row.student_profile_id in financial_profile_ids
        )
        items.append({
            "id": client.id,
            "client_number": client.client_number,
            "first_name": client.first_name,
            "last_name": client.last_name,
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "phone": client.phone if can_view_contact else None,
            "email": client.email if can_view_contact else None,
            "status": client.status,
            "tags": client.tags,
            "joined_on": client.joined_on,
            "last_visit_at": client.last_visit_at,
            "home_location_id": client.home_location_id,
            "location_name": row.location_name,
            "lifetime_value_paise": int(row.lifetime_value_paise or 0) if row_can_view_financial else None,
            "outstanding_paise": int(row.outstanding_paise or 0) if row_can_view_financial else None,
            "invoice_count": int(row.invoice_count or 0) if row_can_view_financial else None,
            "membership_ends_on": row.membership_ends_on,
            "next_appointment_at": row.next_appointment_at,
            "open_signal_count": int(row.open_signal_count or 0),
            "admission_number": row.admission_number,
            "roll_number": row.roll_number,
            "current_semester": row.current_semester,
            "student_status": row.student_status,
            "program_name": row.program_name,
            "cohort_name": row.cohort_name,
            "avatar_url": f"/clients/{client.id}/photo?v={int(photo_updated_at.timestamp())}" if can_view_photos and photo_updated_at else None,
            "version": client.version,
        })
    return {
        "items": items,
        "next_cursor": encode_cursor(
            scope="clients.directory", organization_id=user.organization_id,
            filters=cursor_filters,
            values={"at": rows[-1][0].created_at.isoformat(), "id": rows[-1][0].id},
        ) if has_more and rows else None,
        "has_more": has_more,
        "summary": _summary(
            db, user, location_id, now,
            can_view_financial=can_view_financial,
            financial_client_ids=financial_client_ids,
        ),
        "segment": segment,
        "industry": org.industry.value if org else None,
        "capabilities": {
            "create": (context.level("students") == "manage") if context else (("college.students.manage" in permissions) if is_college else ("clients.manage" in permissions)),
            "edit": (context.level("students") in {"work", "manage"}) if context else (("college.students.manage" in permissions) if is_college else ("clients.manage" in permissions)),
            "view_media": can_view_photos,
            "export": context.has_sensitive("college.data.export") if context else "reports.exports" in permissions,
        },
        "source_timestamp": now,
    }
