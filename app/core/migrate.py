"""One-off data migrations, recorded in the meta table so they run once."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import Meta, Session, now, to_utc

log = logging.getLogger(__name__)

LEGACY_UTC = "legacy_local_to_utc"

# Columns that hold an absolute moment and therefore move to UTC.
TODO_STAMPS = ("due_at", "created_at", "done_at", "notified_at", "lead_notified_at")
HABIT_STAMPS = ("created_at", "snooze_until")


async def run_migrations() -> None:
    await _legacy_local_to_utc()


async def _legacy_local_to_utc() -> None:
    """Before multi-user, timestamps were stored in the server's local zone and
    rows had no owner. Shift them to UTC and hand them to the admin, once.

    Without this every existing deadline would drift by the UTC offset.
    """
    from app.core.users import User
    from app.modules.habits.models import Habit
    from app.modules.todo.models import Todo

    async with Session() as s:
        if await s.get(Meta, LEGACY_UTC):
            return

        todos = list((await s.scalars(select(Todo))).all())
        habits = list((await s.scalars(select(Habit).options(selectinload(Habit.logs)))).all())

        if todos or habits:
            owner = await s.get(User, settings.owner_id)
            if owner is None:
                owner = User(id=settings.owner_id, tz=settings.tz, onboarded=1)
                s.add(owner)
            log.warning(
                "migrating %d task(s) and %d habit(s) to UTC, owner=%s, zone=%s",
                len(todos), len(habits), settings.owner_id, settings.tz,
            )
            for item in todos:
                if not item.user_id:
                    item.user_id = settings.owner_id
                for field in TODO_STAMPS:
                    value = getattr(item, field)
                    if value:
                        setattr(item, field, to_utc(value, settings.tz))
            for habit in habits:
                if not habit.user_id:
                    habit.user_id = settings.owner_id
                for field in HABIT_STAMPS:
                    value = getattr(habit, field)
                    if value:
                        setattr(habit, field, to_utc(value, settings.tz))
                for entry in habit.logs:  # `day` stays a local calendar date
                    if entry.logged_at:
                        entry.logged_at = to_utc(entry.logged_at, settings.tz)

        s.add(Meta(key=LEGACY_UTC, value=now().isoformat(timespec="seconds")))
        await s.commit()
