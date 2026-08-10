from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.broadcast import AdminBroadcastCreate, AdminBroadcastOut, UpdateBroadcastStatusOut
from app.services.admin_log_service import log_action
from app.services.broadcast_service import send_update_broadcast
from app.services.game_config_service import get_config

router = APIRouter(tags=["broadcasts"])


@router.get("/updates/status", response_model=UpdateBroadcastStatusOut)
async def read_update_status(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    config = await get_config(db)
    return UpdateBroadcastStatusOut(broadcast_at=config.last_update_broadcast_at)


@router.post("/admin/broadcasts", response_model=AdminBroadcastOut, dependencies=[Depends(get_current_admin)])
async def create_update_broadcast(
    payload: AdminBroadcastCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    recipients, broadcast_at = await send_update_broadcast(db, payload.message)
    await log_action(
        db, admin.id, "send_update_broadcast", "game_config", 1,
        new_value={"message": payload.message, "recipients": recipients},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return AdminBroadcastOut(recipients=recipients, broadcast_at=broadcast_at)
