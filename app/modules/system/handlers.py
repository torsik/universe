from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.config import settings
from app.core import notify, users
from app.core.scheduler import SWEEP_MINUTES, Scheduler
from app.core.ui import btn, clip, kb, safe_edit
from app.core.users import User
from app.db import local_now, to_local
from app.modules.system import service

log = logging.getLogger(__name__)
router = Router(name="system")
M = "system"
MORE_BTN = "⚙️ More"


def is_admin(user: User) -> bool:
    return user.id == settings.owner_id


def render_more(user: User) -> tuple[str, InlineKeyboardMarkup]:
    rows = [[btn("🌍 My timezone", f"{M}:tz"), btn("📤 Export my data", f"{M}:export")]]
    if is_admin(user):
        rows.append([btn("👥 Users", f"{M}:users"), btn("💾 Backups", f"{M}:backups")])
        rows.append([btn("📊 Scheduled jobs", f"{M}:jobs"), btn("ℹ️ Status", f"{M}:about")])
    rows.append([btn("🗑 Delete my account", f"{M}:wipe")])
    return (
        f"⚙️ <b>More</b>\n\n🌍 Timezone: <b>{user.tz}</b>\n"
        f"🕐 Your local time: <b>{local_now(user.tz):%H:%M}</b>",
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
async def cb_timezone(cq: CallbackQuery) -> None:
    from app.core.common import ZONE_PROMPT, zone_kb

    await safe_edit(cq, ZONE_PROMPT, reply_markup=zone_kb())
    await cq.answer()


# ---------- export / delete my data ----------

@router.callback_query(F.data == f"{M}:export")
async def cb_export(cq: CallbackQuery, user: User) -> None:
    """Their own rows only - never the shared database file."""
    from app.modules.habits import service as habits
    from app.modules.todo import service as todo

    await cq.answer("Collecting…")
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
        what="export", caption="📤 Your tasks and habits.",
    )


@router.callback_query(F.data == f"{M}:wipe")
async def cb_wipe(cq: CallbackQuery) -> None:
    await safe_edit(
        cq,
        "🗑 <b>Delete your account?</b>\n\n"
        "Every task, habit and day of history you have goes with it. "
        "This can't be undone.",
        reply_markup=kb([btn("🗑 Yes, delete everything", f"{M}:wipeok"), btn("✖️ Keep it", f"{M}:more")]),
    )
    await cq.answer()


@router.callback_query(F.data == f"{M}:wipeok")
async def cb_wipe_ok(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    await users.delete(user.id)
    await scheduler.refresh()
    await safe_edit(cq, "Everything is gone. Send /start if you ever want to come back.")
    await cq.answer("Deleted")


# ---------- admin ----------

@router.callback_query(F.data == f"{M}:users")
async def cb_users(cq: CallbackQuery, user: User) -> None:
    if not is_admin(user):
        await cq.answer("Admins only.", show_alert=True)
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


@router.callback_query(F.data == f"{M}:backups")
async def cb_backups(cq: CallbackQuery, user: User) -> None:
    if not is_admin(user):
        await cq.answer("Admins only.", show_alert=True)
        return
    files = service.existing()
    lines = ["💾 <b>Backups on the server</b>", f"<code>{service.backup_dir()}</code>", ""]
    lines += [f"• {f.name} · {round(f.stat().st_size / 1024)} KB" for f in files] or ["Nothing yet."]
    lines.append("\n<i>Made daily at 04:30, last 7 kept.</i>")
    await safe_edit(
        cq, "\n".join(lines),
        reply_markup=kb(
            [btn("💾 Back up now", f"{M}:backup")],
            [btn("📥 Send me the latest", f"{M}:fetch"), btn("◀️ Back", f"{M}:more")],
        ),
    )
    await cq.answer()


@router.callback_query(F.data == f"{M}:backup")
async def cb_backup(cq: CallbackQuery, user: User) -> None:
    if not is_admin(user):
        await cq.answer("Admins only.", show_alert=True)
        return
    await cq.answer("Backing up…")
    try:
        path = await service.make_backup()
    except Exception as e:
        log.exception("backup failed")
        await cq.message.answer(f"⚠️ Backup failed: {e}")
        return
    await cb_backups(cq, user)
    await cq.message.answer(f"✅ Saved <code>{path.name}</code> on the server.")


@router.callback_query(F.data == f"{M}:fetch")
async def cb_fetch(cq: CallbackQuery, user: User) -> None:
    """Hand the newest copy over - the whole database, so admins only."""
    if not is_admin(user):
        await cq.answer("Admins only.", show_alert=True)
        return
    files = service.existing()
    if not files:
        await cq.answer("No backups yet. Make one first.", show_alert=True)
        return
    from aiogram.types import FSInputFile

    await cq.answer("Sending…")
    await notify.send_document(
        cq.bot, user.id, FSInputFile(files[0], filename=files[0].name),
        what="backup download",
        caption="💾 Restore: stop the bot, put this at <code>data/universe.db</code>, start it again.",
    )


@router.callback_query(F.data == f"{M}:jobs")
async def cb_jobs(cq: CallbackQuery, scheduler: Scheduler, user: User) -> None:
    if not is_admin(user):
        await cq.answer("Admins only.", show_alert=True)
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
        reply_markup=kb([btn("◀️ Back", f"{M}:more")]),
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
        await cq.answer("Admins only.", show_alert=True)
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
        reply_markup=kb([btn("◀️ Back", f"{M}:more")]),
    )
    await cq.answer()


# ---------- scheduled ----------

async def daily_backup(bot: Bot) -> None:
    path = await service.make_backup()
    log.info("daily backup written: %s", path)
