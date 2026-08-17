from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.user import User
from app.services.game_config_service import get_config

BROADCAST_TITLE = "Обновление"


def _premium_task_body(task_count: int, message: Optional[str]) -> str:
    """Builds the Russian-pluralized announcement text. Standard Russian
    numeral-agreement rules: 1 (not 11) takes the singular noun/adjective,
    2-4 (not 12-14) take the paucal (genitive singular noun), everything
    else takes the genitive plural."""
    last_two = task_count % 100
    last_one = task_count % 10
    if last_one == 1 and last_two != 11:
        headline = f"Появилось {task_count} новое премиум задание! Успей получить награду"
    elif last_one in (2, 3, 4) and last_two not in (12, 13, 14):
        headline = f"Появилось {task_count} новых премиум задания! Успей получить награду"
    else:
        headline = f"Появилось {task_count} новых премиум заданий! Успей получить награду"

    if message and message.strip():
        return f"{headline}\n\n{message.strip()}"
    return headline


def _premium_task_title(task_count: int) -> str:
    last_two = task_count % 100
    last_one = task_count % 10
    if last_one == 1 and last_two != 11:
        return "⭐ Новое премиум-задание!"
    return "⭐ Новые премиум-задания!"


async def send_update_broadcast(db: AsyncSession, message: str) -> tuple[int, datetime]:
    """Notifies every non-banned user of an app update: persists one
    Notification row per recipient (the bot process polls unsent rows and
    delivers them as real Telegram messages, see bot/services/notifier.py),
    and stamps GameConfig.last_update_broadcast_at so the Mini App can show
    a dismissible "update available" banner."""
    user_ids = (await db.execute(select(User.id).where(User.is_banned.is_(False)))).scalars().all()

    now = datetime.now(timezone.utc)
    if user_ids:
        await db.execute(
            insert(Notification),
            [
                {
                    "user_id": uid, "type": NotificationType.admin_message,
                    "title": BROADCAST_TITLE, "body": message,
                    "is_read": False, "telegram_sent": False, "created_at": now,
                }
                for uid in user_ids
            ],
        )

    config = await get_config(db)
    config.last_update_broadcast_at = now
    db.add(config)

    return len(user_ids), now


async def send_premium_task_broadcast(db: AsyncSession, task_count: int, message: Optional[str]) -> int:
    """Notifies every non-banned user that new premium tasks are available,
    as a single admin-triggered broadcast (one Notification row per
    recipient, bulk-inserted) instead of one notification per task created
    — avoids spamming players when several premium tasks are added at once."""
    user_ids = (await db.execute(select(User.id).where(User.is_banned.is_(False)))).scalars().all()

    now = datetime.now(timezone.utc)
    if user_ids:
        title = _premium_task_title(task_count)
        body = _premium_task_body(task_count, message)
        await db.execute(
            insert(Notification),
            [
                {
                    "user_id": uid, "type": NotificationType.premium_task_available,
                    "title": title, "body": body,
                    "is_read": False, "telegram_sent": False, "created_at": now,
                }
                for uid in user_ids
            ],
        )

    return len(user_ids)
