from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.config import settings

log = logging.getLogger(__name__)


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

    def cron(self, key: str, func, *, hour: int, minute: int, day_of_week: str = "*", **kwargs):
        self._sched.add_job(
            func,
            CronTrigger(hour=hour, minute=minute, day_of_week=day_of_week, timezone=settings.tzinfo),
            id=self._jid(key),
            kwargs=kwargs,
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )

    def once(self, key: str, func, *, run_at: datetime, **kwargs):
        from app.db import now

        if run_at <= now():  # configured TZ, not the host's
            return
        self._sched.add_job(
            func,
            DateTrigger(run_date=run_at, timezone=settings.tzinfo),
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
        self._sched = AsyncIOScheduler(timezone=settings.tzinfo)
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

    def start(self) -> None:
        self._sched.start()

    def shutdown(self) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=False)

    @property
    def jobs(self):
        return self._sched.get_jobs()
