from __future__ import annotations

from datetime import datetime
from pathlib import Path

import logging

from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Every module's models inherit from this so create_all sees them."""


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
            if not col.nullable and col.default is None and col.server_default is None:
                log.error(
                    "cannot auto-add NOT NULL column %s.%s - needs a real migration",
                    table.name, col.name,
                )
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(conn.dialect)}"
            log.warning("migrating: %s", ddl)
            conn.exec_driver_sql(ddl)


async def init_db() -> None:
    """Create any missing tables.

    Imports the modules first: a model only reaches Base.metadata once its
    module has been imported, so discovery has to happen before create_all
    regardless of the order the caller uses.
    """
    from app.core.registry import discover

    discover()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def now() -> datetime:
    """Naive local time in the configured TZ.

    Everything the user sees is local, and SQLite has no tz-aware type, so we
    store naive local consistently rather than mixing UTC and local.
    """
    return datetime.now(tz=settings.tzinfo).replace(tzinfo=None)
