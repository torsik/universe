from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.core.i18n import days_short, month_short, t
from app.db import local_now, now, to_local, to_utc

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


def parse_future(text: str, tz: str) -> datetime:
    """parse_when, but a deadline in the past is an input error, not a reminder."""
    when = parse_when(text, tz)
    if when <= now():
        raise ParseError(f"That's in the past ({human(when, tz)}). Try a later time.")
    return when


def parse_when(text: str, tz: str) -> datetime:
    """What the user typed, read in their zone, returned as UTC."""
    try:
        return to_utc(_parse_when(text, tz), tz)
    except ParseError:
        raise
    except ValueError:  # '31/02 10:00' - shaped right, not a real date
        raise ParseError("That date doesn't exist.") from None


def _parse_when(text: str, tz: str) -> datetime:
    """Flexible one-off reminder times.

    Accepts: 'in 90m', 'in 2h', '18:00', 'tomorrow 18:00', 'fri 09:00',
    '2026-09-20 18:00', '20/09 18:00'.
    """
    raw = text.strip().lower()
    base = local_now(tz)

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


def human(when: datetime, tz: str, lang: str = "en") -> str:
    dt = to_local(when, tz)
    delta = (dt.date() - local_now(tz).date()).days
    if delta == 0:
        return t(lang, "date.today", time=f"{dt:%H:%M}")
    if delta == 1:
        return t(lang, "date.tomorrow", time=f"{dt:%H:%M}")
    if 0 < delta < 7:
        return f"{days_short(lang)[dt.weekday()]} {dt:%H:%M}"
    return f"{dt.day} {month_short(lang, dt.month)} {dt:%H:%M}"


def days_mask_label(mask: str, lang: str = "en") -> str:
    if mask == "0123456":
        return t(lang, "h.daily_label")
    if mask == "01234":
        return t(lang, "h.weekdays")
    if mask == "56":
        return t(lang, "h.weekends")
    return ", ".join(days_short(lang)[int(d)] for d in mask)


def mask_to_cron(mask: str) -> str:
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return ",".join(names[int(d)] for d in mask)


MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def long_date(when: datetime, tz: str, lang: str = "en") -> str:
    """'Tue 22 Sep, 09:00' in the user's zone and language."""
    dt = to_local(when, tz)
    return f"{days_short(lang)[dt.weekday()]} {dt.day} {month_short(lang, dt.month)}, {dt:%H:%M}"


def relative(dt: datetime, lang: str = "en") -> str:
    """'in 3 h', 'in 2 days', '20 min ago'."""
    secs = (dt - now()).total_seconds()
    mins = abs(secs) / 60
    if mins < 60:
        span = t(lang, "date.min", n=max(1, round(mins)))
    elif mins < 60 * 24:
        span = t(lang, "date.hour", n=round(mins / 60))
    else:
        span = t(lang, "date.day", n=round(mins / 1440))
    return t(lang, "date.in" if secs >= 0 else "date.ago", span=span)


def _at(day, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute)


def quick_options(tz: str, lang: str = "en") -> list[tuple[str, str]]:
    """(code, label) for one-tap due times, labelled relative to their now."""
    # Four at most: the calendar covers everything else, and a wall of
    # near-identical buttons is harder to read than two rows.
    hour = local_now(tz).hour
    codes = ["1h"] + (["eve"] if hour < 19 else ["3h"]) + ["tm9"]
    return [(code, t(lang, f"t.q.{code}")) for code in codes]


def quick_when(code: str, tz: str) -> datetime:
    """Resolve a quick code at tap time, so a stale button still means the
    obvious thing (a 'Tonight' tapped after 20:00 rolls to tomorrow). -> UTC."""
    n = local_now(tz).replace(second=0, microsecond=0)
    today = n.date()
    if code == "1h":
        local = n + timedelta(hours=1)
    elif code == "3h":
        local = n + timedelta(hours=3)
    elif code == "eve":
        t = _at(today, 20)
        local = t if t > n else t + timedelta(days=1)
    elif code == "tm9":
        local = _at(today + timedelta(days=1), 9)
    elif code == "tm18":
        local = _at(today + timedelta(days=1), 18)
    elif code == "mon9":
        ahead = (0 - today.weekday()) % 7 or 7
        local = _at(today + timedelta(days=ahead), 9)
    else:
        raise ParseError(f"unknown quick time {code!r}")
    return to_utc(local, tz)
