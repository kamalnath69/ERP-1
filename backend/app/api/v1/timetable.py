"""Timetable + Calendar."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import CalendarEvent, TimetableSlot, User

router = APIRouter(tags=["timetable"])


class TimetableIn(BaseModel):
    section_id: str
    subject_id: str | None = None
    faculty_user_id: str | None = None
    day_of_week: int
    period: int
    start_time: str | None = None  # HH:MM
    end_time: str | None = None
    room: str | None = None
    label: str | None = None


@router.get("/timetable")
def list_timetable(section_id: str | None = None, user: User = Depends(require_permissions("academic.view")), db: Session = Depends(get_db)):
    stmt = select(TimetableSlot).where(TimetableSlot.organization_id == user.organization_id)
    if section_id:
        stmt = stmt.where(TimetableSlot.section_id == section_id)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": t.id, "section_id": t.section_id, "subject_id": t.subject_id, "faculty_user_id": t.faculty_user_id,
            "day_of_week": t.day_of_week, "period": t.period,
            "start_time": t.start_time.isoformat() if t.start_time else None,
            "end_time": t.end_time.isoformat() if t.end_time else None,
            "room": t.room, "label": t.label,
        } for t in rows
    ]


@router.post("/timetable", status_code=status.HTTP_201_CREATED)
def upsert_timetable(body: TimetableIn, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    from datetime import time
    existing = db.execute(
        select(TimetableSlot).where(
            TimetableSlot.section_id == body.section_id,
            TimetableSlot.day_of_week == body.day_of_week,
            TimetableSlot.period == body.period,
            TimetableSlot.organization_id == user.organization_id,
        )
    ).scalar_one_or_none()
    payload = body.model_dump()
    for k in ("start_time", "end_time"):
        if payload.get(k):
            try:
                h, m = payload[k].split(":")
                payload[k] = time(int(h), int(m))
            except Exception:
                payload[k] = None
    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
        db.commit()
        return {"id": existing.id, "updated": True}
    slot = TimetableSlot(organization_id=user.organization_id, **payload)
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return {"id": slot.id, "updated": False}


@router.delete("/timetable/{slot_id}")
def delete_slot(slot_id: str, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    s = db.get(TimetableSlot, slot_id)
    if not s or s.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


class CalendarIn(BaseModel):
    title: str
    description: str | None = None
    event_date: str
    kind: str = "event"
    color: str | None = None


@router.get("/calendar")
def list_events(user: User = Depends(require_permissions("academic.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(CalendarEvent).where(CalendarEvent.organization_id == user.organization_id).order_by(CalendarEvent.event_date)).scalars().all()
    return [{"id": e.id, "title": e.title, "description": e.description, "event_date": e.event_date, "kind": e.kind, "color": e.color} for e in rows]


@router.post("/calendar", status_code=status.HTTP_201_CREATED)
def create_event(body: CalendarIn, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    e = CalendarEvent(organization_id=user.organization_id, **body.model_dump())
    db.add(e)
    db.commit()
    return {"id": e.id}


@router.delete("/calendar/{event_id}")
def delete_event(event_id: str, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    e = db.get(CalendarEvent, event_id)
    if not e or e.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    db.delete(e)
    db.commit()
    return {"ok": True}
