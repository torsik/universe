"""Reusable inline pickers. Callers pass a callback prefix; the pickers append
their own suffixes, so any module can host a calendar or a time grid."""
from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import InlineKeyboardMarkup

from app.core.dates import MONTHS
from app.core.ui import NOOP, btn, kb

TIMES = ["07:00", "08:00", "09:00", "10:00", "12:00", "15:00", "18:00", "20:00", "21:00", "22:00"]


def calendar_kb(prefix: str, year: int, month: int, *, today: date, back_cb: str) -> InlineKeyboardMarkup:
    """Month grid. Navigation -> f"{prefix}:m:YYYYMM", pick -> f"{prefix}:d:YYYYMMDD".

    Past days are shown but inert, so the grid keeps its shape.
    """
    prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
    next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)
    at_start = (year, month) <= (today.year, today.month)

    rows = [[
        btn(" " if at_start else "◀️", NOOP if at_start else f"{prefix}:m:{prev_y}{prev_m:02d}"),
        btn(f"{MONTHS[month - 1]} {year}", NOOP),
        btn("▶️", f"{prefix}:m:{next_y}{next_m:02d}"),
    ]]
    rows.append([btn(d, NOOP) for d in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]])
    for week in calendar.monthcalendar(year, month):
        # Weeks entirely in the past are just noise: drop them.
        if all(day == 0 or date(year, month, day) < today for day in week):
            continue
        row = []
        for day in week:
            if day == 0:
                row.append(btn(" ", NOOP))
                continue
            d = date(year, month, day)
            if d < today:
                row.append(btn("·", NOOP))
            else:
                label = f"•{day}•" if d == today else str(day)
                row.append(btn(label, f"{prefix}:d:{d:%Y%m%d}"))
        rows.append(row)
    rows.append([btn("◀️ Back", back_cb)])
    return kb(*rows)


def time_kb(prefix: str, *, back_cb: str, custom_cb: str, after: tuple[int, int] | None = None) -> InlineKeyboardMarkup:
    """Grid of common times -> f"{prefix}:HHMM". `after` hides times already
    past (used when the chosen day is today)."""
    times = [t for t in TIMES if after is None or tuple(map(int, t.split(":"))) > after]
    cells = [btn(t, f"{prefix}:{t.replace(':', '')}") for t in times]
    rows = [cells[i : i + 4] for i in range(0, len(cells), 4)]
    rows.append([btn("⌨️ Other time", custom_cb), btn("◀️ Back", back_cb)])
    return kb(*rows)
