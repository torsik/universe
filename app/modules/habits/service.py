from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import Session, local_now, now
from app.modules.habits.models import Habit, HabitLog


async def all_habits(user_id: int | None = None, only_active: bool = False) -> list[Habit]:
    """user_id=None returns everyone's - only the scheduler needs that."""
    async with Session() as s:
        q = select(Habit).options(selectinload(Habit.logs)).order_by(Habit.hour, Habit.minute)
        if user_id is not None:
            q = q.where(Habit.user_id == user_id)
        if only_active:
            q = q.where(Habit.active.is_(True))
        return list((await s.scalars(q)).all())


async def get(habit_id: int, user_id: int | None = None) -> Habit | None:
    async with Session() as s:
        habit = await s.scalar(
            select(Habit).options(selectinload(Habit.logs)).where(Habit.id == habit_id)
        )
        if habit is None or (user_id is not None and habit.user_id != user_id):
            return None
        return habit


async def create(user_id: int, name: str, hour: int, minute: int, days: str, *, kind: str = "daily",
                 every_minutes: int = 0, end_hour: int = 18, end_minute: int = 0) -> Habit:
    async with Session() as s:
        h = Habit(user_id=user_id, name=name.strip()[:120], hour=hour, minute=minute, days=days, kind=kind,
                  every_minutes=every_minutes, end_hour=end_hour, end_minute=end_minute)
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


async def log(habit_id: int, status: str, day: date, ) -> None:
    """Mark a once-a-day habit. Idempotent: tapping Done twice is still one day."""
    async with Session() as s:
        existing = await s.scalar(
            select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.day == day)
        )
        if existing:
            existing.status = status
            existing.count = 1 if status == "done" else 0
            existing.logged_at = now()
        else:
            s.add(HabitLog(habit_id=habit_id, day=day, status=status,
                           count=1 if status == "done" else 0))
        await s.commit()


async def bump(habit_id: int, day: date, delta: int = 1) -> tuple[int, int]:
    """Add (or remove) one rep of an interval habit. Returns (count, target).

    The status is derived, so the streak and the history strip keep working
    unchanged: a day counts as done only once the target is reached.
    """
    async with Session() as s:
        habit = await s.scalar(
            select(Habit).options(selectinload(Habit.logs)).where(Habit.id == habit_id)
        )
        if habit is None:
            return 0, 0
        target = target_per_day(habit)
        row = await s.scalar(
            select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.day == day)
        )
        count = max(0, min(target, (row.count if row else 0) + delta))
        status = "done" if count >= target else ("partial" if count else "")
        if row is None:
            if not status:
                return 0, target
            s.add(HabitLog(habit_id=habit_id, day=day, status=status, count=count))
        elif not status:
            await s.delete(row)
        else:
            row.status, row.count, row.logged_at = status, count, now()
        await s.commit()
        return count, target


async def unlog(habit_id: int, day: date) -> None:
    async with Session() as s:
        row = await s.scalar(
            select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.day == day)
        )
        if row:
            await s.delete(row)
            await s.commit()


def occurrences(habit: Habit) -> list[tuple[int, int]]:
    """Every (hour, minute) the habit fires on a scheduled day."""
    if habit.kind != "interval" or habit.every_minutes <= 0:
        return [(habit.hour, habit.minute)]
    start = habit.hour * 60 + habit.minute
    end = habit.end_hour * 60 + habit.end_minute
    if end < start:
        end = start
    return [(m // 60, m % 60) for m in range(start, end + 1, habit.every_minutes)]


def target_per_day(habit: Habit) -> int:
    return len(occurrences(habit))


def window_label(habit: Habit) -> str:
    if habit.kind != "interval":
        return f"{habit.hour:02d}:{habit.minute:02d}"
    every = habit.every_minutes
    step = f"{every} min" if every < 60 else (f"{every // 60} h" if every % 60 == 0 else f"{every // 60} h {every % 60} min")
    return (f"every {step}, {habit.hour:02d}:{habit.minute:02d}–"
            f"{habit.end_hour:02d}:{habit.end_minute:02d}")


def progress(habit: Habit, day: date) -> tuple[int, int]:
    """(done so far, target) for that day."""
    target = target_per_day(habit)
    for l in habit.logs:
        if l.day == day:
            return (0 if l.status == "skip" else l.count), target
    return 0, target


def _scheduled_on(habit: Habit, day: date) -> bool:
    return str(day.weekday()) in habit.days


def streak(habit: Habit, today: date) -> int:
    """Consecutive scheduled days completed, walking back from today.

    Today not yet logged does not break the streak - the day is not over.
    """
    done = {l.day for l in habit.logs if l.status == "done"}
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


def logged_today(habit: Habit, today: date) -> str | None:
    for l in habit.logs:
        if l.day == today:
            return l.status
    return None


def last_30(habit: Habit, today: date) -> str:
    """Compact 30-day strip, oldest left. Days before the habit existed are blank."""
    by_day = {l.day: l.status for l in habit.logs}
    born = habit.created_at.date()
    out = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        if d < born or not _scheduled_on(habit, d):
            out.append("·")
        elif by_day.get(d) == "done":
            out.append("▓")
        elif by_day.get(d) == "partial":
            out.append("▒")
        elif by_day.get(d) == "skip":
            out.append("░")
        elif d == today:
            out.append("?")
        else:
            out.append("✗")
    return "".join(out)


def scheduled_today(habit: Habit, today: date) -> bool:
    return habit.active and _scheduled_on(habit, today)


def best_streak(habit: Habit, today: date) -> int:
    """Longest run of completed scheduled days, ever."""
    done = {l.day for l in habit.logs if l.status == "done"}
    best = run = 0
    day = habit.created_at.date()
    while day <= today:
        if _scheduled_on(habit, day):
            if day in done:
                run += 1
                best = max(best, run)
            elif day != today:  # an unfinished today doesn't break a run
                run = 0
        day += timedelta(days=1)
    return best


def rate_30(habit: Habit, today: date) -> int | None:
    """% of scheduled days done in the last 30 (today counts only once logged)."""
    by_day = {l.day: l.status for l in habit.logs}
    start = max(habit.created_at.date(), today - timedelta(days=29))
    scheduled = done = 0
    day = start
    while day <= today:
        if _scheduled_on(habit, day) and (day != today or day in by_day):
            scheduled += 1
            done += by_day.get(day) == "done"
        day += timedelta(days=1)
    return round(100 * done / scheduled) if scheduled else None


MILESTONES = (7, 30, 100, 365)


def milestone(streak: int) -> str | None:
    """Worth celebrating in the reply to a check-in."""
    return f"🏆 {streak} days in a row!" if streak in MILESTONES else None


def week_bounds(today: date, offset: int = 0) -> tuple[date, date]:
    """Monday..Sunday of the current week, or `offset` weeks back."""
    monday = today - timedelta(days=today.weekday() + 7 * offset)
    return monday, monday + timedelta(days=6)


def week_stats(habit: Habit, start: date, end: date, today: date) -> tuple[int, int]:
    """(done, scheduled so far) between two dates - the future isn't counted."""
    by_day = {l.day: l.status for l in habit.logs}
    done = scheduled = 0
    day = max(start, habit.created_at.date())
    while day <= min(end, today):
        if _scheduled_on(habit, day):
            scheduled += 1
            done += by_day.get(day) == "done"
        day += timedelta(days=1)
    return done, scheduled


def next_reminder(habit: Habit, tz: str) -> datetime | None:
    """The next fire time, as the owner's wall clock."""
    if not habit.active:
        return None
    local = local_now(tz)
    for i in range(8):
        day = local.date() + timedelta(days=i)
        if not _scheduled_on(habit, day):
            continue
        for hour, minute in occurrences(habit):
            at = datetime(day.year, day.month, day.day, hour, minute)
            if at > local:
                return at
    return None
