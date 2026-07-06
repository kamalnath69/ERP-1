"""Exams and marks."""
from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class Exam(TimestampMixin, Base):
    __tablename__ = "exams"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    exam_type: Mapped[str] = mapped_column(String(80), default="internal")  # internal / mid / final / assignment
    subject_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    section_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("sections.id", ondelete="SET NULL"), index=True)
    academic_year_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("academic_years.id", ondelete="SET NULL"))
    max_marks: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    pass_marks: Mapped[float] = mapped_column(Float, default=40.0, nullable=False)
    exam_date: Mapped[str | None] = mapped_column(Date)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


class Mark(TimestampMixin, Base):
    __tablename__ = "marks"
    __table_args__ = (UniqueConstraint("exam_id", "student_id", name="uq_mark_exam_student"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    exam_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    obtained: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    grade: Mapped[str | None] = mapped_column(String(10))
    remarks: Mapped[str | None] = mapped_column(String(300))
    entered_by_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
