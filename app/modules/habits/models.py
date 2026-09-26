from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, now


class Habit(Base):
    __tablename__ = "habit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Whose it is. 0 only appears mid-migration on a pre-multiuser database.
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, default=0)
    name: Mapped[str] = mapped_column(String(120))
    hour: Mapped[int] = mapped_column(Integer, default=9)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    # "daily" = once at hour:minute. "interval" = every `every_minutes`
    # between hour:minute and end_hour:end_minute, several times a day.
    kind: Mapped[str] = mapped_column(String(10), default="daily")
    every_minutes: Mapped[int] = mapped_column(Integer, default=0)
    end_hour: Mapped[int] = mapped_column(Integer, default=18)
    end_minute: Mapped[int] = mapped_column(Integer, default=0)
    # Weekday bitmap as digits, Mon=0: "0123456" daily, "01234" weekdays.
    days: Mapped[str] = mapped_column(String(7), default="0123456")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    # "Remind me in 1 hour" from a nudge. Stored, not just scheduled, because
    # jobs are rebuilt from the database and would otherwise vanish on restart.
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    logs: Mapped[list["HabitLog"]] = relationship(
        back_populates="habit", cascade="all, delete-orphan", lazy="selectin"
    )


class HabitLog(Base):
    """One row per habit per day. Streaks are computed from these, never stored."""

    __tablename__ = "habit_log"
    __table_args__ = (UniqueConstraint("habit_id", "day", name="uq_habit_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habit.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(10))  # done | skip | partial
    # How many times it was done that day. Always 1 for a once-a-day habit;
    # an interval habit counts up to its daily target.
    count: Mapped[int] = mapped_column(Integer, default=1)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    habit: Mapped[Habit] = relationship(back_populates="logs")
