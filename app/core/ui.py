from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.core.registry import ButtonFn, discover

log = logging.getLogger(__name__)

TODAY_BTN = "☀️ Today"
NOOP = "noop"


def main_keyboard() -> ReplyKeyboardMarkup:
    """The always-visible keyboard at the bottom of the chat.

    Built from the registry, so a new module's buttons appear automatically.
    """
    labels = [TODAY_BTN] + [label for m in discover() for label, _ in m.buttons]
    rows = [labels[i : i + 2] for i in range(0, len(labels), 2)]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Type a task to add it…",
    )


def button_actions() -> dict[str, ButtonFn]:
    from app.core.today import show_today

    actions: dict[str, ButtonFn] = {TODAY_BTN: show_today}
    for mod in discover():
        actions.update(dict(mod.buttons))
    return actions


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


def cancel_kb(back_cb: str, label: str = "✖️ Cancel") -> InlineKeyboardMarkup:
    return kb([btn(label, back_cb)])


def progress_bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return ""
    filled = round(width * done / total)
    return "▰" * filled + "▱" * (width - filled)


def clip(text: str, n: int = 32) -> str:
    """Button labels have no wrapping - keep them short."""
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


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
