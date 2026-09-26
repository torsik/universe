from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.core.today import render_today
from app.core.ui import NOOP, btn, button_actions, kb, main_keyboard, safe_edit
from app.core.users import User

router = Router(name="core")

# A short list covering most users; anything else can be typed.
ZONES = [
    ("Kyiv", "Europe/Kyiv"), ("Warsaw", "Europe/Warsaw"), ("Berlin", "Europe/Berlin"),
    ("London", "Europe/London"), ("Dublin", "Europe/Dublin"), ("Lisbon", "Europe/Lisbon"),
    ("Tbilisi", "Asia/Tbilisi"), ("Dubai", "Asia/Dubai"), ("Almaty", "Asia/Almaty"),
    ("New York", "America/New_York"), ("Los Angeles", "America/Los_Angeles"),
    ("Bangkok", "Asia/Bangkok"), ("Tokyo", "Asia/Tokyo"), ("Sydney", "Australia/Sydney"),
]


class Onboarding(StatesGroup):
    zone = State()


def zone_kb() -> InlineKeyboardMarkup:
    cells = [btn(label, f"tz:set:{name}") for label, name in ZONES]
    rows = [cells[i : i + 3] for i in range(0, len(cells), 3)]
    rows.append([btn("⌨️ Type my timezone", "tz:type")])
    return kb(*rows)


ZONE_PROMPT = (
    "🌍 <b>Which timezone are you in?</b>\n"
    "<i>Reminders and deadlines follow it.</i>"
)


WELCOME = (
    "👋 <b>Hi! I'm your personal assistant.</b>\n\n"
    "📝 <b>Tasks</b>: just type anything and I'll add it. Give it a due time "
    "and I'll remind you.\n"
    "🔁 <b>Habits</b>: daily check-ins with reminders and streaks.\n"
    "☀️ <b>Today</b>: everything for today on one screen.\n\n"
    "Use the buttons below 👇"
)


class KeyboardButtonPressed(Filter):
    """Matches a label from the bottom keyboard and injects its action.

    Registered in the core router, which is included first, so a button press
    wins over any half-finished dialog instead of being swallowed as input.
    """

    async def __call__(self, message: Message) -> bool | dict[str, Any]:
        action = button_actions().get(message.text or "")
        return {"action": action} if action else False


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer(WELCOME, reply_markup=main_keyboard())
    if not user.onboarded:
        await message.answer(ZONE_PROMPT, reply_markup=zone_kb())


@router.callback_query(F.data.startswith("tz:set:"))
async def cb_set_zone(cq: CallbackQuery, user: User) -> None:
    from app.core import users

    name = cq.data.split(":", 2)[2]
    await users.update(user.id, tz=name, onboarded=1)
    await safe_edit(cq, f"🌍 Timezone set to <b>{name}</b>.\nEverything follows your local clock now.")
    await cq.answer("Saved")


@router.callback_query(F.data == "tz:type")
async def cb_type_zone(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Onboarding.zone)
    await safe_edit(
        cq,
        "⌨️ <b>Type your timezone</b>\n<i>Like</i> <code>Europe/Kyiv</code> <i>or</i> <code>Asia/Tokyo</code>",
    )
    await cq.answer()


@router.message(Onboarding.zone)
async def typed_zone(message: Message, state: FSMContext, user: User) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from app.core import users

    name = (message.text or "").strip()
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        await message.answer("🤔 I don't know that one. Try <code>Europe/Kyiv</code>, or pick from the list.",
                             reply_markup=zone_kb())
        return
    await state.clear()
    await users.update(user.id, tz=name, onboarded=1)
    await message.answer(f"🌍 Timezone set to <b>{name}</b>.", reply_markup=main_keyboard())


@router.message(KeyboardButtonPressed())
async def on_keyboard(message: Message, state: FSMContext, action, user: User) -> None:
    await state.clear()
    await action(message, state, user)


@router.callback_query(F.data == "today:refresh")
async def today_refresh(cq: CallbackQuery, user: User) -> None:
    text, markup = await render_today(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer("Updated")


@router.callback_query(F.data == NOOP)
async def cb_noop(cq: CallbackQuery) -> None:
    await cq.answer()


# Included after everything else (see main.build): catches taps on buttons from
# older versions of the bot still sitting in the chat, which no handler knows.
stale = Router(name="stale-buttons")


@stale.callback_query()
async def cb_stale(cq: CallbackQuery) -> None:
    await cq.answer("This button is from an older version. Use the buttons below 👇", show_alert=True)
