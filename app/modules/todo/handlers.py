from __future__ import annotations

import html
import re
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.dates import ParseError, human, parse_future
from app.core.scheduler import Scheduler
from app.core.ui import back_row, cancel_kb, safe_edit
from app.db import now
from app.modules.todo import service

router = Router(name="todo")
M = "todo"


class AddTodo(StatesGroup):
    text = State()


class EditTodo(StatesGroup):
    due = State()
    rename = State()


def _split_when(raw: str) -> tuple[str, "datetime | None", str | None]:
    """'buy milk @ tomorrow 18:00' -> (text, when, error).

    An '@' that isn't followed by a time (an email address) stays in the text;
    one followed by a bad or past time is reported rather than swallowed.
    """
    text, sep, when_raw = raw.rpartition("@")
    if not sep or not text.strip():
        return raw, None, None
    try:
        return text, parse_future(when_raw), None
    except ParseError as e:
        if re.search(r"\d|today|tomorrow|tmr|mon|tue|wed|thu|fri|sat|sun|in ", when_raw.lower()):
            return raw, None, str(e)
        return raw, None, None


def _label(item) -> str:
    text = html.escape(item.text)
    if item.due_at:
        overdue = item.due_at < now()
        stamp = human(item.due_at)
        text += f"  <i>{'⚠️ ' if overdue else '· '}{stamp}</i>"
    return text


async def _render_list() -> tuple[str, InlineKeyboardBuilder]:
    """One row per open item: tick it, or open its detail view."""
    items = await service.open_items()
    kb = InlineKeyboardBuilder()

    if items:
        lines = ["<b>\U0001F4DD To-Do</b>", ""]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {_label(item)}")
            kb.row(
                InlineKeyboardButton(text=f"\u2705 {i}", callback_data=f"{M}:done:{item.id}"),
                InlineKeyboardButton(
                    text=f"\u2699\ufe0f {item.text[:20]}", callback_data=f"{M}:item:{item.id}"
                ),
            )
        body = "\n".join(lines)
    else:
        body = "<b>\U0001F4DD To-Do</b>\n\nNothing open. Enjoy it."

    kb.row(
        InlineKeyboardButton(text="\u2795 Add", callback_data=f"{M}:add"),
        InlineKeyboardButton(text="\U0001F5C2 Done", callback_data=f"{M}:history"),
    )
    kb.row(*back_row())
    return body, kb


@router.callback_query(F.data == f"open:{M}")
async def open_module(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:done:"))
async def complete_item(cq: CallbackQuery, scheduler: Scheduler) -> None:
    changed = await service.complete(int(cq.data.split(":")[2]))
    await cq.answer("Done ✅" if changed else "Already done")
    await scheduler.refresh(M)
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith(f"{M}:item:"))
async def item_detail(cq: CallbackQuery) -> None:
    item = await service.get(int(cq.data.split(":")[2]))
    if item is None:
        await cq.answer("Gone already.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Complete", callback_data=f"{M}:done:{item.id}")
    kb.button(text="⏰ Remind", callback_data=f"{M}:due:{item.id}")
    kb.button(text="✏️ Rename", callback_data=f"{M}:rename:{item.id}")
    if item.due_at:
        kb.button(text="🚫 Clear time", callback_data=f"{M}:undue:{item.id}")
    kb.button(text="🗑 Delete", callback_data=f"{M}:del:{item.id}")
    kb.adjust(2)
    kb.row(*back_row(M))
    due = f"\n\n⏰ {human(item.due_at)}" if item.due_at else ""
    await safe_edit(cq, f"<b>{html.escape(item.text)}</b>{due}", reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:del:"))
async def delete_item(cq: CallbackQuery, scheduler: Scheduler) -> None:
    await service.delete(int(cq.data.split(":")[2]))
    await scheduler.refresh(M)
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())
    await cq.answer("Deleted")


@router.callback_query(F.data.startswith(f"{M}:undue:"))
async def clear_due(cq: CallbackQuery, scheduler: Scheduler) -> None:
    await service.set_due(int(cq.data.split(":")[2]), None)
    await scheduler.refresh(M)
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())
    await cq.answer("Reminder cleared")


# ---------- add ----------

@router.callback_query(F.data == f"{M}:add")
async def ask_text(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddTodo.text)
    await safe_edit(cq, 
        "What needs doing?\n\n<i>Tip: end with <code>@ tomorrow 18:00</code> to set a reminder.</i>",
        reply_markup=cancel_kb(M),
    )
    await cq.answer()


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject, scheduler: Scheduler) -> None:
    # Registered before the AddTodo.text handler so "/add x" typed mid-dialog
    # is treated as a command, not saved as a to-do called "/add x".
    if not command.args:
        await message.answer("Usage: <code>/add buy milk @ tomorrow 18:00</code>")
        return
    text, when, err = _split_when(command.args)
    if err:
        await message.answer(err)
        return
    await service.add(text, when)
    await scheduler.refresh(M)
    suffix = f" (⏰ {human(when)})" if when else ""
    await message.answer(f"Added: <b>{html.escape(text.strip())}</b>{suffix}")


@router.message(AddTodo.text)
async def save_text(message: Message, state: FSMContext, scheduler: Scheduler) -> None:
    text, when, err = _split_when(message.text or "")
    if err:
        await message.answer(err, reply_markup=cancel_kb(M))
        return
    if not text.strip():
        await message.answer("Needs some text.", reply_markup=cancel_kb(M))
        return
    await service.add(text, when)
    await state.clear()
    await scheduler.refresh(M)
    body, kb = await _render_list()
    await message.answer(body, reply_markup=kb.as_markup())


# ---------- reminder / rename ----------

@router.callback_query(F.data.startswith(f"{M}:due:"))
async def ask_due(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(todo_id=int(cq.data.split(":")[2]))
    await state.set_state(EditTodo.due)
    await safe_edit(cq, 
        "When should I remind you?\n\n"
        "<code>in 2h</code> · <code>18:00</code> · <code>tomorrow 09:00</code> · "
        "<code>fri 18:30</code> · <code>2026-10-01 07:00</code>",
        reply_markup=cancel_kb(M),
    )
    await cq.answer()


@router.message(EditTodo.due)
async def save_due(message: Message, state: FSMContext, scheduler: Scheduler) -> None:
    try:
        when = parse_future(message.text or "")
    except ParseError as e:
        await message.answer(str(e), reply_markup=cancel_kb(M))
        return
    data = await state.get_data()
    await service.set_due(data["todo_id"], when)
    await state.clear()
    await scheduler.refresh(M)
    body, kb = await _render_list()
    await message.answer(f"⏰ Set for {human(when)}.")
    await message.answer(body, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith(f"{M}:rename:"))
async def ask_rename(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(todo_id=int(cq.data.split(":")[2]))
    await state.set_state(EditTodo.rename)
    await safe_edit(cq, "New text?", reply_markup=cancel_kb(M))
    await cq.answer()


@router.message(EditTodo.rename)
async def save_rename(message: Message, state: FSMContext) -> None:
    if not (message.text or "").strip():
        await message.answer("Needs some text.", reply_markup=cancel_kb(M))
        return
    data = await state.get_data()
    await service.rename(data["todo_id"], message.text or "")
    await state.clear()
    body, kb = await _render_list()
    await message.answer(body, reply_markup=kb.as_markup())


# ---------- history ----------

@router.callback_query(F.data == f"{M}:history")
async def history(cq: CallbackQuery) -> None:
    items = await service.done_items()
    lines = [f"✅ <s>{html.escape(i.text)}</s>" for i in items] or ["Nothing completed yet."]
    kb = InlineKeyboardBuilder()
    if items:
        kb.button(text="🧹 Clear history", callback_data=f"{M}:clear")
    kb.row(*back_row(M))
    await safe_edit(cq, "<b>Recently done</b>\n\n" + "\n".join(lines), reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data == f"{M}:clear")
async def clear(cq: CallbackQuery) -> None:
    n = await service.clear_done()
    body, kb = await _render_list()
    await safe_edit(cq, body, reply_markup=kb.as_markup())
    await cq.answer(f"Cleared {n}")


# ---------- scheduled reminders ----------

async def fire_reminder(bot: Bot, todo_id: int) -> None:
    from app.config import settings

    item = await service.get(todo_id)
    if item is None or item.done:
        return
    await service.mark_notified(todo_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Done", callback_data=f"{M}:done:{item.id}")
    kb.button(text="⏰ +1h", callback_data=f"{M}:snooze:{item.id}")
    await bot.send_message(
        settings.owner_id,
        f"⏰ <b>Reminder</b>\n\n{html.escape(item.text)}",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith(f"{M}:snooze:"))
async def snooze(cq: CallbackQuery, scheduler: Scheduler) -> None:
    from datetime import timedelta

    todo_id = int(cq.data.split(":")[2])
    await service.set_due(todo_id, now() + timedelta(hours=1))
    await scheduler.refresh(M)
    await cq.answer("Snoozed 1h")
