import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import db
from keyboards import open_app_keyboard

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60


async def run_free_pack_notifier(bot: Bot) -> None:
    """Polls for users whose free pack just became available and haven't
    been notified yet, and pings them via a real Telegram message."""
    while True:
        try:
            users = await db.fetch_users_with_available_unnotified_free_pack()
            for user in users:
                try:
                    await bot.send_message(
                        user["telegram_id"],
                        "🎁 Твой бесплатный пак снова доступен!",
                        reply_markup=open_app_keyboard(),
                    )
                except TelegramAPIError as exc:
                    logger.warning("Failed to remind user %s: %s", user["telegram_id"], exc)
                else:
                    await db.mark_free_pack_notified(user["id"])
        except Exception:  # noqa: BLE001 - keep the loop alive across transient DB/network errors
            logger.exception("Free pack notifier iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
