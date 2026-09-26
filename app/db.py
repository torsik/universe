from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import logging

from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Every module's models inherit from this so create_all sees them."""


class Meta(Base):
    """Tiny key/value table: records that a one-off migration already ran."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), default="")


Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.db_url, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record) -> None:
    """WAL + foreign keys. WAL matters: the scheduler writes while handlers read."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def _literal_default(col) -> str | None:
    """The column's default as SQL, or None if it has no static one."""
    if col.server_default is not None:
        return str(col.server_default.arg)
    arg = getattr(col.default, "arg", None) if col.default is not None else None
    if arg is None or callable(arg):
        return None
    if isinstance(arg, bool):
        return "1" if arg else "0"
    if isinstance(arg, (int, float)):
        return str(arg)
    if isinstance(arg, str):
        return "'" + arg.replace("'", "''") + "'"
    return None


def _add_missing_columns(conn) -> None:
    """Additive migrations for SQLite, run on every boot.

    create_all creates missing TABLES but never missing COLUMNS, so adding a
    field to an existing model silently produces "no such column" at runtime.
    Anything nullable or defaulted gets ALTERed in; a change this cannot
    express (a rename, a new NOT NULL, a type change) is logged loudly and is
    the point at which this deserves real migrations.
    """
    insp = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            default = _literal_default(col)
            if not col.nullable and default is None:
                log.error(
                    "cannot auto-add NOT NULL column %s.%s - needs a real migration",
                    table.name, col.name,
                )
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(conn.dialect)}"
            if default is not None:
                # Existing rows need the model's default, not NULL.
                ddl += f" DEFAULT {default}"
                if not col.nullable:
                    ddl += " NOT NULL"
            log.warning("migrating: %s", ddl)
            conn.exec_driver_sql(ddl)


async def init_db() -> None:
    """Create any missing tables.

    Imports the modules first: a model only reaches Base.metadata once its
    module has been imported, so discovery has to happen before create_all
    regardless of the order the caller uses.
    """
    import importlib

    from app.core.registry import discover

    importlib.import_module("app.core.users")  # puts the user table in the metadata
    discover()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)

    from app.core.migrate import run_migrations

    await run_migrations()


def now() -> datetime:
    """Naive UTC - what every timestamp in the database is.

    Users live in different timezones, so the database keeps one absolute
    scale and each user's own zone is applied only for display and for
    interpreting what they type.
    """
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


def zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo(settings.tz)


def to_local(when: datetime, tz: str) -> datetime:
    """Naive UTC -> naive wall clock in that zone."""
    return when.replace(tzinfo=timezone.utc).astimezone(zone(tz)).replace(tzinfo=None)


def to_utc(local: datetime, tz: str) -> datetime:
    """Naive wall clock in that zone -> naive UTC (DST-aware)."""
    return local.replace(tzinfo=zone(tz)).astimezone(timezone.utc).replace(tzinfo=None)


def local_now(tz: str) -> datetime:
    return datetime.now(tz=zone(tz)).replace(tzinfo=None)


def local_today(tz: str) -> date:
    return local_now(tz).date()
