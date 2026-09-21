from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.registry import discover

log = logging.getLogger(__name__)

MENU_CB = "menu"


async def safe_edit(cq: CallbackQuery, text: str, reply_markup=None) -> None:
    """Edit the message behind a callback, tolerating the ways that fails.

    Buttons also arrive on pushed reminders, which may be older than the 48h
    edit window or identical to what is already displayed. Neither should
    surface as an error, and neither should leave the button spinning.
    """
    if cq.message is None:  # too old for Telegram to hand back
        await cq.bot.send_message(cq.from_user.id, text, reply_markup=reply_markup)
        return
    try:
        await cq.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        log.info("edit failed (%s), sending instead", e)
        try:
            await cq.message.answer(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            log.warning("could not deliver update for callback %s", cq.data)


def main_menu() -> InlineKeyboardMarkup:
    """Built from the registry - a new module appears here automatically."""
    kb = InlineKeyboardBuilder()
    for mod in discover():
        kb.button(text=mod.title, callback_data=f"open:{mod.name}")
    kb.adjust(1)
    return kb.as_markup()


def back_row(module: str | None = None) -> list[InlineKeyboardButton]:
    row = [InlineKeyboardButton(text="🏠 Menu", callback_data=MENU_CB)]
    if module:
        row.insert(0, InlineKeyboardButton(text="◀️ Back", callback_data=f"open:{module}"))
    return row


def cancel_kb(module: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_row(module)])
