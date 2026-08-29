from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.announcement import AnnouncementOut, AnnouncementUpdate
from app.services.admin_log_service import log_action
from app.services.game_config_service import get_config

router = APIRouter(tags=["announcement"])


def _status_out(config) -> AnnouncementOut:
    return AnnouncementOut(text=config.announcement_text, updated_at=config.announcement_updated_at)


@router.get("/announcement", response_model=AnnouncementOut)
async def read_announcement(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    config = await get_config(db)
    return _status_out(config)


@router.post("/admin/announcement", response_model=AnnouncementOut, dependencies=[Depends(get_current_admin)])
async def set_announcement(
    payload: AnnouncementUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    config = await get_config(db)
    config.announcement_text = payload.text.strip() or None
    config.announcement_updated_at = datetime.now(timezone.utc)
    db.add(config)
    await log_action(
        db, admin.id, "set_announcement", "game_config", config.id,
        new_value={"text": config.announcement_text},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(config)
    return _status_out(config)
