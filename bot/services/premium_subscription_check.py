import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

import db

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 10 * 60
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
    task. A player who's unsubscribed since claiming gets their coins clawed
    back (even into a negative balance) AND the task reset to its pre-claim
    state — reward_claimed=False, reward_coins_granted=NULL — so it shows up
    as claimable again and the player has to resubscribe and press "get
    reward" themselves to earn it back, same as claiming it the first time
    (claim_task_reward already re-verifies live membership on every claim).
    Resetting reward_claimed also drops the row out of
    fetch_claimed_premium_channel_tasks's WHERE clause, so a resubscribed-
    but-not-yet-reclaimed player is simply not checked again — there is no
    separate "restore" branch to run. See docs/superpowers/specs/2026-08-26-
    premium-task-coin-clawback-design.md for the original clawback design."""
    while True:
        try:
            rows = await db.fetch_claimed_premium_channel_tasks()
            for row in rows:
                chat_id = row["channel_chat_id"] or row["channel_username"]
                is_member = await _is_member(bot, chat_id, row["telegram_id"])
                if is_member is None or is_member:
                    await asyncio.sleep(DELAY_BETWEEN_CHECKS_SECONDS)
                    continue

                await db.adjust_coins_allow_negative(
                    row["user_id"], -row["reward_coins_granted"],
                    "Отписка от канала — награда за премиум-задание списана",
                )
                await db.reset_task_for_reclaim(row["user_task_id"])
                await db.create_notification(
                    row["user_id"], "premium_task_coins_withdrawn", "Награда списана",
                    f"Ты отписался от канала — {row['reward_coins_granted']} 🪙 за премиум-задание списаны с баланса. "
                    "Подпишись снова и нажми «Получить награду» в задании ещё раз, чтобы вернуть их.",
                )

                await asyncio.sleep(DELAY_BETWEEN_CHECKS_SECONDS)
        except Exception:  # noqa: BLE001 - keep the sweep alive across transient DB/network errors
            logger.exception("Premium subscription check iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
