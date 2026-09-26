from __future__ import annotations

from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    # The admin: gets failure alerts and the Users screen. Not the only user.
    owner_id: int
    # New people are accepted until this many are registered.
    max_users: int = 50
    # Fallback timezone offered to a new user before they pick their own.
    tz: str = "Europe/Dublin"
    db_path: str = "data/universe.db"
    log_level: str = "INFO"

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()  # type: ignore[call-arg]
