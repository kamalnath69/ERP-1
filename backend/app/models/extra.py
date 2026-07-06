"""Library, Transport, Hostel, Placement, Admissions."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


# ------------------------------------------------------------------ Library
class Book(TimestampMixin, Base):
    __tablename__ = "library_books"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    isbn: Mapped[str | None] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    author: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(80))
    total_copies: Mapped[int] = mapped_column(Integer, default=1)
    available_copies: Mapped[int] = mapped_column(Integer, default=1)


class BookLoan(TimestampMixin, Base):
    __tablename__ = "library_loans"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    book_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("library_books.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    borrowed_on: Mapped[str] = mapped_column(String(20), nullable=False)
    due_on: Mapped[str | None] = mapped_column(String(20))
    returned_on: Mapped[str | None] = mapped_column(String(20))


# ------------------------------------------------------------------ Transport
class TransportRoute(TimestampMixin, Base):
    __tablename__ = "transport_routes"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(40))
    stops: Mapped[list | dict] = mapped_column(JSONB, default=list)
    fare_monthly: Mapped[float] = mapped_column(Float, default=0.0)


class TransportVehicle(TimestampMixin, Base):
    __tablename__ = "transport_vehicles"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    registration_number: Mapped[str] = mapped_column(String(40), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=40)
    route_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("transport_routes.id", ondelete="SET NULL"))
    driver_name: Mapped[str | None] = mapped_column(String(200))
    driver_phone: Mapped[str | None] = mapped_column(String(30))


class TransportAllocation(TimestampMixin, Base):
    __tablename__ = "transport_allocations"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    route_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("transport_routes.id", ondelete="CASCADE"), nullable=False)
    stop: Mapped[str | None] = mapped_column(String(200))


# ------------------------------------------------------------------ Hostel
class HostelBlock(TimestampMixin, Base):
    __tablename__ = "hostel_blocks"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="mixed")  # boys / girls / mixed
    warden_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))


class HostelRoom(TimestampMixin, Base):
    __tablename__ = "hostel_rooms"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    block_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("hostel_blocks.id", ondelete="CASCADE"), nullable=False)
    room_number: Mapped[str] = mapped_column(String(40), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=2)
    occupied: Mapped[int] = mapped_column(Integer, default=0)


class HostelAllocation(TimestampMixin, Base):
    __tablename__ = "hostel_allocations"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    student_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("hostel_rooms.id", ondelete="CASCADE"), nullable=False)
    allocated_on: Mapped[str | None] = mapped_column(String(20))
    vacated_on: Mapped[str | None] = mapped_column(String(20))


# ------------------------------------------------------------------ Placement
class PlacementDrive(TimestampMixin, Base):
    __tablename__ = "placement_drives"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200))
    package_lpa: Mapped[float] = mapped_column(Float, default=0.0)
    drive_date: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="scheduled")  # scheduled / ongoing / closed
    description: Mapped[str | None] = mapped_column(Text)


class PlacementOffer(TimestampMixin, Base):
    __tablename__ = "placement_offers"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    drive_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("placement_drives.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    package_lpa: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="offered")  # offered / accepted / declined


# ------------------------------------------------------------------ Admissions
class AdmissionApplication(TimestampMixin, Base):
    """Public application coming from a tenant's admissions form."""

    __tablename__ = "admission_applications"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    date_of_birth: Mapped[str | None] = mapped_column(String(20))
    prev_school: Mapped[str | None] = mapped_column(String(300))
    interest_department: Mapped[str | None] = mapped_column(String(120))
    parent_name: Mapped[str | None] = mapped_column(String(200))
    parent_phone: Mapped[str | None] = mapped_column(String(30))
    parent_email: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(30), default="new", index=True)  # new / reviewing / interview / accepted / rejected / enrolled
    student_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="SET NULL"))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
