from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db import Session, now, to_utc
from app.modules.todo.models import Todo


REPEATS = [("", "Never"), ("daily", "Every day"), ("weekly", "Every week"),
           ("monthly", "Every month"), ("yearly", "Every year")]


def _add_months(when: datetime, months: int) -> datetime:
    """Keep the day of month, clamped to the target month's length."""
    total = when.month - 1 + months
    year, month = when.year + total // 12, total % 12 + 1
    return when.replace(year=year, month=month, day=min(when.day, calendar.monthrange(year, month)[1]))


def next_due(when: datetime, repeat: str, tz: str = "UTC") -> datetime | None:
    """The next occurrence strictly in the future (skips missed ones).

    Stepping happens on the user's wall clock, so "every month at 09:00" stays
    09:00 for them across a daylight-saving change.
    """
    from app.db import to_local

    local = to_local(when, tz)
    step = {"daily": lambda d: d + timedelta(days=1),
            "weekly": lambda d: d + timedelta(days=7),
            "monthly": lambda d: _add_months(d, 1),
            "yearly": lambda d: _add_months(d, 12)}.get(repeat)
    if step is None:
        return None
    if repeat in ("monthly", "yearly"):
        # Count months from the ORIGINAL date: stepping from each clamped result
        # would drag "the 31st" down to the 28th forever after February.
        months = 1 if repeat == "monthly" else 12
        n = 1
        while n < 500:
            nxt = _add_months(local, months * n)
            if to_utc(nxt, tz) > now():
                return to_utc(nxt, tz)
            n += 1
        return None
    nxt, guard = step(local), 0
    while to_utc(nxt, tz) <= now() and guard < 500:
        nxt, guard = step(nxt), guard + 1
    return to_utc(nxt, tz)


async def add(user_id: int, text: str, due_at: datetime | None = None,
              remind_before: int = 0, repeat: str = "") -> Todo:
    async with Session() as s:
        item = Todo(user_id=user_id, text=text.strip()[:500], due_at=due_at,
                    remind_before=remind_before, repeat=repeat)
        s.add(item)
        await s.commit()
        return item


async def get(todo_id: int, user_id: int | None = None) -> Todo | None:
    """user_id guards against acting on someone else's row via a stale button."""
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item is None or (user_id is not None and item.user_id != user_id):
            return None
        return item


async def open_items(user_id: int) -> list[Todo]:
    """Open items, soonest due first, undated last."""
    async with Session() as s:
        rows = (await s.scalars(
            select(Todo).where(Todo.user_id == user_id, Todo.done.is_(False))
        )).all()
        return sorted(rows, key=lambda t: (t.due_at is None, t.due_at or datetime.max, t.id))


async def done_items(user_id: int, limit: int = 10) -> list[Todo]:
    async with Session() as s:
        return list(
            (
                await s.scalars(
                    select(Todo)
                    .where(Todo.user_id == user_id, Todo.done.is_(True))
                    .order_by(Todo.done_at.desc())
                    .limit(limit)
                )
            ).all()
        )


async def pending_lead() -> list[Todo]:
    """Across all users - the scheduler builds everyone's jobs."""
    async with Session() as s:
        return list((await s.scalars(select(Todo).where(
            Todo.done.is_(False),
            Todo.due_at.is_not(None),
            Todo.remind_before > 0,
            Todo.lead_notified_at.is_(None),
        ))).all())


async def mark_lead_notified(todo_id: int) -> None:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item:
            item.lead_notified_at = now()
            await s.commit()


async def set_lead(todo_id: int, minutes: int) -> Todo | None:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item is None:
            return None
        item.remind_before = minutes
        item.lead_notified_at = None  # re-arm
        await s.commit()
        return item


async def pending_reminders() -> list[Todo]:
    """Across all users. Open, dated, not yet announced.

    Deliberately includes items already past due: jobs live in memory, so a
    reminder whose moment passed while the bot was down would otherwise be
    lost forever. notified_at is what stops it being sent twice.

    No horizon: the schedule is only rebuilt on boot and on edits, so a
    30-day cut-off meant a reminder set further out never got registered.
    """
    async with Session() as s:
        return list(
            (
                await s.scalars(
                    select(Todo).where(
                        Todo.done.is_(False),
                        Todo.due_at.is_not(None),
                        Todo.notified_at.is_(None),
                    )
                )
            ).all()
        )


async def mark_notified(todo_id: int) -> None:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item:
            item.notified_at = now()
            await s.commit()


async def complete(todo_id: int, tz: str = "UTC") -> tuple[bool, Todo | None]:
    """Idempotent. Returns (changed, next occurrence if it repeats).

    Deliberately not a toggle: the Done button also lives on pushed reminders,
    and tapping a stale one must never reopen a finished task.
    """
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item is None or item.done:
            return False, None
        item.done = True
        item.done_at = now()
        nxt = None
        if item.repeat and item.due_at:
            when = next_due(item.due_at, item.repeat, tz)
            if when:
                nxt = Todo(user_id=item.user_id, text=item.text, due_at=when,
                           remind_before=item.remind_before, repeat=item.repeat)
                s.add(nxt)
        await s.commit()
        return True, nxt


async def set_repeat(todo_id: int, repeat: str) -> Todo | None:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item is None:
            return None
        item.repeat = repeat
        await s.commit()
        return item


async def reopen(todo_id: int) -> bool:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item is None or not item.done:
            return False
        item.done = False
        item.done_at = None
        await s.commit()
        return True


async def completed_since(user_id: int, since: datetime) -> int:
    async with Session() as s:
        rows = await s.scalars(select(Todo.id).where(
            Todo.user_id == user_id, Todo.done.is_(True), Todo.done_at >= since
        ))
        return len(rows.all())


async def add_many(user_id: int, texts: list[str]) -> list[Todo]:
    async with Session() as s:
        items = [Todo(user_id=user_id, text=t.strip()[:500]) for t in texts if t.strip()]
        s.add_all(items)
        await s.commit()
        return items


async def set_due(todo_id: int, when: datetime | None) -> Todo | None:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item is None:
            return None
        item.due_at = when
        item.notified_at = None  # re-arm: a new time means a new reminder
        item.lead_notified_at = None
        await s.commit()
        return item


async def rename(todo_id: int, text: str) -> None:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item:
            item.text = text.strip()[:500]
            await s.commit()


async def delete(todo_id: int) -> None:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item:
            await s.delete(item)
            await s.commit()


async def clear_done(user_id: int) -> int:
    async with Session() as s:
        rows = (await s.scalars(
            select(Todo).where(Todo.user_id == user_id, Todo.done.is_(True))
        )).all()
        for r in rows:
            await s.delete(r)
        await s.commit()
        return len(rows)
