import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import db
from keyboards import open_app_keyboard

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5

# related_object_type -> Mini App path prefix, for notifications about a
# specific match (challenge accepted/received, your turn, match finished).
# Lets these carry a "Перейти в игру" button straight into that match
# instead of just the generic "open the app" button every other
# notification gets.
_MATCH_PATH_PREFIXES = {
    "penalty_match": "/play/penalty/matches",
    "tactico_match": "/play/tactico/matches",
}


def _keyboard_for(related_object_type: str | None, related_object_id: int | None):
    prefix = _MATCH_PATH_PREFIXES.get(related_object_type) if related_object_type else None
    if not prefix or related_object_id is None:
        return None
    return open_app_keyboard(f"{prefix}/{related_object_id}", text="🎮 Перейти в игру")


async def run_notification_dispatcher(bot: Bot) -> None:
    """Delivers rows from `notifications` (written by the backend for trade
    events, etc.) as real Telegram messages, then marks them sent."""
    while True:
        try:
            rows = await db.fetch_unsent_notifications()
            for row in rows:
                try:
                    keyboard = _keyboard_for(row["related_object_type"], row["related_object_id"])
                    await bot.send_message(
                        row["telegram_id"], f"<b>{row['title']}</b>\n{row['body']}", reply_markup=keyboard
                    )
                except TelegramAPIError as exc:
                    logger.warning("Failed to deliver notification %s: %s", row["id"], exc)
                await db.mark_notification_sent(row["id"])
        except Exception:  # noqa: BLE001 - keep the dispatcher loop alive across transient DB/network errors
            logger.exception("Notification dispatcher iteration failed")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
