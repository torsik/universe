from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.core.i18n import LANG_NAMES, LANGS, t
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


def lang_kb() -> InlineKeyboardMarkup:
    return kb([btn(LANG_NAMES[code], f"lang:set:{code}") for code in LANGS])


def zone_kb(lang: str) -> InlineKeyboardMarkup:
    cells = [btn(label, f"tz:set:{name}") for label, name in ZONES]
    rows = [cells[i : i + 3] for i in range(0, len(cells), 3)]
    rows.append([btn(t(lang, "zone.type"), "tz:type")])
    return kb(*rows)


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
    await message.answer(t(user.lang, "welcome"), reply_markup=main_keyboard(user.lang))
    if not user.onboarded:
        # Language first: the zone question should already be in their language.
        await message.answer(t(user.lang, "lang.prompt"), reply_markup=lang_kb())


@router.callback_query(F.data.startswith("lang:set:"))
async def cb_set_lang(cq: CallbackQuery, user: User) -> None:
    from app.core import users

    code = cq.data.split(":")[2]
    if code not in LANGS:
        await cq.answer()
        return
    await users.update(user.id, lang=code)
    await safe_edit(cq, t(code, "lang.set", name=LANG_NAMES[code]))
    await cq.message.answer(t(code, "welcome"), reply_markup=main_keyboard(code))
    if not user.onboarded:
        await cq.message.answer(t(code, "zone.prompt"), reply_markup=zone_kb(code))
    await cq.answer()


@router.callback_query(F.data.startswith("tz:set:"))
async def cb_set_zone(cq: CallbackQuery, user: User) -> None:
    from app.core import users

    name = cq.data.split(":", 2)[2]
    await users.update(user.id, tz=name, onboarded=1)
    await safe_edit(cq, t(user.lang, "zone.set", tz=name))
    await cq.answer(t(user.lang, "saved"))


@router.callback_query(F.data == "tz:type")
async def cb_type_zone(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.set_state(Onboarding.zone)
    await safe_edit(cq, t(user.lang, "zone.type_prompt"))
    await cq.answer()


@router.message(Onboarding.zone)
async def typed_zone(message: Message, state: FSMContext, user: User) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from app.core import users

    name = (message.text or "").strip()
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        await message.answer(t(user.lang, "zone.unknown"), reply_markup=zone_kb(user.lang))
        return
    await state.clear()
    await users.update(user.id, tz=name, onboarded=1)
    await message.answer(t(user.lang, "zone.set", tz=name), reply_markup=main_keyboard(user.lang))


@router.message(KeyboardButtonPressed())
async def on_keyboard(message: Message, state: FSMContext, action, user: User) -> None:
    await state.clear()
    await action(message, state, user)


@router.callback_query(F.data == "today:refresh")
async def today_refresh(cq: CallbackQuery, user: User) -> None:
    text, markup = await render_today(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "today.updated"))


@router.callback_query(F.data == NOOP)
async def cb_noop(cq: CallbackQuery) -> None:
    await cq.answer()


# Included after everything else (see main.build): catches taps on buttons from
# older versions of the bot still sitting in the chat, which no handler knows.
stale = Router(name="stale-buttons")


@stale.callback_query()
async def cb_stale(cq: CallbackQuery, user: User | None = None) -> None:
    await cq.answer(t(user.lang if user else "en", "stale_button"), show_alert=True)
