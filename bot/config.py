from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = "0:DEV"
    telegram_bot_username: str = "footycards_bot"
    admin_telegram_ids: str = ""
    mini_app_url: str = "http://localhost:5173"
    bot_mode: str = "polling"
    bot_webhook_url: str = ""
    bot_webhook_secret: str = "dev_webhook_secret"
    bot_webhook_port: int = 8081

    database_url: str = "postgresql://postgres:1234@localhost:5432/footycards"
    timezone: str = "Europe/Moscow"

    @property
    def admin_ids(self) -> List[int]:
        return [int(x) for x in self.admin_telegram_ids.split(",") if x.strip()]

    @property
    def asyncpg_dsn(self) -> str:
        # asyncpg does not understand the SQLAlchemy "+asyncpg" dialect suffix.
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_bot_settings() -> BotSettings:
    return BotSettings()
