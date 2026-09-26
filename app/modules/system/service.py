"""Database backups: a consistent copy of the SQLite file, sent to the chat."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import tempfile
from pathlib import Path

from app.config import settings
from app.db import now

KEEP = 7  # how many daily copies to keep on the server

log = logging.getLogger(__name__)


def _copy(src: str, dest: str) -> None:
    """SQLite's own backup API: consistent even while the bot is writing,
    and it folds in the WAL, unlike copying the file by hand."""
    source = sqlite3.connect(src)
    target = sqlite3.connect(dest)
    try:
        with target:
            source.backup(target)
    finally:
        source.close()
        target.close()


def backup_dir() -> Path:
    """Next to the database, so the same volume holds it."""
    path = Path(settings.db_path).parent / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def make_backup(server_side: bool = True) -> Path:
    """Write a consistent copy. On the server by default; a temp file when it
    is about to be handed to someone and deleted."""
    folder = backup_dir() if server_side else Path(tempfile.gettempdir())
    dest = folder / f"universe-{now():%Y-%m-%d-%H%M}.db"
    await asyncio.to_thread(_copy, settings.db_path, str(dest))
    if server_side:
        prune()
    return dest


def prune(keep: int = KEEP) -> list[Path]:
    """Keep the newest `keep` copies; delete the rest."""
    files = sorted(backup_dir().glob("universe-*.db"), reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            log.warning("could not remove old backup %s", old)
    return files[:keep]


def existing() -> list[Path]:
    return sorted(backup_dir().glob("universe-*.db"), reverse=True)


def db_size_kb() -> int:
    try:
        return round(Path(settings.db_path).stat().st_size / 1024)
    except OSError:
        return 0
