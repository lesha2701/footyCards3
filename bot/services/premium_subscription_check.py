import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

import db

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 6 * 3600
DELAY_BETWEEN_CHECKS_SECONDS = 0.05
_MEMBER_STATUSES = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


async def _is_member(bot: Bot, chat_id, telegram_id: int) -> bool | None:
    """None means "couldn't tell" (API error, bot not admin there, etc.) —
    the caller must skip the row rather than guess, since a clawback
    triggered by a transient failure would wrongly debit a real player."""
    try:
        member = await bot.get_chat_member(chat_id, telegram_id)
    except TelegramAPIError as exc:
        logger.warning("premium_subscription_check: get_chat_member(%s, %s) failed: %s", chat_id, telegram_id, exc)
        return None
    return member.status in _MEMBER_STATUSES


async def run_premium_subscription_check(bot: Bot) -> None:
    """Periodically re-verifies channel membership for every claimed premium
    task and adjusts the player's balance on transitions: clawed back (even
    into a negative balance) if they've since unsubscribed, credited back if
    they've resubscribed. See docs/superpowers/specs/2026-08-26-premium-task-
    coin-clawback-design.md for the full design."""
    while True:
        try:
            rows = await db.fetch_claimed_premium_channel_tasks()
            for row in rows:
                chat_id = row["channel_chat_id"] or row["channel_username"]
                is_member = await _is_member(bot, chat_id, row["telegram_id"])
                if is_member is None:
                    continue

                if is_member and row["coins_withdrawn"]:
                    await db.adjust_coins_allow_negative(
                        row["user_id"], row["reward_coins_granted"],
                        "Подписка на канал восстановлена — награда за задание возвращена",
                    )
                    await db.set_task_coins_withdrawn(row["user_task_id"], False)
                elif not is_member and not row["coins_withdrawn"]:
                    await db.adjust_coins_allow_negative(
                        row["user_id"], -row["reward_coins_granted"],
                        "Отписка от канала — награда за премиум-задание списана",
                    )
                    await db.set_task_coins_withdrawn(row["user_task_id"], True)

                await asyncio.sleep(DELAY_BETWEEN_CHECKS_SECONDS)
        except Exception:  # noqa: BLE001 - keep the sweep alive across transient DB/network errors
            logger.exception("Premium subscription check iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
