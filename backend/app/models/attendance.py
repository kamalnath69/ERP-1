"""Attendance sessions and per-student records."""
import enum

from sqlalchemy import Date, ForeignKey, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class AttendanceStatusEnum(str, enum.Enum):
    """Legacy default codes. Tenants can override via `attendance_status_configs`."""
    present = "present"
    absent = "absent"
    late = "late"
    excused = "excused"


class AttendanceSession(TimestampMixin, Base):
    """One row = one class period marking event."""

    __tablename__ = "attendance_sessions"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    section_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("subjects.id", ondelete="SET NULL"))
    faculty_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_date: Mapped[str] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[str | None] = mapped_column(Time)
    end_time: Mapped[str | None] = mapped_column(Time)
    topic: Mapped[str | None] = mapped_column(Text)


class AttendanceRecord(TimestampMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    session_id: Mapped[str] = mapped_column(
        UUID_STR, ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    # status is now a FREE-FORM code that references the tenant's `attendance_status_configs`
    # (or a default like "present"/"absent"/"late"/"excused" when no catalogue exists).
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="present")
    remarks: Mapped[str | None] = mapped_column(String(300))
