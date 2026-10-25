"""Сторож: tells the admins when the backend is down (and back up), and once
a day what broke — the 500s the backend recorded in `server_errors`
(backend/app/services/error_log_service.py). Without it a fall is noticed
only when players complain."""
import asyncio
import html
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot

import db
from config import get_bot_settings
from services.stars_delivery import alert_admins

logger = logging.getLogger(__name__)
settings = get_bot_settings()

CHECK_EVERY_SECONDS = 60
FAILS_BEFORE_ALERT = 3  # ~3 minutes: a deploy's restart doesn't count
DIGEST_HOUR = 10  # local time
KEEP_ERRORS_DAYS = 14
_TIMEOUT = aiohttp.ClientTimeout(total=10)


def health_url() -> str:
    base = settings.internal_backend_url.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[: -len("/api/v1")]
    return f"{base}/api/health/deep"


async def backend_ok() -> bool:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(health_url()) as resp:
                return resp.status == 200
    except Exception:  # noqa: BLE001 - any failure to answer is "down"
        return False


class Watch:
    """Up/down bookkeeping, separate from the loop so it can be tested."""

    def __init__(self) -> None:
        self.fails = 0
        self.down_since: Optional[datetime] = None
        self.alerted = False

    def step(self, ok: bool, now: datetime) -> Optional[str]:
        """The admin message this check calls for, if any."""
        if ok:
            message = None
            if self.alerted and self.down_since:
                minutes = max(1, round((now - self.down_since).total_seconds() / 60))
                message = f"✅ <b>Бэкенд снова работает</b>\nПростой: ~{minutes} мин."
            self.fails, self.down_since, self.alerted = 0, None, False
            return message
        self.fails += 1
        if self.down_since is None:
            self.down_since = now
        if self.fails >= FAILS_BEFORE_ALERT and not self.alerted:
            self.alerted = True
            return (
                f"⚠️ <b>Бэкенд не отвечает</b> с {self.down_since:%H:%M}\n"
                "Игроки не могут открыть игру. На сервере:\n"
                "<code>cd ~/footyCards3 &amp;&amp; docker compose -f docker-compose.prod.yml ps</code>\n"
                "<code>docker compose -f docker-compose.prod.yml logs --tail=80 backend</code>"
            )
        return None


def digest_text(rows: list, total: int) -> Optional[str]:
    """rows: (method, path, count, last_error) by count, the top few."""
    if not total:
        return None
    lines = [f"🧯 <b>Ошибки сервера за сутки: {total}</b>"]
    for row in rows:
        lines.append(
            f"• {row['count']}× <code>{html.escape(row['method'])} {html.escape(row['path'])}</code>\n"
            f"  {html.escape(row['last_error'][:150])}"
        )
    lines.append("\nПодробности (traceback) — в таблице server_errors.")
    return "\n".join(lines)


async def _errors_last_day() -> tuple[list, int]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT count(*) FROM server_errors WHERE created_at > now() - interval '1 day'")
        rows = await conn.fetch(
            """
            SELECT method, path, count(*) AS count,
                   (array_agg(error ORDER BY created_at DESC))[1] AS last_error
            FROM server_errors
            WHERE created_at > now() - interval '1 day'
            GROUP BY method, path
            ORDER BY count(*) DESC
            LIMIT 5
            """
        )
        await conn.execute(f"DELETE FROM server_errors WHERE created_at < now() - interval '{KEEP_ERRORS_DAYS} days'")
    return list(rows), total or 0


async def run_watchdog_loop(bot: Bot) -> None:
    tz = ZoneInfo(settings.timezone)
    watch = Watch()
    digest_sent_on = None
    while True:
        try:
            now = datetime.now(tz)
            message = watch.step(await backend_ok(), now)
            if message:
                await alert_admins(bot, message)
            if now.hour == DIGEST_HOUR and digest_sent_on != now.date():
                digest_sent_on = now.date()
                rows, total = await _errors_last_day()
                text = digest_text(rows, total)
                if text:
                    await alert_admins(bot, text)
        except Exception:  # noqa: BLE001 - the watchdog itself must keep running
            logger.exception("Watchdog iteration failed")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
