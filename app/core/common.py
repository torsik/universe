from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.registry import discover
from app.core.scheduler import Scheduler
from app.core.ui import main_menu, safe_edit

router = Router(name="core")

GREETING = (
    "<b>Universe</b> - your assistant.\n\nPick something below, "
    "or use /menu any time to come back here."
)


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(GREETING, reply_markup=main_menu())


@router.callback_query(F.data == "menu")
async def cb_menu(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit(cq, GREETING, reply_markup=main_menu())
    await cq.answer()


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    """Each module contributes its own block - no module knows about the others."""
    blocks = []
    for mod in discover():
        if mod.digest is None:
            continue
        try:
            block = await mod.digest()
        except Exception:
            logging.getLogger(__name__).exception("digest failed for %s", mod.name)
            continue
        if block:
            blocks.append(block)
    text = "\n\n".join(blocks) if blocks else "Nothing on. Clear day. \U0001F31E"
    await message.answer(f"<b>Today</b>\n\n{text}", reply_markup=main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu())


@router.message(Command("jobs"))
async def cmd_jobs(message: Message, scheduler: Scheduler) -> None:
    """Debug view: what is actually scheduled right now."""
    jobs = sorted(scheduler.jobs, key=lambda j: j.id)
    if not jobs:
        await message.answer("No jobs scheduled.")
        return
    lines = [
        f"<code>{j.id}</code> - next: {j.next_run_time:%Y-%m-%d %H:%M}"
        if j.next_run_time
        else f"<code>{j.id}</code> - paused"
        for j in jobs
    ]
    await message.answer("<b>Scheduled jobs</b>\n" + "\n".join(lines))
