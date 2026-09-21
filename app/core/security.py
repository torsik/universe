from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings

log = logging.getLogger(__name__)


class OwnerOnlyMiddleware(BaseMiddleware):
    """Single-user bot: anyone who is not OWNER_ID is silently dropped.

    Outer middleware, so unauthorised updates never reach a handler or the FSM.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id != settings.owner_id:
            if user is not None:
                log.warning("blocked update from uid=%s (@%s)", user.id, user.username)
            if isinstance(event, CallbackQuery):
                await event.answer("Not your bot.", show_alert=True)
            elif isinstance(event, Message):
                pass  # stay quiet - do not confirm the bot exists
            return None
        return await handler(event, data)
