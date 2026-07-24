from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    telegram_bot_token: str = "0:DEV"
    telegram_bot_username: str = "footycards_bot"
    admin_telegram_ids: str = ""
    mini_app_url: str = "http://localhost:5173"
    bot_mode: str = "polling"
    bot_webhook_url: str = ""
    bot_webhook_secret: str = "dev_webhook_secret"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:1234@localhost:5432/footycards"

    # Backend
    jwt_secret: str = "dev_only_secret"
    jwt_expire_minutes: int = 720
    dev_mode: bool = False
    dev_user_telegram_id: int = 999000001
    environment: str = "development"
    cors_origins: str = "http://localhost:5173"
    timezone: str = "Europe/Moscow"
    starting_balance: int = 500
    backend_port: int = 8000

    # Static
    static_root: str = "static/players"
    max_upload_size_mb: int = 5

    @property
    def admin_ids(self) -> List[int]:
        return [int(x) for x in self.admin_telegram_ids.split(",") if x.strip()]

    @property
    def cors_origin_list(self) -> List[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
