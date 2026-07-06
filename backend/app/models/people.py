"""Students, parents, and faculty profile records."""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class Student(TimestampMixin, Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("organization_id", "admission_number", name="uq_student_org_admission"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    admission_number: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    date_of_birth: Mapped[str | None] = mapped_column(String(20))
    gender: Mapped[str | None] = mapped_column(String(20))
    section_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("sections.id", ondelete="SET NULL"), index=True)
    department_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("departments.id", ondelete="SET NULL"))
    roll_number: Mapped[str | None] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    address: Mapped[str | None] = mapped_column(Text)


class Parent(TimestampMixin, Base):
    __tablename__ = "parents"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(30))
    occupation: Mapped[str | None] = mapped_column(String(150))


class StudentParent(Base):
    __tablename__ = "student_parents"
    __table_args__ = (UniqueConstraint("student_id", "parent_id", name="uq_student_parent"),)

    id: Mapped[str] = uuid_pk()
    student_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    relationship: Mapped[str] = mapped_column(String(30), default="guardian")  # father/mother/guardian


class Faculty(TimestampMixin, Base):
    __tablename__ = "faculty"
    __table_args__ = (UniqueConstraint("organization_id", "employee_number", name="uq_faculty_org_empno"),)

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_number: Mapped[str] = mapped_column(String(60), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(120))
    department_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("departments.id", ondelete="SET NULL"))
    qualification: Mapped[str | None] = mapped_column(String(300))
    experience_years: Mapped[int | None] = mapped_column(Integer)
    joined_on: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
