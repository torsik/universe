"""Registered people. One row per Telegram account that uses the bot."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func, select
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base, Session, now

log = logging.getLogger(__name__)


class User(Base):
    __tablename__ = "user"

    # The Telegram user id, so there is no second identity to reconcile.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    tz: Mapped[str] = mapped_column(String(64), default=settings.tz)
    first_name: Mapped[str] = mapped_column(String(120), default="")
    username: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Cleared when Telegram says the bot is blocked, so we stop pushing.
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    # 0 = not asked yet; the onboarding asks for a timezone once.
    onboarded: Mapped[int] = mapped_column(Integer, default=0)


async def get(user_id: int) -> User | None:
    async with Session() as s:
        return await s.get(User, user_id)


async def count() -> int:
    async with Session() as s:
        return int(await s.scalar(select(func.count()).select_from(User)) or 0)


async def all_users(only_active: bool = True) -> list[User]:
    async with Session() as s:
        q = select(User).order_by(User.created_at)
        if only_active:
            q = q.where(User.is_active.is_(True), User.blocked.is_(False))
        return list((await s.scalars(q)).all())


async def register(user_id: int, first_name: str = "", username: str = "") -> tuple[User | None, bool]:
    """Returns (user, created). None means the bot is full."""
    async with Session() as s:
        existing = await s.get(User, user_id)
        if existing:
            existing.last_seen_at = now()
            existing.first_name = first_name or existing.first_name
            existing.username = username or existing.username
            existing.blocked = False
            await s.commit()
            return existing, False
        total = int(await s.scalar(select(func.count()).select_from(User)) or 0)
        if total >= settings.max_users and user_id != settings.owner_id:
            log.warning("rejected %s: %d users already registered", user_id, total)
            return None, False
        user = User(id=user_id, first_name=first_name, username=username, tz=settings.tz)
        s.add(user)
        await s.commit()
        log.info("registered new user %s (%s)", user_id, username or first_name)
        return user, True


async def update(user_id: int, **fields) -> None:
    async with Session() as s:
        user = await s.get(User, user_id)
        if user is None:
            return
        for k, v in fields.items():
            setattr(user, k, v)
        await s.commit()


async def touch(user_id: int) -> None:
    await update(user_id, last_seen_at=now())


async def mark_blocked(user_id: int) -> None:
    log.info("user %s blocked the bot", user_id)
    await update(user_id, blocked=True)


async def delete(user_id: int) -> None:
    """Remove the person and everything they stored."""
    from app.modules.habits.models import Habit
    from app.modules.todo.models import Todo

    async with Session() as s:
        for model in (Todo, Habit):
            for row in (await s.scalars(select(model).where(model.user_id == user_id))).all():
                await s.delete(row)
        user = await s.get(User, user_id)
        if user:
            await s.delete(user)
        await s.commit()
