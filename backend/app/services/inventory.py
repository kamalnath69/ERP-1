"""Inventory reads and atomic location transfers."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import CatalogItem, Location, StockLevel, StockMovement, User
from app.services.audit import log_action
from app.services.business_access import ensure_location, filter_locations, tenant_get
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size


def _serialize(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _scope_levels(statement, db: Session, user: User, location_id: str | None):
    statement = filter_locations(statement, StockLevel, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(StockLevel.location_id == location_id)
    return statement


def _apply_level_state(statement, state: str | None):
    if state == "in_stock":
        return statement.where(StockLevel.quantity_milli > 0)
    if state == "low":
        return statement.where(StockLevel.quantity_milli > 0, StockLevel.quantity_milli <= StockLevel.reorder_level_milli)
    if state == "out":
        return statement.where(StockLevel.quantity_milli <= 0)
    if state == "expiring":
        return statement.where(StockLevel.expires_on.is_not(None), StockLevel.expires_on <= date.today() + timedelta(days=30))
    if state == "available":
        return statement.where(StockLevel.quantity_milli > StockLevel.reorder_level_milli)
    return statement


def _inventory_summary(db: Session, user: User, location_id: str | None) -> dict:
    statement = select(
        func.count(func.distinct(case((StockLevel.quantity_milli > 0, StockLevel.item_id), else_=None))),
        func.coalesce(func.sum((StockLevel.quantity_milli * CatalogItem.cost_paise) / 1000), 0),
        func.coalesce(func.sum(case((and_(StockLevel.quantity_milli > 0, StockLevel.quantity_milli <= StockLevel.reorder_level_milli), 1), else_=0)), 0),
        func.coalesce(func.sum(case((StockLevel.quantity_milli <= 0, 1), else_=0)), 0),
        func.coalesce(func.sum(case((and_(StockLevel.expires_on.is_not(None), StockLevel.expires_on <= date.today() + timedelta(days=30)), 1), else_=0)), 0),
    ).join(CatalogItem, CatalogItem.id == StockLevel.item_id).where(
        StockLevel.organization_id == user.organization_id,
        CatalogItem.organization_id == user.organization_id,
    )
    statement = _scope_levels(statement, db, user, location_id)
    row = db.execute(statement).one()
    return {
        "stocked_items": int(row[0] or 0),
        "stock_value_paise": int(row[1] or 0),
        "low_stock": int(row[2] or 0),
        "out_of_stock": int(row[3] or 0),
        "expiring_batches": int(row[4] or 0),
    }


def inventory_levels_page(
    db: Session,
    user: User,
    location_id: str | None,
    query: str | None,
    state: str | None,
    batches_only: bool,
    cursor: str | None,
    limit: int,
) -> dict:
    normalized_query = " ".join((query or "").casefold().split())
    filters = {
        "location_id": location_id,
        "q": normalized_query,
        "state": state,
        "batches_only": batches_only,
    }
    values = decode_cursor(
        cursor,
        scope="inventory.levels",
        organization_id=user.organization_id,
        filters=filters,
    )
    statement = select(StockLevel, CatalogItem, Location).join(
        CatalogItem, CatalogItem.id == StockLevel.item_id,
    ).join(
        Location, Location.id == StockLevel.location_id,
    ).where(
        StockLevel.organization_id == user.organization_id,
        CatalogItem.organization_id == user.organization_id,
        Location.organization_id == user.organization_id,
    )
    statement = _scope_levels(statement, db, user, location_id)
    statement = _apply_level_state(statement, state)
    if batches_only:
        statement = statement.where(or_(StockLevel.batch_number != "", StockLevel.expires_on.is_not(None)))
    if normalized_query:
        term = f"%{normalized_query}%"
        statement = statement.where(or_(
            func.lower(CatalogItem.name).like(term),
            func.lower(CatalogItem.sku).like(term),
            func.lower(func.coalesce(CatalogItem.hsn_sac, "")).like(term),
            func.lower(StockLevel.batch_number).like(term),
        ))
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            StockLevel.updated_at < pivot_at,
            and_(StockLevel.updated_at == pivot_at, StockLevel.id < str(values["id"])),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(StockLevel.updated_at.desc(), StockLevel.id.desc()).limit(size + 1)).all())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="inventory.levels",
        organization_id=user.organization_id,
        filters=filters,
        values={"at": rows[-1][0].updated_at.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return {
        "items": [
            {**_serialize(level), "item": _serialize(item), "location": _serialize(location)}
            for level, item, location in rows
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "summary": _inventory_summary(db, user, location_id),
    }


def inventory_movements_page(
    db: Session,
    user: User,
    location_id: str | None,
    query: str | None,
    movement_type: str | None,
    cursor: str | None,
    limit: int,
) -> dict:
    normalized_query = " ".join((query or "").casefold().split())
    filters = {"location_id": location_id, "q": normalized_query, "movement_type": movement_type}
    values = decode_cursor(
        cursor,
        scope="inventory.movements",
        organization_id=user.organization_id,
        filters=filters,
    )
    statement = select(StockMovement, CatalogItem, Location).join(
        CatalogItem, CatalogItem.id == StockMovement.item_id,
    ).join(
        Location, Location.id == StockMovement.location_id,
    ).where(
        StockMovement.organization_id == user.organization_id,
        CatalogItem.organization_id == user.organization_id,
        Location.organization_id == user.organization_id,
    )
    statement = filter_locations(statement, StockMovement, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        statement = statement.where(StockMovement.location_id == location_id)
    if movement_type:
        statement = statement.where(StockMovement.movement_type == movement_type)
    if normalized_query:
        term = f"%{normalized_query}%"
        statement = statement.where(or_(
            func.lower(CatalogItem.name).like(term),
            func.lower(CatalogItem.sku).like(term),
            func.lower(StockMovement.reason).like(term),
            func.lower(StockMovement.movement_type).like(term),
        ))
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            StockMovement.created_at < pivot_at,
            and_(StockMovement.created_at == pivot_at, StockMovement.id < str(values["id"])),
        ))
    size = page_size(limit, default=50)
    rows = list(db.execute(statement.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(size + 1)).all())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="inventory.movements",
        organization_id=user.organization_id,
        filters=filters,
        values={"at": rows[-1][0].created_at.isoformat(), "id": rows[-1][0].id},
    ) if has_more and rows else None
    return {
        "items": [
            {
                **_serialize(movement),
                "item_name": item.name,
                "item_sku": item.sku,
                "location_name": location.name,
            }
            for movement, item, location in rows
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


def inventory_workspace(db: Session, user: User, location_id: str | None, query: str | None, state: str | None) -> dict:
    level_stmt = select(StockLevel).where(StockLevel.organization_id == user.organization_id)
    level_stmt = filter_locations(level_stmt, StockLevel, db, user)
    if location_id:
        ensure_location(db, user, location_id)
        level_stmt = level_stmt.where(StockLevel.location_id == location_id)
    if state == "low":
        level_stmt = level_stmt.where(StockLevel.quantity_milli > 0, StockLevel.quantity_milli <= StockLevel.reorder_level_milli)
    elif state == "in_stock":
        level_stmt = level_stmt.where(StockLevel.quantity_milli > 0)
    elif state == "out":
        level_stmt = level_stmt.where(StockLevel.quantity_milli <= 0)
    elif state == "expiring":
        level_stmt = level_stmt.where(StockLevel.expires_on.is_not(None), StockLevel.expires_on <= date.today() + timedelta(days=30))
    elif state == "available":
        level_stmt = level_stmt.where(StockLevel.quantity_milli > StockLevel.reorder_level_milli)
    rows = db.execute(level_stmt.order_by(StockLevel.updated_at.desc(), StockLevel.id)).scalars().all()
    item_ids = {row.item_id for row in rows}
    location_ids = {row.location_id for row in rows}
    items = {item.id: item for item in db.execute(select(CatalogItem).where(
        CatalogItem.organization_id == user.organization_id, CatalogItem.id.in_(item_ids),
    )).scalars()} if item_ids else {}
    locations = {location.id: location for location in db.execute(select(Location).where(
        Location.organization_id == user.organization_id, Location.id.in_(location_ids),
    )).scalars()} if location_ids else {}
    if query:
        needle = query.casefold().replace(" ", "")
        rows = [row for row in rows if needle in f"{items.get(row.item_id).name if items.get(row.item_id) else ''}{items.get(row.item_id).sku if items.get(row.item_id) else ''}{row.batch_number}".casefold().replace(" ", "")]

    movement_stmt = select(StockMovement).where(StockMovement.organization_id == user.organization_id)
    movement_stmt = filter_locations(movement_stmt, StockMovement, db, user)
    if location_id:
        movement_stmt = movement_stmt.where(StockMovement.location_id == location_id)
    movements = db.execute(movement_stmt.order_by(StockMovement.created_at.desc()).limit(100)).scalars().all()
    movement_item_ids = {row.item_id for row in movements} - set(items)
    if movement_item_ids:
        items.update({item.id: item for item in db.execute(select(CatalogItem).where(
            CatalogItem.organization_id == user.organization_id, CatalogItem.id.in_(movement_item_ids),
        )).scalars()})
    movement_location_ids = {row.location_id for row in movements} - set(locations)
    if movement_location_ids:
        locations.update({location.id: location for location in db.execute(select(Location).where(
            Location.organization_id == user.organization_id, Location.id.in_(movement_location_ids),
        )).scalars()})

    all_rows_stmt = select(StockLevel).where(StockLevel.organization_id == user.organization_id)
    all_rows_stmt = filter_locations(all_rows_stmt, StockLevel, db, user)
    if location_id:
        all_rows_stmt = all_rows_stmt.where(StockLevel.location_id == location_id)
    all_rows = db.execute(all_rows_stmt).scalars().all()
    all_item_ids = {row.item_id for row in all_rows}
    all_items = {item.id: item for item in db.execute(select(CatalogItem).where(CatalogItem.organization_id == user.organization_id, CatalogItem.id.in_(all_item_ids))).scalars()} if all_item_ids else {}
    stock_value = sum(round(row.quantity_milli * (all_items.get(row.item_id).cost_paise if all_items.get(row.item_id) else 0) / 1000) for row in all_rows)
    low = sum(0 < row.quantity_milli <= row.reorder_level_milli for row in all_rows)
    out = sum(row.quantity_milli <= 0 for row in all_rows)
    expiring = sum(bool(row.expires_on and row.expires_on <= date.today() + timedelta(days=30)) for row in all_rows)
    return {
        "summary": {
            "stocked_items": len({row.item_id for row in all_rows if row.quantity_milli > 0}),
            "stock_value_paise": stock_value,
            "low_stock": low,
            "out_of_stock": out,
            "expiring_batches": expiring,
        },
        "levels": [{**_serialize(row), "item": _serialize(items[row.item_id]), "location": _serialize(locations[row.location_id])} for row in rows if row.item_id in items and row.location_id in locations],
        "movements": [{**_serialize(row), "item_name": items.get(row.item_id).name if items.get(row.item_id) else "Unavailable item", "location_name": locations.get(row.location_id).name if locations.get(row.location_id) else "Unavailable location"} for row in movements],
        "generated_at": datetime.now(timezone.utc),
    }


def transfer_stock(
    db: Session, user: User, *, item_id: str, source_location_id: str,
    destination_location_id: str, quantity_milli: int, batch_number: str,
    reason: str,
) -> dict:
    if source_location_id == destination_location_id:
        raise HTTPException(422, "Choose a different destination location")
    source_location = ensure_location(db, user, source_location_id)
    destination_location = ensure_location(db, user, destination_location_id)
    item = tenant_get(db, CatalogItem, item_id, user)
    if not item.track_stock:
        raise HTTPException(409, "This item does not track stock")
    location_order = sorted([source_location_id, destination_location_id])
    locked = db.execute(select(StockLevel).where(
        StockLevel.organization_id == user.organization_id,
        StockLevel.item_id == item_id,
        StockLevel.location_id.in_(location_order),
        StockLevel.batch_number == batch_number,
    ).order_by(StockLevel.location_id).with_for_update()).scalars().all()
    levels = {row.location_id: row for row in locked}
    source = levels.get(source_location_id)
    if not source or source.quantity_milli < quantity_milli:
        raise HTTPException(409, "The source location does not have enough stock")
    destination = levels.get(destination_location_id)
    if not destination:
        destination = StockLevel(
            organization_id=user.organization_id, location_id=destination_location_id,
            item_id=item_id, quantity_milli=0, reorder_level_milli=source.reorder_level_milli,
            batch_number=batch_number, expires_on=source.expires_on,
        )
        db.add(destination)
        db.flush()
    source.quantity_milli -= quantity_milli
    destination.quantity_milli += quantity_milli
    source.version += 1
    destination.version += 1
    transfer_id = str(uuid4())
    common = {
        "organization_id": user.organization_id, "item_id": item.id,
        "movement_type": "transfer", "reason": reason,
        "reference_type": "stock_transfer", "reference_id": transfer_id,
        "performed_by_user_id": user.id,
    }
    db.add_all([
        StockMovement(location_id=source_location.id, stock_level_id=source.id, quantity_delta_milli=-quantity_milli, **common),
        StockMovement(location_id=destination_location.id, stock_level_id=destination.id, quantity_delta_milli=quantity_milli, **common),
    ])
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="inventory.transfer", resource_type="stock_transfer", resource_id=transfer_id, changes={"item_id": item.id, "source_location_id": source_location.id, "destination_location_id": destination_location.id, "quantity_milli": quantity_milli})
    db.commit()
    return {
        "id": transfer_id, "item_id": item.id, "item_name": item.name,
        "source_location": source_location.name, "destination_location": destination_location.name,
        "quantity_milli": quantity_milli, "batch_number": batch_number,
    }
