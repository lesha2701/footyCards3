import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

import db
from keyboards import open_app_keyboard
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60
# Same pacing as services.notifier — everyone whose free pack becomes
# available in the same poll window used to get pinged near-simultaneously,
# which (with enough users) caused a synchronized wave of app opens a few
# minutes later and a matching spike of nginx 502s. Sends are now paced the
# same way, spreading both the notifications and the resulting app opens.
TARGET_SENDS_PER_SECOND = 25.0
MAX_CONCURRENT_SENDS = 30


async def _remind_one(bot: Bot, user, semaphore: asyncio.Semaphore, rate_limiter: RateLimiter) -> None:
    async with semaphore:
        await rate_limiter.acquire()
        try:
            await bot.send_message(
                user["telegram_id"],
                "🎁 Твой бесплатный пак снова доступен!",
                reply_markup=open_app_keyboard(),
            )
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            await rate_limiter.acquire()
            try:
                await bot.send_message(
                    user["telegram_id"],
                    "🎁 Твой бесплатный пак снова доступен!",
                    reply_markup=open_app_keyboard(),
                )
            except TelegramAPIError as exc2:
                logger.warning("Failed to remind user %s after retry: %s", user["telegram_id"], exc2)
                return
        except TelegramAPIError as exc:
            logger.warning("Failed to remind user %s: %s", user["telegram_id"], exc)
            return
    await db.mark_free_pack_notified(user["id"])


async def run_free_pack_notifier(bot: Bot) -> None:
    """Polls for users whose free pack just became available and haven't
    been notified yet, and pings them via a real Telegram message."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SENDS)
    rate_limiter = RateLimiter(TARGET_SENDS_PER_SECOND)
    while True:
        try:
            users = await db.fetch_users_with_available_unnotified_free_pack()
            if users:
                await asyncio.gather(*(_remind_one(bot, user, semaphore, rate_limiter) for user in users))
        except Exception:  # noqa: BLE001 - keep the loop alive across transient DB/network errors
            logger.exception("Free pack notifier iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
