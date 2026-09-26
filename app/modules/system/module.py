from __future__ import annotations

from app.core.registry import ModuleSpec
from app.core.scheduler import ScheduleContext
from app.modules.system import handlers


async def schedule(ctx: ScheduleContext) -> None:
    # Server-side: the file stays on the volume, nothing is pushed to a chat.
    ctx.cron("backup", handlers.daily_backup, hour=4, minute=30, bot=ctx.bot)


MODULE = ModuleSpec(
    name="system",
    title="More",
    router=handlers.router,
    order=90,
    buttons=[(handlers.MORE_BTN, handlers.show_more)],
    schedule=schedule,
)
