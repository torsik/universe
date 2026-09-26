from __future__ import annotations

import html
import re
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.core import notify
from app.core.i18n import t
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
NEW_TASK_KEY = "btn.new_task"
TASKS_KEY = "btn.tasks"

LEAD_MINUTES = (0, 10, 60, 180, 1440, 2880)


def repeat_label(code: str, lang: str) -> str:
    return t(lang, f"t.rep.{code}")


def lead_label(minutes: int, lang: str) -> str:
    return t(lang, f"t.lead.{minutes}")


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


SECTIONS = [("overdue", "⚠️"), ("today", "☀️"), ("upcoming", "📅"), ("anytime", "▫️")]


def _line(item: Todo, tz: str, lang: str = "en") -> str:
    text = html.escape(item.text) + (" 🔁" if item.repeat else "")
    b = _bucket(item, tz)
    if b == "anytime":
        return f"• {text}"
    if b == "overdue":
        return f"• {text} · <i>{relative(item.due_at, lang)}</i>"
    if b == "today":
        return f"• {text} · <i>{to_local(item.due_at, tz):%H:%M}</i>"
    return f"• {text} · <i>{human(item.due_at, tz, lang)}</i>"


async def render_list(
    user: User, page: int = 0, undo: Todo | None = None, undo_next: int | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    items = await service.open_items(user.id)
    rows = []
    if undo:
        # undo_next: the occurrence a repeating task spawned, removed together
        # with the completion, or undoing would leave a duplicate behind.
        rows.append([btn(t(user.lang, "t.undo", name=clip(undo.text, 22)),
                         f"{M}:undo:{undo.id}:{undo_next or '-'}")])

    if not items:
        text = t(user.lang, "t.empty")
    else:
        pages = -(-len(items) // PAGE)
        page = min(max(page, 0), pages - 1)
        chunk = items[page * PAGE : (page + 1) * PAGE]
        lines = [t(user.lang, "t.title", n=len(items))]
        for key, icon in SECTIONS:
            group = [i for i in chunk if _bucket(i, user.tz) == key]
            if not group:
                continue
            lines += ["", t(user.lang, f"t.sec.{key}")] + [_line(i, user.tz, user.lang) for i in group]
            rows += [[btn(f"{icon} {clip(i.text)}", f"{M}:open:{i.id}")] for i in group]
        if pages > 1:
            rows.append([
                btn("◀️", f"{M}:list:{page - 1}") if page > 0 else btn(" ", NOOP),
                btn(f"{page + 1} / {pages}", NOOP),
                btn("▶️", f"{M}:list:{page + 1}") if page < pages - 1 else btn(" ", NOOP),
            ])
        text = "\n".join(lines) + "\n\n" + t(user.lang, "t.tap_hint")

    rows.append([btn(t(user.lang, "t.new"), f"{M}:new"),
                 btn(t(user.lang, "t.completed"), f"{M}:history")])
    return text, kb(*rows)


def render_detail(user: User, item: Todo, note: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    lines = [note, ""] if note else []
    lines.append(f"📌 <b>{html.escape(item.text)}</b>")

    if item.done:
        when = long_date(item.done_at, user.tz, user.lang) if item.done_at else ""
        lines.append(t(user.lang, "t.completed_at", when=when))
        return "\n".join(lines), kb(
            [btn(t(user.lang, "t.reopen"), f"{M}:reopen:{item.id}"),
             btn(t(user.lang, "t.delete"), f"{M}:del:{item.id}")],
            [btn(t(user.lang, "t.all"), f"{M}:list:0")],
        )

    # One prominent action; the due time carries its own value; everything
    # rarer lives one tap away under Edit. Four buttons instead of seven.
    rows = [[btn(t(user.lang, "t.done"), f"{M}:done:{item.id}")]]
    if item.due_at:
        status = t(user.lang, "t.overdue") if item.due_at < now() else relative(item.due_at, user.lang)
        lines.append(t(user.lang, "t.due_line",
                       when=long_date(item.due_at, user.tz, user.lang), status=status))
        lines.append(t(user.lang, "t.remind_line",
                       when=lead_label(item.remind_before, user.lang).lower()))
        if item.repeat:
            lines.append(t(user.lang, "t.repeat_line",
                           how=repeat_label(item.repeat, user.lang).lower()))
        rows.append([btn(t(user.lang, "t.due_with", when=human(item.due_at, user.tz, user.lang)),
                         f"{M}:when:{item.id}")])
    else:
        lines.append(t(user.lang, "t.no_due"))
        rows.append([btn(t(user.lang, "t.set_due"), f"{M}:when:{item.id}")])
    rows.append([btn(t(user.lang, "t.edit"), f"{M}:edit:{item.id}"),
                 btn(t(user.lang, "t.all"), f"{M}:list:0")])
    return "\n".join(lines), kb(*rows)


def render_edit(user: User, item: Todo) -> tuple[str, InlineKeyboardMarkup]:
    """The rarely-used half: rename, reminder, repeat, delete."""
    rows = [[btn(t(user.lang, "t.rename"), f"{M}:rename:{item.id}")]]
    if item.due_at:
        rows.append([btn(t(user.lang, "t.remind_btn",
                          when=lead_label(item.remind_before, user.lang).lower()),
                         f"{M}:rem:{item.id}")])
        rows.append([btn(t(user.lang, "t.repeat_btn",
                          how=repeat_label(item.repeat, user.lang).lower()),
                         f"{M}:rep:{item.id}")])
    rows.append([btn(t(user.lang, "t.delete"), f"{M}:del:{item.id}"),
                 btn(t(user.lang, "back"), f"{M}:open:{item.id}")])
    return t(user.lang, "t.edit_title", name=html.escape(item.text)), kb(*rows)


def render_lead(user: User, item: Todo) -> tuple[str, InlineKeyboardMarkup]:
    """Offered right after a deadline is set, so a heads-up is one tap away."""
    opts = [
        btn(f"{'● ' if m == item.remind_before else ''}{lead_label(m, user.lang)}",
            f"{M}:setrem:{item.id}:{m}")
        for m in LEAD_MINUTES
    ]
    rows = [opts[i : i + 2] for i in range(0, len(opts), 2)]
    rows.append([btn(t(user.lang, "back"), f"{M}:open:{item.id}")])
    return (
        t(user.lang, "t.lead_q", name=html.escape(item.text),
          when=long_date(item.due_at, user.tz, user.lang)),
        kb(*rows),
    )


def render_when(user: User, item: Todo, note: str | None = None, *, fresh: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    head = f"{note}\n\n" if note else ""
    text = head + t(user.lang, "t.when_q", name=html.escape(item.text))
    quick = [btn(label, f"{M}:q:{item.id}:{code}")
             for code, label in quick_options(user.tz, user.lang)]
    rows = [quick[i : i + 2] for i in range(0, len(quick), 2)]
    rows.append([
        btn(t(user.lang, "t.pick_date"), f"{M}:cal:{item.id}:m:{local_now(user.tz):%Y%m}"),
        btn(t(user.lang, "t.type_it"), f"{M}:type:{item.id}"),
    ])
    if fresh:  # just added: the only other choice is "no due time"
        rows.append([btn(t(user.lang, "t.skip_due"), f"{M}:q:{item.id}:skip")])
    else:
        rows.append([
            btn(t(user.lang, "t.no_due_btn"), f"{M}:q:{item.id}:none"),
            btn(t(user.lang, "back"), f"{M}:open:{item.id}"),
        ])
    return text, kb(*rows)


async def render_history(user: User) -> tuple[str, InlineKeyboardMarkup]:
    items = await service.done_items(user.id)
    if not items:
        return t(user.lang, "t.hist.empty"), kb([btn(t(user.lang, "t.all"), f"{M}:list:0")])
    lines = [t(user.lang, "t.hist.title"), ""]
    lines += [f"✅ <s>{html.escape(i.text)}</s>" for i in items]
    lines += ["", t(user.lang, "t.hist.hint")]
    rows = [[btn(f"↩️ {clip(i.text)}", f"{M}:hreopen:{i.id}")] for i in items]
    rows.append([btn(t(user.lang, "t.hist.clear"), f"{M}:clear"),
                 btn(t(user.lang, "t.all"), f"{M}:list:0")])
    return "\n".join(lines), kb(*rows)


async def _load(cq: CallbackQuery, user: User, todo_id: int) -> Todo | None:
    """Fetch this user's task, or say it is gone and show the list instead."""
    item = await service.get(todo_id, user.id)
    if item is None:
        await cq.answer(t(user.lang, "gone.task"), show_alert=True)
        text, markup = await render_list(user)
        await safe_edit(cq, text, reply_markup=markup)
    return item


# ---------- bottom keyboard ----------

async def show_tasks(message: Message, state: FSMContext, user: User) -> None:
    text, markup = await render_list(user)
    await message.answer(text, reply_markup=markup)


async def ask_new_task(message: Message, state: FSMContext, user: User) -> None:
    await message.answer(t(user.lang, "t.new_prompt"))


# ---------- list & navigation ----------

@router.callback_query(F.data.startswith(f"{M}:list:"))
async def cb_list(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    text, markup = await render_list(user, int(_parts(cq)[2]))
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data == f"{M}:new")
async def cb_new(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    await safe_edit(cq, t(user.lang, "t.new_prompt"),
                    reply_markup=cancel_kb(f"{M}:list:0", t(user.lang, "back")))
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
        await cq.answer(t(user.lang, "t.next_one", when=human(nxt.due_at, user.tz, user.lang)))
    else:
        await cq.answer(t(user.lang, "t.done_toast") if changed else t(user.lang, "t.already"))
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
    await cq.answer(t(user.lang, "t.restored"))


@router.callback_query(F.data.startswith(f"{M}:reopen:"))
async def cb_reopen(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await _load(cq, user, todo_id) is None:
        return
    await service.reopen(todo_id)
    await scheduler.refresh(M)
    if item := await _load(cq, user, todo_id):
        text, markup = render_detail(user, item, note=t(user.lang, "t.reopened"))
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
    # Only offer "warn me earlier" when there is room for it to matter; for
    # "in 1 hour" the extra screen is just a tap in the way.
    far_off = when is not None and (when - now()) > timedelta(hours=24)
    if far_off and not item.remind_before:
        text, markup = render_lead(user, item)
    else:
        text, markup = render_detail(
            user, item, note=note or (t(user.lang, "t.saved_note") if when
                                      else t(user.lang, "t.due_removed"))
        )
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "saved"))


@router.callback_query(F.data.startswith(f"{M}:q:"))
async def cb_quick(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    _, _, todo_id, code = _parts(cq)
    if code == "skip":
        await _apply_due(cq, user, scheduler, int(todo_id), None, note=t(user.lang, "t.added"))
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
        text = t(user.lang, "t.pick_day", name=html.escape(item.text))
        markup = calendar_kb(
            f"{M}:cal:{todo_id}", int(value[:4]), int(value[4:]), today=today,
            back_cb=f"{M}:when:{todo_id}", lang=user.lang,
        )
    else:
        day = datetime.strptime(value, "%Y%m%d").date()
        n = local_now(user.tz)
        from app.core.i18n import days_short, month_short

        shown = f"{days_short(user.lang)[day.weekday()]} {day.day} {month_short(user.lang, day.month)}"
        text = t(user.lang, "t.what_time", day=shown)
        markup = time_kb(
            f"{M}:at:{todo_id}:{value}",
            back_cb=f"{M}:cal:{todo_id}:m:{value[:6]}",
            custom_cb=f"{M}:tt:{todo_id}:{value}",
            after=(n.hour, n.minute) if day == today else None,
            lang=user.lang,
        )
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:at:"))
async def cb_at(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    _, _, todo_id, ymd, hm = _parts(cq)
    when = to_utc(datetime.strptime(ymd + hm, "%Y%m%d%H%M"), user.tz)
    if when <= now():
        await cq.answer(t(user.lang, "t.passed"), show_alert=True)
        return
    await _apply_due(cq, user, scheduler, int(todo_id), when)


@router.callback_query(F.data.startswith(f"{M}:type:"))
async def cb_type(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    await state.set_state(EditTask.when_text)
    await state.update_data(todo_id=todo_id)
    await safe_edit(cq, t(user.lang, "t.type_due"),
                    reply_markup=cancel_kb(f"{M}:when:{todo_id}", t(user.lang, "cancel")))
    await cq.answer()


@router.message(EditTask.when_text)
async def typed_when(message: Message, state: FSMContext, scheduler: Scheduler, user: User) -> None:
    try:
        when = parse_future(message.text or "", user.tz)
    except ParseError as e:
        await message.answer(t(user.lang, "t.retry", err=e))
        return
    data = await state.get_data()
    await state.clear()
    if await service.get(data["todo_id"], user.id) is None:
        await message.answer(t(user.lang, "gone.task"))
        return
    item = await service.set_due(data["todo_id"], when)
    await scheduler.refresh(M)
    if (when - now()) > timedelta(hours=24):
        text, markup = render_lead(user, item)
    else:
        text, markup = render_detail(user, item, note=t(user.lang, "t.saved_note"))
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:tt:"))
async def cb_type_time(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    _, _, todo_id, ymd = _parts(cq)
    await state.set_state(EditTask.time_text)
    await state.update_data(todo_id=int(todo_id), day=ymd)
    await safe_edit(cq, t(user.lang, "t.type_time"),
                    reply_markup=cancel_kb(f"{M}:cal:{todo_id}:d:{ymd}", t(user.lang, "cancel")))
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
        await message.answer(t(user.lang, "t.passed_long"))
        return
    await state.clear()
    if await service.get(data["todo_id"], user.id) is None:
        await message.answer(t(user.lang, "gone.task"))
        return
    item = await service.set_due(data["todo_id"], when)
    await scheduler.refresh(M)
    if (when - now()) > timedelta(hours=24):
        text, markup = render_lead(user, item)
    else:
        text, markup = render_detail(user, item, note=t(user.lang, "t.saved_note"))
    await message.answer(text, reply_markup=markup)


def render_repeat(user: User, item: Todo) -> tuple[str, InlineKeyboardMarkup]:
    opts = [
        btn(f"{'● ' if code == item.repeat else ''}{repeat_label(code, user.lang)}",
            f"{M}:setrep:{item.id}:{code or '-'}")
        for code, _ in service.REPEATS
    ]
    rows = [opts[i : i + 2] for i in range(0, len(opts), 2)]
    rows.append([btn(t(user.lang, "back"), f"{M}:open:{item.id}")])
    return t(user.lang, "t.rep_q", name=html.escape(item.text)), kb(*rows)


@router.callback_query(F.data.startswith(f"{M}:rep:"))
async def cb_repeat(cq: CallbackQuery, user: User) -> None:
    item = await _load(cq, user, int(_parts(cq)[2]))
    if item is None:
        return
    if item.due_at is None:
        await cq.answer(t(user.lang, "t.repeat_needs_date"), show_alert=True)
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
    text, markup = render_detail(user, item, note=t(user.lang, "t.rep_set"))
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "saved"))


@router.callback_query(F.data.startswith(f"{M}:edit:"))
async def cb_edit(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    if item := await _load(cq, user, int(_parts(cq)[2])):
        text, markup = render_edit(user, item)
        await safe_edit(cq, text, reply_markup=markup)
        await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:rem:"))
async def cb_reminder(cq: CallbackQuery, user: User) -> None:
    item = await _load(cq, user, int(_parts(cq)[2]))
    if item is None:
        return
    if item.due_at is None:
        await cq.answer(t(user.lang, "t.set_due_first"), show_alert=True)
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
    text, markup = render_detail(user, item, note=t(user.lang, "t.lead_set"))
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "saved"))


# ---------- rename / delete ----------

@router.callback_query(F.data.startswith(f"{M}:rename:"))
async def cb_rename(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await _load(cq, user, todo_id) is None:
        return
    await state.set_state(EditTask.rename)
    await state.update_data(todo_id=todo_id)
    await safe_edit(cq, t(user.lang, "t.type_text"),
                    reply_markup=cancel_kb(f"{M}:open:{todo_id}", t(user.lang, "cancel")))
    await cq.answer()


@router.message(EditTask.rename)
async def typed_rename(message: Message, state: FSMContext, user: User) -> None:
    if not (message.text or "").strip():
        await message.answer("🤔 It needs some text.")
        return
    data = await state.get_data()
    await state.clear()
    if await service.get(data["todo_id"], user.id) is None:
        await message.answer(t(user.lang, "gone.task"))
        return
    await service.rename(data["todo_id"], message.text)
    item = await service.get(data["todo_id"], user.id)
    text, markup = render_detail(user, item, note=t(user.lang, "t.renamed"))
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:del:"))
async def cb_delete(cq: CallbackQuery, user: User) -> None:
    if item := await _load(cq, user, int(_parts(cq)[2])):
        await safe_edit(
            cq,
            t(user.lang, "t.del_q", name=html.escape(item.text))
            + f"\n<i>{t(user.lang, 'cant_undo')}</i>",
            reply_markup=kb([
                btn(t(user.lang, "yes_delete"), f"{M}:delok:{item.id}"),
                btn(t(user.lang, "keep"), f"{M}:open:{item.id}"),
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
    await cq.answer(t(user.lang, "deleted"))


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
        await cq.answer(t(user.lang, "gone.task"), show_alert=True)
        return
    await service.reopen(todo_id)
    await scheduler.refresh(M)
    text, markup = await render_history(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "t.hist.back_on"))


@router.callback_query(F.data == f"{M}:clear")
async def cb_clear(cq: CallbackQuery, user: User) -> None:
    await safe_edit(
        cq,
        t(user.lang, "t.hist.clear_q") + f"\n<i>{t(user.lang, 'cant_undo')}</i>",
        reply_markup=kb([btn(t(user.lang, "t.hist.clear"), f"{M}:clearok"),
                         btn(t(user.lang, "keep"), f"{M}:history")]),
    )
    await cq.answer()


@router.callback_query(F.data == f"{M}:clearok")
async def cb_clear_ok(cq: CallbackQuery, user: User) -> None:
    n = await service.clear_done(user.id)
    text, markup = await render_history(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "t.hist.cleared", n=n))


# ---------- reminders (pushed messages) ----------

async def fire_reminder(bot: Bot, todo_id: int) -> None:
    from app.core import users

    item = await service.get(todo_id)
    if item is None or item.done:
        return
    user = await users.get(item.user_id)
    if user is None or user.blocked:
        return
    lang = user.lang
    snooze = [btn(t(lang, "t.push.h1"), f"{M}:rsnz:{item.id}:1h")]
    if local_now(user.tz).hour < 19:
        snooze.append(btn(t(lang, "t.push.tonight"), f"{M}:rsnz:{item.id}:eve"))
    snooze.append(btn(t(lang, "t.push.tomorrow"), f"{M}:rsnz:{item.id}:tm9"))
    ok = await notify.send(
        bot,
        user.id,
        t(lang, "t.push.reminder", name=html.escape(item.text),
          when=human(item.due_at, user.tz, lang)),
        what=f"reminder for task {todo_id}",
        reply_markup=kb([btn(t(lang, "t.done"), f"{M}:rdone:{item.id}")], snooze),
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
        t(user.lang, "t.push.heads", name=html.escape(item.text),
          when=human(item.due_at, user.tz, user.lang), rel=relative(item.due_at, user.lang)),
        what=f"heads-up for task {todo_id}",
        reply_markup=kb([
            btn(t(user.lang, "t.done"), f"{M}:rdone:{item.id}"),
            btn(t(user.lang, "t.push.open"), f"{M}:open:{item.id}"),
        ]),
    )
    if ok:  # unflagged means the next sweep tries again
        await service.mark_lead_notified(todo_id)


@router.callback_query(F.data.startswith(f"{M}:rdone:"))
async def cb_reminder_done(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    todo_id = int(_parts(cq)[2])
    if await service.get(todo_id, user.id) is None:
        await cq.answer(t(user.lang, "gone.task"), show_alert=True)
        return
    _, nxt = await service.complete(todo_id, user.tz)
    await scheduler.refresh(M)
    item = await service.get(todo_id, user.id)
    name = html.escape(item.text) if item else "—"
    text = (t(user.lang, "t.push.next", name=name, when=human(nxt.due_at, user.tz, user.lang))
            if nxt else t(user.lang, "t.push.nice", name=name))
    await safe_edit(cq, text, reply_markup=kb([btn(t(user.lang, "t.push.open_list"), f"{M}:list:0")]))
    await cq.answer(t(user.lang, "t.done_toast"))


@router.callback_query(F.data.startswith(f"{M}:rsnz:"))
async def cb_reminder_snooze(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    _, _, todo_id, code = _parts(cq)
    if await service.get(int(todo_id), user.id) is None:
        await cq.answer(t(user.lang, "gone.task"), show_alert=True)
        return
    when = quick_when(code, user.tz)
    item = await service.set_due(int(todo_id), when)
    await scheduler.refresh(M)
    await safe_edit(
        cq,
        t(user.lang, "t.push.snoozed", name=html.escape(item.text),
          when=human(when, user.tz, user.lang)),
        reply_markup=kb([btn(t(user.lang, "t.push.open"), f"{M}:open:{item.id}")]),
    )
    await cq.answer(t(user.lang, "t.snoozed"))


# ---------- any text = a new task ----------

_BULLET = re.compile(r"^\s*(?:[-•*▫️]|\d+[.)])\s+")


@fallback.message(StateFilter(None), F.text)
async def quick_add(message: Message, user: User) -> None:
    if message.text.startswith("/"):
        await message.answer(t(user.lang, "no_commands"), reply_markup=main_keyboard(user.lang))
        return
    lines = [_BULLET.sub("", line).strip() for line in message.text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return
    if len(lines) == 1:
        item = await service.add(user.id, lines[0])
        text, markup = render_when(user, item, note=t(user.lang, "t.added"), fresh=True)
        await message.answer(text, reply_markup=markup)
        return
    items = await service.add_many(user.id, lines)
    text, markup = await render_list(user)
    await message.answer(f"{t(user.lang, 't.added_many', n=len(items))}\n\n{text}", reply_markup=markup)


@fallback.message(StateFilter(None))
async def not_text(message: Message, user: User) -> None:
    await message.answer(t(user.lang, "not_text"), reply_markup=main_keyboard(user.lang))