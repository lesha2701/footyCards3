import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError

from services import free_pack_notifier as notifier

USER = {"id": 1, "telegram_id": 100}


def _remind(error=None):
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=error)
    limiter = MagicMock(acquire=AsyncMock())
    with patch.object(notifier, "db") as db:
        db.mark_free_pack_notified = AsyncMock()
        db.mark_bot_blocked = AsyncMock()
        asyncio.run(notifier._remind_one(bot, USER, asyncio.Semaphore(1), limiter))
    return db


def test_delivered_leaves_the_queue():
    db = _remind()
    db.mark_free_pack_notified.assert_awaited_once_with(1)


def test_a_user_who_never_started_the_bot_leaves_the_queue():
    db = _remind(TelegramBadRequest(MagicMock(), "Bad Request: chat not found"))
    db.mark_free_pack_notified.assert_awaited_once_with(1)
    db.mark_bot_blocked.assert_not_awaited()


def test_a_blocked_bot_is_recorded():
    db = _remind(TelegramForbiddenError(MagicMock(), "Forbidden: bot was blocked by the user"))
    db.mark_bot_blocked.assert_awaited_once_with(1)
    db.mark_free_pack_notified.assert_not_awaited()


def test_a_passing_failure_stays_in_the_queue():
    db = _remind(TelegramNetworkError(MagicMock(), "timeout"))
    db.mark_free_pack_notified.assert_not_awaited()
