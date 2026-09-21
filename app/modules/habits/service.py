from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import Session, now
from app.modules.habits.models import Habit, HabitLog


async def all_habits(only_active: bool = False) -> list[Habit]:
    async with Session() as s:
        q = select(Habit).options(selectinload(Habit.logs)).order_by(Habit.hour, Habit.minute)
        if only_active:
            q = q.where(Habit.active.is_(True))
        return list((await s.scalars(q)).all())


async def get(habit_id: int) -> Habit | None:
    async with Session() as s:
        return await s.scalar(
            select(Habit).options(selectinload(Habit.logs)).where(Habit.id == habit_id)
        )


async def create(name: str, hour: int, minute: int, days: str) -> Habit:
    async with Session() as s:
        h = Habit(name=name.strip()[:120], hour=hour, minute=minute, days=days)
        s.add(h)
        await s.commit()
        return h


async def update(habit_id: int, **fields) -> None:
    async with Session() as s:
        h = await s.get(Habit, habit_id)
        if h is None:
            return
        for k, v in fields.items():
            setattr(h, k, v)
        await s.commit()


async def delete(habit_id: int) -> None:
    async with Session() as s:
        h = await s.get(Habit, habit_id)
        if h:
            await s.delete(h)
            await s.commit()


async def log(habit_id: int, status: str, day: date | None = None) -> None:
    """Idempotent per day - tapping Done twice does not double-count."""
    day = day or now().date()
    async with Session() as s:
        existing = await s.scalar(
            select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.day == day)
        )
        if existing:
            existing.status = status
            existing.logged_at = now()
        else:
            s.add(HabitLog(habit_id=habit_id, day=day, status=status))
        await s.commit()


def _scheduled_on(habit: Habit, day: date) -> bool:
    return str(day.weekday()) in habit.days


def streak(habit: Habit) -> int:
    """Consecutive scheduled days completed, walking back from today.

    Today not yet logged does not break the streak - the day is not over.
    """
    done = {l.day for l in habit.logs if l.status == "done"}
    today = now().date()
    floor = habit.created_at.date()
    count, cursor, misses = 0, today, 0
    while misses == 0 and cursor >= floor and cursor > today - timedelta(days=400):
        if _scheduled_on(habit, cursor):
            if cursor in done:
                count += 1
            elif cursor == today:
                pass  # still time left today
            else:
                misses = 1
        cursor -= timedelta(days=1)
    return count


def logged_today(habit: Habit) -> str | None:
    today = now().date()
    for l in habit.logs:
        if l.day == today:
            return l.status
    return None


def last_30(habit: Habit) -> str:
    """Compact 30-day strip, oldest left. Days before the habit existed are blank."""
    by_day = {l.day: l.status for l in habit.logs}
    today = now().date()
    born = habit.created_at.date()
    out = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        if d < born or not _scheduled_on(habit, d):
            out.append("·")
        elif by_day.get(d) == "done":
            out.append("▓")
        elif by_day.get(d) == "skip":
            out.append("░")
        elif d == today:
            out.append("?")
        else:
            out.append("✗")
    return "".join(out)


async def due_now(habit: Habit) -> bool:
    return habit.active and _scheduled_on(habit, now().date())
