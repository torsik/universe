# Universe

A personal Telegram assistant. Single user, single container, SQLite on disk.

## Modules

| Module | What it does |
|---|---|
| 📝 **To-Do** | Open list, optional reminders that arrive as a message with a Done button |
| 🔁 **Habits** | Scheduled nudges, Done/Skip logging, streaks and a 30-day history strip |

Commands: `/menu` · `/add buy milk @ tomorrow 18:00` · `/today` · `/jobs` · `/cancel`

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

The menu is generated from a registry, so a new feature is one folder:

```
app/modules/<name>/
  models.py     SQLAlchemy models (inherit from app.db.Base)
  service.py    data access, no Telegram types
  handlers.py   aiogram router
  module.py     MODULE = ModuleSpec(name=, title=, router=, schedule=, digest=)
```

`schedule` is optional and receives a `ScheduleContext` to declare cron/one-shot
jobs. `digest` is optional and contributes a block to `/today`. Drop the folder
in, restart — it appears in the menu, its tables are created, its jobs are
registered. Nothing else needs editing.

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

**Times are naive local** in the configured `TZ`. SQLite has no timezone-aware
type, so storing naive local consistently beats mixing UTC and local.

## Backup

Everything is in `data/universe.db`. Copy it.

```bash
docker compose exec universe sqlite3 /app/data/universe.db ".backup '/app/data/backup.db'"
```
