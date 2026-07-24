import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import db
from config import get_bot_settings

logger = logging.getLogger(__name__)
settings = get_bot_settings()

CHECK_INTERVAL_SECONDS = 3600  # once an hour is enough; the reminder itself is once-per-day per user


async def run_daily_reward_reminder(bot: Bot) -> None:
    """Once a day, nudges users who have not yet claimed today's daily reward."""
    last_sent_date = None
    tz = ZoneInfo(settings.timezone)

    while True:
        try:
            now_local = datetime.now(tz)
            # Send once per day, shortly after local midnight has passed.
            if last_sent_date != now_local.date() and now_local.hour >= 9:
                users = await db.fetch_users_missing_daily_reward(now_local.date())
                for user in users:
                    try:
                        await bot.send_message(
                            user["telegram_id"],
                            "🎁 Твоя ежедневная награда уже ждёт тебя в приложении FootyCards!",
                        )
                    except TelegramAPIError as exc:
                        logger.warning("Failed to remind user %s: %s", user["telegram_id"], exc)
                last_sent_date = now_local.date()
        except Exception:  # noqa: BLE001 - keep the reminder loop alive across transient DB/network errors
            logger.exception("Daily reward reminder iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
