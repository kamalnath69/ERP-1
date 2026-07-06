"""Generic academic hierarchy: Org > Campus > Unit > Level > Group > Section, plus Subjects and faculty assignments."""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class Department(TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_dept_org_code"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    campus_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("campuses.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    hod_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))


class AcademicUnit(TimestampMixin, Base):
    """A stream/programme (e.g. CSE, ECE for college; "Primary", "Secondary" for school)."""

    __tablename__ = "academic_units"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    department_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("departments.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)


class AcademicLevel(TimestampMixin, Base):
    """e.g. class 10, or year 2 of B.Tech."""

    __tablename__ = "academic_levels"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    unit_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("academic_units.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class AcademicGroup(TimestampMixin, Base):
    """Optional grouping: batch, stream, elective group."""

    __tablename__ = "academic_groups"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    level_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("academic_levels.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Section(TimestampMixin, Base):
    __tablename__ = "sections"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    level_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("academic_levels.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("academic_groups.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # A, B, C
    advisor_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    room: Mapped[str | None] = mapped_column(String(50))


class Subject(TimestampMixin, Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_subject_org_code"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    department_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("departments.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AcademicYear(TimestampMixin, Base):
    __tablename__ = "academic_years"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. 2025-2026
    start_date: Mapped[str | None] = mapped_column(String(20))
    end_date: Mapped[str | None] = mapped_column(String(20))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class FacultyAssignment(TimestampMixin, Base):
    """Assigns a faculty user to a subject in a section for a given academic year."""

    __tablename__ = "faculty_assignments"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    faculty_user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    section_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("academic_years.id", ondelete="SET NULL"))
    role: Mapped[str] = mapped_column(String(50), default="teacher")  # teacher / advisor / hod / coordinator
