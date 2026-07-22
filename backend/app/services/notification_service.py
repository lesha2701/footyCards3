from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType
from app.models.notification import Notification


async def notify(
    db: AsyncSession,
    user_id: int,
    type_: NotificationType,
    title: str,
    body: str,
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
) -> Notification:
    """Persists a notification row. The bot process polls unsent rows and
    delivers them via the Telegram Bot API, decoupling backend from bot."""
    notification = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )
    db.add(notification)
    return notification
