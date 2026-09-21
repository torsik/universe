from __future__ import annotations

import html

from app.core.dates import mask_to_cron
from app.core.registry import ModuleSpec
from app.core.scheduler import ScheduleContext
from app.modules.habits import handlers, service


async def schedule(ctx: ScheduleContext) -> None:
    for h in await service.all_habits(only_active=True):
        ctx.cron(
            f"nudge:{h.id}",
            handlers.fire_nudge,
            hour=h.hour,
            minute=h.minute,
            day_of_week=mask_to_cron(h.days),
            bot=ctx.bot,
            habit_id=h.id,
        )


async def digest() -> str | None:
    habits = [h for h in await service.all_habits(only_active=True) if await service.due_now(h)]
    if not habits:
        return None
    lines = ["🔁 <b>Habits today</b>"]
    for h in habits:
        mark = {"done": "✅", "skip": "⏭"}.get(service.logged_today(h), "▫️")
        lines.append(f"  {mark} {html.escape(h.name)} <i>({h.hour:02d}:{h.minute:02d})</i>")
    return "\n".join(lines)


MODULE = ModuleSpec(
    name="habits",
    title="🔁 Habits",
    router=handlers.router,
    order=20,
    schedule=schedule,
    digest=digest,
)
