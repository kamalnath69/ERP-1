"""Configurable academic engine — tenant-defined exam types, attendance statuses,
and grading bands. Every row is metadata; application logic reads from the DB.
"""
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, uuid_pk, tenant_fk


class ExamType(TimestampMixin, Base):
    """Assessment type catalogue — e.g. "Mid Sem" / "Class Test" / "Project"."""
    __tablename__ = "exam_types"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_exam_type_org_code"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    weightage_default: Mapped[float] = mapped_column(Float, default=0.0)
    max_marks_default: Mapped[float] = mapped_column(Float, default=100.0)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AttendanceStatusConfig(TimestampMixin, Base):
    """Attendance status catalogue — e.g. "Present" / "Absent" / "OD" / "Sick Leave"."""
    __tablename__ = "attendance_status_configs"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_att_status_org_code"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    code: Mapped[str] = mapped_column(String(30), nullable=False)  # short: P|A|OD|L
    label: Mapped[str] = mapped_column(String(80), nullable=False)  # human: "Present" / "On duty"
    counts_as_present: Mapped[bool] = mapped_column(Boolean, default=False)  # for % computation
    is_leave: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str | None] = mapped_column(String(20))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class GradeBand(TimestampMixin, Base):
    """Percentage-to-grade mapping — tenant-defined grading scale."""
    __tablename__ = "grade_bands"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    min_percent: Mapped[float] = mapped_column(Float, nullable=False)
    max_percent: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    grade: Mapped[str] = mapped_column(String(10), nullable=False)  # O, A+, A, B+, ...
    grade_point: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str | None] = mapped_column(String(200))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
