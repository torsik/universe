from __future__ import annotations

import html

from app.core.registry import ModuleSpec
from app.core.scheduler import ScheduleContext
from app.modules.todo import handlers, service


async def schedule(ctx: ScheduleContext) -> None:
    """One-shot job per dated open item, rebuilt from the table every time.

    Anything already overdue and unannounced fires shortly after boot rather
    than being silently skipped.
    """
    from datetime import timedelta

    from app.db import now

    catch_up = now() + timedelta(seconds=30)
    for item in await service.pending_reminders():
        ctx.once(
            f"due:{item.id}",
            handlers.fire_reminder,
            run_at=max(item.due_at, catch_up),
            bot=ctx.bot,
            todo_id=item.id,
        )


async def digest() -> str | None:
    items = await service.open_items()
    if not items:
        return None
    from app.db import now

    today = now().date()
    due_today = [i for i in items if i.due_at and i.due_at.date() <= today]
    lines = [f"📝 <b>To-do</b> - {len(items)} open"]
    for i in due_today[:5]:
        lines.append(f"  • {html.escape(i.text)} <i>({i.due_at:%H:%M})</i>")
    return "\n".join(lines)


MODULE = ModuleSpec(
    name="todo",
    title="📝 To-Do",
    router=handlers.router,
    order=10,
    schedule=schedule,
    digest=digest,
)
