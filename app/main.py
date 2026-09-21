from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

from app.config import settings
from app.core import common
from app.core.registry import discover
from app.core.scheduler import Scheduler
from app.core.security import OwnerOnlyMiddleware
from app.db import init_db

log = logging.getLogger("universe")


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    modules = discover()
    await init_db()
    log.info("loaded modules: %s", ", ".join(m.name for m in modules))

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Outer: unauthorised updates never reach a handler or touch the FSM.
    dp.message.outer_middleware(OwnerOnlyMiddleware())
    dp.callback_query.outer_middleware(OwnerOnlyMiddleware())

    scheduler = Scheduler(bot)
    dp["scheduler"] = scheduler  # injected into any handler that asks for it

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        """Log, tell the owner, and keep polling.

        Without this an exception inside a handler is swallowed and the user is
        left looking at a button that never resolves.
        """
        log.exception("unhandled error: %s", event.exception)
        update = event.update
        chat_id = None
        if update.message:
            chat_id = update.message.chat.id
        elif update.callback_query:
            try:  # the handler may already have answered it
                await update.callback_query.answer("Something broke - check the logs.", show_alert=True)
            except Exception:
                pass
        if chat_id:
            try:
                await bot.send_message(chat_id, "\u26a0\ufe0f Something broke. It is in the logs.")
            except Exception:
                log.exception("could not report the error to the owner")
        return True

    dp.include_router(common.router)
    for mod in modules:
        dp.include_router(mod.router)
        if mod.schedule:
            scheduler.register(mod.name, mod.schedule)

    await scheduler.refresh()
    scheduler.start()

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="menu", description="Main menu"),
                BotCommand(command="today", description="Today at a glance"),
                BotCommand(command="add", description="Quick-add a to-do"),
                BotCommand(command="jobs", description="Show scheduled jobs"),
                BotCommand(command="cancel", description="Cancel current action"),
            ]
        )
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("polling as @%s", (await bot.me()).username)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
