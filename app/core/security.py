from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


log = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=1)


class StaleMessageMiddleware(BaseMiddleware):
    """Drop messages that sat in Telegram's queue for too long.

    Pending updates are no longer discarded at startup, so a tap made while the
    bot was down still arrives. But after a long outage the whole backlog would
    replay at once, turning day-old texts into new tasks - so anything older
    than MAX_AGE is ignored. Button presses are exempt: they only redraw a
    screen, and a callback carries no timestamp of its own.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.date:
            age = datetime.now(timezone.utc) - event.date
            if age > MAX_AGE:
                log.info("ignoring message from %s (%s old)", event.date, age)
                return None
        return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    """Registers or loads the person behind every update.

    Replaces the old single-owner gate: anyone may use the bot until
    MAX_USERS is reached, and each handler is handed its own `user`.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from app.core import users

        tg = data.get("event_from_user")
        if tg is None or tg.is_bot:
            return None

        user = await users.get(tg.id)
        if user is None:
            from app.core.i18n import pick_lang

            user, created = await users.register(
                tg.id, tg.first_name or "", tg.username or "", pick_lang(tg.language_code)
            )
            if user is None:  # the bot is full
                from app.core.i18n import t

                lang = pick_lang(tg.language_code)
                if isinstance(event, CallbackQuery):
                    await event.answer(t(lang, "full.short"), show_alert=True)
                elif isinstance(event, Message):
                    await event.answer(t(lang, "full", id=tg.id))
                log.warning("turned away user %s (@%s)", tg.id, tg.username)
                return None
        elif isinstance(event, Message):
            await users.touch(user.id)

        data["user"] = user
        return await handler(event, data)
