"""Salon industry workspace API."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_entitlements, require_permissions
from app.services.salon import salon_workspace


router = APIRouter(prefix="/salon", tags=["salon"])


@router.get("/workspace", dependencies=[Depends(require_entitlements("module.salon"))])
def workspace(
    location_id: str | None = None,
    range_days: int = Query(30, alias="range"),
    user=Depends(require_permissions("appointments.view")),
    db: Session = Depends(get_db),
):
    return salon_workspace(db, user, location_id, range_days if range_days in {7, 30, 90} else 30)


def _section(db, user, location_id: str | None, range_days: int, key: str):
    data = salon_workspace(db, user, location_id, range_days if range_days in {7, 30, 90} else 30)
    return {key: data[key], "generated_at": data["generated_at"]}


@router.get("/summary", dependencies=[Depends(require_entitlements("module.salon"))])
def summary(
    location_id: str | None = None,
    range_days: int = Query(30, alias="range"),
    user=Depends(require_permissions("appointments.view")),
    db: Session = Depends(get_db),
):
    return _section(db, user, location_id, range_days, "summary")


@router.get("/bookings", dependencies=[Depends(require_entitlements("module.salon"))])
def bookings(
    location_id: str | None = None,
    range_days: int = Query(30, alias="range"),
    user=Depends(require_permissions("appointments.view")),
    db: Session = Depends(get_db),
):
    return _section(db, user, location_id, range_days, "bookings")


@router.get("/rebooking", dependencies=[Depends(require_entitlements("module.salon"))])
def rebooking(
    location_id: str | None = None,
    range_days: int = Query(90, alias="range"),
    user=Depends(require_permissions("clients.view")),
    db: Session = Depends(get_db),
):
    return _section(db, user, location_id, range_days, "rebooking")


@router.get("/follow-ups", dependencies=[Depends(require_entitlements("module.salon"))])
def follow_ups(
    location_id: str | None = None,
    range_days: int = Query(30, alias="range"),
    user=Depends(require_permissions("clients.view")),
    db: Session = Depends(get_db),
):
    return _section(db, user, location_id, range_days, "follow_ups")
