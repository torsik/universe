from __future__ import annotations

import html

from app.core.dates import mask_to_cron
from app.core.registry import Digest, ModuleSpec
from app.core.scheduler import ScheduleContext
from app.core.ui import btn, clip, progress_bar
from app.core.users import User
from app.db import local_today, now
from app.modules.habits import handlers, service
from app.modules.habits.handlers import HABITS_BTN, MARK, M


async def schedule(ctx: ScheduleContext) -> None:
    """Every user's habits, each on their own wall clock."""
    from app.core import users

    zones = {u.id: u.tz for u in await users.all_users()}
    for user_id, tz in zones.items():
        # Sunday evening report, 19:00 where that person lives
        ctx.cron(f"weekly:{user_id}", _weekly, hour=SUNDAY_REPORT_HOUR, minute=0,
                 day_of_week="sun", tz=tz, bot=ctx.bot, user_id=user_id)

    for h in await service.all_habits(only_active=True):
        tz = zones.get(h.user_id)
        if tz is None:  # blocked or deleted owner: no reminders
            continue
        # One job per occurrence: an hourly habit gets a job for each hour of
        # its window, which keeps arbitrary intervals (30 min, 90 min) exact.
        for hour, minute in service.occurrences(h):
            ctx.cron(
                f"nudge:{h.id}:{hour:02d}{minute:02d}",
                handlers.fire_nudge,
                hour=hour,
                minute=minute,
                day_of_week=mask_to_cron(h.days),
                tz=tz,
                bot=ctx.bot,
                habit_id=h.id,
            )
        if h.snooze_until and h.snooze_until > now():
            ctx.once(f"snooze:{h.id}", handlers.fire_nudge, run_at=h.snooze_until, bot=ctx.bot, habit_id=h.id)


SUNDAY_REPORT_HOUR = 19


async def _weekly(bot, user_id: int) -> None:
    await handlers.send_weekly_report(bot, user_id)


async def digest(user: User) -> Digest | None:
    habits = await service.all_habits(user.id, only_active=True)
    if not habits:
        return None
    today = local_today(user.tz)
    todays = [h for h in habits if service.scheduled_today(h, today)]
    if not todays:
        return Digest("🔁 <b>Habits</b>\nRest day. Nothing scheduled 🌿")

    done = sum(service.logged_today(h, today) == "done" for h in todays)
    lines = [f"🔁 <b>Habits</b>  {progress_bar(done, len(todays), 8)} {done}/{len(todays)}"]
    buttons = []
    for h in todays:
        status = service.logged_today(h, today)
        if h.kind == "interval":
            count, target = service.progress(h, today)
            mark = "✅" if count >= target else ("⏭" if status == "skip" else "▫️")
            lines.append(f"{mark} {html.escape(h.name)} · <b>{count}/{target}</b>")
            if count < target and status != "skip":
                buttons.append(btn(f"➕ {clip(h.name, 20)} {count + 1}/{target}", f"{M}:tdone:{h.id}"))
            continue
        when = "" if status else f" · <i>{h.hour:02d}:{h.minute:02d}</i>"
        lines.append(f"{MARK.get(status, '▫️')} {html.escape(h.name)}{when}")
        if not status:
            buttons.append(btn(f"✔️ Done: {clip(h.name, 24)}", f"{M}:tdone:{h.id}"))
    if done == len(todays):
        lines.append("🎉 All done!")
    return Digest("\n".join(lines), buttons)


MODULE = ModuleSpec(
    name="habits",
    title="Habits",
    router=handlers.router,
    order=20,
    buttons=[(HABITS_BTN, handlers.show_habits)],
    schedule=schedule,
    digest=digest,
)
