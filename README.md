# Universe

A Telegram assistant for a small group (up to MAX_USERS, default 50).
One container, SQLite on disk, each person with their own data and timezone.

## How it works

No commands. Everything is on buttons, plus one shortcut: **type anything and
it becomes a task.**

The keyboard at the bottom of the chat is always there:

| Button | Opens |
|---|---|
| ☀️ **Today** | Tasks due today and overdue, today's habits with one-tap check-off |
| ➕ **New task** | Asks what to add (typing a task anywhere works too) |
| 📝 **Tasks** | Your list, grouped into Overdue / Today / Upcoming / Anytime |
| 🔁 **Habits** | Today's checklist with a progress bar and streaks |
| ⚙️ **More** | Backup, scheduled jobs, status |

**English and Russian.** The first `/start` asks for a language (pre-picked
from the Telegram client's own), then the timezone. Both can be changed later
in ⚙️ More. All interface text lives in `app/core/i18n.py`, one key with both
languages side by side.

**Each person has their own data.** The first `/start` registers you and asks
for your timezone; everything after that runs on your local clock. Nobody can
see or touch anyone else's tasks — buttons are checked against their owner, not
just their id. The admin (`OWNER_ID`) additionally gets a Users screen, the
backups and failure alerts.

**Screens stay shallow.** A task's card shows one prominent Done, the due time
on its own button, and everything rarer (rename, reminder, repeat, delete)
behind a single Edit — four buttons instead of seven. Habits work the same way.

**Tasks.** Add by typing: one line per task, bullets and numbers are stripped.
Pick a due time with one tap (in 1 hour, tonight, tomorrow), from a calendar,
or by typing (`fri 18:00`, `25/12 10:00`). For a deadline more than a day out it
then asks how early to — at the deadline, 10 minutes, an hour, 3 hours, a day or two days
before — and you get both the heads-up and the deadline reminder, each with
Done and snooze buttons. Tasks can repeat daily, weekly, monthly or yearly:
completing one creates the next occurrence automatically, keeping its reminder
settings. Completing offers Undo; completed tasks can be brought back.

**Habits.** Two kinds:

- *Once a day* — a reminder at a set time, checked off with one tap.
- *Several times a day* — every 30 minutes, hour, 2 or 3 hours between two
  hours of your choosing (e.g. push-ups every hour from 09:00 to 18:00). Each
  step sends its own reminder, and the day counts up: 3/10, 4/10. The day only
  counts as done once you hit the target, so the streak means what it says.
  "Skip today" silences the rest of the day's reminders.

Both pick any days (every day, weekdays or a mix like Mon/Wed/Fri). Each habit
shows its current and best streak, a completion rate and a 30-day history
(▓ done, ▒ partial, ░ skipped, ✗ missed), and has a "Test reminder" button that
fires it immediately so you can check notifications. Milestones at 7, 30, 100
and 365 days get called out. **📊 This week** compares this week against last;
the same report arrives every Sunday at 19:00.

**⚙️ More.** Your timezone, an export of your own tasks and habits as a text
file, and deleting your account with everything in it.

**Backups are server-side and silent.** A consistent copy of the database is
written to `data/backups/` every day at 04:30 and the last 7 are kept. Nothing
is ever sent into a chat: the file holds everyone's data. To restore: stop the
bot, put the file at `data/universe.db`, start it again. Individuals can export
their own tasks and habits as a text file from ⚙️ More.

`/start` brings the keyboard back if you ever hide it. The bot publishes its
own profile description on boot (`publish_profile` in `app/main.py`), so a new
person sees what it does before pressing Start.
## Setup

1. `@BotFather` → `/newbot` → copy the token.
2. `@userinfobot` → copy your numeric id.
3. Configure and run:

```bash
cp .env.example .env
```

Fill in `BOT_TOKEN` and `OWNER_ID`, then set `PUID`/`PGID` to your own ids —
the container writes to the bind-mounted `data/`, and without matching ids it
cannot create the database:

```bash
echo "PUID=$(id -u)" >> .env && echo "PGID=$(id -g)" >> .env
```

```bash
docker compose up -d --build
```

```bash
docker compose logs -f
```

Anyone who isn't `OWNER_ID` is silently ignored.

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.main
```

## Adding a module

The keyboard, the Today screen and the schedule are generated from a registry,
so a new feature is one folder:

```
app/modules/<name>/
  models.py     SQLAlchemy models (inherit from app.db.Base)
  service.py    data access, no Telegram types
  handlers.py   aiogram router
  module.py     MODULE = ModuleSpec(...)
```

`ModuleSpec` fields, all optional except the first three:

- `buttons`: labels for the bottom keyboard and what each one does
- `schedule`: receives a `ScheduleContext` to declare cron or one-shot jobs
- `digest`: returns a `Digest` (text + buttons) for the Today screen
- `fallback`: a router tried after every module router, for catch-alls

Drop the folder in and restart. Its buttons appear, its tables are created,
its jobs are registered. Nothing else needs editing.

## Design notes

**Jobs are derived state.** APScheduler runs in memory and the entire schedule
is rebuilt from the database at boot and after every edit (`scheduler.refresh(module)`).
One source of truth, and no pickled job surviving a restart pointing at a habit
you deleted.

**Reminders survive downtime.** Scheduled jobs live in memory, so a reminder
whose moment passed while the bot was off would be lost. Each to-do carries a
`notified_at`; anything due-but-unannounced fires 30 seconds after boot, and the
flag is what stops it arriving twice. Re-arming the time clears it.

**Schema changes are additive.** `create_all` creates missing tables but never
missing columns, so `init_db` also ALTERs in any new nullable column on boot.
A rename, a type change or a new NOT NULL logs an error instead — that is the
point at which this deserves real migrations (Alembic).

**Pushes retry, and a lost one is re-sent.** Everything the bot sends on its
own goes through `core/notify.py`: 3 attempts (2s, 5s, 15s) for network and
server errors, no retry for a blocked chat. A reminder is flagged as sent only
after it actually arrived, and every 15 minutes the scheduler re-derives its
jobs from the database — so a reminder lost to a network blip goes out within
15 minutes instead of waiting for a restart. Failures are recorded and shown on
⚙️ More → Status, and a crashed background job messages the owner.

**A tap made while the bot was down still counts.** Pending updates are not
discarded at startup; messages older than an hour are ignored so a long outage
doesn't replay a day-old backlog as new tasks.

**Times are stored in UTC**, and each user's zone is applied only for display
and for reading what they type. Habit reminders are cron jobs in the owner's
zone, so "21:00" means 21:00 where they live, across daylight-saving changes.
Habit history is keyed by their local calendar date.

## Backup

Everything is in `data/universe.db`. Copy it.

```bash
docker compose exec universe sqlite3 /app/data/universe.db ".backup '/app/data/backup.db'"
```
