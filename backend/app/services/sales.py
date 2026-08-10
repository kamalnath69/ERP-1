"""Permission-scoped sales reads and atomic checkout operations."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    CatalogItem,
    Client,
    Employee,
    EmployeeLocation,
    Location,
    Membership,
    Notification,
    SaleInvoice,
    SaleLine,
    SalePayment,
    StockLevel,
    StockMovement,
    User,
)
from app.services.audit import log_action
from app.services.business_access import (
    allowed_client_ids,
    ensure_client_access,
    ensure_location,
    filter_locations,
    organization_for,
)
from app.services.cursor_pagination import decode_cursor_or_legacy_id, encode_cursor
from app.services.rbac import get_user_permissions


SALE_STATUSES = {"draft", "issued", "partially_paid", "paid", "void", "refunded"}
PAYMENT_METHODS = {"cash", "upi", "card", "bank"}


def _serialize(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _scoped_statement(db: Session, user: User):
    statement = select(SaleInvoice).where(SaleInvoice.organization_id == user.organization_id)
    statement = filter_locations(statement, SaleInvoice, db, user)
    client_ids = allowed_client_ids(db, user)
    if client_ids is not None:
        client_clause = SaleInvoice.client_id.in_(client_ids) if client_ids else False
        # Walk-in invoices contain no Client identity and remain location-scoped.
        statement = statement.where(or_(client_clause, SaleInvoice.client_id.is_(None)))
    return statement


def _filtered_statement(
    db: Session,
    user: User,
    *,
    location_id: str | None,
    query: str | None,
    status_filter: str | None,
    starts_at: datetime | None,
    ends_at: datetime | None,
):
    statement = _scoped_statement(db, user)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(SaleInvoice.location_id == location_id)
    if status_filter:
        if status_filter not in SALE_STATUSES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown invoice status")
        statement = statement.where(SaleInvoice.status == status_filter)
    if starts_at:
        statement = statement.where(SaleInvoice.created_at >= starts_at)
    if ends_at:
        statement = statement.where(SaleInvoice.created_at < ends_at)
    if query:
        normalized = " ".join(query.casefold().split())
        compact = "".join(character for character in normalized if character.isalnum())
        client_name = func.lower(func.concat_ws(" ", Client.first_name, Client.last_name, Client.phone, Client.email))
        compact_client = func.regexp_replace(client_name, r"[^[:alnum:]]+", "", "g")
        line_match = exists(select(SaleLine.id).where(
            SaleLine.invoice_id == SaleInvoice.id,
            or_(
                func.lower(SaleLine.item_name).contains(normalized),
                func.lower(func.coalesce(SaleLine.sku, "")).contains(normalized),
            ),
        ))
        statement = statement.outerjoin(Client, Client.id == SaleInvoice.client_id).where(or_(
            func.lower(SaleInvoice.invoice_number).contains(normalized),
            client_name.contains(normalized),
            compact_client.contains(compact) if compact else False,
            line_match,
        ))
    return statement


def _invoice_access(db: Session, user: User, invoice_id: str, *, lock: bool = False) -> SaleInvoice:
    statement = _scoped_statement(db, user).where(SaleInvoice.id == invoice_id)
    if lock:
        statement = statement.with_for_update()
    invoice = db.execute(statement).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if invoice.client_id:
        client = db.get(Client, invoice.client_id)
        if client:
            ensure_client_access(db, user, client)
    return invoice


def _invoice_references(db: Session, invoices: list[SaleInvoice]):
    client_ids = {row.client_id for row in invoices if row.client_id}
    employee_ids = {row.employee_id for row in invoices if row.employee_id}
    location_ids = {row.location_id for row in invoices}
    clients = {row.id: row for row in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()} if client_ids else {}
    employees = {row.id: row for row in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars()} if employee_ids else {}
    locations = {row.id: row for row in db.execute(select(Location).where(Location.id.in_(location_ids))).scalars()} if location_ids else {}
    invoice_ids = [row.id for row in invoices]
    lines = db.execute(select(SaleLine).where(SaleLine.invoice_id.in_(invoice_ids)).order_by(SaleLine.invoice_id, SaleLine.display_order, SaleLine.id)).scalars().all() if invoice_ids else []
    grouped_lines: dict[str, list[SaleLine]] = defaultdict(list)
    for line in lines:
        grouped_lines[line.invoice_id].append(line)
    return clients, employees, locations, grouped_lines


def _invoice_summary(row: SaleInvoice, clients, employees, locations, grouped_lines) -> dict:
    client = clients.get(row.client_id)
    employee = employees.get(row.employee_id)
    location = locations.get(row.location_id)
    lines = grouped_lines.get(row.id, [])
    return {
        **_serialize(row),
        "balance_paise": max(row.total_paise - row.paid_paise, 0),
        "voidable": row.paid_paise == 0 and row.status in {"draft", "issued"},
        "client": ({
            "id": client.id,
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "client_number": client.client_number,
        } if client else None),
        "employee": ({
            "id": employee.id,
            "display_name": f"{employee.first_name} {employee.last_name}".strip(),
        } if employee else None),
        "location": ({"id": location.id, "name": location.name} if location else None),
        "line_count": len(lines),
        "items_preview": [line.item_name for line in lines[:3]],
    }


def sales_workspace(
    db: Session,
    user: User,
    *,
    location_id: str | None = None,
    query: str | None = None,
    status_filter: str | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    statement = _filtered_statement(
        db,
        user,
        location_id=location_id,
        query=query,
        status_filter=status_filter,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    filtered = statement.subquery()
    count, billed, collected, outstanding = db.execute(select(
        func.count(filtered.c.id),
        func.coalesce(func.sum(case((filtered.c.status.notin_(["void", "refunded"]), filtered.c.total_paise), else_=0)), 0),
        func.coalesce(func.sum(case((filtered.c.status.notin_(["void", "refunded"]), filtered.c.paid_paise), else_=0)), 0),
        func.coalesce(func.sum(case((filtered.c.status.notin_(["void", "refunded"]), func.greatest(filtered.c.total_paise - filtered.c.paid_paise, 0)), else_=0)), 0),
    )).one()
    cursor_filters = {
        "location_id": location_id, "q": query, "status": status_filter,
        "starts_at": starts_at.isoformat() if starts_at else None,
        "ends_at": ends_at.isoformat() if ends_at else None,
    }
    cursor_values = decode_cursor_or_legacy_id(
        cursor, scope="sales.workspace", organization_id=user.organization_id,
        filters=cursor_filters,
    ) if cursor else None
    if cursor_values:
        if cursor_values.get("legacy"):
            pivot = db.get(SaleInvoice, cursor_values["id"])
            if not pivot or pivot.organization_id != user.organization_id:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid invoice cursor")
            pivot_at, pivot_id = pivot.created_at, pivot.id
        else:
            pivot_at = datetime.fromisoformat(str(cursor_values.get("at")))
            pivot_id = str(cursor_values.get("id") or "")
        statement = statement.where(or_(
            SaleInvoice.created_at < pivot_at,
            and_(SaleInvoice.created_at == pivot_at, SaleInvoice.id < pivot_id),
        ))
    page_size = min(max(limit, 1), 100)
    invoices = db.execute(statement.order_by(SaleInvoice.created_at.desc(), SaleInvoice.id.desc()).limit(page_size + 1)).scalars().unique().all()
    has_more = len(invoices) > page_size
    invoices = invoices[:page_size]
    references = _invoice_references(db, invoices)
    permissions = get_user_permissions(db, user)
    return {
        "summary": {
            "invoice_count": int(count or 0),
            "billed_paise": int(billed or 0),
            "collected_paise": int(collected or 0),
            "outstanding_paise": int(outstanding or 0),
        },
        "items": [_invoice_summary(row, *references) for row in invoices],
        "next_cursor": encode_cursor(
            scope="sales.workspace", organization_id=user.organization_id,
            filters=cursor_filters,
            values={"at": invoices[-1].created_at.isoformat(), "id": invoices[-1].id},
        ) if has_more and invoices else None,
        "has_more": has_more,
        "capabilities": {
            "create": "sales.manage" in permissions,
            "record_payment": "payments.record" in permissions,
            "void_invoice": "sales.manage" in permissions,
            "view_financials": "sales.view" in permissions,
        },
        "source_timestamp": datetime.now(timezone.utc),
    }


def invoice_detail(db: Session, user: User, invoice_id: str) -> dict:
    invoice = _invoice_access(db, user, invoice_id)
    references = _invoice_references(db, [invoice])
    data = _invoice_summary(invoice, *references)
    data["lines"] = [_serialize(row) for row in references[3].get(invoice.id, [])]
    data["payments"] = [
        _serialize(row)
        for row in db.execute(select(SalePayment).where(
            SalePayment.organization_id == user.organization_id,
            SalePayment.invoice_id == invoice.id,
        ).order_by(SalePayment.created_at.desc())).scalars()
    ]
    return data


def _allocate_invoice_discount(amounts: list[int], discount_paise: int) -> list[int]:
    if discount_paise < 0 or discount_paise > sum(amounts):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Discount exceeds the eligible sale amount")
    if not discount_paise:
        return [0 for _ in amounts]
    total = sum(amounts)
    if total == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A discount cannot be applied to a zero-value sale")
    allocations = [discount_paise * amount // total for amount in amounts]
    remainder = discount_paise - sum(allocations)
    for index in sorted(range(len(amounts)), key=lambda value: (-amounts[value], value)):
        if not remainder:
            break
        room = amounts[index] - allocations[index]
        added = min(room, remainder)
        allocations[index] += added
        remainder -= added
    return allocations


def _line_amount(item: CatalogItem, quantity_milli: int, discount_paise: int) -> tuple[int, int, int]:
    gross = item.price_paise * quantity_milli // 1000
    if discount_paise > gross:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Discount exceeds the price of {item.name}")
    net = gross - discount_paise
    if item.tax_inclusive and item.tax_rate_bps:
        tax = net * item.tax_rate_bps // (10000 + item.tax_rate_bps)
        subtotal = net - tax
        return subtotal, tax, net
    subtotal = net
    tax = subtotal * item.tax_rate_bps // 10000
    return subtotal, tax, subtotal + tax


def _taxed_amount(amount_paise: int, rate_bps: int, inclusive: bool) -> tuple[int, int, int]:
    if inclusive and rate_bps:
        tax = amount_paise * rate_bps // (10000 + rate_bps)
        return amount_paise - tax, tax, amount_paise
    tax = amount_paise * rate_bps // 10000
    return amount_paise, tax, amount_paise + tax


def membership_invoice_quote(
    db: Session,
    user: User,
    plan,
    *,
    include_joining_fee: bool,
    interstate: bool = False,
) -> dict:
    """Build the tax snapshot used by both checkout display and invoice creation."""
    organization = organization_for(db, user)
    tax_settings = organization.tax_settings or {}
    rate_bps = max(int(tax_settings.get("default_tax_rate_bps") or 0), 0)
    inclusive = bool(tax_settings.get("prices_include_tax", False))
    inputs = [("membership", f"{plan.name} membership", int(plan.price_paise))]
    if include_joining_fee and plan.joining_fee_paise:
        inputs.append(("joining_fee", "Joining fee", int(plan.joining_fee_paise)))

    lines = []
    for code, name, amount in inputs:
        subtotal, tax, total = _taxed_amount(amount, rate_bps, inclusive)
        lines.append({
            "code": code,
            "item_name": name,
            "charge_paise": amount,
            "subtotal_paise": subtotal,
            "tax_paise": tax,
            "total_paise": total,
            "tax_rate_bps": rate_bps,
        })
    subtotal = sum(line["subtotal_paise"] for line in lines)
    tax = sum(line["tax_paise"] for line in lines)
    total = sum(line["total_paise"] for line in lines)
    cgst = 0 if interstate else tax // 2
    sgst = 0 if interstate else tax - cgst
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "base_fee_paise": int(plan.price_paise),
        "joining_fee_paise": int(plan.joining_fee_paise) if include_joining_fee else 0,
        "subtotal_paise": subtotal,
        "tax_paise": tax,
        "cgst_paise": cgst,
        "sgst_paise": sgst,
        "igst_paise": tax if interstate else 0,
        "total_paise": total,
        "tax_rate_bps": rate_bps,
        "prices_include_tax": inclusive,
        "interstate": interstate,
        "lines": lines,
    }


def create_membership_invoice(
    db: Session,
    user: User,
    *,
    location_id: str,
    client_id: str,
    plan,
    include_joining_fee: bool,
    interstate: bool,
    idempotency_key: str,
    notes: str,
) -> tuple[SaleInvoice, dict, bool]:
    """Create an issued membership invoice without committing the outer transaction."""
    existing = db.execute(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
    if existing:
        return existing, existing.tax_snapshot or {}, False

    ensure_location(db, user, location_id)
    organization = organization_for(db, user)
    local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(organization.timezone))
    location = db.execute(select(Location).where(
        Location.id == location_id,
        Location.organization_id == user.organization_id,
    ).with_for_update()).scalar_one()
    location.invoice_sequence += 1
    quote = membership_invoice_quote(
        db,
        user,
        plan,
        include_joining_fee=include_joining_fee,
        interstate=interstate,
    )
    invoice = SaleInvoice(
        organization_id=user.organization_id,
        location_id=location_id,
        client_id=client_id,
        invoice_number=f"{organization.invoice_prefix}-{location.code}-{local_now.year}-{location.invoice_sequence:06d}",
        status="paid" if quote["total_paise"] == 0 else "issued",
        subtotal_paise=quote["subtotal_paise"],
        cgst_paise=quote["cgst_paise"],
        sgst_paise=quote["sgst_paise"],
        igst_paise=quote["igst_paise"],
        total_paise=quote["total_paise"],
        tax_snapshot={
            "rate_bps": quote["tax_rate_bps"],
            "prices_include_tax": quote["prices_include_tax"],
            "interstate": quote["interstate"],
            "subtotal_paise": quote["subtotal_paise"],
            "tax_paise": quote["tax_paise"],
            "total_paise": quote["total_paise"],
        },
        notes=notes,
        idempotency_key=idempotency_key,
        issued_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.flush()
    for index, line in enumerate(quote["lines"]):
        db.add(SaleLine(
            organization_id=user.organization_id,
            invoice_id=invoice.id,
            display_order=index,
            item_name=line["item_name"],
            sku="MEMBERSHIP" if line["code"] == "membership" else "JOINING-FEE",
            quantity_milli=1000,
            unit_price_paise=line["charge_paise"],
            tax_rate_bps=line["tax_rate_bps"],
            tax_paise=line["tax_paise"],
            total_paise=line["total_paise"],
        ))
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="sale.create",
        resource_type="sale_invoice",
        resource_id=invoice.id,
        permission="gym.memberships.manage",
        changes={"source": "membership", "total_paise": invoice.total_paise, "line_count": len(quote["lines"])},
    )
    return invoice, quote, True


def _deduct_stock(
    db: Session,
    user: User,
    invoice: SaleInvoice,
    items: dict[str, CatalogItem],
    quantities: dict[str, int],
    local_date: date,
) -> None:
    for item_id in sorted(quantities):
        item = items[item_id]
        needed = quantities[item_id]
        if not item.track_stock:
            continue
        levels = db.execute(select(StockLevel).where(
            StockLevel.organization_id == user.organization_id,
            StockLevel.location_id == invoice.location_id,
            StockLevel.item_id == item.id,
            StockLevel.quantity_milli > 0,
            or_(StockLevel.expires_on.is_(None), StockLevel.expires_on >= local_date),
        ).order_by(StockLevel.expires_on.asc().nullslast(), StockLevel.created_at, StockLevel.id).with_for_update()).scalars().all()
        if sum(level.quantity_milli for level in levels) < needed:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Insufficient available stock for {item.name}")
        remaining = needed
        for level in levels:
            if not remaining:
                break
            deduction = min(level.quantity_milli, remaining)
            level.quantity_milli -= deduction
            level.version += 1
            remaining -= deduction
            db.add(StockMovement(
                organization_id=user.organization_id,
                location_id=invoice.location_id,
                item_id=item.id,
                stock_level_id=level.id,
                movement_type="sale",
                quantity_delta_milli=-deduction,
                reason=f"Invoice {invoice.invoice_number}",
                reference_type="sale_invoice",
                reference_id=invoice.id,
                performed_by_user_id=user.id,
            ))


def create_sale(db: Session, user: User, body) -> dict:
    ensure_location(db, user, body.location_id)
    existing = db.execute(select(SaleInvoice).where(
        SaleInvoice.organization_id == user.organization_id,
        SaleInvoice.idempotency_key == body.idempotency_key,
    )).scalar_one_or_none()
    if existing:
        return invoice_detail(db, user, existing.id)
    if body.client_id:
        client = db.get(Client, body.client_id)
        if not client:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
        ensure_client_access(db, user, client)
    if body.employee_id:
        employee = db.execute(select(Employee).where(
            Employee.id == body.employee_id,
            Employee.organization_id == user.organization_id,
            Employee.status == "active",
        )).scalar_one_or_none()
        if not employee:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
        assigned = db.scalar(select(func.count(EmployeeLocation.id)).where(
            EmployeeLocation.employee_id == employee.id,
            EmployeeLocation.location_id == body.location_id,
        ))
        if not assigned:
            raise HTTPException(status.HTTP_409_CONFLICT, "Employee is not assigned to this location")

    item_ids = {line.item_id for line in body.lines}
    items = {item.id: item for item in db.execute(select(CatalogItem).where(
        CatalogItem.organization_id == user.organization_id,
        CatalogItem.id.in_(item_ids),
        CatalogItem.is_active.is_(True),
    )).scalars()}
    if len(items) != len(item_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more sale items are unavailable")

    gross_after_line_discount = []
    for line in body.lines:
        item = items[line.item_id]
        gross = item.price_paise * line.quantity_milli // 1000
        if line.discount_paise > gross:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Discount exceeds the price of {item.name}")
        gross_after_line_discount.append(gross - line.discount_paise)
    allocations = _allocate_invoice_discount(gross_after_line_discount, body.discount_paise)

    organization = organization_for(db, user)
    local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(organization.timezone))
    location = db.execute(select(Location).where(
        Location.id == body.location_id,
        Location.organization_id == user.organization_id,
    ).with_for_update()).scalar_one()
    location.invoice_sequence += 1
    invoice_number = f"{organization.invoice_prefix}-{location.code}-{local_now.year}-{location.invoice_sequence:06d}"
    invoice = SaleInvoice(
        organization_id=user.organization_id,
        location_id=body.location_id,
        client_id=body.client_id,
        employee_id=body.employee_id,
        invoice_number=invoice_number,
        status="issued" if body.issue else "draft",
        discount_paise=body.discount_paise,
        notes=body.notes,
        idempotency_key=body.idempotency_key,
        issued_at=datetime.now(timezone.utc) if body.issue else None,
    )
    db.add(invoice)
    db.flush()

    subtotal = tax_total = total = 0
    quantities: dict[str, int] = defaultdict(int)
    for index, input_line in enumerate(body.lines):
        item = items[input_line.item_id]
        effective_discount = input_line.discount_paise + allocations[index]
        line_subtotal, tax, line_total = _line_amount(item, input_line.quantity_milli, effective_discount)
        subtotal += line_subtotal
        tax_total += tax
        total += line_total
        quantities[item.id] += input_line.quantity_milli
        db.add(SaleLine(
            organization_id=user.organization_id,
            invoice_id=invoice.id,
            display_order=index,
            item_id=item.id,
            item_name=item.name,
            sku=item.sku,
            hsn_sac=item.hsn_sac,
            quantity_milli=input_line.quantity_milli,
            unit_price_paise=item.price_paise,
            discount_paise=effective_discount,
            tax_rate_bps=item.tax_rate_bps,
            tax_paise=tax,
            total_paise=line_total,
        ))
    invoice.subtotal_paise = subtotal
    invoice.total_paise = total
    if body.interstate:
        invoice.igst_paise = tax_total
    else:
        invoice.cgst_paise = tax_total // 2
        invoice.sgst_paise = tax_total - invoice.cgst_paise
    invoice.tax_snapshot = {
        "source": "catalog_lines",
        "interstate": body.interstate,
        "subtotal_paise": subtotal,
        "tax_paise": tax_total,
        "total_paise": total,
    }
    if body.issue:
        _deduct_stock(db, user, invoice, items, quantities, local_now.date())
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="sale.create",
        resource_type="sale_invoice",
        resource_id=invoice.id,
        permission="sales.manage",
        changes={"status": invoice.status, "total_paise": invoice.total_paise, "line_count": len(body.lines)},
    )
    db.commit()
    return invoice_detail(db, user, invoice.id)


def apply_invoice_payment(
    db: Session,
    user: User,
    invoice: SaleInvoice,
    *,
    amount_paise: int,
    method: str,
    reference: str | None,
    idempotency_key: str,
    version: int | None = None,
    permission: str = "payments.record",
) -> SalePayment:
    existing = db.execute(select(SalePayment).where(
        SalePayment.organization_id == user.organization_id,
        SalePayment.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
    if existing:
        return existing
    if version is not None and version != invoice.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice changed since you opened it. Review the latest balance and try again.")
    if invoice.status in {"draft", "void", "refunded"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice cannot accept payment")
    if method not in PAYMENT_METHODS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown payment method")
    if amount_paise <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payment amount must be greater than zero")
    balance = max(invoice.total_paise - invoice.paid_paise, 0)
    if amount_paise > balance:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment exceeds the current invoice balance")
    payment = SalePayment(
        organization_id=user.organization_id,
        invoice_id=invoice.id,
        received_by_user_id=user.id,
        amount_paise=amount_paise,
        method=method,
        reference=reference,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    invoice.paid_paise += amount_paise
    invoice.status = "paid" if invoice.paid_paise == invoice.total_paise else "partially_paid"
    invoice.version += 1
    db.add(Notification(
        organization_id=user.organization_id,
        user_id=user.id,
        kind="success",
        category="payments",
        title=f"Payment recorded for {invoice.invoice_number}",
        body=f"INR {amount_paise / 100:,.2f} received via {method.upper()}.",
        destination={"route": "sales", "invoice": invoice.id},
    ))
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="payment.record",
        resource_type="sale_invoice",
        resource_id=invoice.id,
        permission=permission,
        changes={"amount_paise": amount_paise, "method": method, "invoice_version": invoice.version},
    )
    db.flush()
    return payment


def record_payment(db: Session, user: User, invoice_id: str, body) -> dict:
    invoice = _invoice_access(db, user, invoice_id, lock=True)
    payment = apply_invoice_payment(
        db,
        user,
        invoice,
        amount_paise=body.amount_paise,
        method=body.method,
        reference=body.reference,
        idempotency_key=body.idempotency_key,
        version=body.version,
    )
    db.commit()
    return _serialize(payment)


def void_unpaid_invoice(
    db: Session,
    user: User,
    invoice: SaleInvoice,
    *,
    reason: str,
    version: int | None = None,
    permission: str = "sales.manage",
) -> SaleInvoice:
    clean_reason = " ".join(reason.split())
    if len(clean_reason) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A clear void reason is required")
    if version is not None and version != invoice.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice changed since you opened it. Review it and try again.")
    if invoice.paid_paise or invoice.status == "partially_paid":
        raise HTTPException(status.HTTP_409_CONFLICT, "Paid and partially paid invoices cannot be voided")
    if invoice.status not in {"draft", "issued"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an unpaid open invoice can be voided")
    previous_status = invoice.status
    invoice.status = "void"
    invoice.void_reason = clean_reason
    invoice.voided_at = datetime.now(timezone.utc)
    invoice.voided_by_user_id = user.id
    invoice.version += 1
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="sale.void",
        resource_type="sale_invoice",
        resource_id=invoice.id,
        permission=permission,
        changes={"from_status": previous_status, "reason": clean_reason, "invoice_version": invoice.version},
    )
    db.flush()
    return invoice


def void_invoice(db: Session, user: User, invoice_id: str, body) -> dict:
    invoice = _invoice_access(db, user, invoice_id, lock=True)
    void_unpaid_invoice(db, user, invoice, reason=body.reason, version=body.version)
    db.commit()
    return invoice_detail(db, user, invoice.id)
