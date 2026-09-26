from __future__ import annotations

import html
from datetime import timedelta

from app.core.dates import relative
from app.core.registry import Digest, ModuleSpec
from app.core.scheduler import ScheduleContext
from app.core.ui import btn, clip
from app.core.users import User
from app.db import local_now, now, to_local, to_utc
from app.modules.todo import handlers, service
from app.modules.todo.handlers import M, NEW_TASK_BTN, TASKS_BTN, _bucket

TODAY_LIMIT = 6


async def schedule(ctx: ScheduleContext) -> None:
    """One-shot job per dated open item, for every user, rebuilt each time.

    Deadlines are absolute moments, so these jobs live in UTC and need no
    per-user zone. Anything already overdue and unannounced fires shortly
    after boot rather than being silently skipped.
    """
    from app.core import users

    live = {u.id for u in await users.all_users()}
    catch_up = now() + timedelta(seconds=30)
    for item in await service.pending_reminders():
        if item.user_id not in live:
            continue
        ctx.once(
            f"due:{item.id}",
            handlers.fire_reminder,
            run_at=max(item.due_at, catch_up),
            bot=ctx.bot,
            todo_id=item.id,
        )
    for item in await service.pending_lead():
        if item.user_id not in live:
            continue
        if item.due_at <= now():
            continue  # the deadline push covers it
        ctx.once(
            f"lead:{item.id}",
            handlers.fire_lead,
            run_at=max(item.due_at - timedelta(minutes=item.remind_before), catch_up),
            bot=ctx.bot,
            todo_id=item.id,
        )


async def digest(user: User) -> Digest:
    items = await service.open_items(user.id)
    midnight = local_now(user.tz).replace(hour=0, minute=0, second=0, microsecond=0)
    done_today = await service.completed_since(user.id, to_utc(midnight, user.tz))
    due = [i for i in items if _bucket(i, user.tz) in ("overdue", "today")]

    lines = ["📝 <b>Tasks</b>"]
    for i in due[:TODAY_LIMIT]:
        if _bucket(i, user.tz) == "overdue":
            lines.append(f"⚠️ {html.escape(i.text)} · <i>{relative(i.due_at)}</i>")
        else:
            lines.append(f"• {html.escape(i.text)} · <i>{to_local(i.due_at, user.tz):%H:%M}</i>")
    if len(due) > TODAY_LIMIT:
        lines.append(f"<i>…and {len(due) - TODAY_LIMIT} more</i>")
    if not due:
        lines.append("Nothing due today 🎉")

    extras = []
    if done_today:
        extras.append(f"✨ {done_today} done today")
    if len(items) > len(due):
        extras.append(f"{len(items) - len(due)} more on your list")
    if extras:
        lines.append(f"<i>{' · '.join(extras)}</i>")

    buttons = [
        btn(f"{'⚠️' if _bucket(i, user.tz) == 'overdue' else '☀️'} {clip(i.text)}", f"{M}:open:{i.id}")
        for i in due[:TODAY_LIMIT]
    ]
    return Digest("\n".join(lines), buttons)


MODULE = ModuleSpec(
    name="todo",
    title="Tasks",
    router=handlers.router,
    order=10,
    buttons=[(NEW_TASK_BTN, handlers.ask_new_task), (TASKS_BTN, handlers.show_tasks)],
    schedule=schedule,
    digest=digest,
    fallback=handlers.fallback,
)
