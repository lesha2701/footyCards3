from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    telegram_bot_token: str = "0:DEV"
    telegram_bot_username: str = "footycards_bot"
    # Forward proxy for reaching api.telegram.org, e.g. "socks5://user:pass@host:1080"
    # or "http://host:8080". Leave empty to connect directly.
    telegram_proxy_url: str = ""
    admin_telegram_ids: str = ""
    mini_app_url: str = "http://localhost:5173"
    bot_mode: str = "polling"
    bot_webhook_url: str = ""
    bot_webhook_secret: str = "dev_webhook_secret"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:1234@localhost:5432/footycards"
    # SQLAlchemy's own defaults (pool_size=5, max_overflow=10) proved too
    # small in production: prod runs multiple uvicorn workers, each with its
    # own independent pool, so the old defaults capped the whole backend at
    # workers*(5+10) concurrent DB connections. A burst of concurrent users
    # (e.g. right after a push notification to thousands of users) blew
    # through that and every further request queued for a connection until
    # it hit pool_timeout and 500'd with "QueuePool limit ... reached".
    # Sized for a 4-worker prod deployment on a 4+ CPU / 8+ GB RAM server:
    # 4*(25+50)=300 from the backend, plus the bot's own asyncpg pool
    # (max_size=10, see bot/db.py) and headroom for direct/admin
    # connections, all under Postgres's max_connections (see
    # docker-compose.prod.yml's POSTGRES_MAX_CONNECTIONS, default 400 —
    # bump both together, never raise this past what that's set to).
    db_pool_size: int = 25
    db_max_overflow: int = 50
    db_pool_timeout: int = 30
    # Recycle connections periodically so a connection that's sat idle
    # longer than typical firewall/proxy/Postgres idle-timeout windows
    # doesn't get handed back out already-dropped by the network.
    db_pool_recycle: int = 1800

    # Backend
    jwt_secret: str = "dev_only_secret"
    jwt_expire_minutes: int = 720
    # Shared secret authenticating server-to-server calls from the bot (e.g.
    # relaying a Telegram Stars successful_payment) — not a user credential,
    # never sent from the frontend. Must match INTERNAL_API_SECRET in the
    # bot's own settings.
    internal_api_secret: str = "dev_only_internal_secret"
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
