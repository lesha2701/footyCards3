import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import db

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


async def run_notification_dispatcher(bot: Bot) -> None:
    """Delivers rows from `notifications` (written by the backend for trade
    events, etc.) as real Telegram messages, then marks them sent."""
    while True:
        try:
            rows = await db.fetch_unsent_notifications()
            for row in rows:
                try:
                    await bot.send_message(row["telegram_id"], f"<b>{row['title']}</b>\n{row['body']}")
                except TelegramAPIError as exc:
                    logger.warning("Failed to deliver notification %s: %s", row["id"], exc)
                await db.mark_notification_sent(row["id"])
        except Exception:  # noqa: BLE001 - keep the dispatcher loop alive across transient DB/network errors
            logger.exception("Notification dispatcher iteration failed")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
