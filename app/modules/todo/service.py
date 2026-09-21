from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.db import Session, now
from app.modules.todo.models import Todo


async def add(text: str, due_at: datetime | None = None) -> Todo:
    async with Session() as s:
        item = Todo(text=text.strip()[:500], due_at=due_at)
        s.add(item)
        await s.commit()
        return item


async def get(todo_id: int) -> Todo | None:
    async with Session() as s:
        return await s.get(Todo, todo_id)


async def open_items() -> list[Todo]:
    """Open items, soonest due first, undated last."""
    async with Session() as s:
        rows = (await s.scalars(select(Todo).where(Todo.done.is_(False)))).all()
        return sorted(rows, key=lambda t: (t.due_at is None, t.due_at or datetime.max, t.id))


async def done_items(limit: int = 10) -> list[Todo]:
    async with Session() as s:
        return list(
            (
                await s.scalars(
                    select(Todo)
                    .where(Todo.done.is_(True))
                    .order_by(Todo.done_at.desc())
                    .limit(limit)
                )
            ).all()
        )


async def pending_reminders() -> list[Todo]:
    """Open, dated, not yet announced.

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


async def complete(todo_id: int) -> bool:
    """Idempotent. Returns False if it was already done (or is gone).

    Deliberately not a toggle: the Done button also lives on pushed reminders,
    and tapping a stale one must never reopen a finished task.
    """
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item is None or item.done:
            return False
        item.done = True
        item.done_at = now()
        await s.commit()
        return True


async def set_due(todo_id: int, when: datetime | None) -> Todo | None:
    async with Session() as s:
        item = await s.get(Todo, todo_id)
        if item is None:
            return None
        item.due_at = when
        item.notified_at = None  # re-arm: a new time means a new reminder
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


async def clear_done() -> int:
    async with Session() as s:
        rows = (await s.scalars(select(Todo).where(Todo.done.is_(True)))).all()
        for r in rows:
            await s.delete(r)
        await s.commit()
        return len(rows)
