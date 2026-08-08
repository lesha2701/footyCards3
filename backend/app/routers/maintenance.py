from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_user
from app.core.timeutil import ensure_aware
from app.database import get_db
from app.models.user import User
from app.schemas.maintenance import MaintenanceStatusOut
from app.services.admin_log_service import log_action
from app.services.game_config_service import get_config

router = APIRouter(tags=["maintenance"])

BANNER_DURATION = timedelta(minutes=5)


def _status_out(until) -> MaintenanceStatusOut:
    if until is None:
        return MaintenanceStatusOut(active=False)
    until_aware = ensure_aware(until)
    active = until_aware > datetime.now(timezone.utc)
    return MaintenanceStatusOut(active=active, until=until_aware if active else None)


@router.get("/maintenance", response_model=MaintenanceStatusOut)
async def read_maintenance_status(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    config = await get_config(db)
    return _status_out(config.maintenance_banner_until)


@router.post("/admin/maintenance/start", response_model=MaintenanceStatusOut, dependencies=[Depends(get_current_admin)])
async def start_maintenance_banner(request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    config = await get_config(db)
    config.maintenance_banner_until = datetime.now(timezone.utc) + BANNER_DURATION
    db.add(config)
    await log_action(
        db, admin.id, "start_maintenance_banner", "game_config", config.id,
        new_value={"maintenance_banner_until": config.maintenance_banner_until.isoformat()},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(config)
    return _status_out(config.maintenance_banner_until)


@router.post("/admin/maintenance/clear", response_model=MaintenanceStatusOut, dependencies=[Depends(get_current_admin)])
async def clear_maintenance_banner(request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    config = await get_config(db)
    config.maintenance_banner_until = None
    db.add(config)
    await log_action(
        db, admin.id, "clear_maintenance_banner", "game_config", config.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return _status_out(None)
