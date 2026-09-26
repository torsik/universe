from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.config import settings
from app.core import notify, users
from app.core.i18n import t
from app.core.scheduler import SWEEP_MINUTES, Scheduler
from app.core.ui import btn, clip, kb, safe_edit
from app.core.users import User
from app.db import local_now, to_local
from app.modules.system import service

log = logging.getLogger(__name__)
router = Router(name="system")
M = "system"
MORE_KEY = "btn.more"


def is_admin(user: User) -> bool:
    return user.id == settings.owner_id


def render_more(user: User) -> tuple[str, InlineKeyboardMarkup]:
    rows = [[btn(t(user.lang, "lang.button"), f"{M}:lang"), btn(t(user.lang, "s.tz"), f"{M}:tz")],
            [btn(t(user.lang, "s.export"), f"{M}:export")]]
    if is_admin(user):
        rows.append([btn(t(user.lang, "s.users"), f"{M}:users")])
        rows.append([btn(t(user.lang, "s.jobs"), f"{M}:jobs"), btn(t(user.lang, "s.status"), f"{M}:about")])
    rows.append([btn(t(user.lang, "s.wipe"), f"{M}:wipe")])
    return (
        t(user.lang, "s.title", tz=user.tz, time=f"{local_now(user.tz):%H:%M}"),
        kb(*rows),
    )


async def show_more(message: Message, state: FSMContext, user: User) -> None:
    text, markup = render_more(user)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == f"{M}:more")
async def cb_more(cq: CallbackQuery, user: User) -> None:
    text, markup = render_more(user)
    await safe_edit(cq, text, reply_markup=markup)
    await cq.answer()


# ---------- timezone ----------

@router.callback_query(F.data == f"{M}:tz")
async def cb_timezone(cq: CallbackQuery, user: User) -> None:
    from app.core.common import zone_kb

    await safe_edit(cq, t(user.lang, "zone.prompt"), reply_markup=zone_kb(user.lang))
    await cq.answer()


@router.callback_query(F.data == f"{M}:lang")
async def cb_language(cq: CallbackQuery, user: User) -> None:
    from app.core.common import lang_kb

    await safe_edit(cq, t(user.lang, "lang.prompt"), reply_markup=lang_kb())
    await cq.answer()


# ---------- export / delete my data ----------

@router.callback_query(F.data == f"{M}:export")
async def cb_export(cq: CallbackQuery, user: User) -> None:
    """Their own rows only - never the shared database file."""
    from app.modules.habits import service as habits
    from app.modules.todo import service as todo

    await cq.answer(t(user.lang, "s.collecting"))
    lines = [f"# Universe export · {local_now(user.tz):%Y-%m-%d %H:%M} · {user.tz}", "", "## Tasks"]
    for item in await todo.open_items(user.id):
        due = to_local(item.due_at, user.tz).strftime("%Y-%m-%d %H:%M") if item.due_at else "-"
        lines.append(f"- [ ] {item.text} · due {due}" + (f" · repeats {item.repeat}" if item.repeat else ""))
    for item in await todo.done_items(user.id, limit=100):
        lines.append(f"- [x] {item.text}")
    lines += ["", "## Habits"]
    for h in await habits.all_habits(user.id):
        lines.append(f"- {h.name} · {habits.window_label(h)} · {h.days}"
                     f"{'' if h.active else ' · paused'}")
        for entry in sorted(h.logs, key=lambda l: l.day):
            lines.append(f"    {entry.day} {entry.status} x{entry.count}")
    from aiogram.types import BufferedInputFile

    data = "\n".join(lines).encode()
    await notify.send_document(
        cq.bot, user.id,
        BufferedInputFile(data, filename=f"universe-export-{local_now(user.tz):%Y%m%d}.md"),
        what="export", caption=t(user.lang, "s.export_caption"),
    )


@router.callback_query(F.data == f"{M}:wipe")
async def cb_wipe(cq: CallbackQuery, user: User) -> None:
    await safe_edit(
        cq,
        t(user.lang, "s.wipe_q"),
        reply_markup=kb([btn(t(user.lang, "s.wipe_ok"), f"{M}:wipeok"),
                         btn(t(user.lang, "keep"), f"{M}:more")]),
    )
    await cq.answer()


@router.callback_query(F.data == f"{M}:wipeok")
async def cb_wipe_ok(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    await users.delete(user.id)
    await scheduler.refresh()
    await safe_edit(cq, t(user.lang, "s.wiped"))
    await cq.answer(t(user.lang, "deleted"))


# ---------- admin ----------

@router.callback_query(F.data == f"{M}:users")
async def cb_users(cq: CallbackQuery, user: User) -> None:
    if not is_admin(user):
        await cq.answer(t(user.lang, "admins_only"), show_alert=True)
        return
    from app.modules.habits import service as habits
    from app.modules.todo import service as todo

    rows = await users.all_users(only_active=False)
    lines = [f"👥 <b>Users</b> · {len(rows)} of {settings.max_users}", ""]
    for u in rows:
        tasks = len(await todo.open_items(u.id))
        habs = len(await habits.all_habits(u.id))
        who = html.escape(u.first_name or str(u.id))
        tag = f" @{html.escape(u.username)}" if u.username else ""
        flags = " 🚫 blocked" if u.blocked else ""
        lines.append(f"• <b>{clip(who, 20)}</b>{tag}{flags}\n"
                     f"   {u.tz} · {tasks} task(s), {habs} habit(s) · seen {u.last_seen_at:%d %b}")
    await safe_edit(cq, "\n".join(lines), reply_markup=kb([btn("◀️ Back", f"{M}:more")]))
    await cq.answer()


@router.callback_query(F.data == f"{M}:jobs")
async def cb_jobs(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    if not is_admin(user):
        await cq.answer(t(user.lang, "admins_only"), show_alert=True)
        return
    jobs = sorted(scheduler.jobs, key=lambda j: j.id)
    shown = jobs[:25]
    lines = [
        f"<code>{j.id}</code> → {to_local(j.next_run_time.replace(tzinfo=None), user.tz):%a %d %b %H:%M}"
        if getattr(j, "next_run_time", None)
        else f"<code>{j.id}</code>"
        for j in shown
    ] or ["Nothing scheduled."]
    if len(jobs) > len(shown):
        lines.append(f"<i>…and {len(jobs) - len(shown)} more</i>")
    await safe_edit(
        cq, f"📊 <b>Scheduled jobs</b> · {len(jobs)}\n" + "\n".join(lines),
        reply_markup=kb([btn(t(user.lang, "back"), f"{M}:more")]),
    )
    await cq.answer()


def _failures_block() -> str:
    """Recent delivery or job failures, so a silent breakage is visible."""
    if not notify.FAILURES:
        return "\n✅ No delivery problems since the last restart"
    lines = ["\n⚠️ <b>Recent problems</b>"]
    for when, what, detail in list(notify.FAILURES)[-3:]:
        lines.append(f"<i>{when:%d %b %H:%M} UTC</i> · {what}\n   <code>{detail[:80]}</code>")
    return "\n".join(lines)


@router.callback_query(F.data == f"{M}:about")
async def cb_about(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    if not is_admin(user):
        await cq.answer(t(user.lang, "admins_only"), show_alert=True)
        return
    from app.modules.habits import service as habits
    from app.modules.todo import service as todo

    everyone = await users.all_users(only_active=False)
    tasks = sum(len(await todo.open_items(u.id)) for u in everyone)
    habs = sum(len(await habits.all_habits(u.id)) for u in everyone)
    await safe_edit(
        cq,
        "ℹ️ <b>Status</b>\n\n"
        f"👥 {len(everyone)} user(s) of {settings.max_users}\n"
        f"📝 {tasks} open task(s) · 🔁 {habs} habit(s)\n"
        f"💾 Database: {service.db_size_kb()} KB · {len(service.existing())} backup(s)\n"
        f"⏱ {len(scheduler.jobs)} scheduled job(s), re-checked every {SWEEP_MINUTES} min\n"
        + _failures_block(),
        reply_markup=kb([btn(t(user.lang, "back"), f"{M}:more")]),
    )
    await cq.answer()


# ---------- scheduled ----------

async def daily_backup(bot: Bot) -> None:
    path = await service.make_backup()
    log.info("daily backup written: %s", path)
