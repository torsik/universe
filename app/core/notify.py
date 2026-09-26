"""Outgoing messages to the owner, with retries.

Everything the bot pushes on its own (reminders, nudges, the morning brief,
backups) goes through here. A single network blip at the moment a reminder
fires used to lose it silently.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter, TelegramServerError,
)

from app.config import settings
from app.db import now

log = logging.getLogger(__name__)

RETRY_PAUSES = (2, 5, 15)  # seconds between attempts
FAILURES: deque[tuple[datetime, str, str]] = deque(maxlen=10)


def record_failure(what: str, detail: str) -> None:
    """Kept in memory and shown on the Status screen, so a silent breakage
    doesn't stay silent until someone reads the logs."""
    FAILURES.append((now(), what, detail[:200]))
    log.error("delivery failure (%s): %s", what, detail)


async def _attempt(send, what: str, user_id: int | None = None) -> bool:
    for attempt, pause in enumerate((0, *RETRY_PAUSES)):
        if pause:
            await asyncio.sleep(pause)
        try:
            await send()
            if attempt:
                log.info("%s delivered on attempt %d", what, attempt + 1)
            return True
        except TelegramRetryAfter as e:  # flood control: it tells us how long
            log.warning("%s throttled, waiting %ss", what, e.retry_after)
            await asyncio.sleep(e.retry_after)
        except (TelegramNetworkError, TelegramServerError) as e:
            log.warning("%s attempt %d failed: %s", what, attempt + 1, e)
        except TelegramForbiddenError as e:
            # They blocked the bot or deleted the chat: stop pushing to them.
            log.info("%s: %s - marking user %s blocked", what, e, user_id)
            if user_id is not None:
                from app.core import users

                await users.mark_blocked(user_id)
            return False
        except TelegramAPIError as e:
            # Bad request and friends - retrying cannot help.
            record_failure(what, f"{type(e).__name__}: {e}")
            return False
    record_failure(what, "network unreachable after retries")
    return False


async def send(bot: Bot, chat_id: int, text: str, *, what: str = "message", **kwargs) -> bool:
    return await _attempt(lambda: bot.send_message(chat_id, text, **kwargs), what, chat_id)


async def send_document(bot: Bot, chat_id: int, document, *, what: str = "document", **kwargs) -> bool:
    return await _attempt(lambda: bot.send_document(chat_id, document, **kwargs), what, chat_id)


async def tell_admin(bot: Bot, text: str, *, what: str = "admin alert") -> bool:
    return await send(bot, settings.owner_id, text, what=what)
