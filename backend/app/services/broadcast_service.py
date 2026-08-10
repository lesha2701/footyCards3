from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.user import User
from app.services.game_config_service import get_config

BROADCAST_TITLE = "Обновление"


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
