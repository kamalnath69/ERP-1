"""Library, Transport, Hostel, Placement, Admissions routes."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    AdmissionApplication,
    Book,
    BookLoan,
    HostelAllocation,
    HostelBlock,
    HostelRoom,
    Organization,
    PlacementDrive,
    PlacementOffer,
    Student,
    TransportAllocation,
    TransportRoute,
    TransportVehicle,
    User,
)

router = APIRouter(tags=["extra"])


# ----------------------------------------------------------------- LIBRARY
class BookIn(BaseModel):
    title: str
    author: str | None = None
    isbn: str | None = None
    category: str | None = None
    total_copies: int = 1


@router.get("/library/books")
def list_books(user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(Book).where(Book.organization_id == user.organization_id).order_by(Book.title)).scalars().all()
    return [{"id": b.id, "title": b.title, "author": b.author, "isbn": b.isbn, "category": b.category, "total_copies": b.total_copies, "available_copies": b.available_copies} for b in rows]


@router.post("/library/books", status_code=status.HTTP_201_CREATED)
def create_book(body: BookIn, user: User = Depends(require_permissions("students.create")), db: Session = Depends(get_db)):
    b = Book(organization_id=user.organization_id, available_copies=body.total_copies, **body.model_dump())
    db.add(b)
    db.commit()
    return {"id": b.id}


class LoanIn(BaseModel):
    book_id: str
    student_id: str
    due_on: str | None = None


@router.post("/library/loans", status_code=status.HTTP_201_CREATED)
def create_loan(body: LoanIn, user: User = Depends(require_permissions("students.edit")), db: Session = Depends(get_db)):
    book = db.get(Book, body.book_id)
    if not book or book.organization_id != user.organization_id:
        raise HTTPException(404, "Book not found")
    if book.available_copies <= 0:
        raise HTTPException(400, "No copies available")
    book.available_copies -= 1
    loan = BookLoan(organization_id=user.organization_id, book_id=body.book_id, student_id=body.student_id, borrowed_on=date.today().isoformat(), due_on=body.due_on)
    db.add(loan)
    db.commit()
    return {"id": loan.id}


@router.post("/library/loans/{loan_id}/return")
def return_loan(loan_id: str, user: User = Depends(require_permissions("students.edit")), db: Session = Depends(get_db)):
    loan = db.get(BookLoan, loan_id)
    if not loan or loan.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    if loan.returned_on:
        return {"ok": True, "already": True}
    loan.returned_on = date.today().isoformat()
    book = db.get(Book, loan.book_id)
    if book:
        book.available_copies += 1
    db.commit()
    return {"ok": True}


@router.get("/library/loans")
def list_loans(user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(BookLoan).where(BookLoan.organization_id == user.organization_id).order_by(BookLoan.created_at.desc())).scalars().all()
    return [{"id": ln.id, "book_id": ln.book_id, "student_id": ln.student_id, "borrowed_on": ln.borrowed_on, "due_on": ln.due_on, "returned_on": ln.returned_on} for ln in rows]


# ----------------------------------------------------------------- TRANSPORT
class RouteIn(BaseModel):
    name: str
    code: str | None = None
    stops: list = []
    fare_monthly: float = 0.0


class VehicleIn(BaseModel):
    registration_number: str
    capacity: int = 40
    route_id: str | None = None
    driver_name: str | None = None
    driver_phone: str | None = None


@router.get("/transport/routes")
def list_routes(user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(TransportRoute).where(TransportRoute.organization_id == user.organization_id)).scalars().all()
    return [{"id": r.id, "name": r.name, "code": r.code, "stops": r.stops, "fare_monthly": r.fare_monthly} for r in rows]


@router.post("/transport/routes", status_code=status.HTTP_201_CREATED)
def create_route(body: RouteIn, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    r = TransportRoute(organization_id=user.organization_id, **body.model_dump())
    db.add(r)
    db.commit()
    return {"id": r.id}


@router.get("/transport/vehicles")
def list_vehicles(user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(TransportVehicle).where(TransportVehicle.organization_id == user.organization_id)).scalars().all()
    return [{"id": v.id, "registration_number": v.registration_number, "capacity": v.capacity, "route_id": v.route_id, "driver_name": v.driver_name, "driver_phone": v.driver_phone} for v in rows]


@router.post("/transport/vehicles", status_code=status.HTTP_201_CREATED)
def create_vehicle(body: VehicleIn, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    v = TransportVehicle(organization_id=user.organization_id, **body.model_dump())
    db.add(v)
    db.commit()
    return {"id": v.id}


# ----------------------------------------------------------------- HOSTEL
class BlockIn(BaseModel):
    name: str
    kind: str = "mixed"


class RoomIn(BaseModel):
    block_id: str
    room_number: str
    capacity: int = 2


class HostelAllocIn(BaseModel):
    student_id: str
    room_id: str


@router.get("/hostel/blocks")
def list_blocks(user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(HostelBlock).where(HostelBlock.organization_id == user.organization_id)).scalars().all()
    return [{"id": b.id, "name": b.name, "kind": b.kind} for b in rows]


@router.post("/hostel/blocks", status_code=status.HTTP_201_CREATED)
def create_block(body: BlockIn, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    b = HostelBlock(organization_id=user.organization_id, **body.model_dump())
    db.add(b)
    db.commit()
    return {"id": b.id}


@router.get("/hostel/rooms")
def list_rooms(block_id: str | None = None, user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    stmt = select(HostelRoom).where(HostelRoom.organization_id == user.organization_id)
    if block_id:
        stmt = stmt.where(HostelRoom.block_id == block_id)
    rows = db.execute(stmt).scalars().all()
    return [{"id": r.id, "block_id": r.block_id, "room_number": r.room_number, "capacity": r.capacity, "occupied": r.occupied} for r in rows]


@router.post("/hostel/rooms", status_code=status.HTTP_201_CREATED)
def create_room(body: RoomIn, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    r = HostelRoom(organization_id=user.organization_id, **body.model_dump())
    db.add(r)
    db.commit()
    return {"id": r.id}


@router.post("/hostel/allocations", status_code=status.HTTP_201_CREATED)
def allocate_hostel(body: HostelAllocIn, user: User = Depends(require_permissions("students.edit")), db: Session = Depends(get_db)):
    room = db.get(HostelRoom, body.room_id)
    if not room or room.organization_id != user.organization_id:
        raise HTTPException(404, "Room not found")
    if room.occupied >= room.capacity:
        raise HTTPException(400, "Room is full")
    room.occupied += 1
    a = HostelAllocation(organization_id=user.organization_id, student_id=body.student_id, room_id=body.room_id, allocated_on=date.today().isoformat())
    db.add(a)
    db.commit()
    return {"id": a.id}


# ----------------------------------------------------------------- PLACEMENT
class DriveIn(BaseModel):
    company: str
    role: str | None = None
    package_lpa: float = 0.0
    drive_date: str | None = None
    description: str | None = None


class OfferIn(BaseModel):
    drive_id: str
    student_id: str
    package_lpa: float = 0.0


@router.get("/placements/drives")
def list_drives(user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(PlacementDrive).where(PlacementDrive.organization_id == user.organization_id).order_by(PlacementDrive.created_at.desc())).scalars().all()
    return [{"id": d.id, "company": d.company, "role": d.role, "package_lpa": d.package_lpa, "drive_date": d.drive_date, "status": d.status} for d in rows]


@router.post("/placements/drives", status_code=status.HTTP_201_CREATED)
def create_drive(body: DriveIn, user: User = Depends(require_permissions("students.create")), db: Session = Depends(get_db)):
    d = PlacementDrive(organization_id=user.organization_id, **body.model_dump())
    db.add(d)
    db.commit()
    return {"id": d.id}


@router.post("/placements/offers", status_code=status.HTTP_201_CREATED)
def create_offer(body: OfferIn, user: User = Depends(require_permissions("students.edit")), db: Session = Depends(get_db)):
    o = PlacementOffer(organization_id=user.organization_id, **body.model_dump())
    db.add(o)
    db.commit()
    return {"id": o.id}


@router.get("/placements/summary")
def placement_summary(user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    total_drives = db.execute(select(func.count(PlacementDrive.id)).where(PlacementDrive.organization_id == user.organization_id)).scalar()
    total_offers = db.execute(select(func.count(PlacementOffer.id)).where(PlacementOffer.organization_id == user.organization_id)).scalar()
    avg_package = db.execute(
        select(func.coalesce(func.avg(PlacementOffer.package_lpa), 0)).where(PlacementOffer.organization_id == user.organization_id, PlacementOffer.status.in_(["offered", "accepted"]))
    ).scalar()
    top_package = db.execute(
        select(func.coalesce(func.max(PlacementOffer.package_lpa), 0)).where(PlacementOffer.organization_id == user.organization_id)
    ).scalar()
    return {"drives": total_drives, "offers": total_offers, "avg_package_lpa": round(float(avg_package or 0), 2), "top_package_lpa": float(top_package or 0)}


# ----------------------------------------------------------------- ADMISSIONS (public + admin)
class PublicApplication(BaseModel):
    org_slug: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None
    date_of_birth: str | None = None
    prev_school: str | None = None
    interest_department: str | None = None
    parent_name: str | None = None
    parent_phone: str | None = None
    parent_email: EmailStr | None = None
    notes: str | None = None


@router.get("/public/organization/{slug}")
def public_org_info(slug: str, db: Session = Depends(get_db)):
    org = db.execute(select(Organization).where(Organization.slug == slug.lower())).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Not found")
    return {"id": org.id, "name": org.name, "slug": org.slug, "org_type": org.org_type.value, "logo_url": org.logo_url, "description": org.description}


@router.post("/public/admissions", status_code=status.HTTP_201_CREATED)
def public_apply(body: PublicApplication, db: Session = Depends(get_db)):
    org = db.execute(select(Organization).where(Organization.slug == body.org_slug.lower())).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")
    data = body.model_dump()
    slug = data.pop("org_slug")  # not stored
    del slug  # silence unused
    if data.get("email"):
        data["email"] = str(data["email"]).lower()
    if data.get("parent_email"):
        data["parent_email"] = str(data["parent_email"]).lower()
    app_row = AdmissionApplication(organization_id=org.id, stage="new", **data)
    db.add(app_row)
    db.commit()
    return {"id": app_row.id, "ok": True}


@router.get("/admissions")
def list_applications(stage: str | None = None, user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    stmt = select(AdmissionApplication).where(AdmissionApplication.organization_id == user.organization_id)
    if stage:
        stmt = stmt.where(AdmissionApplication.stage == stage)
    rows = db.execute(stmt.order_by(AdmissionApplication.created_at.desc())).scalars().all()
    return [
        {
            "id": a.id, "first_name": a.first_name, "last_name": a.last_name,
            "email": a.email, "phone": a.phone, "interest_department": a.interest_department,
            "stage": a.stage, "created_at": a.created_at, "prev_school": a.prev_school,
            "student_id": a.student_id,
        } for a in rows
    ]


class StageUpdate(BaseModel):
    stage: str


@router.patch("/admissions/{app_id}")
def update_stage(app_id: str, body: StageUpdate, user: User = Depends(require_permissions("students.edit")), db: Session = Depends(get_db)):
    a = db.get(AdmissionApplication, app_id)
    if not a or a.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    a.stage = body.stage
    db.commit()
    return {"ok": True, "stage": a.stage}


@router.post("/admissions/{app_id}/enroll")
def enroll_application(app_id: str, user: User = Depends(require_permissions("students.create")), db: Session = Depends(get_db)):
    a = db.get(AdmissionApplication, app_id)
    if not a or a.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    if a.student_id:
        return {"ok": True, "student_id": a.student_id, "already": True}
    # Create student
    adm = f"ADM-{a.id[:8].upper()}"
    s = Student(
        organization_id=user.organization_id,
        admission_number=adm,
        first_name=a.first_name,
        last_name=a.last_name,
        email=a.email,
        phone=a.phone,
        date_of_birth=a.date_of_birth,
    )
    db.add(s)
    db.flush()
    a.student_id = s.id
    a.stage = "enrolled"
    db.commit()
    return {"ok": True, "student_id": s.id}
