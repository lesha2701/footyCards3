"""«Возвращайся»: one message to a player who hasn't opened the game for a
few days (GameConfig.bot_comeback_*), once per absence — users.comeback_sent_at
is set before sending, and a player only qualifies again after coming back
(last_seen_at moves past it). Players gone 30+ days are left alone."""
import asyncio
import html
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

import db
from config import get_bot_settings
from keyboards import open_app_keyboard
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
settings = get_bot_settings()

CHECK_INTERVAL_SECONDS = 900
# A routine ping, paced like the other reminders so the app-open wave spreads.
TARGET_SENDS_PER_SECOND = 8.0


def comeback_text(first_name: Optional[str], free_pack_ready: bool) -> str:
    name = html.escape(first_name.strip()) if first_name and first_name.strip() else ""
    hello = f"👋 {name}, давно не виделись!" if name else "👋 Давно не виделись!"
    waiting = "бесплатный пак и награда дня" if free_pack_ready else "награда дня и новые задания"
    return f"{hello}\nВ VICTOR FC тебя ждут {waiting}. Загляни — это минута ⚽"


async def _send(bot: Bot, user, rate_limiter: RateLimiter, retry: bool = True) -> None:
    await rate_limiter.acquire()
    try:
        await bot.send_message(
            user["telegram_id"], comeback_text(user["first_name"], user["free_pack_ready"]), reply_markup=open_app_keyboard(),
        )
    except TelegramForbiddenError:
        await db.mark_bot_blocked(user["id"])
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        if retry:
            await _send(bot, user, rate_limiter, retry=False)
    except TelegramAPIError as exc:
        logger.warning("Failed to send comeback to %s: %s", user["telegram_id"], exc)


async def run_comeback_loop(bot: Bot) -> None:
    tz = ZoneInfo(settings.timezone)
    rate_limiter = RateLimiter(TARGET_SENDS_PER_SECOND)
    while True:
        try:
            config = await db.fetch_comeback_settings()
            now_local = datetime.now(tz)
            # Evenings only (after the hour, before midnight) — no 3 a.m. pings.
            if config is not None and config["bot_comeback_enabled"] and now_local.hour >= config["bot_comeback_hour"]:
                for user in await db.fetch_comeback_recipients(max(1, config["bot_comeback_days"])):
                    # Marked first: a crash mid-send must not ping anyone twice.
                    await db.mark_comeback_sent(user["id"])
                    await _send(bot, user, rate_limiter)
        except Exception:  # noqa: BLE001 - keep the loop alive across transient DB/network errors
            logger.exception("Comeback iteration failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
