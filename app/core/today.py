from __future__ import annotations

import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message

from app.core.i18n import t
from app.core.registry import discover
from app.core.ui import btn, kb
from app.core.users import User
from app.db import local_now

log = logging.getLogger(__name__)

FULL_DAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
}
MONTHS_GEN = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
           "августа", "сентября", "октября", "ноября", "декабря"],
}


def long_day(when, lang: str) -> str:
    days = FULL_DAYS.get(lang, FULL_DAYS["en"])
    months = MONTHS_GEN.get(lang, MONTHS_GEN["en"])
    if lang == "ru":
        return f"{days[when.weekday()]}, {when.day} {months[when.month - 1]}"
    return f"{days[when.weekday()]}, {when.day} {months[when.month - 1]}"


async def render_today(user: User) -> tuple[str, InlineKeyboardMarkup]:
    """Every module contributes a block; none of them knows about the others."""
    n = local_now(user.tz)
    head = t(user.lang, "today.title", date=long_day(n, user.lang))
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
        blocks.append(t(user.lang, "today.empty"))
    rows.append([btn(t(user.lang, "today.refresh"), "today:refresh")])
    return "\n\n".join(blocks), kb(*rows)


async def show_today(message: Message, state: FSMContext, user: User) -> None:
    text, markup = await render_today(user)
    await message.answer(text, reply_markup=markup)

