from __future__ import annotations

import html
import re
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.core import notify
from app.core.dates import (
    ParseError, human, long_date, parse_future, parse_time, quick_options, quick_when, relative,
)
from app.core.pickers import calendar_kb, time_kb
from app.core.scheduler import Scheduler
from app.core.ui import NOOP, btn, cancel_kb, clip, kb, main_keyboard, safe_edit
from app.core.users import User
from app.db import local_now, local_today, now, to_local, to_utc
from app.modules.todo import service
from app.modules.todo.models import Todo

router = Router(name="todo")
# Included after every module router: "any text becomes a task" must be the
# last thing tried, or it would swallow other modules' input.
fallback = Router(name="todo-fallback")

M = "todo"
PAGE = 8
NEW_TASK_BTN = "➕ New task"
TASKS_BTN = "📝 Tasks"

LEAD_OPTIONS = [
    (0, "At the deadline"), (10, "10 min before"), (60, "1 hour before"),
    (180, "3 hours before"), (1440, "1 day before"), (2880, "2 days before"),
]


def repeat_label(code: str) -> str:
    return dict(service.REPEATS).get(code, "Never")


def lead_label(minutes: int) -> str:
    return dict(LEAD_OPTIONS).get(minutes, f"{minutes} min before")


NEW_PROMPT = (
    "✍️ <b>What do you need to do?</b>\n\n"
    "Just type it and send. Several lines add several tasks."
)


class EditTask(StatesGroup):
    rename = State()
    when_text = State()   # data: todo_id
    time_text = State()   # data: todo_id, day


def _parts(cq: CallbackQuery) -> list[str]:
    return cq.data.split(":")


# ---------- rendering ----------

def _bucket(item: Todo, tz: str) -> str:
    if item.due_at is None:
        return "anytime"
    if item.due_at < now():
        return "overdue"
    return "today" if to_local(item.due_at, tz).date() == local_today(tz) else "upcoming"


SECTIONS = [
    ("overdue", "⚠️ <b>Overdue</b>", "⚠️"),
    ("today", "☀️ <b>Today</b>", "☀️"),
    ("upcoming", "📅 <b>Upcoming</b>", "📅"),
    ("anytime", "🗂 <b>Anytime</b>", "▫️"),
]


def _line(item: Todo, tz: str) -> str:
    text = html.escape(item.text) + (" 🔁" if item.repeat else "")
    b = _bucket(item, tz)
    if b == "anytime":
        return f"• {text}"
    if b == "overdue":
        return f"• {text} · <i>{relative(item.due_at)}</i>"
    if b == "today":
        return f"• {text} · <i>{to_local(item.due_at, tz):%H:%M}</i>"
    return f"• {text} · <i>{human(item.due_at, tz)}</i>"


async def render_list(
    user: User, page: int = 0, undo: Todo | None = None, undo_next: int | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    items = await service.open_items(user.id)
    rows = []
    if undo:
        # undo_next: the occurrence a repeating task spawned, removed together
        # with the completion, or undoing would leave a duplicate behind.
        rows.append([btn(f"↩️ Undo: {clip(undo.text, 24)}", f"{M}:undo:{undo.id}:{undo_next or '-'}")])

    if not items:
        text = "📝 <b>Tasks</b>\n\nAll clear! 🎉\nType anything to add a task."
    else:
        pages = -(-len(items) // PAGE)
        page = min(max(page, 0), pages - 1)
        chunk = items[page * PAGE : (page + 1) * PAGE]
        lines = [f"📝 <b>Tasks</b> · {len(items)} open"]
        for key, title, icon in SECTIONS:
            group = [i for i in chunk if _bucket(i, user.tz) == key]
            if not group:
                continue
            lines += ["", title] + [_line(i, user.tz) for i in group]
            rows += [[btn(f"{icon} {clip(i.text)}", f"{M}:open:{i.id}")] for i in group]
        if pages > 1:
            rows.append([
                btn("◀️", f"{M}:list:{page - 1}") if page > 0 else btn(" ", NOOP),
                btn(f"{page + 1} / {pages}", NOOP),
                btn("▶️", f"{M}:list:{page + 1}") if page < pages - 1 else btn(" ", NOOP),
            ])
        text = "\n".join(lines) + "\n\n<i>Tap a task to open it.</i>"

    rows.append([btn("➕ New task", f"{M}:new"), btn("🗂 Completed", f"{M}:history")])
    return text, kb(*rows)


def render_detail(user: User, item: Todo, note: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    lines = [note, ""] if note else []
    lines.append(f"📌 <b>{html.escape(item.text)}</b>")

    if item.done:
        lines.append(f"✅ Completed {long_date(item.done_at, user.tz)}" if item.done_at else "✅ Completed")
        return "\n".join(lines), kb(
            [btn("↩️ Reopen", f"{M}:reopen:{item.id}"), btn("🗑 Delete", f"{M}:del:{item.id}")],
            [btn("◀️ All tasks", f"{M}:list:0")],
        )

    rows = [[btn("✅ Done", f"{M}:done:{item.id}"), btn("⏰ Due time", f"{M}:when:{item.id}")]]
    if item.due_at:
        status = "⚠️ overdue" if item.due_at < now() else relative(item.due_at)
        lines.append(f"⏰ Due {long_date(item.due_at, user.tz)} · <i>{status}</i>")
        lines.append(f"🔔 Reminder: {lead_label(item.remind_before).lower()}")
        if item.repeat:
            lines.append(f"🔁 Repeats: {repeat_label(item.repeat).lower()}")
        rows.append([
            btn(f"🔔 {lead_label(item.remind_before)}", f"{M}:rem:{item.id}"),
            btn(f"🔁 {repeat_label(item.repeat)}", f"{M}:rep:{item.id}"),
        ])
    else:
        lines.append("⏰ No due time")
    rows.append([btn("✏️ Rename", f"{M}:rename:{item.id}"), btn("🗑 Delete", f"{M}:del:{item.id}")])
    rows.append([btn("◀️ All tasks", f"{M}:list:0")])
    return "\n".join(lines), kb(*rows)


def render_lead(user: User, item: Todo) -> tuple[str, InlineKeyboardMarkup]:
    """Offered right after a deadline is set, so a heads-up is one tap away."""
    opts = [
        btn(f"{'● ' if m == item.remind_before else ''}{label}", f"{M}:setrem:{item.id}:{m}")
        for m, label in LEAD_OPTIONS
    ]
    rows = [opts[i : i + 2] for i in range(0, len(opts), 2)]
    rows.append([btn("◀️ Back", f"{M}:open:{item.id}")])
    return (
        f"🔔 When should I remind you about <b>{html.escape(item.text)}</b>?\n"
        f"<i>Deadline: {long_date(item.due_at, user.tz)}</i>",
        kb(*rows),
    )


def render_when(user: User, item: Todo, note: str | None = None, *, fresh: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    head = f"{note}\n\n" if note else ""
    text = (
        f"{head}⏰ When is <b>{html.escape(item.text)}</b> due?\n"
        "<i>I'll send you a reminder at that time.</i>"
    )
    quick = [btn(label, f"{M}:q:{item.id}:{code}") for code, label in quick_options(user.tz)]
    rows = [quick[i : i + 2] for i in range(0, len(quick), 2)]
    rows.append([
        btn("📅 Pick a date", f"{M}:cal:{item.id}:m:{local_now(user.tz):%Y%m}"),
        btn("⌨️ Type it", f"{M}:type:{item.id}"),
    ])
    if fresh:  # just added: the only other choice is "no due time"
        rows.append([btn("⏭ Skip, no due time", f"{M}:q:{item.id}:skip")])
    else:
        rows.append([
            btn("🚫 No due time", f"{M}:q:{item.id}:none"),
            btn("◀️ Back", f"{M}:open:{item.id}"),
        ])
    return text, kb(*rows)


async def render_history(user: User) -> tuple[str, InlineKeyboardMarkup]:
    items = await service.done_items(user.id)
    if not items:
        return "🗂 <b>Completed</b>\n\nNothing completed yet.", kb([btn("◀️ All tasks", f"{M}:list:0")])
    lines = ["🗂 <b>Completed</b> · last 10", ""]
    lines += [f"✅ <s>{html.escape(i.text)}</s>" for i in items]
    lines += ["", "<i>Tap one to bring it back.</i>"]
    rows = [[btn(f"↩️ {clip(i.text)}", f"{M}:hreopen:{i.id}")] for i in items]
    rows.append([btn("🧹 Clear all", f"{M}:clear"), btn("◀️ All tasks", f"{M}:list:0")])
    return "\n".join(lines), kb(*rows)


async def _load(cq: CallbackQuery, user: User, todo_id: int) -> Todo | None:
    """Fetch this user's task, or say it is gone and show the list instead."""
    item = await service.get(todo_id, user.id)
    if item is None:
        await cq.answer("This task no longer exists.", show_alert=True)
        text, markup = await render_list(user)
        await safe_edit(cq, text, reply_markup=markup)
    return item


# ---------- bottom keyboard ----------

async def show_tasks(message: Message, state: FSMContext, user: User) -> None:
    text, markup = await render_list(user)
    await message.answer(text, reply_markup=markup)


async def ask_new_task(message: Message, state: FSMContext, user: User) -> None:
    await message.answer(NEW_PROMPT)


# ---------- list & navigation ----------

@router.callback_query(F.data.startswith(f"{M}:list:"))
async def cb_list(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    text, markup = await render_list(user, int(_parts(cq)[2]))
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data == f"{M}:new")
async def cb_new(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(cq, NEW_PROMPT, reply_markup=cancel_kb(f"{M}:list:0", "◀️ Back"))
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:open:"))
async def cb_open(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    if item := await _load(cq, user, int(_parts(cq)[2])):
        text, markup = render_detail(user, item)
        await safe_edit(cq, text, reply_markup=markup)
        await cq.answer()


# ---------- complete / undo / reopen ----------

@router.callback_query(F.data.startswith(f"{M}:done:"))
async def cb_done(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await _load(cq, user, todo_id) is None:
        return
    changed, nxt = await service.complete(todo_id, user.tz)
    if nxt:
        await cq.answer(f"✅ Done! Next one: {human(nxt.due_at, user.tz)}")
    else:
        await cq.answer("✅ Done!" if changed else "Already done")
    await scheduler.refresh(M)
    text, markup = await render_list(
        user,
        undo=await service.get(todo_id, user.id) if changed else None,
        undo_next=nxt.id if nxt else None,
    )
    await safe_edit(cq, text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:undo:"))
async def cb_undo(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    parts = _parts(cq)
    if await _load(cq, user, int(parts[2])) is None:
        return
    await service.reopen(int(parts[2]))
    if len(parts) > 3 and parts[3] != "-":
        await service.delete(int(parts[3]))
    await scheduler.refresh(M)
    text, markup = await render_list(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer("Restored")


@router.callback_query(F.data.startswith(f"{M}:reopen:"))
async def cb_reopen(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await _load(cq, user, todo_id) is None:
        return
    await service.reopen(todo_id)
    await scheduler.refresh(M)
    if item := await _load(cq, user, todo_id):
        text, markup = render_detail(user, item, note="↩️ Reopened")
        await safe_edit(cq, text, reply_markup=markup)
        await cq.answer()


# ---------- due time: quick picks, calendar, typed ----------

@router.callback_query(F.data.startswith(f"{M}:when:"))
async def cb_when(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    if item := await _load(cq, user, int(_parts(cq)[2])):
        text, markup = render_when(user, item)
        await safe_edit(cq, text, reply_markup=markup)
        await cq.answer()


async def _apply_due(
    cq: CallbackQuery, user: User, scheduler: Scheduler, todo_id: int,
    when: datetime | None, note: str | None = None,
) -> None:
    if await _load(cq, user, todo_id) is None:
        return
    item = await service.set_due(todo_id, when)
    await scheduler.refresh(M)
    if when:  # ask how early to warn - the deadline alone is often too late
        text, markup = render_lead(user, item)
    else:
        text, markup = render_detail(user, item, note=note or "🚫 <b>Due time removed</b>")
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer("Saved")


@router.callback_query(F.data.startswith(f"{M}:q:"))
async def cb_quick(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    _, _, todo_id, code = _parts(cq)
    if code == "skip":
        await _apply_due(cq, user, scheduler, int(todo_id), None, note="✅ <b>Task added</b>")
    else:
        when = None if code == "none" else quick_when(code, user.tz)
        await _apply_due(cq, user, scheduler, int(todo_id), when)


@router.callback_query(F.data.startswith(f"{M}:cal:"))
async def cb_calendar(cq: CallbackQuery, user: User) -> None:
    _, _, todo_id, kind, value = _parts(cq)
    item = await _load(cq, user, int(todo_id))
    if item is None:
        return
    today = local_today(user.tz)
    if kind == "m":
        text = f"📅 Pick a day for <b>{html.escape(item.text)}</b>"
        markup = calendar_kb(
            f"{M}:cal:{todo_id}", int(value[:4]), int(value[4:]), today=today, back_cb=f"{M}:when:{todo_id}"
        )
    else:
        day = datetime.strptime(value, "%Y%m%d").date()
        n = local_now(user.tz)
        text = f"🕐 What time on <b>{day:%a %d %b}</b>?"
        markup = time_kb(
            f"{M}:at:{todo_id}:{value}",
            back_cb=f"{M}:cal:{todo_id}:m:{value[:6]}",
            custom_cb=f"{M}:tt:{todo_id}:{value}",
            after=(n.hour, n.minute) if day == today else None,
        )
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:at:"))
async def cb_at(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    _, _, todo_id, ymd, hm = _parts(cq)
    when = to_utc(datetime.strptime(ymd + hm, "%Y%m%d%H%M"), user.tz)
    if when <= now():
        await cq.answer("That time has already passed.", show_alert=True)
        return
    await _apply_due(cq, user, scheduler, int(todo_id), when)


@router.callback_query(F.data.startswith(f"{M}:type:"))
async def cb_type(cq: CallbackQuery, state: FSMContext) -> None:
    todo_id = int(_parts(cq)[2])
    await state.set_state(EditTask.when_text)
    await state.update_data(todo_id=todo_id)
    await safe_edit(
        cq,
        "⌨️ <b>Type the due time</b>\n\n"
        "For example:\n<code>in 2h</code> · <code>18:30</code> · <code>tomorrow 9:00</code>\n"
        "<code>fri 18:00</code> · <code>25/12 10:00</code>",
        reply_markup=cancel_kb(f"{M}:when:{todo_id}"),
    )
    await cq.answer()


@router.message(EditTask.when_text)
async def typed_when(message: Message, state: FSMContext, scheduler: Scheduler, user: User) -> None:
    try:
        when = parse_future(message.text or "", user.tz)
    except ParseError as e:
        await message.answer(f"🤔 {e}\nTry again, or tap Cancel above.")
        return
    data = await state.get_data()
    await state.clear()
    if await service.get(data["todo_id"], user.id) is None:
        await message.answer("That task no longer exists.")
        return
    item = await service.set_due(data["todo_id"], when)
    await scheduler.refresh(M)
    text, markup = render_lead(user, item)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:tt:"))
async def cb_type_time(cq: CallbackQuery, state: FSMContext) -> None:
    _, _, todo_id, ymd = _parts(cq)
    await state.set_state(EditTask.time_text)
    await state.update_data(todo_id=int(todo_id), day=ymd)
    await safe_edit(
        cq,
        "⌨️ <b>Type the time</b>, e.g. <code>17:45</code>",
        reply_markup=cancel_kb(f"{M}:cal:{todo_id}:d:{ymd}"),
    )
    await cq.answer()


@router.message(EditTask.time_text)
async def typed_time(message: Message, state: FSMContext, scheduler: Scheduler, user: User) -> None:
    try:
        hour, minute = parse_time(message.text or "")
    except ParseError as e:
        await message.answer(f"🤔 {e}")
        return
    data = await state.get_data()
    local = datetime.strptime(data["day"], "%Y%m%d").replace(hour=hour, minute=minute)
    when = to_utc(local, user.tz)
    if when <= now():
        await message.answer("🤔 That time has already passed. Try a later one.")
        return
    await state.clear()
    if await service.get(data["todo_id"], user.id) is None:
        await message.answer("That task no longer exists.")
        return
    item = await service.set_due(data["todo_id"], when)
    await scheduler.refresh(M)
    text, markup = render_lead(user, item)
    await message.answer(text, reply_markup=markup)


def render_repeat(user: User, item: Todo) -> tuple[str, InlineKeyboardMarkup]:
    opts = [
        btn(f"{'● ' if code == item.repeat else ''}{label}", f"{M}:setrep:{item.id}:{code or '-'}")
        for code, label in service.REPEATS
    ]
    rows = [opts[i : i + 2] for i in range(0, len(opts), 2)]
    rows.append([btn("◀️ Back", f"{M}:open:{item.id}")])
    return (
        f"🔁 How often does <b>{html.escape(item.text)}</b> come back?\n"
        "<i>Completing it creates the next one automatically.</i>",
        kb(*rows),
    )


@router.callback_query(F.data.startswith(f"{M}:rep:"))
async def cb_repeat(cq: CallbackQuery, user: User) -> None:
    item = await _load(cq, user, int(_parts(cq)[2]))
    if item is None:
        return
    if item.due_at is None:
        await cq.answer("Set a due time first - a repeat needs a date to count from.", show_alert=True)
        return
    text, markup = render_repeat(user, item)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:setrep:"))
async def cb_set_repeat(cq: CallbackQuery, user: User) -> None:
    _, _, todo_id, code = _parts(cq)
    if await _load(cq, user, int(todo_id)) is None:
        return
    item = await service.set_repeat(int(todo_id), "" if code == "-" else code)
    text, markup = render_detail(user, item, note="🔁 <b>Repeat set</b>")
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer("Saved")


@router.callback_query(F.data.startswith(f"{M}:rem:"))
async def cb_reminder(cq: CallbackQuery, user: User) -> None:
    item = await _load(cq, user, int(_parts(cq)[2]))
    if item is None:
        return
    if item.due_at is None:
        await cq.answer("Set a due time first.", show_alert=True)
        return
    text, markup = render_lead(user, item)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:setrem:"))
async def cb_set_reminder(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    _, _, todo_id, minutes = _parts(cq)
    if await _load(cq, user, int(todo_id)) is None:
        return
    item = await service.set_lead(int(todo_id), int(minutes))
    await scheduler.refresh(M)
    text, markup = render_detail(user, item, note="🔔 <b>Reminder set</b>")
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer("Saved")


# ---------- rename / delete ----------

@router.callback_query(F.data.startswith(f"{M}:rename:"))
async def cb_rename(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await _load(cq, user, todo_id) is None:
        return
    await state.set_state(EditTask.rename)
    await state.update_data(todo_id=todo_id)
    await safe_edit(cq, "✏️ <b>Type the new text</b>", reply_markup=cancel_kb(f"{M}:open:{todo_id}"))
    await cq.answer()


@router.message(EditTask.rename)
async def typed_rename(message: Message, state: FSMContext, user: User) -> None:
    if not (message.text or "").strip():
        await message.answer("🤔 It needs some text.")
        return
    data = await state.get_data()
    await state.clear()
    if await service.get(data["todo_id"], user.id) is None:
        await message.answer("That task no longer exists.")
        return
    await service.rename(data["todo_id"], message.text)
    item = await service.get(data["todo_id"], user.id)
    text, markup = render_detail(user, item, note="✏️ Renamed")
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:del:"))
async def cb_delete(cq: CallbackQuery, user: User) -> None:
    if item := await _load(cq, user, int(_parts(cq)[2])):
        await safe_edit(
            cq,
            f"🗑 Delete <b>{html.escape(item.text)}</b>?\n<i>This can't be undone.</i>",
            reply_markup=kb([
                btn("🗑 Yes, delete", f"{M}:delok:{item.id}"),
                btn("✖️ Keep it", f"{M}:open:{item.id}"),
            ]),
        )
        await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:delok:"))
async def cb_delete_ok(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await _load(cq, user, todo_id) is None:
        return
    await service.delete(todo_id)
    await scheduler.refresh(M)
    text, markup = await render_list(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer("Deleted")


# ---------- completed ----------

@router.callback_query(F.data == f"{M}:history")
async def cb_history(cq: CallbackQuery, user: User) -> None:
    text, markup = await render_history(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:hreopen:"))
async def cb_history_reopen(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await service.get(todo_id, user.id) is None:
        await cq.answer("This task no longer exists.", show_alert=True)
        return
    await service.reopen(todo_id)
    await scheduler.refresh(M)
    text, markup = await render_history(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer("↩️ Back on your list")


@router.callback_query(F.data == f"{M}:clear")
async def cb_clear(cq: CallbackQuery, user: User) -> None:
    await safe_edit(
        cq,
        "🧹 Clear all completed tasks?\n<i>This can't be undone.</i>",
        reply_markup=kb([btn("🧹 Yes, clear", f"{M}:clearok"), btn("✖️ Keep", f"{M}:history")]),
    )
    await cq.answer()


@router.callback_query(F.data == f"{M}:clearok")
async def cb_clear_ok(cq: CallbackQuery, user: User) -> None:
    n = await service.clear_done(user.id)
    text, markup = await render_history(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(f"Cleared {n}")


# ---------- reminders (pushed messages) ----------

async def fire_reminder(bot: Bot, todo_id: int) -> None:
    from app.core import users

    item = await service.get(todo_id)
    if item is None or item.done:
        return
    user = await users.get(item.user_id)
    if user is None or user.blocked:
        return
    snooze = [btn("⏰ +1 hour", f"{M}:rsnz:{item.id}:1h")]
    if local_now(user.tz).hour < 19:
        snooze.append(btn("🌙 Tonight", f"{M}:rsnz:{item.id}:eve"))
    snooze.append(btn("📅 Tomorrow", f"{M}:rsnz:{item.id}:tm9"))
    ok = await notify.send(
        bot,
        user.id,
        f"⏰ <b>Reminder</b>\n\n📌 {html.escape(item.text)}\n"
        f"<i>Due {human(item.due_at, user.tz)}</i>",
        what=f"reminder for task {todo_id}",
        reply_markup=kb([btn("✅ Done", f"{M}:rdone:{item.id}")], snooze),
    )
    # Marked only after a successful send: if Telegram is unreachable the
    # reminder stays pending and the next sweep retries it.
    if ok:
        await service.mark_notified(todo_id)


async def fire_lead(bot: Bot, todo_id: int) -> None:
    """The early warning, ahead of the deadline."""
    from app.core import users

    item = await service.get(todo_id)
    if item is None or item.done or item.due_at is None:
        return
    user = await users.get(item.user_id)
    if user is None or user.blocked:
        return
    ok = await notify.send(
        bot,
        user.id,
        f"🔔 <b>Heads up</b>\n\n📌 {html.escape(item.text)}\n"
        f"<i>Due {human(item.due_at, user.tz)} · {relative(item.due_at)}</i>",
        what=f"heads-up for task {todo_id}",
        reply_markup=kb([
            btn("✅ Done", f"{M}:rdone:{item.id}"),
            btn("📌 Open task", f"{M}:open:{item.id}"),
        ]),
    )
    if ok:  # unflagged means the next sweep tries again
        await service.mark_lead_notified(todo_id)


@router.callback_query(F.data.startswith(f"{M}:rdone:"))
async def cb_reminder_done(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await service.get(todo_id, user.id) is None:
        await cq.answer("This task no longer exists.", show_alert=True)
        return
    _, nxt = await service.complete(todo_id, user.tz)
    await scheduler.refresh(M)
    item = await service.get(todo_id, user.id)
    name = html.escape(item.text) if item else "Task"
    tail = f"\n🔁 Next one: {human(nxt.due_at, user.tz)}" if nxt else "\nNice work! 🎉"
    await safe_edit(cq, f"✅ <s>{name}</s>{tail}", reply_markup=kb([btn("📝 Open tasks", f"{M}:list:0")]))
    await cq.answer("✅ Done!")


@router.callback_query(F.data.startswith(f"{M}:rsnz:"))
async def cb_reminder_snooze(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    _, _, todo_id, code = _parts(cq)
    if await service.get(int(todo_id), user.id) is None:
        await cq.answer("This task no longer exists.", show_alert=True)
        return
    when = quick_when(code, user.tz)
    item = await service.set_due(int(todo_id), when)
    await scheduler.refresh(M)
    await safe_edit(
        cq,
        f"⏰ <b>{html.escape(item.text)}</b>\nSnoozed. I'll remind you {human(when, user.tz)}.",
        reply_markup=kb([btn("📌 Open task", f"{M}:open:{item.id}")]),
    )
    await cq.answer("Snoozed")


# ---------- any text = a new task ----------

_BULLET = re.compile(r"^\s*(?:[-•*▫️]|\d+[.)])\s+")


@fallback.message(StateFilter(None), F.text)
async def quick_add(message: Message, user: User) -> None:
    if message.text.startswith("/"):
        await message.answer(
            "I don't need commands 🙂 Use the buttons below, or just type a task.",
            reply_markup=main_keyboard(),
        )
        return
    lines = [_BULLET.sub("", line).strip() for line in message.text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return
    if len(lines) == 1:
        item = await service.add(user.id, lines[0])
        text, markup = render_when(user, item, note="✅ <b>Task added</b>", fresh=True)
        await message.answer(text, reply_markup=markup)
        return
    items = await service.add_many(user.id, lines)
    text, markup = await render_list(user)
    await message.answer(f"✅ <b>Added {len(items)} tasks</b>\n\n{text}", reply_markup=markup)


@fallback.message(StateFilter(None))
async def not_text(message: Message) -> None:
    await message.answer(
        "I can only read text 🙂 Type a task, or use the buttons below.",
        reply_markup=main_keyboard(),
    )
