"""Scoped, presentation-ready Gym operation reads."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    ClassBooking,
    Client,
    DietPlan,
    Employee,
    Equipment,
    FitnessMeasurement,
    GymCheckIn,
    GymClass,
    Location,
    Membership,
    MembershipPlan,
    SaleInvoice,
    SaleLine,
    TrainerAssignment,
    User,
    WorkoutPlan,
)
from app.services.business_access import (
    allowed_client_ids,
    ensure_client_access,
    ensure_location,
    filter_locations,
    organization_for,
)
from app.services.audit import log_action
from app.services.rbac import get_user_permissions


def serialize(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def local_today(db: Session, user: User):
    organization = organization_for(db, user)
    try:
        zone = ZoneInfo(organization.timezone or "Asia/Kolkata")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Kolkata")
    now = datetime.now(timezone.utc).astimezone(zone)
    start = datetime.combine(now.date(), time.min, tzinfo=zone).astimezone(timezone.utc)
    return now.date(), start, start + timedelta(days=1)


def _membership_statement(db: Session, user: User, location_id: str | None = None):
    statement = select(Membership).where(Membership.organization_id == user.organization_id)
    statement = filter_locations(statement, Membership, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(Membership.location_id == location_id)
    clients = allowed_client_ids(db, user)
    if clients is not None:
        statement = statement.where(Membership.client_id.in_(clients))
    return statement


def _membership_transition(
    db: Session,
    row: Membership,
    status_value: str,
    *,
    user_id: str | None,
    reason: str,
) -> bool:
    if row.status == status_value:
        return False
    previous = row.status
    row.status = status_value
    row.version += 1
    log_action(
        db,
        organization_id=row.organization_id,
        user_id=user_id,
        action="membership.lifecycle_transition",
        resource_type="membership",
        resource_id=row.id,
        permission="gym.memberships.manage" if user_id else None,
        changes={"from_status": previous, "to_status": status_value, "reason": reason},
    )
    return True


def reconcile_membership_rows(
    db: Session,
    rows: list[Membership],
    today: date,
    *,
    user_id: str | None = None,
) -> bool:
    """Apply date-driven membership transitions without committing the caller's transaction."""
    changed = False
    by_client: dict[str, list[Membership]] = defaultdict(list)
    by_id = {row.id: row for row in rows}
    for row in rows:
        by_client[row.client_id].append(row)

    # Normalize the previous renewal implementation, which promoted a future
    # term too early and could retire a still-valid current term.
    for client_rows in by_client.values():
        existing_scheduled = next((row for row in client_rows if row.status == "scheduled"), None)
        future_current = next((
            row for row in client_rows
            if row.status in {"active", "frozen"} and row.starts_on > today
        ), None)
        if future_current:
            if existing_scheduled:
                changed |= _membership_transition(
                    db, future_current, "cancelled", user_id=user_id, reason="duplicate legacy future term"
                )
            else:
                future_current.frozen_from = None
                future_current.frozen_until = None
                changed |= _membership_transition(
                    db, future_current, "scheduled", user_id=user_id, reason="future term normalized"
                )
                existing_scheduled = future_current
        has_current = any(
            row.status in {"active", "frozen"} and row.starts_on <= today <= row.ends_on
            for row in client_rows
        )
        legacy_current = next((
            row for row in client_rows
            if row.status == "renewed" and row.starts_on <= today <= row.ends_on
        ), None)
        if not has_current and existing_scheduled and legacy_current:
            changed |= _membership_transition(
                db, legacy_current, "active", user_id=user_id, reason="legacy early renewal repaired"
            )
    if changed:
        db.flush()

    # Resolve current terms first so activating a scheduled term cannot violate
    # the one-current-term database constraint.
    for client_rows in by_client.values():
        scheduled = [row for row in client_rows if row.status == "scheduled"]
        for row in client_rows:
            if row.status not in {"active", "frozen"}:
                continue
            if row.cancellation_effective_on and today >= row.cancellation_effective_on:
                changed |= _membership_transition(
                    db, row, "cancelled", user_id=user_id, reason="scheduled cancellation became effective"
                )
                continue
            if row.status == "frozen" and row.frozen_until and today > row.frozen_until:
                extension = max((row.frozen_until - (row.frozen_from or row.frozen_until)).days, 0)
                if extension:
                    row.ends_on += timedelta(days=extension)
                    for next_term in scheduled:
                        if next_term.starts_on <= row.ends_on:
                            term_length = next_term.ends_on - next_term.starts_on
                            next_term.starts_on = row.ends_on + timedelta(days=1)
                            next_term.ends_on = next_term.starts_on + term_length
                            next_term.version += 1
                row.frozen_from = None
                row.frozen_until = None
                changed |= _membership_transition(
                    db, row, "active", user_id=user_id, reason="freeze period ended"
                )
            if row.status == "active" and row.ends_on < today:
                next_exists = any(next_term.starts_on <= today for next_term in scheduled)
                changed |= _membership_transition(
                    db,
                    row,
                    "renewed" if next_exists else "expired",
                    user_id=user_id,
                    reason="membership term ended",
                )
    if changed:
        db.flush()

    for client_rows in by_client.values():
        current = next((row for row in client_rows if row.status in {"active", "frozen"}), None)
        scheduled = sorted(
            (row for row in client_rows if row.status == "scheduled"),
            key=lambda row: (row.starts_on, row.created_at, row.id),
        )
        for row in scheduled:
            if current and row.starts_on <= current.ends_on:
                term_length = row.ends_on - row.starts_on
                row.starts_on = current.ends_on + timedelta(days=1)
                row.ends_on = row.starts_on + term_length
                row.version += 1
                changed = True
                continue
            if row.starts_on > today or current:
                continue
            previous = by_id.get(row.previous_membership_id)
            if previous and previous.status in {"active", "frozen"}:
                changed |= _membership_transition(
                    db, previous, "renewed", user_id=user_id, reason="scheduled renewal activated"
                )
                db.flush()
            changed |= _membership_transition(
                db, row, "active", user_id=user_id, reason="scheduled term start reached"
            )
            current = row
            break
    if changed:
        db.flush()
    return changed


def reconcile_memberships(
    db: Session,
    user: User,
    *,
    client_id: str | None = None,
    lock: bool = False,
) -> bool:
    today = local_today(db, user)[0]
    statement = _membership_statement(db, user).where(
        or_(
            Membership.status.in_(["active", "frozen", "scheduled"]),
            and_(
                Membership.status == "renewed",
                Membership.starts_on <= today,
                Membership.ends_on >= today,
            ),
        )
    )
    if client_id:
        statement = statement.where(Membership.client_id == client_id)
    if lock:
        statement = statement.with_for_update()
    rows = db.execute(statement.order_by(Membership.client_id, Membership.starts_on, Membership.id)).scalars().all()
    return reconcile_membership_rows(db, rows, today, user_id=user.id)


def membership_for_user(db: Session, user: User, membership_id: str, *, lock: bool = False) -> Membership:
    statement = _membership_statement(db, user).where(Membership.id == membership_id)
    if lock:
        statement = statement.with_for_update()
    membership = db.execute(statement).scalar_one_or_none()
    if not membership:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")
    client = db.get(Client, membership.client_id)
    if client:
        ensure_client_access(db, user, client)
    reconcile_memberships(db, user, client_id=membership.client_id, lock=lock)
    db.refresh(membership)
    return membership


def gym_summary(db: Session, user: User, location_id: str | None) -> dict:
    if reconcile_memberships(db, user):
        db.commit()
    today, start, end = local_today(db, user)
    memberships = _membership_statement(db, user, location_id).subquery()

    checkins = select(GymCheckIn).where(
        GymCheckIn.organization_id == user.organization_id,
        GymCheckIn.checked_in_at >= start,
        GymCheckIn.checked_in_at < end,
    )
    checkins = filter_locations(checkins, GymCheckIn, db, user)
    classes = select(GymClass).where(
        GymClass.organization_id == user.organization_id,
        GymClass.starts_at >= start,
        GymClass.starts_at < end,
    )
    classes = filter_locations(classes, GymClass, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        checkins = checkins.where(GymCheckIn.location_id == location_id)
        classes = classes.where(GymClass.location_id == location_id)
    clients = allowed_client_ids(db, user)
    if clients is not None:
        checkins = checkins.where(GymCheckIn.client_id.in_(clients))
    checkins_subquery = checkins.subquery()
    classes_subquery = classes.subquery()
    return {
        "active_memberships": int(db.scalar(select(func.count(memberships.c.id)).where(memberships.c.status == "active")) or 0),
        "expiring_7_days": int(db.scalar(select(func.count(memberships.c.id)).where(
            memberships.c.status == "active",
            memberships.c.ends_on.between(today, today + timedelta(days=7)),
        )) or 0),
        "check_ins_today": int(db.scalar(select(func.count(checkins_subquery.c.id))) or 0),
        "inside_now": int(db.scalar(select(func.count(checkins_subquery.c.id)).where(checkins_subquery.c.checked_out_at.is_(None))) or 0),
        "classes_today": int(db.scalar(select(func.count(classes_subquery.c.id))) or 0),
        "generated_at": datetime.now(timezone.utc),
    }


def membership_directory(db: Session, user: User, location_id: str | None, status_filter: str | None) -> list[dict]:
    if reconcile_memberships(db, user):
        db.commit()
    statement = _membership_statement(db, user, location_id)
    if status_filter:
        statement = statement.where(Membership.status == status_filter)
    rows = db.execute(statement.order_by(Membership.ends_on, Membership.id).limit(500)).scalars().all()
    client_ids = {row.client_id for row in rows}
    clients = {row.id: row for row in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()} if client_ids else {}
    plans = {row.id: row for row in db.execute(select(MembershipPlan).where(MembershipPlan.id.in_({row.plan_id for row in rows}))).scalars()} if rows else {}
    permissions = get_user_permissions(db, user)
    invoice_ids = {row.invoice_id for row in rows if row.invoice_id}
    invoices = {row.id: row for row in db.execute(select(SaleInvoice).where(SaleInvoice.id.in_(invoice_ids))).scalars()} if invoice_ids and "sales.view" in permissions else {}
    lines = db.execute(select(SaleLine).where(SaleLine.invoice_id.in_(invoice_ids)).order_by(SaleLine.invoice_id, SaleLine.display_order, SaleLine.id)).scalars().all() if invoices else []
    invoice_items: dict[str, list[str]] = defaultdict(list)
    for line in lines:
        invoice_items[line.invoice_id].append(line.item_name)
    locations = {row.id: row for row in db.execute(select(Location).where(Location.id.in_({row.location_id for row in rows}))).scalars()} if rows else {}
    assignments = db.execute(select(TrainerAssignment).where(
        TrainerAssignment.organization_id == user.organization_id,
        TrainerAssignment.client_id.in_(client_ids),
        TrainerAssignment.status == "active",
    ).order_by(TrainerAssignment.created_at.desc())).scalars().all() if client_ids else []
    assignment_map = {}
    for assignment in assignments:
        assignment_map.setdefault(assignment.client_id, assignment)
    employee_ids = {row.trainer_employee_id for row in assignment_map.values()}
    employees = {row.id: row for row in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars()} if employee_ids else {}
    open_clients = set(db.execute(select(GymCheckIn.client_id).where(
        GymCheckIn.organization_id == user.organization_id,
        GymCheckIn.client_id.in_(client_ids),
        GymCheckIn.checked_out_at.is_(None),
    )).scalars()) if client_ids else set()
    return [{
        **serialize(row),
        "client": ({
            "id": client.id,
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "client_number": client.client_number,
            "phone": client.phone,
        } if (client := clients.get(row.client_id)) else None),
        "plan": ({
            "id": plan.id,
            "name": plan.name,
            "duration_days": plan.duration_days,
            "price_paise": plan.price_paise,
        } if (plan := plans.get(row.plan_id)) else None),
        "invoice_linked": bool(row.invoice_id),
        "invoice": ({
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "status": invoice.status,
            "total_paise": invoice.total_paise,
            "paid_paise": invoice.paid_paise,
            "balance_paise": max(invoice.total_paise - invoice.paid_paise, 0),
            "item_names": invoice_items.get(invoice.id, []),
        } if (invoice := invoices.get(row.invoice_id)) else None),
        "location_name": locations[row.location_id].name if row.location_id in locations else None,
        "trainer": ({
            "id": trainer.id,
            "display_name": f"{trainer.first_name} {trainer.last_name}".strip(),
        } if (assignment := assignment_map.get(row.client_id)) and (trainer := employees.get(assignment.trainer_employee_id)) else None),
        "inside_now": row.client_id in open_clients,
    } for row in rows]


def checkin_directory(db: Session, user: User, location_id: str | None) -> list[dict]:
    statement = select(GymCheckIn).where(GymCheckIn.organization_id == user.organization_id)
    statement = filter_locations(statement, GymCheckIn, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(GymCheckIn.location_id == location_id)
    clients_scope = allowed_client_ids(db, user)
    if clients_scope is not None:
        statement = statement.where(GymCheckIn.client_id.in_(clients_scope))
    rows = db.execute(statement.order_by(GymCheckIn.checked_in_at.desc(), GymCheckIn.id.desc()).limit(300)).scalars().all()
    clients = {row.id: row for row in db.execute(select(Client).where(Client.id.in_({row.client_id for row in rows}))).scalars()} if rows else {}
    locations = {row.id: row for row in db.execute(select(Location).where(Location.id.in_({row.location_id for row in rows}))).scalars()} if rows else {}
    return [{
        **serialize(row),
        "client": ({
            "id": client.id,
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "client_number": client.client_number,
        } if (client := clients.get(row.client_id)) else None),
        "location_name": locations[row.location_id].name if row.location_id in locations else None,
        "duration_minutes": int(((row.checked_out_at or datetime.now(timezone.utc)) - row.checked_in_at).total_seconds() // 60),
    } for row in rows]


def class_directory(db: Session, user: User, location_id: str | None) -> list[dict]:
    statement = select(GymClass).where(GymClass.organization_id == user.organization_id)
    statement = filter_locations(statement, GymClass, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(GymClass.location_id == location_id)
    rows = db.execute(statement.order_by(GymClass.starts_at, GymClass.id).limit(300)).scalars().all()
    employee_ids = {row.trainer_employee_id for row in rows if row.trainer_employee_id}
    employees = {row.id: row for row in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars()} if employee_ids else {}
    locations = {row.id: row for row in db.execute(select(Location).where(Location.id.in_({row.location_id for row in rows}))).scalars()} if rows else {}
    class_ids = {row.id for row in rows}
    booking_counts = dict(db.execute(select(ClassBooking.gym_class_id, func.count(ClassBooking.id)).where(
        ClassBooking.gym_class_id.in_(class_ids),
        ClassBooking.status == "booked",
    ).group_by(ClassBooking.gym_class_id)).all()) if class_ids else {}
    return [{
        **serialize(row),
        "trainer_name": (
            f"{employees[row.trainer_employee_id].first_name} {employees[row.trainer_employee_id].last_name}".strip()
            if row.trainer_employee_id in employees else None
        ),
        "location_name": locations[row.location_id].name if row.location_id in locations else None,
        "booked": int(booking_counts.get(row.id, 0)),
        "available": max(row.capacity - int(booking_counts.get(row.id, 0)), 0),
    } for row in rows]


def coaching_directory(db: Session, user: User, section: str, client_id: str | None = None) -> list[dict]:
    permissions = get_user_permissions(db, user)
    permission = {
        "trainers": "gym.coaching.view",
        "measurements": "gym.measurements.view",
        "workouts": "gym.workouts.view",
        "diets": "gym.diets.view",
    }.get(section)
    if not permission or permission not in permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This coaching area is outside your access")
    if client_id:
        client = db.get(Client, client_id)
        if not client:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
        ensure_client_access(db, user, client)
    model = {
        "trainers": TrainerAssignment,
        "measurements": FitnessMeasurement,
        "workouts": WorkoutPlan,
        "diets": DietPlan,
    }[section]
    statement = select(model).where(model.organization_id == user.organization_id)
    clients_scope = allowed_client_ids(db, user)
    if clients_scope is not None:
        statement = statement.where(model.client_id.in_(clients_scope))
    if client_id:
        statement = statement.where(model.client_id == client_id)
    order = model.measured_on.desc() if model is FitnessMeasurement else model.created_at.desc()
    rows = db.execute(statement.order_by(order).limit(300)).scalars().all()
    client_ids = {row.client_id for row in rows}
    clients = {row.id: row for row in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()} if client_ids else {}
    employee_ids = {
        employee_id for row in rows
        if (employee_id := getattr(row, "trainer_employee_id", None))
    }
    employees = {row.id: row for row in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars()} if employee_ids else {}
    return [{
        **serialize(row),
        "client": ({
            "id": client.id,
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "client_number": client.client_number,
        } if (client := clients.get(row.client_id)) else None),
        "trainer_name": (
            f"{employees[employee_id].first_name} {employees[employee_id].last_name}".strip()
            if (employee_id := getattr(row, "trainer_employee_id", None)) in employees else None
        ),
    } for row in rows]


def equipment_directory(db: Session, user: User, location_id: str | None) -> list[dict]:
    statement = select(Equipment).where(Equipment.organization_id == user.organization_id)
    statement = filter_locations(statement, Equipment, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(Equipment.location_id == location_id)
    rows = db.execute(statement.order_by(Equipment.next_service_on.asc().nullslast(), Equipment.name).limit(300)).scalars().all()
    locations = {row.id: row for row in db.execute(select(Location).where(Location.id.in_({row.location_id for row in rows}))).scalars()} if rows else {}
    return [{**serialize(row), "location_name": locations[row.location_id].name if row.location_id in locations else None} for row in rows]
