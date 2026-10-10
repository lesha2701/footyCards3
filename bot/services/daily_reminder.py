import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

import db
from config import get_bot_settings
from keyboards import open_app_keyboard
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
settings = get_bot_settings()

CHECK_INTERVAL_SECONDS = 600
# A routine daily ping, not a backlog: paced like the free pack notifier so
# the resulting wave of app opens is spread out.
TARGET_SENDS_PER_SECOND = 8.0


def digest_text(daily_ready: bool, tasks_ready: int) -> str | None:
    """None when nothing is waiting — such players get no message at all."""
    parts = []
    if daily_ready:
        parts.append("ежедневная награда")
    if tasks_ready:
        parts.append(f"выполненных заданий: {tasks_ready}")
    if not parts:
        return None
    return "🎁 Тебя ждут в VICTOR FC: " + " и ".join(parts) + ".\nЗабери всё одной кнопкой на главной."


async def _send(bot: Bot, user, text: str, rate_limiter: RateLimiter) -> None:
    await rate_limiter.acquire()
    try:
        await bot.send_message(user["telegram_id"], text, reply_markup=open_app_keyboard())
    except TelegramForbiddenError:
        await db.mark_bot_blocked(user["id"])
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
    except TelegramAPIError as exc:
        logger.warning("Failed to send digest to %s: %s", user["telegram_id"], exc)


async def run_daily_reward_reminder(bot: Bot) -> None:
    """Once a day after the admin-set hour (GameConfig.bot_daily_digest_*),
    tells players what is waiting for them. Off unless enabled in the admin
    panel; re-reads the setting every check so toggling needs no restart."""
    last_sent_date = None
    tz = ZoneInfo(settings.timezone)
    rate_limiter = RateLimiter(TARGET_SENDS_PER_SECOND)

    while True:
        try:
            now_local = datetime.now(tz)
            config = await db.fetch_daily_digest_settings()
            if (
                config is not None and config["bot_daily_digest_enabled"]
                and last_sent_date != now_local.date() and now_local.hour >= config["bot_daily_digest_hour"]
            ):
                last_sent_date = now_local.date()
                for user in await db.fetch_daily_digest_recipients(now_local.date()):
                    text = digest_text(user["daily_ready"], user["tasks_ready"])
                    if text:
                        await _send(bot, user, text, rate_limiter)
        except Exception:  # noqa: BLE001 - keep the reminder loop alive across transient DB/network errors
            logger.exception("Daily digest iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
