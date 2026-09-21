from __future__ import annotations

import html
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.dates import DAY_LABELS, ParseError, days_mask_label, parse_time
from app.core.scheduler import Scheduler
from app.core.ui import back_row, cancel_kb, safe_edit
from app.db import now
from app.modules.habits import service

router = Router(name="habits")
M = "habits"

PRESETS = [("Every day", "0123456"), ("Weekdays", "01234"), ("Weekends", "56")]


class NewHabit(StatesGroup):
    name = State()
    time = State()


class EditHabit(StatesGroup):
    rename = State()
    time = State()


async def _render_list() -> tuple[str, InlineKeyboardBuilder]:
    habits = await service.all_habits()
    kb = InlineKeyboardBuilder()
    if habits:
        lines = ["<b>🔁 Habits</b>", ""]
        for h in habits:
            mark = {"done": "✅", "skip": "⏭"}.get(service.logged_today(h), "▫️")
            streak = service.streak(h)
            flame = f" 🔥{streak}" if streak else ""
            dim = "" if h.active else " <i>(paused)</i>"
            lines.append(
                f"{mark} <b>{html.escape(h.name)}</b>{flame}{dim}\n"
                f"    <code>{h.hour:02d}:{h.minute:02d}</code> · {days_mask_label(h.days)}"
            )
            kb.row(
                InlineKeyboardButton(text=f"✅ {h.name[:14]}", callback_data=f"{M}:done:{h.id}"),
                InlineKeyboardButton(text="⚙️", callback_data=f"{M}:edit:{h.id}"),
            )
        body = "\n".join(lines)
    else:
        body = "<b>🔁 Habits</b>\n\nNo habits yet. Add one and I'll nudge you on schedule."
    kb.row(InlineKeyboardButton(text="➕ Add habit", callback_data=f"{M}:add"))
    kb.row(*back_row())
    return body, kb


@router.callback_query(F.data == f"open:{M}")
async def open_module(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())
    await cq.answer()


# ---------- logging ----------

def _log_target(data: str) -> tuple[int, date]:
    """'habits:done:3' -> today; 'habits:done:3:20260920' -> that day.

    Nudges carry their own date. Without it, the Done on a 21:30 nudge tapped
    at 00:10 was credited to the new day: yesterday became a miss (streak
    gone) and today's nudge was suppressed as already logged.
    """
    parts = data.split(":")
    hid = int(parts[2])
    today = now().date()
    if len(parts) > 3:
        day = datetime.strptime(parts[3], "%Y%m%d").date()
        if today - timedelta(days=7) <= day <= today:
            return hid, day
    return hid, today


@router.callback_query(F.data.startswith(f"{M}:done:"))
async def mark_done(cq: CallbackQuery) -> None:
    hid, day = _log_target(cq.data)
    await service.log(hid, "done", day)
    h = await service.get(hid)
    await cq.answer(f"🔥 {service.streak(h)} day streak" if h else "Logged")
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith(f"{M}:skip:"))
async def mark_skip(cq: CallbackQuery) -> None:
    hid, day = _log_target(cq.data)
    await service.log(hid, "skip", day)
    await cq.answer("Skipped - streak broken but no guilt.")
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())


# ---------- create ----------

@router.callback_query(F.data == f"{M}:add")
async def ask_name(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewHabit.name)
    await safe_edit(cq, 
        "What habit?\n\n<i>e.g. Read 20 pages · Practise a card trick · Stretch</i>",
        reply_markup=cancel_kb(M),
    )
    await cq.answer()


@router.message(NewHabit.name)
async def ask_time(message: Message, state: FSMContext) -> None:
    if not (message.text or "").strip():
        await message.answer("Give it a name.", reply_markup=cancel_kb(M))
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(NewHabit.time)
    await message.answer(
        "What time should I nudge you? <code>08:00</code>, <code>21:30</code>...",
        reply_markup=cancel_kb(M),
    )


def _days_kb(target: str, mask: str) -> InlineKeyboardBuilder:
    """Toggle picker. target is "new" (wizard) or a habit id (edit).

    Each button carries the mask it would produce, so no FSM state is needed
    and any number of days can be picked (e.g. Mon/Wed/Fri).
    """
    kb = InlineKeyboardBuilder()
    for label, preset in PRESETS:
        mark = "● " if mask == preset else ""
        kb.button(text=f"{mark}{label}", callback_data=f"{M}:pick:{target}:{preset}")
    for i, label in enumerate(DAY_LABELS):
        d = str(i)
        toggled = "".join(sorted(set(mask) ^ {d}))
        kb.button(
            text=f"{'✅' if d in mask else '▫️'} {label}",
            callback_data=f"{M}:pick:{target}:{toggled or '-'}",
        )
    kb.button(text="💾 Save", callback_data=f"{M}:savedays:{target}:{mask or '-'}")
    kb.adjust(3, 4, 3, 1)
    kb.row(*back_row(M))
    return kb


def _days_prompt(mask: str) -> str:
    chosen = days_mask_label(mask) if mask else "none yet"
    return f"Which days?\n\nSelected: <b>{chosen}</b>"


@router.message(NewHabit.time)
async def ask_days(message: Message, state: FSMContext) -> None:
    try:
        hour, minute = parse_time(message.text or "")
    except ParseError as e:
        await message.answer(str(e), reply_markup=cancel_kb(M))
        return
    await state.update_data(hour=hour, minute=minute)
    mask = PRESETS[0][1]
    await message.answer(_days_prompt(mask), reply_markup=_days_kb("new", mask).as_markup())


@router.callback_query(F.data.startswith(f"{M}:pick:"))
async def pick_days(cq: CallbackQuery) -> None:
    _, _, target, mask = cq.data.split(":")
    mask = "" if mask == "-" else mask
    await safe_edit(cq, _days_prompt(mask), reply_markup=_days_kb(target, mask).as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:savedays:"))
async def save_days(cq: CallbackQuery, state: FSMContext, scheduler: Scheduler) -> None:
    _, _, target, mask = cq.data.split(":")
    if mask == "-":
        await cq.answer("Pick at least one day.", show_alert=True)
        return
    if target == "new":
        data = await state.get_data()
        if "name" not in data:
            await cq.answer("Session expired, start again.", show_alert=True)
            await state.clear()
            return
        await service.create(data["name"], data["hour"], data["minute"], mask)
        await state.clear()
        note = "Habit added"
    else:
        await service.update(int(target), days=mask)
        note = "Days updated"
    await scheduler.refresh(M)
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())
    await cq.answer(note)


# ---------- edit ----------

@router.callback_query(F.data.startswith(f"{M}:edit:"))
async def edit_menu(cq: CallbackQuery) -> None:
    h = await service.get(int(cq.data.split(":")[2]))
    if h is None:
        await cq.answer("Gone.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Rename", callback_data=f"{M}:rename:{h.id}")
    kb.button(text="🕐 Time", callback_data=f"{M}:retime:{h.id}")
    kb.button(text="📅 Days", callback_data=f"{M}:redays:{h.id}")
    kb.button(
        text="▶️ Resume" if not h.active else "⏸ Pause", callback_data=f"{M}:toggle:{h.id}"
    )
    kb.button(text="⏭ Skip today", callback_data=f"{M}:skip:{h.id}")
    kb.button(text="🗑 Delete", callback_data=f"{M}:del:{h.id}")
    kb.adjust(2)
    kb.row(*back_row(M))
    text = (
        f"<b>{html.escape(h.name)}</b>\n\n"
        f"🕐 {h.hour:02d}:{h.minute:02d} · {days_mask_label(h.days)}\n"
        f"🔥 streak: {service.streak(h)}\n\n"
        f"<code>{service.last_30(h)}</code>\n<i>last 30 days</i>"
    )
    await safe_edit(cq, text, reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:toggle:"))
async def toggle_active(cq: CallbackQuery, scheduler: Scheduler) -> None:
    hid = int(cq.data.split(":")[2])
    h = await service.get(hid)
    if h:
        await service.update(hid, active=not h.active)
        await scheduler.refresh(M)
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())
    await cq.answer("Paused" if h and h.active else "Resumed")


@router.callback_query(F.data.startswith(f"{M}:del:"))
async def delete_habit(cq: CallbackQuery, scheduler: Scheduler) -> None:
    await service.delete(int(cq.data.split(":")[2]))
    await scheduler.refresh(M)
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())
    await cq.answer("Deleted")


@router.callback_query(F.data.startswith(f"{M}:rename:"))
async def ask_rename(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(habit_id=int(cq.data.split(":")[2]))
    await state.set_state(EditHabit.rename)
    await safe_edit(cq, "New name?", reply_markup=cancel_kb(M))
    await cq.answer()


@router.message(EditHabit.rename)
async def do_rename(message: Message, state: FSMContext) -> None:
    if not (message.text or "").strip():
        await message.answer("Give it a name.", reply_markup=cancel_kb(M))
        return
    data = await state.get_data()
    await service.update(data["habit_id"], name=(message.text or "").strip()[:120])
    await state.clear()
    body, kb = await _render_list()
    await message.answer(body, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith(f"{M}:retime:"))
async def ask_retime(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(habit_id=int(cq.data.split(":")[2]))
    await state.set_state(EditHabit.time)
    await safe_edit(cq, "New time? e.g. <code>07:30</code>", reply_markup=cancel_kb(M))
    await cq.answer()


@router.message(EditHabit.time)
async def do_retime(message: Message, state: FSMContext, scheduler: Scheduler) -> None:
    try:
        hour, minute = parse_time(message.text or "")
    except ParseError as e:
        await message.answer(str(e), reply_markup=cancel_kb(M))
        return
    data = await state.get_data()
    await service.update(data["habit_id"], hour=hour, minute=minute)
    await state.clear()
    await scheduler.refresh(M)
    body, kb = await _render_list()
    await message.answer(body, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith(f"{M}:redays:"))
async def ask_redays(cq: CallbackQuery) -> None:
    h = await service.get(int(cq.data.split(":")[2]))
    if h is None:
        await cq.answer("Gone.", show_alert=True)
        return
    await safe_edit(cq, _days_prompt(h.days), reply_markup=_days_kb(str(h.id), h.days).as_markup())
    await cq.answer()


# ---------- the nudge ----------

async def fire_nudge(bot: Bot, habit_id: int) -> None:
    from app.config import settings

    h = await service.get(habit_id)
    if h is None or not h.active or service.logged_today(h):
        return
    kb = InlineKeyboardBuilder()
    stamp = now().strftime("%Y%m%d")
    kb.button(text="✅ Done", callback_data=f"{M}:done:{h.id}:{stamp}")
    kb.button(text="⏭ Skip", callback_data=f"{M}:skip:{h.id}:{stamp}")
    streak = service.streak(h)
    tail = f"\n\n🔥 {streak} day streak on the line." if streak > 1 else ""
    await bot.send_message(
        settings.owner_id,
        f"🔁 <b>{html.escape(h.name)}</b>{tail}",
        reply_markup=kb.as_markup(),
    )
