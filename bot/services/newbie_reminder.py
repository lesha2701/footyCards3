"""«Путь дебютанта»: one message on day 2 and one on day 3 when that day's
gift (GameConfig.newbie_day2_coins / newbie_day3_rarity) is open and the
player hasn't come in yet — from GameConfig.newbie_reminder_hour local time.
newbie_progress.reminded_day is set before sending, so nobody gets a gift
reminder twice."""
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
TARGET_SENDS_PER_SECOND = 8.0
RARITY_LABELS = {"common": "обычная", "rare": "редкая", "epic": "эпическая", "legendary": "легендарная", "diamond": "диамантовая"}


def gift_text(first_name: Optional[str], day: int, coins: int, rarity: str) -> str:
    name = html.escape(first_name.strip()) if first_name and first_name.strip() else ""
    who = f"{name}, " if name else ""
    if day == 2:
        amount = f"{coins:,}".replace(",", " ")
        return f"🎁 {who}твои {amount} монет ждут!\nПодарок второго дня «Пути дебютанта» уже открыт — заходи и забирай ⚽"
    card = RARITY_LABELS.get(rarity, "новая")
    return f"🌟 {who}тебя ждёт {card} карта!\nПодарок третьего дня «Пути дебютанта» открыт — забери и поставь её в состав ⚽"


async def _send(bot: Bot, user, text: str, rate_limiter: RateLimiter, retry: bool = True) -> None:
    await rate_limiter.acquire()
    try:
        await bot.send_message(user["telegram_id"], text, reply_markup=open_app_keyboard())
    except TelegramForbiddenError:
        await db.mark_bot_blocked(user["id"])
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        if retry:
            await _send(bot, user, text, rate_limiter, retry=False)
    except TelegramAPIError as exc:
        logger.warning("Failed to send newbie reminder to %s: %s", user["telegram_id"], exc)


async def run_newbie_reminder_loop(bot: Bot) -> None:
    tz = ZoneInfo(settings.timezone)
    rate_limiter = RateLimiter(TARGET_SENDS_PER_SECOND)
    while True:
        try:
            config = await db.fetch_newbie_reminder_settings()
            now_local = datetime.now(tz)
            if config is not None and config["newbie_enabled"] and now_local.hour >= config["newbie_reminder_hour"]:
                midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
                for user in await db.fetch_newbie_gift_recipients(now_local.date(), midnight):
                    # Marked first: a crash mid-send must not ping anyone twice.
                    await db.mark_newbie_reminded(user["id"], user["day"])
                    text = gift_text(user["first_name"], user["day"], config["newbie_day2_coins"], config["newbie_day3_rarity"])
                    await _send(bot, user, text, rate_limiter)
        except Exception:  # noqa: BLE001 - keep the loop alive across transient DB/network errors
            logger.exception("Newbie reminder iteration failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
