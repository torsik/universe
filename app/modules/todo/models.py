from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now


class Todo(Base):
    __tablename__ = "todo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Whose it is. 0 only appears mid-migration on a pre-multiuser database.
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, default=0)
    text: Mapped[str] = mapped_column(String(500))
    done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # Set when the reminder actually went out, so a restart cannot lose one
    # (scheduled jobs live in memory) nor send it twice.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # Minutes before the deadline for the heads-up; 0 = only at the deadline.
    remind_before: Mapped[int] = mapped_column(Integer, default=0)
    # "" | daily | weekly | monthly | yearly - completing it creates the next one.
    repeat: Mapped[str] = mapped_column(String(10), default="")
    lead_notified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
