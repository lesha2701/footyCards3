import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

import db
from keyboards import open_app_keyboard

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 200
# Telegram's bot-wide soft limit is ~30 messages/sec; this stays comfortably
# under that while still delivering a bulk broadcast (thousands of rows) in
# a couple of minutes instead of the tens of minutes a purely sequential,
# 50-per-5s dispatcher takes.
MAX_CONCURRENT_SENDS = 20

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


async def _deliver_one(bot: Bot, row, semaphore: asyncio.Semaphore) -> None:
    keyboard = _keyboard_for(row["related_object_type"], row["related_object_id"])
    text = f"<b>{row['title']}</b>\n{row['body']}"
    async with semaphore:
        try:
            await bot.send_message(row["telegram_id"], text, reply_markup=keyboard)
        except TelegramRetryAfter as exc:
            # Telegram's own flood-control backoff — wait it out and retry once,
            # rather than just dropping the message.
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.send_message(row["telegram_id"], text, reply_markup=keyboard)
            except TelegramAPIError as exc2:
                logger.warning("Failed to deliver notification %s after retry: %s", row["id"], exc2)
        except TelegramAPIError as exc:
            logger.warning("Failed to deliver notification %s: %s", row["id"], exc)
    await db.mark_notification_sent(row["id"])


async def run_notification_dispatcher(bot: Bot) -> None:
    """Delivers rows from `notifications` (written by the backend for trade
    events, etc.) as real Telegram messages, then marks them sent.

    Sends within a batch concurrently (bounded by MAX_CONCURRENT_SENDS) and
    only sleeps between polls once a batch comes back short of BATCH_SIZE —
    a full batch means there's likely more backlog (e.g. a bulk admin
    broadcast to thousands of users), so the next fetch runs immediately
    instead of waiting out a flat 5s poll interval for no reason. A purely
    sequential, one-at-a-time dispatcher took tens of minutes to drain a
    ~9000-row broadcast; this drains the same backlog in a couple of
    minutes while still respecting Telegram's rate limits.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SENDS)
    while True:
        try:
            rows = await db.fetch_unsent_notifications(limit=BATCH_SIZE)
            if rows:
                await asyncio.gather(*(_deliver_one(bot, row, semaphore) for row in rows))
            if len(rows) < BATCH_SIZE:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001 - keep the dispatcher loop alive across transient DB/network errors
            logger.exception("Notification dispatcher iteration failed")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
