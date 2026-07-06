"""Timetable slots — a weekly schedule attached to a section."""
from sqlalchemy import ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUID_STR, uuid_pk, tenant_fk


class TimetableSlot(TimestampMixin, Base):
    __tablename__ = "timetable_slots"
    __table_args__ = (
        UniqueConstraint("section_id", "day_of_week", "period", name="uq_tt_section_day_period"),
    )

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    section_id: Mapped[str] = mapped_column(UUID_STR, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("subjects.id", ondelete="SET NULL"))
    faculty_user_id: Mapped[str | None] = mapped_column(UUID_STR, ForeignKey("users.id", ondelete="SET NULL"))
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon..6=Sun
    period: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..N
    start_time: Mapped[str | None] = mapped_column(Time)
    end_time: Mapped[str | None] = mapped_column(Time)
    room: Mapped[str | None] = mapped_column(String(60))
    label: Mapped[str | None] = mapped_column(String(120))


class CalendarEvent(TimestampMixin, Base):
    __tablename__ = "calendar_events"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = tenant_fk()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    event_date: Mapped[str] = mapped_column(String(20), nullable=False)  # ISO date
    kind: Mapped[str] = mapped_column(String(40), default="event")  # event/holiday/exam/deadline
    color: Mapped[str | None] = mapped_column(String(20))
