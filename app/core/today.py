from __future__ import annotations

import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message

from app.core.dates import MONTHS
from app.core.registry import discover
from app.core.ui import btn, kb
from app.core.users import User
from app.db import local_now

log = logging.getLogger(__name__)

FULL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


async def render_today(user: User) -> tuple[str, InlineKeyboardMarkup]:
    """Every module contributes a block; none of them knows about the others."""
    n = local_now(user.tz)
    head = f"☀️ <b>Today</b> · {FULL_DAYS[n.weekday()]}, {n.day} {MONTHS[n.month - 1]}"
    blocks, rows = [head], []
    for mod in discover():
        if mod.digest is None:
            continue
        try:
            d = await mod.digest(user)
        except Exception:
            log.exception("digest failed for %s", mod.name)
            continue
        if d:
            blocks.append(d.text)
            rows += [[b] for b in d.buttons]
    if len(blocks) == 1:
        blocks.append("Nothing planned. Enjoy the day 🌿")
    rows.append([btn("🔄 Refresh", "today:refresh")])
    return "\n\n".join(blocks), kb(*rows)


async def show_today(message: Message, state: FSMContext, user: User) -> None:
    text, markup = await render_today(user)
    await message.answer(text, reply_markup=markup)

