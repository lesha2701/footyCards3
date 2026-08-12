import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

import db
from keyboards import open_app_keyboard

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 200
# Telegram's bot-wide soft limit is ~30 messages/sec. A concurrency cap
# alone does NOT bound throughput to this — if requests come back fast,
# N concurrent slots can produce far more than N sends/sec (confirmed
# locally: 300 fast-failing sends drained in ~1s, i.e. ~300/sec). The
# RateLimiter below is what actually keeps real send *attempts* under the
# limit; MAX_CONCURRENT_SENDS just bounds how many requests can be
# in-flight at once so a burst of slow responses doesn't pile up tasks.
TARGET_SENDS_PER_SECOND = 25.0
MAX_CONCURRENT_SENDS = 30


class RateLimiter:
    """Token bucket: at most `rate` acquisitions per second, sustained."""

    def __init__(self, rate: float) -> None:
        self._rate = rate
        self._tokens = rate
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self._rate, self._tokens + (now - self._updated) * self._rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self._rate)


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


async def _deliver_one(bot: Bot, row, semaphore: asyncio.Semaphore, rate_limiter: "RateLimiter") -> None:
    keyboard = _keyboard_for(row["related_object_type"], row["related_object_id"])
    text = f"<b>{row['title']}</b>\n{row['body']}"
    async with semaphore:
        await rate_limiter.acquire()
        try:
            await bot.send_message(row["telegram_id"], text, reply_markup=keyboard)
        except TelegramRetryAfter as exc:
            # Telegram's own flood-control backoff — wait it out and retry once,
            # rather than just dropping the message.
            await asyncio.sleep(exc.retry_after)
            await rate_limiter.acquire()
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

    Send *attempts* are paced by a token-bucket RateLimiter to at most
    TARGET_SENDS_PER_SECOND, which is what actually keeps this under
    Telegram's ~30 msg/sec bot-wide limit — MAX_CONCURRENT_SENDS alone
    would not (a concurrency cap bounds how many requests are in-flight,
    not how many start per second). Only sleeps between polls once a
    batch comes back short of BATCH_SIZE — a full batch means there's
    likely more backlog (e.g. a bulk admin broadcast to thousands of
    users), so the next fetch runs immediately. A purely sequential,
    one-at-a-time dispatcher took tens of minutes to drain a ~9000-row
    broadcast; this drains the same backlog in a few minutes while
    actually respecting Telegram's rate limit throughout.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SENDS)
    rate_limiter = RateLimiter(TARGET_SENDS_PER_SECOND)
    while True:
        try:
            rows = await db.fetch_unsent_notifications(limit=BATCH_SIZE)
            if rows:
                await asyncio.gather(*(_deliver_one(bot, row, semaphore, rate_limiter) for row in rows))
            if len(rows) < BATCH_SIZE:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001 - keep the dispatcher loop alive across transient DB/network errors
            logger.exception("Notification dispatcher iteration failed")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
