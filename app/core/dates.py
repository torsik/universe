from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.db import now

WEEKDAYS = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ParseError(ValueError):
    pass


def parse_time(text: str) -> tuple[int, int]:
    """'8', '08:00', '8.00', '2030' -> (hour, minute)."""
    t = text.strip().replace(".", ":")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", t) or re.fullmatch(r"(\d{2})(\d{2})", t)
    if not m:
        raise ParseError("Use a time like <code>08:00</code> or <code>21:30</code>.")
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ParseError("That is not a real time of day.")
    return hour, minute


def parse_future(text: str) -> datetime:
    """parse_when, but a deadline in the past is an input error, not a reminder."""
    when = parse_when(text)
    if when <= now():
        raise ParseError(f"That's in the past ({human(when)}). Try a later time.")
    return when


def parse_when(text: str) -> datetime:
    try:
        return _parse_when(text)
    except ParseError:
        raise
    except ValueError:  # '31/02 10:00' - shaped right, not a real date
        raise ParseError("That date doesn't exist.") from None


def _parse_when(text: str) -> datetime:
    """Flexible one-off reminder times.

    Accepts: 'in 90m', 'in 2h', '18:00', 'tomorrow 18:00', 'fri 09:00',
    '2026-09-20 18:00', '20/09 18:00'.
    """
    raw = text.strip().lower()
    base = now()

    m = re.fullmatch(r"in\s+(\d+)\s*(m|min|mins|minutes|h|hr|hrs|hours|d|days?)", raw)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        base = base.replace(second=0, microsecond=0)
        if unit.startswith("m"):
            return base + timedelta(minutes=n)
        if unit.startswith("h"):
            return base + timedelta(hours=n)
        return base + timedelta(days=n)

    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[\s,]+(.+)", raw)
    if m:
        h, mi = parse_time(m.group(2))
        d = datetime.strptime(m.group(1), "%Y-%m-%d")
        return d.replace(hour=h, minute=mi)

    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[\s,]+(.+)", raw)
    if m:
        h, mi = parse_time(m.group(3))
        day, month = int(m.group(1)), int(m.group(2))
        year = base.year + (1 if (month, day) < (base.month, base.day) else 0)
        return datetime(year, month, day, h, mi)

    m = re.fullmatch(r"(today|tomorrow|tmr)(?:[\s,]+(.+))?", raw)
    if m:
        h, mi = parse_time(m.group(2)) if m.group(2) else (9, 0)
        day = base + (timedelta(days=1) if m.group(1) != "today" else timedelta())
        return day.replace(hour=h, minute=mi, second=0, microsecond=0)

    m = re.fullmatch(r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*(?:[\s,]+(.+))?", raw)
    if m:
        h, mi = parse_time(m.group(2)) if m.group(2) else (9, 0)
        ahead = (WEEKDAYS[m.group(1)] - base.weekday()) % 7 or 7
        day = base + timedelta(days=ahead)
        return day.replace(hour=h, minute=mi, second=0, microsecond=0)

    h, mi = parse_time(raw)  # bare time -> next occurrence
    cand = base.replace(hour=h, minute=mi, second=0, microsecond=0)
    return cand if cand > base else cand + timedelta(days=1)


def human(dt: datetime) -> str:
    today = now().date()
    delta = (dt.date() - today).days
    if delta == 0:
        return f"today {dt:%H:%M}"
    if delta == 1:
        return f"tomorrow {dt:%H:%M}"
    if 0 < delta < 7:
        return f"{DAY_LABELS[dt.weekday()]} {dt:%H:%M}"
    return f"{dt:%d %b} {dt:%H:%M}"


def days_mask_label(mask: str) -> str:
    if mask == "0123456":
        return "every day"
    if mask == "01234":
        return "weekdays"
    if mask == "56":
        return "weekends"
    return ", ".join(DAY_LABELS[int(d)] for d in mask)


def mask_to_cron(mask: str) -> str:
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return ",".join(names[int(d)] for d in mask)
