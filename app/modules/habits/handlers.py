from __future__ import annotations

import html
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.core import notify
from app.core.i18n import days_short, month_short, t
from app.core.dates import ParseError, days_mask_label, parse_time
from app.core.pickers import time_kb
from app.core.scheduler import Scheduler
from app.core.ui import btn, cancel_kb, clip, kb, progress_bar, safe_edit
from app.core.users import User
from app.db import local_now, local_today, to_utc
from app.modules.habits import service
from app.modules.habits.models import Habit

router = Router(name="habits")
M = "habits"
HABITS_KEY = "btn.habits"

PRESETS = [("h.preset.daily", "0123456"), ("h.preset.weekdays", "01234"), ("h.preset.weekends", "56")]
TEMPLATE_KEYS = [f"h.tpl.{i}" for i in range(6)]
MARK = {"done": "✅", "skip": "⏭"}


INTERVALS = (30, 60, 120, 180)
WINDOWS = [("h.win.work", 9, 0, 18, 0), ("h.win.waking", 8, 0, 22, 0)]


class NewHabit(StatesGroup):
    name = State()
    time = State()
    window = State()


class EditHabit(StatesGroup):
    rename = State()
    time = State()
    window = State()


def _parts(cq: CallbackQuery) -> list[str]:
    return cq.data.split(":")


def _hm(h: Habit) -> str:
    return f"{h.hour:02d}:{h.minute:02d}"


# ---------- rendering ----------

async def render_home(user: User) -> tuple[str, InlineKeyboardMarkup]:
    """Today's checklist: one tap checks a habit off (tap again to undo)."""
    habits = await service.all_habits(user.id)
    n = local_now(user.tz)
    today = n.date()
    date_label = f"{days_short(user.lang)[n.weekday()]} {n.day} {month_short(user.lang, n.month)}"
    head = t(user.lang, "h.title", date=date_label)
    if not habits:
        return (
            f"{head}\n\n{t(user.lang, 'h.empty')}",
            kb([btn(t(user.lang, "h.new"), f"{M}:new")]),
        )

    todays = [h for h in habits if service.scheduled_today(h, today)]
    resting = [h for h in habits if h.active and not service.scheduled_today(h, today)]
    paused = [h for h in habits if not h.active]
    lines, rows = [head], []

    if todays:
        done = sum(service.logged_today(h, today) == "done" for h in todays)
        reps_done = sum(service.progress(h, today)[0] for h in todays)
        reps_total = sum(service.progress(h, today)[1] for h in todays)
        if reps_total > len(todays):
            lines.append(f"{progress_bar(reps_done, reps_total)}  " + t(
                user.lang, "h.progress_reps", done=done, total=len(todays),
                reps=reps_done, reps_total=reps_total))
        else:
            lines.append(f"{progress_bar(done, len(todays))}  " + t(
                user.lang, "h.progress", done=done, total=len(todays)))
        if done == len(todays):
            lines.append(t(user.lang, "h.all_done"))
        lines.append("")
        for h in todays:
            status = service.logged_today(h, today)
            streak = service.streak(h, today, user.tz)
            fire = f" · 🔥{streak}" if streak else ""
            if h.kind == "interval":
                count, target = service.progress(h, today)
                mark = "✅" if count >= target else ("⏭" if status == "skip" else "▫️")
                lines.append(
                    f"{mark} {html.escape(h.name)} · <b>{count}/{target}</b>"
                    f" · <i>{service.window_label(h, user.lang)}</i>{fire}"
                )
                rows.append([btn(f"{mark} {clip(h.name, 22)} {count}/{target}", f"{M}:tap:{h.id}")])
            else:
                when = "" if status else f" · <i>{_hm(h)}</i>"
                lines.append(f"{MARK.get(status, '▫️')} {html.escape(h.name)}{when}{fire}")
                rows.append([btn(f"{MARK.get(status, '▫️')} {clip(h.name)}", f"{M}:tap:{h.id}")])
    else:
        lines.append(t(user.lang, "h.rest"))

    if resting:
        names = ", ".join(f"{html.escape(h.name)} ({days_mask_label(h.days, user.lang)})" for h in resting)
        lines.append(t(user.lang, "h.not_today", list=names))
    if paused:
        lines.append(t(user.lang, "h.paused_list", list=", ".join(html.escape(h.name) for h in paused)))
    if todays:
        lines.append(t(user.lang, "h.tap_hint"))

    rows.append([btn(t(user.lang, "h.new"), f"{M}:new"), btn(t(user.lang, "h.manage"), f"{M}:manage")])
    rows.append([btn(t(user.lang, "h.week"), f"{M}:stats")])
    return "\n".join(lines), kb(*rows)


async def render_stats(user: User) -> tuple[str, InlineKeyboardMarkup]:
    habits = await service.all_habits(user.id, only_active=True)
    today = local_today(user.tz)
    start, end = service.week_bounds(today)
    prev_start, prev_end = service.week_bounds(today, 1)
    fmt = lambda d: f"{d.day} {month_short(user.lang, d.month)}"  # noqa: E731
    lines = [t(user.lang, "h.week.title", start=fmt(start), end=fmt(end)), ""]

    if not habits:
        lines.append(t(user.lang, "h.week.none"))
        return "\n".join(lines), kb([btn(t(user.lang, "back"), f"{M}:home")])

    done_total = sched_total = 0
    for h in habits:
        done, sched = service.week_stats(h, start, end, today, user.tz)
        done_total, sched_total = done_total + done, sched_total + sched
        bar = progress_bar(done, sched, 6) if sched else "······"
        lines.append(f"{bar}  {done}/{sched}  {html.escape(h.name)}")

    prev_done = prev_sched = 0
    for h in habits:
        d, sc = service.week_stats(h, prev_start, prev_end, today, user.tz)
        prev_done, prev_sched = prev_done + d, prev_sched + sc

    pct = round(100 * done_total / sched_total) if sched_total else 0
    lines.append("")
    summary = t(user.lang, "h.week.sum", done=done_total, total=sched_total, pct=pct)
    if prev_sched:
        prev_pct = round(100 * prev_done / prev_sched)
        arrow = "▲" if pct > prev_pct else ("▼" if pct < prev_pct else "▬")
        summary += t(user.lang, "h.week.prev", pct=prev_pct, arrow=arrow)
    lines.append(summary)

    best = max(habits, key=lambda h: service.streak(h, today, user.tz))
    if service.streak(best, today, user.tz):
        lines.append(t(user.lang, "h.week.longest", n=service.streak(best, today, user.tz),
                       name=html.escape(best.name)))
    return "\n".join(lines), kb([btn(t(user.lang, "back"), f"{M}:home")])


@router.callback_query(F.data == f"{M}:stats")
async def cb_stats(cq: CallbackQuery, user: User) -> None:
    text, markup = await render_stats(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


async def render_manage(user: User) -> tuple[str, InlineKeyboardMarkup]:
    habits = await service.all_habits(user.id)
    rows = [
        [btn(f"{'🔁' if h.active else '💤'} {clip(h.name, 26)} · {_hm(h)}", f"{M}:open:{h.id}")]
        for h in habits
    ]
    rows.append([btn(t(user.lang, "h.new"), f"{M}:new"), btn(t(user.lang, "back"), f"{M}:home")])
    text = t(user.lang, "h.manage.title" if habits else "h.manage.empty")
    return text, kb(*rows)


def render_detail(user: User, h: Habit, note: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    today = local_today(user.tz)
    lines = [note, ""] if note else []
    lines.append(f"🔁 <b>{html.escape(h.name)}</b>"
                 f"{'' if h.active else t(user.lang, 'h.paused_tag')}")
    lines.append(t(user.lang, "h.sched_line", when=service.window_label(h, user.lang),
                   days=days_mask_label(h.days, user.lang)))
    if h.kind == "interval":
        count, target = service.progress(h, today)
        lines.append(t(user.lang, "h.today_line", done=count, total=target))
    nxt = service.next_reminder(h, user.tz)
    if nxt:
        lines.append(t(user.lang, "h.next", when=_local_human(nxt, today, user.lang)))
    best = service.best_streak(h, today, user.tz)
    lines.append(t(user.lang, "h.streak", now=service.streak(h, today, user.tz), best=best)
                 if best else t(user.lang, "h.no_streak"))
    rate = service.rate_30(h, today, user.tz)
    if rate is not None:
        lines.append(t(user.lang, "h.rate", pct=rate))
    lines += ["", f"<code>{service.last_30(h, today, user.tz)}</code>", t(user.lang, "h.legend")]
    # Today's action first, then the schedule, then everything rare under Edit.
    rows = []
    if service.scheduled_today(h, today):
        if h.kind == "interval":
            rows.append([btn(t(user.lang, "h.plus"), f"{M}:plus:{h.id}"),
                         btn(t(user.lang, "h.minus"), f"{M}:minus:{h.id}")])
        else:
            done = service.logged_today(h, today) == "done"
            rows.append([btn(t(user.lang, "h.mark_undo" if done else "h.mark_done"),
                             f"{M}:dtap:{h.id}")])
    rows.append([btn(t(user.lang, "h.schedule" if h.kind == "interval" else "h.time"),
                     f"{M}:retime:{h.id}")])
    rows.append([btn(t(user.lang, "h.edit"), f"{M}:hedit:{h.id}"),
                 btn(t(user.lang, "back"), f"{M}:manage")])
    return "\n".join(lines), kb(*rows)


def render_edit(user: User, h: Habit) -> tuple[str, InlineKeyboardMarkup]:
    """Rename, days, pause, test, delete - the half you touch once."""
    return t(user.lang, "h.edit_title", name=html.escape(h.name)), kb(
        [btn(t(user.lang, "t.rename"), f"{M}:rename:{h.id}"),
         btn(t(user.lang, "h.days"), f"{M}:redays:{h.id}")],
        [btn(t(user.lang, "h.resume" if not h.active else "h.pause"), f"{M}:toggle:{h.id}"),
         btn(t(user.lang, "h.test"), f"{M}:test:{h.id}")],
        [btn(t(user.lang, "t.delete"), f"{M}:del:{h.id}"),
         btn(t(user.lang, "back"), f"{M}:open:{h.id}")],
    )


def _days_kb(target: str, mask: str, lang: str = "en") -> InlineKeyboardMarkup:
    """Toggle picker. target is "new" (wizard) or a habit id (edit).

    Each button carries the mask it would produce, so no FSM state is needed
    and any combination of days can be picked (e.g. Mon/Wed/Fri).
    """
    presets = [
        btn(f"{'● ' if mask == preset else ''}{t(lang, key)}", f"{M}:pick:{target}:{preset}")
        for key, preset in PRESETS
    ]
    days = []
    for i, label in enumerate(days_short(lang)):
        d = str(i)
        toggled = "".join(sorted(set(mask) ^ {d}))
        days.append(btn(f"{'✅' if d in mask else '▫️'} {label}", f"{M}:pick:{target}:{toggled or '-'}"))
    back = f"{M}:new" if target == "new" else f"{M}:open:{target}"
    return kb(
        presets, days[:4], days[4:],
        [btn(t(lang, "save"), f"{M}:savedays:{target}:{mask or '-'}"), btn(t(lang, "back"), back)],
    )


def _days_prompt(mask: str, lang: str = "en") -> str:
    chosen = days_mask_label(mask, lang) if mask else t(lang, "h.days_none")
    return t(lang, "h.days_q", sel=chosen)


def _local_human(local: datetime, today: date, lang: str = "en") -> str:
    """A wall-clock datetime already in the user's zone."""
    delta = (local.date() - today).days
    if delta == 0:
        return t(lang, "date.today", time=f"{local:%H:%M}")
    if delta == 1:
        return t(lang, "date.tomorrow", time=f"{local:%H:%M}")
    if 0 < delta < 7:
        return f"{days_short(lang)[local.weekday()]} {local:%H:%M}"
    return f"{local.day} {month_short(lang, local.month)} {local:%H:%M}"


async def _load(cq: CallbackQuery, user: User, habit_id: int) -> Habit | None:
    h = await service.get(habit_id, user.id)
    if h is None:
        await cq.answer(t(user.lang, "gone.habit"), show_alert=True)
        text, markup = await render_manage(user)
        await safe_edit(cq, text, reply_markup=markup)
    return h


# ---------- bottom keyboard ----------

async def show_habits(message: Message, state: FSMContext, user: User) -> None:
    text, markup = await render_home(user)
    await message.answer(text, reply_markup=markup)


# ---------- checklist ----------

@router.callback_query(F.data == f"{M}:home")
async def cb_home(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    text, markup = await render_home(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:tap:"))
async def cb_tap(cq: CallbackQuery, user: User) -> None:
    today = local_today(user.tz)
    h = await service.get(int(_parts(cq)[2]), user.id)
    if h is None:
        await cq.answer(t(user.lang, "gone.habit"), show_alert=True)
    elif h.kind == "interval":
        count, target = await service.bump(h.id, today, 1)
        h = await service.get(h.id, user.id)
        if count >= target:
            streak = service.streak(h, today, user.tz) if h else 0
            badge = service.milestone(streak)
            await cq.answer(badge or t(user.lang, "h.target_hit", done=count, total=target), show_alert=bool(badge))
        else:
            await cq.answer(f"💪 {count}/{target}")
    elif service.logged_today(h, today) == "done":
        await service.unlog(h.id, today)
        await cq.answer(t(user.lang, "h.unchecked"))
    else:
        await service.log(h.id, "done", today)
        h = await service.get(h.id, user.id)
        streak = service.streak(h, today, user.tz)
        await cq.answer(
            service.milestone(streak, user.lang) or (
                t(user.lang, "h.streak_toast", n=streak) if streak > 1 else t(user.lang, "h.done_toast")
            ),
            show_alert=bool(service.milestone(streak, user.lang)),
        )
    text, markup = await render_home(user)
    await safe_edit(cq, text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:plus:"))
@router.callback_query(F.data.startswith(f"{M}:minus:"))
async def cb_step(cq: CallbackQuery, user: User) -> None:
    parts = _parts(cq)
    habit_id = int(parts[2])
    if await _load(cq, user, habit_id) is None:
        return
    count, target = await service.bump(habit_id, local_today(user.tz), 1 if parts[1] == "plus" else -1)
    h = await service.get(habit_id, user.id)
    text, markup = render_detail(user, h)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(f"{count}/{target}")


@router.callback_query(F.data.startswith(f"{M}:tdone:"))
async def cb_today_done(cq: CallbackQuery, user: User) -> None:
    """Check-off from the Today screen: stay on the Today screen."""
    from app.core.today import render_today  # imported here: today imports the registry

    today = local_today(user.tz)
    habit_id = int(_parts(cq)[2])
    h = await service.get(habit_id, user.id)
    if h is None:
        await cq.answer(t(user.lang, "gone.habit"), show_alert=True)
        return
    if h.kind == "interval":
        count, target = await service.bump(habit_id, today, 1)
        await cq.answer(f"💪 {count}/{target}" if count < target
                        else t(user.lang, "h.target_hit", done=count, total=target))
    else:
        await service.log(habit_id, "done", today)
        h = await service.get(habit_id, user.id)
        streak = service.streak(h, today, user.tz) if h else 0
        await cq.answer(t(user.lang, "h.streak_toast", n=streak) if streak > 1
                        else t(user.lang, "h.done_toast"))
    text, markup = await render_today(user)
    await safe_edit(cq, text, reply_markup=markup)


# ---------- manage & detail ----------

@router.callback_query(F.data == f"{M}:manage")
async def cb_manage(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    text, markup = await render_manage(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:open:"))
async def cb_open(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    if h := await _load(cq, user, int(_parts(cq)[2])):
        text, markup = render_detail(user, h)
        await safe_edit(cq, text, reply_markup=markup)
        await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:dtap:"))
async def cb_detail_tap(cq: CallbackQuery, user: User) -> None:
    """Check off from the habit's own card and stay on it."""
    today = local_today(user.tz)
    h = await _load(cq, user, int(_parts(cq)[2]))
    if h is None:
        return
    if service.logged_today(h, today) == "done":
        await service.unlog(h.id, today)
        await cq.answer(t(user.lang, "h.unchecked"))
    else:
        await service.log(h.id, "done", today)
        h = await service.get(h.id, user.id)
        streak = service.streak(h, today, user.tz)
        await cq.answer(service.milestone(streak, user.lang)
                        or (t(user.lang, "h.streak_toast", n=streak) if streak > 1
                            else t(user.lang, "h.done_toast")))
    h = await service.get(h.id, user.id)
    text, markup = render_detail(user, h)
    await safe_edit(cq, text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:hedit:"))
async def cb_edit(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    if h := await _load(cq, user, int(_parts(cq)[2])):
        text, markup = render_edit(user, h)
        await safe_edit(cq, text, reply_markup=markup)
        await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:toggle:"))
async def cb_toggle(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    habit_id = int(_parts(cq)[2])
    if h := await _load(cq, user, habit_id):
        await service.update(habit_id, active=not h.active)
        await scheduler.refresh(M)
        h = await service.get(habit_id, user.id)
        text, markup = render_detail(
            user, h, note=t(user.lang, "h.resumed" if h.active else "h.paused_note")
        )
        await safe_edit(cq, text, reply_markup=markup)
        await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:del:"))
async def cb_delete(cq: CallbackQuery, user: User) -> None:
    if h := await _load(cq, user, int(_parts(cq)[2])):
        await safe_edit(
            cq,
            t(user.lang, "h.del_q", name=html.escape(h.name),
              now=service.streak(h, local_today(user.tz), user.tz),
              best=service.best_streak(h, local_today(user.tz), user.tz)),
            reply_markup=kb([btn(t(user.lang, "yes_delete"), f"{M}:delok:{h.id}"),
                             btn(t(user.lang, "keep"), f"{M}:open:{h.id}")]),
        )
        await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:delok:"))
async def cb_delete_ok(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    habit_id = int(_parts(cq)[2])
    if await _load(cq, user, habit_id) is None:
        return
    await service.delete(habit_id)
    await scheduler.refresh(M)
    text, markup = await render_manage(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "deleted"))


# ---------- new habit: name -> time -> days ----------

def _name_prompt(lang: str = "en") -> tuple[str, InlineKeyboardMarkup]:
    tpl = [btn(t(lang, key), f"{M}:tpl:{i}") for i, key in enumerate(TEMPLATE_KEYS)]
    rows = [tpl[i : i + 2] for i in range(0, len(tpl), 2)]
    rows.append([btn(t(lang, "cancel"), f"{M}:home")])
    return t(lang, "h.name_q"), kb(*rows)


def _kind_prompt(name: str, lang: str = "en") -> tuple[str, InlineKeyboardMarkup]:
    return (
        t(lang, "h.kind_q", name=html.escape(name)),
        kb(
            [btn(t(lang, "h.once"), f"{M}:kind:once")],
            [btn(t(lang, "h.many"), f"{M}:kind:many")],
            [btn(t(lang, "cancel"), f"{M}:home")],
        ),
    )


def _time_prompt(name: str, lang: str = "en") -> tuple[str, InlineKeyboardMarkup]:
    return (
        t(lang, "h.time_q", name=html.escape(name)),
        time_kb(f"{M}:nt", back_cb=f"{M}:new", custom_cb=f"{M}:ntc", lang=lang),
    )


def _interval_prompt(target: str, lang: str = "en") -> tuple[str, InlineKeyboardMarkup]:
    rows = [[btn(t(lang, f"h.int.{mins}"), f"{M}:ivl:{target}:{mins}")] for mins in INTERVALS]
    rows.append([btn(t(lang, "back"), f"{M}:new" if target == "new" else f"{M}:open:{target}")])
    return t(lang, "h.interval_q"), kb(*rows)


def _window_prompt(target: str, every: int, lang: str = "en") -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [btn(f"{t(lang, key)} · {(((eh * 60 + em) - (sh * 60 + sm)) // every) + 1}×",
             f"{M}:win:{target}:{every}:{sh:02d}{sm:02d}:{eh:02d}{em:02d}")]
        for key, sh, sm, eh, em in WINDOWS
    ]
    rows.append([btn(t(lang, "h.custom_hours"), f"{M}:winc:{target}:{every}")])
    rows.append([btn(t(lang, "back"), f"{M}:ivlback:{target}")])
    return t(lang, "h.window_q"), kb(*rows)


@router.callback_query(F.data == f"{M}:new")
async def cb_new(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    await state.set_state(NewHabit.name)
    text, markup = _name_prompt(user.lang)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:tpl:"))
async def cb_template(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    name = t(user.lang, TEMPLATE_KEYS[int(_parts(cq)[2])])
    await state.update_data(name=name)
    await state.set_state(None)
    text, markup = _kind_prompt(name, user.lang)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:kind:"))
async def cb_kind(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    data = await state.get_data()
    if "name" not in data:
        await cq.answer(t(user.lang, "expired"), show_alert=True)
        await state.set_state(NewHabit.name)
        text, markup = _name_prompt(user.lang)
        await safe_edit(cq, text, reply_markup=markup)
        return
    if _parts(cq)[2] == "once":
        await state.update_data(kind="daily", every_minutes=0)
        text, markup = _time_prompt(data["name"], user.lang)
    else:
        await state.update_data(kind="interval")
        text, markup = _interval_prompt("new", user.lang)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:ivlback:"))
async def cb_interval_back(cq: CallbackQuery, user: User) -> None:
    text, markup = _interval_prompt(_parts(cq)[2], user.lang)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:ivl:"))
async def cb_interval(cq: CallbackQuery, user: User) -> None:
    _, _, target, every = _parts(cq)
    text, markup = _window_prompt(target, int(every), user.lang)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


async def _apply_window(
    cq: CallbackQuery, state: FSMContext, scheduler: Scheduler, user: User, target: str,
    every: int, sh: int, sm: int, eh: int, em: int,
) -> None:
    if (eh * 60 + em) <= (sh * 60 + sm):
        await cq.answer(t(user.lang, "h.end_after"), show_alert=True)
        return
    if target == "new":
        await state.update_data(hour=sh, minute=sm, end_hour=eh, end_minute=em, every_minutes=every)
        mask = PRESETS[0][1]
        await safe_edit(cq, _days_prompt(mask, user.lang), reply_markup=_days_kb("new", mask, user.lang))
        await cq.answer()
        return
    if await _load(cq, user, int(target)) is None:
        return
    await service.update(int(target), kind="interval", every_minutes=every,
                         hour=sh, minute=sm, end_hour=eh, end_minute=em)
    await scheduler.refresh(M)
    h = await service.get(int(target), user.id)
    text, markup = render_detail(user, h, note=t(user.lang, "h.sched_updated"))
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "saved"))


@router.callback_query(F.data.startswith(f"{M}:win:"))
async def cb_window(cq: CallbackQuery, state: FSMContext, scheduler: Scheduler, user: User) -> None:
    _, _, target, every, start, end = _parts(cq)
    await _apply_window(cq, state, scheduler, user, target, int(every),
                        int(start[:2]), int(start[2:]), int(end[:2]), int(end[2:]))


@router.callback_query(F.data.startswith(f"{M}:winc:"))
async def cb_window_custom(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    _, _, target, every = _parts(cq)
    await state.update_data(win_target=target, win_every=int(every))
    await state.set_state(NewHabit.window if target == "new" else EditHabit.window)
    await safe_edit(
        cq,
        t(user.lang, "h.type_hours"),
        reply_markup=cancel_kb(f"{M}:ivl:{target}:{every}", t(user.lang, "back")),
    )
    await cq.answer()


@router.message(NewHabit.window)
@router.message(EditHabit.window)
async def typed_window(message: Message, state: FSMContext, scheduler: Scheduler, user: User) -> None:
    raw = (message.text or "").replace("–", "-").replace(" to ", "-")
    parts = [p for p in raw.split("-") if p.strip()]
    try:
        if len(parts) != 2:
            raise ParseError(t(user.lang, "h.bad_range"))
        sh, sm = parse_time(parts[0])
        eh, em = parse_time(parts[1])
    except ParseError as e:
        await message.answer(f"🤔 {e}")
        return
    if (eh * 60 + em) <= (sh * 60 + sm):
        await message.answer("🤔 " + t(user.lang, "h.end_after"))
        return
    data = await state.get_data()
    target, every = data.get("win_target", "new"), data.get("win_every", 60)
    await state.set_state(None)
    if target == "new":
        await state.update_data(hour=sh, minute=sm, end_hour=eh, end_minute=em, every_minutes=every)
        mask = PRESETS[0][1]
        await message.answer(_days_prompt(mask, user.lang), reply_markup=_days_kb("new", mask, user.lang))
        return
    if await service.get(int(target), user.id) is None:
        await message.answer(t(user.lang, "gone.habit"))
        return
    await service.update(int(target), kind="interval", every_minutes=every,
                         hour=sh, minute=sm, end_hour=eh, end_minute=em)
    await scheduler.refresh(M)
    h = await service.get(int(target), user.id)
    text, markup = render_detail(user, h, note=t(user.lang, "h.sched_updated"))
    await message.answer(text, reply_markup=markup)


@router.message(NewHabit.name)
async def typed_name(message: Message, state: FSMContext, user: User) -> None:
    name = (message.text or "").strip()[:120]
    if not name:
        await message.answer(t(user.lang, "h.need_name"))
        return
    await state.update_data(name=name)
    await state.set_state(None)
    text, markup = _kind_prompt(name, user.lang)
    await message.answer(text, reply_markup=markup)


async def _to_days(state: FSMContext, hour: int, minute: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    await state.update_data(hour=hour, minute=minute)
    mask = PRESETS[0][1]
    return _days_prompt(mask, lang), _days_kb("new", mask, lang)


@router.callback_query(F.data.startswith(f"{M}:nt:"))
async def cb_new_time(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    if "name" not in await state.get_data():
        await cq.answer(t(user.lang, "expired"), show_alert=True)
        text, markup = _name_prompt(user.lang)
        await state.set_state(NewHabit.name)
        await safe_edit(cq, text, reply_markup=markup)
        return
    hm = _parts(cq)[2]
    text, markup = await _to_days(state, int(hm[:2]), int(hm[2:]), user.lang)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


@router.callback_query(F.data == f"{M}:ntc")
async def cb_new_time_custom(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.set_state(NewHabit.time)
    await safe_edit(cq, t(user.lang, "t.type_time"), reply_markup=cancel_kb(f"{M}:home", t(user.lang, "cancel")))
    await cq.answer()


@router.message(NewHabit.time)
async def typed_new_time(message: Message, state: FSMContext, user: User) -> None:
    try:
        hour, minute = parse_time(message.text or "")
    except ParseError as e:
        await message.answer(f"🤔 {e}")
        return
    await state.set_state(None)
    text, markup = await _to_days(state, hour, minute, user.lang)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:pick:"))
async def cb_pick_days(cq: CallbackQuery, user: User) -> None:
    _, _, target, mask = _parts(cq)
    mask = "" if mask == "-" else mask
    await safe_edit(cq, _days_prompt(mask, user.lang), reply_markup=_days_kb(target, mask, user.lang))
    await cq.answer()


@router.callback_query(F.data.startswith(f"{M}:savedays:"))
async def cb_save_days(cq: CallbackQuery, state: FSMContext, scheduler: Scheduler, user: User) -> None:
    _, _, target, mask = _parts(cq)
    if mask == "-":
        await cq.answer(t(user.lang, "h.pick_day_min"), show_alert=True)
        return
    if target == "new":
        data = await state.get_data()
        if "name" not in data or "hour" not in data:
            await cq.answer(t(user.lang, "expired"), show_alert=True)
            await state.clear()
            text, markup = await render_home(user)
            await safe_edit(cq, text, reply_markup=markup)
            return
        h = await service.create(
            user.id, data["name"], data["hour"], data["minute"], mask,
            kind=data.get("kind", "daily"),
            every_minutes=data.get("every_minutes", 0),
            end_hour=data.get("end_hour", 18),
            end_minute=data.get("end_minute", 0),
        )
        await state.clear()
        await scheduler.refresh(M)
        h = await service.get(h.id, user.id)
        nxt = service.next_reminder(h, user.tz)
        note = t(user.lang, "h.created") + (
            t(user.lang, "h.first_rem", when=_local_human(nxt, local_today(user.tz), user.lang))
            if nxt else ""
        )
    else:
        if await _load(cq, user, int(target)) is None:
            return
        await service.update(int(target), days=mask)
        await scheduler.refresh(M)
        h = await service.get(int(target), user.id)
        note = t(user.lang, "h.days_updated")
    text, markup = render_detail(user, h, note=note)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "saved"))


# ---------- edit: rename, time, days ----------

@router.callback_query(F.data.startswith(f"{M}:rename:"))
async def cb_rename(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    habit_id = int(_parts(cq)[2])
    if await _load(cq, user, habit_id) is None:
        return
    await state.set_state(EditHabit.rename)
    await state.update_data(habit_id=habit_id)
    await safe_edit(cq, t(user.lang, "h.type_name"),
                    reply_markup=cancel_kb(f"{M}:open:{habit_id}", t(user.lang, "cancel")))
    await cq.answer()


@router.message(EditHabit.rename)
async def typed_rename(message: Message, state: FSMContext, user: User) -> None:
    name = (message.text or "").strip()[:120]
    if not name:
        await message.answer(t(user.lang, "h.need_name"))
        return
    data = await state.get_data()
    await state.clear()
    if await service.get(data["habit_id"], user.id) is None:
        await message.answer(t(user.lang, "gone.habit"))
        return
    await service.update(data["habit_id"], name=name)
    h = await service.get(data["habit_id"], user.id)
    text, markup = render_detail(user, h, note=t(user.lang, "t.renamed"))
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:retime:"))
async def cb_retime(cq: CallbackQuery, user: User) -> None:
    if h := await _load(cq, user, int(_parts(cq)[2])):
        if h.kind == "interval":
            text, markup = _interval_prompt(str(h.id), user.lang)
            await safe_edit(cq, text, reply_markup=markup)
            await cq.answer()
            return
        await safe_edit(
            cq,
            t(user.lang, "h.new_time_q", name=html.escape(h.name), when=_hm(h)),
            reply_markup=time_kb(f"{M}:st:{h.id}", back_cb=f"{M}:open:{h.id}",
                                 custom_cb=f"{M}:stc:{h.id}", lang=user.lang),
        )
        await cq.answer()


async def _set_time(habit_id: int, hour: int, minute: int, scheduler: Scheduler, user: User) -> Habit | None:
    await service.update(habit_id, hour=hour, minute=minute)
    await scheduler.refresh(M)
    return await service.get(habit_id, user.id)


@router.callback_query(F.data.startswith(f"{M}:st:"))
async def cb_set_time(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    _, _, habit_id, hm = _parts(cq)
    if await _load(cq, user, int(habit_id)) is None:
        return
    h = await _set_time(int(habit_id), int(hm[:2]), int(hm[2:]), scheduler, user)
    text, markup = render_detail(user, h, note=t(user.lang, "h.time_moved", when=_hm(h)))
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer(t(user.lang, "saved"))


@router.callback_query(F.data.startswith(f"{M}:stc:"))
async def cb_set_time_custom(cq: CallbackQuery, state: FSMContext, user: User) -> None:
    habit_id = int(_parts(cq)[2])
    await state.set_state(EditHabit.time)
    await state.update_data(habit_id=habit_id)
    await safe_edit(cq, "⌨️ <b>Type the time</b>, e.g. <code>06:45</code>", reply_markup=cancel_kb(f"{M}:open:{habit_id}"))
    await cq.answer()


@router.message(EditHabit.time)
async def typed_time(message: Message, state: FSMContext, scheduler: Scheduler, user: User) -> None:
    try:
        hour, minute = parse_time(message.text or "")
    except ParseError as e:
        await message.answer(f"🤔 {e}")
        return
    data = await state.get_data()
    await state.clear()
    if await service.get(data["habit_id"], user.id) is None:
        await message.answer(t(user.lang, "gone.habit"))
        return
    h = await _set_time(data["habit_id"], hour, minute, scheduler, user)
    text, markup = render_detail(user, h, note=t(user.lang, "h.time_moved", when=_hm(h)))
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(f"{M}:redays:"))
async def cb_redays(cq: CallbackQuery, user: User) -> None:
    if h := await _load(cq, user, int(_parts(cq)[2])):
        await safe_edit(cq, _days_prompt(h.days, user.lang), reply_markup=_days_kb(str(h.id), h.days, user.lang))
        await cq.answer()


# ---------- the nudge (pushed message) ----------

def _nudge_day(parts: list[str], today: date) -> date:
    """The day a nudge was for. It travels in the callback, so a Done tapped
    after midnight still credits the right day. Clamped to the last week."""
    try:
        day = datetime.strptime(parts[3], "%Y%m%d").date()
    except (IndexError, ValueError):
        return today
    return day if today - timedelta(days=7) <= day <= today else today


async def fire_nudge(bot: Bot, habit_id: int, test: bool = False) -> None:
    """The scheduled nudge. `test` sends it on demand, ignoring today's log,
    so you can check that notifications actually arrive."""
    from app.core import users

    h = await service.get(habit_id)
    if h is None or (not h.active and not test):
        return
    user = await users.get(h.user_id)
    if user is None or user.blocked:
        return
    lang, today = user.lang, local_today(user.tz)
    if h.snooze_until and not test:
        await service.update(habit_id, snooze_until=None)
    stamp = f"{today:%Y%m%d}"
    name = html.escape(h.name)

    if h.kind == "interval":
        count, target = service.progress(h, today)
        if not test and (service.logged_today(h, today) == "skip" or count >= target):
            return  # target hit, or skipped for today - stay quiet
        await notify.send(
            bot,
            user.id,
            t(lang, "h.push.interval", name=name, done=count, total=target),
            what=f"nudge for habit {habit_id}",
            reply_markup=kb([
                btn(t(lang, "h.push.done_n", n=count + 1, total=target), f"{M}:nbump:{h.id}:{stamp}"),
                btn(t(lang, "h.push.skip"), f"{M}:nskip:{h.id}:{stamp}"),
            ]),
        )
        return

    if service.logged_today(h, today) and not test:
        return
    streak = service.streak(h, today, user.tz)
    tail = (t(lang, "h.push.streak_tail", n=streak) if streak > 1
            else t(lang, "h.push.encourage"))
    later = []
    # A snooze that crosses midnight would land on the wrong day - don't offer it.
    local = local_now(user.tz)
    if (local + timedelta(hours=1)).date() == local.date():
        later.append(btn(t(lang, "h.push.in1h"), f"{M}:nsnz:{h.id}:{stamp}"))
    await notify.send(
        bot,
        user.id,
        t(lang, "h.push.time", name=name) + tail,
        what=f"nudge for habit {habit_id}",
        reply_markup=kb(
            [btn(t(lang, "t.done"), f"{M}:ndone:{h.id}:{stamp}"),
             btn(t(lang, "h.push.skip"), f"{M}:nskip:{h.id}:{stamp}")],
            later,
        ),
    )


@router.callback_query(F.data.startswith(f"{M}:test:"))
async def cb_test(cq: CallbackQuery, user: User) -> None:
    habit_id = int(_parts(cq)[2])
    if await _load(cq, user, habit_id) is None:
        return
    await fire_nudge(cq.bot, habit_id, test=True)
    await cq.answer(t(user.lang, "h.test_sent"), show_alert=True)


async def send_weekly_report(bot: Bot, user_id: int) -> None:
    from app.core import users

    user = await users.get(user_id)
    if user is None or user.blocked:
        return
    if not await service.all_habits(user.id, only_active=True):
        return
    text, _ = await render_stats(user)
    await notify.send(
        bot,
        user.id,
        text + t(user.lang, "h.week.tail"),
        what="weekly habit report",
        reply_markup=kb([btn(t(user.lang, "h.push.open"), f"{M}:home")]),
    )


@router.callback_query(F.data.startswith(f"{M}:ndone:"))
async def cb_nudge_done(cq: CallbackQuery, user: User) -> None:
    parts = _parts(cq)
    habit_id = int(parts[2])
    today = local_today(user.tz)
    if await service.get(habit_id, user.id) is None:
        await cq.answer(t(user.lang, "gone.habit"), show_alert=True)
        return
    await service.log(habit_id, "done", _nudge_day(parts, today))
    h = await service.get(habit_id, user.id)
    streak = service.streak(h, today, user.tz)
    text = t(user.lang, "h.push.did", name=html.escape(h.name))
    if streak > 1:
        text += " " + t(user.lang, "h.streak_toast", n=streak)
    badge = service.milestone(streak, user.lang)
    if badge:
        text += f"\n{badge}"
    await safe_edit(cq, text, reply_markup=kb([btn(t(user.lang, "h.push.open"), f"{M}:home")]))
    await cq.answer(t(user.lang, "h.nice"))


@router.callback_query(F.data.startswith(f"{M}:nbump:"))
async def cb_nudge_bump(cq: CallbackQuery, user: User) -> None:
    parts = _parts(cq)
    habit_id = int(parts[2])
    today = local_today(user.tz)
    if await service.get(habit_id, user.id) is None:
        await cq.answer(t(user.lang, "gone.habit"), show_alert=True)
        return
    count, target = await service.bump(habit_id, _nudge_day(parts, today), 1)
    h = await service.get(habit_id, user.id)
    name = html.escape(h.name)
    if count >= target:
        streak = service.streak(h, today, user.tz)
        badge = service.milestone(streak, user.lang)
        done = t(user.lang, "h.push.finished", name=name, done=count, total=target)
        if streak > 1:
            done += "\n" + t(user.lang, "h.streak_toast", n=streak)
        if badge:
            done += f"\n{badge}"
        await safe_edit(cq, done, reply_markup=kb([btn(t(user.lang, "h.push.open"), f"{M}:home")]))
    else:
        await safe_edit(
            cq, t(user.lang, "h.push.count", name=name, done=count, total=target),
            reply_markup=kb([btn(t(user.lang, "h.push.open"), f"{M}:home")]),
        )
    await cq.answer(t(user.lang, "h.nice"))


@router.callback_query(F.data.startswith(f"{M}:nskip:"))
async def cb_nudge_skip(cq: CallbackQuery, user: User) -> None:
    parts = _parts(cq)
    habit_id = int(parts[2])
    if await service.get(habit_id, user.id) is None:
        await cq.answer(t(user.lang, "gone.habit"), show_alert=True)
        return
    await service.log(habit_id, "skip", _nudge_day(parts, local_today(user.tz)))
    h = await service.get(habit_id, user.id)
    await safe_edit(
        cq, t(user.lang, "h.push.skipped", name=html.escape(h.name)),
        reply_markup=kb([btn(t(user.lang, "h.push.open"), f"{M}:home")]),
    )
    await cq.answer(t(user.lang, "h.skipped"))


@router.callback_query(F.data.startswith(f"{M}:nsnz:"))
async def cb_nudge_snooze(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    parts = _parts(cq)
    habit_id = int(parts[2])
    h = await service.get(habit_id, user.id)
    if h is None:
        await cq.answer(t(user.lang, "gone.habit"), show_alert=True)
        return
    local = local_now(user.tz).replace(second=0, microsecond=0) + timedelta(hours=1)
    if local.date() != _nudge_day(parts, local_today(user.tz)):
        await cq.answer(t(user.lang, "h.push.too_late"), show_alert=True)
        return
    await service.update(habit_id, snooze_until=to_utc(local, user.tz))
    await scheduler.refresh(M)
    await safe_edit(cq, t(user.lang, "h.push.snoozed", name=html.escape(h.name), when=f"{local:%H:%M}"))
    await cq.answer(t(user.lang, "t.snoozed"))