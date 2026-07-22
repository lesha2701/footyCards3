from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)
    )
    return result.scalars().all()


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(notification_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.core.exceptions import ForbiddenError, NotFoundError

    notification = await db.get(Notification, notification_id)
    if not notification:
        raise NotFoundError("Notification not found")
    if notification.user_id != user.id:
        raise ForbiddenError("This notification does not belong to you")
    notification.is_read = True
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification


@router.post("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await db.execute(
        update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False)).values(is_read=True)
    )
    await db.commit()
    return {"status": "ok"}
