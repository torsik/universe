from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger


log = logging.getLogger(__name__)

SWEEP_MINUTES = 15


class ScheduleContext:
    """Handed to a module's schedule() so it can declare its jobs.

    Job ids are namespaced "<module>:<key>" so a refresh can wipe exactly one
    module's jobs without touching anyone else's.
    """

    def __init__(self, bot: Bot, scheduler: AsyncIOScheduler, module: str) -> None:
        self.bot = bot
        self.module = module
        self._sched = scheduler

    def _jid(self, key: str) -> str:
        return f"{self.module}:{key}"

    def cron(self, key: str, func, *, hour: int, minute: int, day_of_week: str = "*",
             tz: str | None = None, **kwargs):
        """hour/minute are wall clock in `tz` - each user gets their own."""
        from app.db import zone

        self._sched.add_job(
            func,
            CronTrigger(hour=hour, minute=minute, day_of_week=day_of_week,
                        timezone=zone(tz) if tz else timezone.utc),
            id=self._jid(key),
            kwargs=kwargs,
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )

    def once(self, key: str, func, *, run_at: datetime, **kwargs):
        """run_at is naive UTC, like every timestamp in the database."""
        from app.db import now

        if run_at <= now():
            return
        self._sched.add_job(
            func,
            DateTrigger(run_date=run_at, timezone=timezone.utc),
            id=self._jid(key),
            kwargs=kwargs,
            replace_existing=True,
            misfire_grace_time=3600,
        )


class Scheduler:
    """Jobs are derived state, never persisted.

    APScheduler runs in-memory and the whole schedule is rebuilt from the DB at
    boot and after any edit. That keeps one source of truth (the tables), and
    avoids pickled jobs surviving a restart pointing at habits you deleted.
    """

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._sched = AsyncIOScheduler(timezone=timezone.utc)
        self._providers: dict[str, object] = {}

    def register(self, module: str, fn) -> None:
        self._providers[module] = fn

    async def refresh(self, module: str | None = None) -> None:
        targets = [module] if module else list(self._providers)
        for name in targets:
            fn = self._providers.get(name)
            if fn is None:
                continue
            for job in self._sched.get_jobs():
                if job.id.startswith(f"{name}:"):
                    job.remove()
            try:
                await fn(ScheduleContext(self.bot, self._sched, name))
            except Exception:
                log.exception("failed to build schedule for module %s", name)
        log.info("schedule rebuilt (%s): %d jobs", module or "all", len(self._sched.get_jobs()))

    async def _sweep(self) -> None:
        """Re-derive every module's jobs from the database.

        Jobs are one-shot and live in memory. If a reminder fired but could not
        be delivered, its "sent" flag stays unset and the job is gone - without
        this sweep nothing would put it back until a restart. Costs ~20 ms.
        """
        for name in list(self._providers):
            if name != "core":  # never rebuild the job we are running inside
                await self.refresh(name)

    def _on_job_error(self, event) -> None:
        """A background job raised. Log it, remember it for the Status screen,
        and try to tell the owner."""
        from app.core import notify

        detail = f"{type(event.exception).__name__}: {event.exception}"
        notify.record_failure(f"job {event.job_id}", detail)
        try:
            asyncio.get_running_loop().create_task(
                notify.tell_admin(
                    self.bot,
                    f"⚠️ <b>A background job failed</b>\n<code>{event.job_id}</code>\n{detail}",
                    what="job failure alert",
                )
            )
        except RuntimeError:
            pass  # no loop (shutdown) - the log and Status screen still have it

    def start(self) -> None:
        self._sched.add_job(
            self._sweep,
            IntervalTrigger(minutes=SWEEP_MINUTES),
            id="core:sweep",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._sched.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        self._sched.start()

    def shutdown(self) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=False)

    @property
    def jobs(self):
        return self._sched.get_jobs()
